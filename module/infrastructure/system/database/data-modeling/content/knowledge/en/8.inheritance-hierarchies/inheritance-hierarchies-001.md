# Generalization, Specialization, and Subtype Partitioning Criteria

## Lesson Objectives

After this lesson, you will be able to explain **generalization** and **specialization** in data modeling; determine when multiple entities should share a supertype and when subtypes are needed; write membership criteria for each subtype; distinguish the two independent constraint axes of disjoint/overlapping and total/partial; and evaluate ways to represent hierarchies in the relational model.

You will also know how to avoid creating subtypes merely due to differing UI screens or a few different attributes, how to handle an object that can change type over time, and how to validate a hierarchy against data and business rules.

## 1. Why Model Hierarchies?

In a business domain, multiple types of objects may share common attributes and behaviors while still having distinct characteristics.

For example, in an HR system:

- Full-time employees have an employee ID, full name, hire date, and department.
- Contractors also have a profile ID, full name, contract start date, and supervising unit.
- Both are people working for the organization, yet their employment relationship type, benefit policies, and contract termination rules differ.

If these two types are stored completely separately, shared information may be duplicated and finding everyone currently working becomes difficult. If everything is merged into a single entity without distinguishing types, type-specific rules may get mixed up and many fields become NULL or carry unclear meanings.

Hierarchy modeling helps represent shared and type-specific parts intentionally:

- **Supertype:** describes the generalized concept and shared attributes/relationships.
- **Subtype:** describes a specific group of objects belonging to the supertype, with additional attributes, relationships, or rules of its own.

For example:

~~~text
                 WORKER
          (worker_id, full_name)
                    |
          ---------------------
          |                   |
     EMPLOYEE             CONTRACTOR
     (salary_grade)       (contract_end)
~~~

An Employee is also a Worker; a Contractor is also a Worker. Both inherit identity and shared attributes from Worker in the conceptual model.

The key point is that a hierarchy must reflect business semantics. The fact that one class in code inherits from another is not sufficient to conclude that two data concepts have a supertype/subtype relationship.

## 2. Generalization and Specialization

These two approaches both produce a hierarchy, but start from opposite analytical directions.

### 2.1. Generalization

**Generalization** is the process of moving from multiple specific types up to a generalized type by identifying their commonalities.

For example, a system has two concepts:

- Individual Customer: customer_id, name, email, contact address.
- Business Customer: customer_id, legal name, contact email, registered address.

If both share a customer identity, contact information, and common management rules, they can be generalized into Customer, and then specialized into IndividualCustomer and BusinessCustomer.

This process is typically bottom-up:

1. Identify concrete entity types.
2. Compare attributes, relationships, and rules.
3. Determine the shared parts that genuinely have the same meaning.
4. Create a supertype containing the shared parts.
5. Keep specific attributes and rules in the subtypes.

You should not generalize merely because two tables have columns with the same name. Two fields named `email` may have different semantics, authoritative sources, or verification rules.

### 2.2. Specialization

**Specialization** is the process of starting from a generalized type and dividing it into subtypes according to meaningful business criteria.

For example, Payment is a general concept with payment_id, amount, currency, and created_at. It can be specialized into:

- CardPayment: has card_token and authorization_code.
- BankTransferPayment: has bank_reference and bank_account.
- CashPayment: has collected_at and collector_id.

This process is typically top-down:

1. Identify the supertype and scope of objects.
2. Find groups with differing rules or data.
3. Write the condition determining whether an object belongs to a subtype.
4. Determine whether the subtypes are mutually exclusive or can overlap.
5. Determine whether every supertype object must belong to at least one subtype.
6. Check edge cases that belong to no subtype or multiple subtypes.

### 2.3. Comparing the Two Approaches

| Criterion | Generalization | Specialization |
|---|---|---|
| Analytical direction | From multiple specific types up to a common type | From a common type down to specific types |
| Key question | What commonalities with the same meaning do they share? | Which groups require distinct rules? |
| Result | Supertype and shared parts | Subtypes and membership criteria |
| Risk | Grouping concepts that only look similar in name or structure | Splitting into too many subtypes or unclear criteria |

In practice, both approaches are used iteratively. While analyzing subtypes, a team may discover a new commonality requiring generalization; while generalizing, a team may uncover distinct object categories requiring specialization.

## 3. What Do Supertype and Subtype Mean?

### 3.1. Supertype

A supertype represents the general concept. It contains:

- shared identity;
- attributes meaningful to every member;
- relationships applicable to every member;
- shared invariants;
- shared behaviors or events, if any.

For example, Payment may contain:

- payment_id;
- order_id;
- amount;
- currency;
- status;
- created_at.

These attributes are meaningful for every payment method within the scope of the model.

### 3.2. Subtype

A subtype represents a subset of a supertype. An object belonging to a subtype is simultaneously an object belonging to the supertype.

For example, CardPayment is a Payment. It can add:

- payment_token;
- authorization_code;
- card_network.

These specific attributes are only meaningful for card payments.

A subtype typically:

- inherits the supertype's identity;
- inherits shared attributes and relationships;
- adds specific attributes or relationships;
- is subject to both shared invariants and type-specific invariants.

### 3.3. The is-a Relationship

The relationship between a subtype and a supertype is an **is-a** relationship:

- CardPayment is a Payment.
- BusinessCustomer is a Customer.
- FullTimeEmployee is a Worker.

If you cannot state the "is-a" sentence naturally and accurately in business terms, you may be mistakenly modeling a has-a, role, or category relationship as inheritance.

For example:

- Car has an Engine: this is a composition relationship, not Car is an Engine.
- Employee has a Department: this is a reference relationship, not Employee is a Department.
- Customer has a PreferredLanguage: this is usually an attribute, not a subtype.

### 3.4. Subtypes Inherit Identity Rather Than Creating Another Independent Object

A CardPayment is not a separate Payment plus another CardPayment. It is the same entity viewed at a general level and at a specialized level.

In the relational model, implementation may span multiple tables, but rows in a subtype table must be tied to the same identity as the supertype row. You should not generate two independent IDs if the business treats them as a single object.

## 4. Subtype Partitioning Criteria Must Be Clear

A subtype needs explainable and verifiable membership criteria. Those criteria determine which objects belong to the group and when membership changes.

### 4.1. Criteria Based on Business Type

For example, Customer is divided into IndividualCustomer and BusinessCustomer based on the legal status of the buyer.

- IndividualCustomer is a natural-person customer.
- BusinessCustomer is an organizational/business customer.

This criterion is meaningful because the two groups may have different legal details, verification processes, and invoicing obligations.

### 4.2. Criteria Based on Rules or Policies

For example, Worker is divided into Employee and Contractor based on the employment relationship type confirmed by the organization.

Conditions might include:

- Employee has an employment relationship under an employee contract.
- Contractor provides services under a contractor agreement.

An unstable attribute such as company email or department name should not be used as the criterion if it does not accurately determine the relationship type.

### 4.3. Criteria Based on Capabilities or Distinct Structure

For example, payment methods can be divided by processing mechanism:

- CardPayment requires a token and authorization.
- BankTransferPayment requires a bank reference code.
- CashPayment requires a collector and collection timestamp.

Differences must be meaningful in terms of data, processes, or invariants. If types only differ in display labels with no distinct attributes or rules, a type attribute may suffice.

### 4.4. Writing a Predicate for a Subtype

Subtype criteria should be written as a clear logical condition or business statement:

~~~text
CardPayment(p) :=
    p.method = 'CARD'
    AND p.authorization_required = true
~~~

Or:

> A Worker belongs to Employee when the profile has an approved and currently active employee work relationship.

A predicate helps answer:

- What data proves subtype membership?
- Can it be checked automatically?
- Who has authority to confirm it?
- Can the condition change over time?
- Can one object satisfy multiple predicates simultaneously?

A predicate does not have to be an SQL expression. It is a business definition first, after which storage and enforcement mechanisms are chosen.

### 4.5. Do Not Split Subtypes Based Solely on Screens or Access Permissions

The following reasons are generally insufficient to create a subtype:

- screen A displays fewer fields than screen B;
- user groups have different view permissions;
- a report requires a specific set of columns;
- a workflow only processes certain records;
- an API has two serialization formats.

Those differences can be addressed with views, projections, policies, roles, or API DTOs. Only create a subtype when there are differences in concepts, attributes, relationships, or business invariants.

## 5. Two Constraint Axes of a Hierarchy

When dividing a supertype into multiple subtypes, two independent questions must be answered:

1. Can an object belong to multiple subtypes at the same time?
2. Must every object belonging to the supertype belong to at least one subtype?

The first question determines **disjointness**. The second question determines **completeness**.

### 5.1. Disjoint Subtypes

A **disjoint** hierarchy means a supertype object can belong to at most one subtype in the considered group.

For example, if policy states that each Payment uses only one primary processing method, CardPayment and BankTransferPayment can be disjoint.

~~~text
                PAYMENT
                   |
                {disjoint}
                /       \
       CARD_PAYMENT   BANK_TRANSFER
~~~

A Payment cannot be both a CardPayment and a BankTransferPayment under this model.

### 5.2. Overlapping Subtypes

An **overlapping** hierarchy allows an object to belong to multiple subtypes at the same time.

For example, a party can be both a Customer and a Supplier on the same platform. If the supertype is Party, the Customer and Supplier subtypes can be overlapping.

~~~text
                  PARTY
                    |
                {overlap}
                /       \
           CUSTOMER   SUPPLIER
~~~

You should not force these two roles into a single exclusive type if an organization can simultaneously buy and supply goods.

### 5.3. Total Specialization

A **total** hierarchy means every object of the supertype must belong to at least one subtype in the defined set of subtypes.

For example, if the system only records a Payment after a method has been selected and every valid method falls under CardPayment, BankTransferPayment, or CashPayment, the hierarchy can be total.

### 5.4. Partial Specialization

A **partial** hierarchy allows a supertype object to belong to no subtype in the considered group yet.

For example, a Payment might be created in the `PENDING_METHOD` state before the customer selects a method. At that point, the Payment does not yet belong to CardPayment, BankTransferPayment, or CashPayment.

### 5.5. Four Combinations

Disjointness and completeness are two independent axes:

| | Total | Partial |
|---|---|---|
| Disjoint | Each object belongs to exactly one subtype | Each object belongs to at most one subtype, possibly none yet |
| Overlapping | Each object belongs to at least one subtype, possibly multiple | May belong to zero, one, or multiple subtypes |

The chosen combination must be explicitly specified for each hierarchy. You should not assume every hierarchy is disjoint and total by default.

## 6. Hierarchies Can Change Over Time

An object can transition from one subtype to another or start/end a role.

For example:

- A Contractor becomes an Employee.
- An individual customer transitions to a business customer after changing the contracting entity.
- A Party starts or ends the Supplier role.
- A Payment transitions from `PENDING_METHOD` to a specific method type after the user selects one.

Questions to ask:

- Does changing subtypes change the object's identity?
- Must the history of the old type be preserved?
- How should type-specific attributes of the old subtype be handled?
- Do relationships dependent on the subtype need to be migrated?
- Is there an interval where two subtypes are simultaneously effective?

### 6.1. Changing Subtypes While Preserving Identity

If it remains the same business entity, the supertype ID is usually kept. Switching subtypes is a change in classification or role, not creating a new person or object.

For example, a Worker keeps the same `worker_id` when transitioning from Contractor to Employee. The old contractor agreement is closed; a new employee work relationship record is opened.

### 6.2. Storing Subtype Membership History

If auditing is required, classification history can be stored:

~~~text
WORKER_TYPE_HISTORY
- worker_id
- worker_type
- valid_from
- valid_to
- recorded_at
~~~

You must specify whether the time interval is inclusive of endpoints and whether intervals are allowed to overlap. If only the current subtype is stored, you cannot answer what relationship type a Worker had at a point in the past.

### 6.3. Distinguishing Subtype from Role

A role can usually be added or removed without changing the fundamental type of the entity.

For example, a Party can simultaneously hold the Customer and Supplier roles. These are business roles that can change independently. Depending on the domain, roles can be modeled with time-effective association tables rather than rigid inheritance.

A subtype usually describes a specialized kind of a concept; a role describes a capacity in which an entity acts within a context or time period. The boundary should be based on domain language and actual lifecycle.

## 7. Representing Hierarchies in an ERD

A hierarchy diagram typically depicts the supertype and subtypes along with the inheritance relationship.

For example:

~~~mermaid
classDiagram
    class PAYMENT {
      +payment_id
      +amount
      +currency
      +status
    }
    class CARD_PAYMENT {
      +payment_token
      +authorization_code
    }
    class BANK_TRANSFER_PAYMENT {
      +bank_reference
      +bank_account
    }
    PAYMENT <|-- CARD_PAYMENT
    PAYMENT <|-- BANK_TRANSFER_PAYMENT
~~~

The diagram shows that subtypes inherit the shared concept from PAYMENT and add specific data. However, a simple class diagram does not fully convey disjointness, overlap, total, or partial. Annotations, notes, or constraints must be added in the model documentation.

### 7.1. Distinguishing Inheritance from Regular Relationships

An inheritance line represents is-a. An association line represents a link between entities.

For example:

- CardPayment is a Payment: inheritance.
- Payment belongs to Order: reference relationship.
- Payment uses PaymentProvider: reference or collaboration relationship.
- Payment has PaymentAttempt: composition or lifecycle association relationship.

You should not draw every connecting line as inheritance. Each relationship type has different semantics and implementation strategies.

### 7.2. Hierarchy Notation

Some ERD notations use a specialization circle with labels:

- `d`: disjoint;
- `o`: overlapping;
- single or double lines to indicate partial/total depending on the notation.

Conventions vary across tools. Provide a clear legend and do not rely on the visual diagram without confirming the meaning in the tool being used.

## 8. Mapping Hierarchies to Relational Databases

A conceptual supertype/subtype model can be implemented using several strategies. There is no single best strategy for every case.

### 8.1. One Table for the Entire Hierarchy (Single Table / Table-per-Hierarchy)

All shared and specific attributes are stored in one table, using a discriminator column to identify the subtype.

~~~sql
CREATE TABLE payments (
    payment_id BIGINT PRIMARY KEY,
    payment_type VARCHAR(30) NOT NULL,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    currency CHAR(3) NOT NULL,
    card_token VARCHAR(200),
    authorization_code VARCHAR(100),
    bank_reference VARCHAR(100),
    cash_collector_id BIGINT,
    cash_collected_at TIMESTAMP,
    CHECK (
        (payment_type = 'CARD'
            AND card_token IS NOT NULL
            AND bank_reference IS NULL
            AND cash_collector_id IS NULL)
        OR
        (payment_type = 'BANK_TRANSFER'
            AND bank_reference IS NOT NULL
            AND card_token IS NULL
            AND cash_collector_id IS NULL)
        OR
        (payment_type = 'CASH'
            AND cash_collector_id IS NOT NULL
            AND cash_collected_at IS NOT NULL
            AND card_token IS NULL
            AND bank_reference IS NULL)
    )
);
~~~

Advantages:

- querying the supertype is simple because data resides in one table;
- no JOIN is needed to read shared and specific attributes;
- inserting/updating an object is usually straightforward.

Limitations:

- many subtype columns may be NULL;
- the schema bloats when there are many subtypes;
- CHECK constraints become complex with many types;
- overlapping subtypes are hard to represent with a single discriminator;
- changing subtypes may require updating multiple columns and rules.

This strategy fits when the number of subtypes is small, the structure is relatively stable, and queries frequently read across the entire hierarchy.

### 8.2. Table for the Supertype and Each Subtype (Class/Table-per-Type)

Shared attributes are stored in the parent table; each subtype has its own table using the same key as both PK and FK.

~~~sql
CREATE TABLE payments (
    payment_id BIGINT PRIMARY KEY,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    currency CHAR(3) NOT NULL,
    status VARCHAR(20) NOT NULL
);

CREATE TABLE card_payments (
    payment_id BIGINT PRIMARY KEY
        REFERENCES payments(payment_id),
    card_token VARCHAR(200) NOT NULL,
    authorization_code VARCHAR(100)
);

CREATE TABLE bank_transfer_payments (
    payment_id BIGINT PRIMARY KEY
        REFERENCES payments(payment_id),
    bank_reference VARCHAR(100) NOT NULL
);

CREATE TABLE cash_payments (
    payment_id BIGINT PRIMARY KEY
        REFERENCES payments(payment_id),
    collector_id BIGINT NOT NULL,
    collected_at TIMESTAMP NOT NULL
);
~~~

Advantages:

- specific attributes reside in the appropriate tables;
- reduces NULL columns in the parent table;
- subtype-specific constraints are clearer;
- subtypes can be extended with minimal impact on other subtypes.

Limitations:

- reading a subtype object requires a JOIN;
- insert/delete requires operating on multiple tables within the same transaction;
- an FK to the supertype does not automatically enforce disjoint or total;
- querying all Payments requires JOIN/UNION depending on the need.

This is often a direct, clear representation when subtypes have many specific attributes or rules.

### 8.3. Separate Table for Each Concrete Type (Table-per-Concrete-Type)

Each subtype has a table containing both shared and specific attributes. There is no separate physical supertype table.

~~~sql
CREATE TABLE card_payments (
    payment_id BIGINT PRIMARY KEY,
    amount NUMERIC(12, 2) NOT NULL,
    currency CHAR(3) NOT NULL,
    status VARCHAR(20) NOT NULL,
    card_token VARCHAR(200) NOT NULL
);

CREATE TABLE bank_transfer_payments (
    payment_id BIGINT PRIMARY KEY,
    amount NUMERIC(12, 2) NOT NULL,
    currency CHAR(3) NOT NULL,
    status VARCHAR(20) NOT NULL,
    bank_reference VARCHAR(100) NOT NULL
);
~~~

Advantages:

- each subtype has an independent table;
- querying a specific type does not require joining a parent table;
- specific and shared attributes sit in the same row.

Limitations:

- shared attributes are duplicated across tables;
- updating shared rules must be synchronized across multiple tables;
- hierarchy-wide unique keys are hard to guarantee without a shared table/registry;
- querying all Payments requires UNION;
- relationships referencing Payment in general become hard to express with a simple FK.

This strategy may fit when subtypes are stored and queried independently, but data duplication and shared identity must be evaluated carefully.

### 8.4. Comparing the Three Strategies

| Strategy | Stores shared attributes | Stores specific attributes | Strengths | Main limitations |
|---|---|---|---|---|
| Single table | One table | Same table | Simple reads, few JOINs | Many NULL columns, complex constraints |
| Table-per-type | Parent table | Individual subtype tables | Clear structure, good normalization | JOINs and multi-table transactions |
| Table-per-concrete-type | Duplicated in each child table | Same child table | Simple queries for individual subtypes | Shared attribute duplication, hard global references |

### 8.5. Choosing a Strategy Based on Workload and Rules

Consider:

- current and projected number of subtypes;
- whether specific attributes are numerous or few;
- whether queries typically read the supertype or a specific subtype;
- whether subtypes are disjoint or overlapping;
- whether FKs referencing all object types are required;
- to what degree total/disjoint must be enforced in the database;
- whether adding new subtypes is frequent;
- whether subtype transition history is needed.

Do not choose solely based on having the fewest tables. Evaluate how well the representation protects rules and supports critical queries.

## 9. Discriminators and Subtype Membership Control

A discriminator is an attribute used to indicate the subtype of a record, commonly seen in table-per-hierarchy.

For example:

~~~text
payment_type = CARD
payment_type = BANK_TRANSFER
payment_type = CASH
~~~

A discriminator can be an enum, type code, or business-meaningful attribute. It must have a clear definition and controlled value set.

### 9.1. Disjoint

If subtypes are disjoint, a single discriminator is usually appropriate because each record has only one type. A CHECK constraint can ensure that specific columns match the selected type.

### 9.2. Overlapping

If an object can belong to multiple subtypes, a single discriminator is usually insufficient. You may need:

- multiple membership flags;
- separate subtype tables sharing the same supertype ID;
- a membership/role table;
- or another composition model suited to the semantics.

For example, a Party that is both a Customer and a Supplier should not be forced into a single `party_type` column if both roles can coexist.

### 9.3. Total

If specialization is total, you must ensure every supertype belongs to at least one subtype. An FK from a subtype table to the parent table only guarantees a subtype has a parent; it does not guarantee every parent has a subtype.

This can be protected by a NOT NULL discriminator in single-table, appropriate triggers/constraints, or transactional workflows. With table-per-type, checking total is usually more complex and depends on DBMS capabilities.

### 9.4. Disjoint

If subtypes are disjoint, you must prevent one supertype ID from appearing in multiple subtype tables simultaneously. Separate subtype tables with `payment_id` as PK in each table do not prevent the same ID from appearing in two different tables.

You can use a discriminator on the parent table, triggers, or a subtype registry pattern for enforcement. Choose an approach suited to your technology stack and test concurrent updates.

## 10. Should Relationships Reference the Supertype or Subtype?

When another entity needs to reference the hierarchy, determine whether it needs all types or only a specific subtype.

### 10.1. Referencing the Supertype

For example, an Order can have multiple Payments regardless of payment method:

~~~text
ORDER -> PAYMENT
           |
       -------------
       |           |
   CARD_PAYMENT  BANK_TRANSFER
~~~

Order should reference the Payment supertype because the relationship applies to all methods.

### 10.2. Referencing a Subtype

If an entity may only reference CardPayment, the relationship can point directly to the subtype or use an FK to the supertype paired with a subtype verification rule.

For example, a `CardAuthorization` table only applies to `CardPayment`. In a table-per-type relational model, it can reference `card_payments(payment_id)`.

### 10.3. Avoid Unprotected Polymorphic FKs

A design such as:

~~~text
target_type
target_id
~~~

may allow a row to reference different tables depending on `target_type`. However, standard FKs cannot automatically guarantee that `target_id` exists in the table selected by the `target_type` value.

If polymorphic references are used, an explicit control mechanism is needed, such as a shared supertype table, triggers, or dedicated association tables. Otherwise, orphaned data can appear.

## 11. When Should You Not Create a Subtype?

Not every difference requires a hierarchy.

### 11.1. Differing Only by a Few Optional Attributes

If one customer type merely has one extra rarely used field, a nullable attribute or an extension table can be used if clearly justified. Creating a subtype is not always necessary.

However, if that field comes with distinct verification rules, lifecycle, or relationships, a subtype can make the model clearer.

### 11.2. Differing Only by Status

States like ACTIVE, SUSPENDED, CLOSED are typically statuses of the same entity, not subtypes.

For example, an active account and a suspended account are still the same Account type. Transitioning state does not create a new account type unless the business defines genuinely distinct structures and rules.

### 11.3. Differing Only by Role

An organization can be both a customer and a supplier. If two roles can coexist and change independently, a role/membership model is usually more suitable than a disjoint hierarchy.

### 11.4. Differing Only by Access Permissions

View/edit permissions on data should be modeled via authorization, roles, and policies. Do not create subtypes just because user groups see different sets of fields.

### 11.5. Differing Only by Output Format

API DTOs, views, or projections can provide different structures for different clients. That does not necessarily change the conceptual data model.

## 12. Validating Hierarchies with Scenarios

Before finalizing, check these cases:

1. An object belongs to only one subtype.
2. An object belongs to two subtypes simultaneously.
3. An object belongs to no subtype yet.
4. An object satisfies none of the subtype predicates.
5. An object transitions from subtype A to subtype B.
6. A new subtype is added.
7. A relationship referencing the supertype needs to retrieve all types.
8. A relationship is only allowed to reference a specific subtype.
9. Two concurrent transactions change subtype membership.
10. Legacy data lacks a discriminator or has an obsolete type value.

For each scenario, check:

- is the membership predicate clear;
- is disjoint/overlap protected;
- is total/partial accurate;
- is identity kept stable;
- are subtype attributes omitted or left as orphaned data;
- are FKs and dependent relationships valid;
- is type-transition history stored if needed.

### 12.1. Illustrative Acceptance Criteria

For Payment divided into CardPayment and BankTransferPayment, assuming the two subtypes are disjoint and specialization is total after a Payment is confirmed:

- Every CONFIRMED Payment must belong to exactly one of the two subtypes.
- CardPayment must have a valid `card_token`.
- BankTransferPayment must have a `bank_reference`.
- A `payment_id` must not appear simultaneously in both subtype tables.
- A Payment in the `PENDING_METHOD` state may belong to no subtype yet.
- Once the method is confirmed, changing subtypes is prohibited unless going through an authorized business workflow.
- Every subtype record must reference an existing Payment.

These criteria both define behavior and indicate the constraints and tests required.

## 13. Common Mistakes

- **Creating subtypes just because tables have different columns:** structural differences are not enough; clear business criteria and distinct rules are required.
- **Confusing is-a with has-a:** composition or reference relationships are not inheritance.
- **Not writing subtype predicates:** data entrants do not know when an object belongs to a subtype.
- **Assuming disjoint and total by default:** in reality, hierarchies can be overlapping or partial.
- **Using a single discriminator for overlapping subtypes:** an object can belong to multiple groups, so a single value cannot express it.
- **Assuming a subtype FK guarantees total:** an FK only guarantees a child record has a parent, not that every parent has a child record.
- **Assuming separate PKs in each subtype table guarantee disjoint:** the same ID can still appear across different child tables.
- **Treating states or roles as subtypes:** makes the hierarchy rigid and hard to adapt when roles coexist or change over time.
- **Ignoring type-transition history:** historical reports may misinterpret the object's type at that point in time.
- **Choosing a table strategy solely by JOIN count:** constraints, queries, extensibility, and integrity must be balanced.
- **Using target_type/target_id without referential protection:** can create orphaned links.
- **Not testing new subtypes:** adding a new type can break total/disjoint assumptions and code handling the discriminator.

## 14. Conclusion

Generalization finds commonalities across specific types to form a supertype; specialization divides a supertype into subtypes based on business criteria. Each subtype must satisfy an is-a relationship, inherit shared identity and rules, and have sufficiently meaningful specific attributes or invariants.

When designing a hierarchy, write membership predicates, determine disjoint vs. overlapping and total vs. partial, consider lifecycle and transition history, and then choose a mapping strategy suited to the workload and constraint enforcement capabilities. A good hierarchy accurately expresses concepts and rules, avoids data duplication, and remains able to evolve as the business changes.

## Self-Check

1. Distinguish generalization and specialization with an example.
2. Why must a subtype satisfy an is-a relationship with its supertype?
3. How does disjoint/overlapping differ from total/partial?
4. A Party can be both a Customer and a Supplier. Should you choose an overlapping hierarchy or a role model? Explain.
5. Why doesn't an FK from a subtype table to a supertype table automatically guarantee total specialization?
6. Compare single table, table-per-type, and table-per-concrete-type.
7. When should status or access permissions not be modeled as subtypes?
8. If a Contractor becomes an Employee, what aspects of identity, attributes, and history must be considered?
9. A system has Payment, CardPayment, and BankTransferPayment. Write the predicates, completeness/disjointness, and propose a schema to enforce those rules.
