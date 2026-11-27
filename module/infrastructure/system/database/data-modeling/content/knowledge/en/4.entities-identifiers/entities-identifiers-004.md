# Natural Keys, Surrogate Keys, and Selection Criteria

In the **Entities and Identifiers** chapter of the **DATABASE_DATA_MODELING** module, learners need to understand which business object an entity represents, what keeps that object identifiable across its lifecycle, and how to protect its uniqueness. Once entities are identified, a key decision is choosing a natural key, a surrogate key, or a combination of both.

A key is not merely a column used to join tables. It is an identification contract among data, business processes, and consuming systems. Choosing an unstable key can cause business code changes to break relationships, create duplicate records, or force cascading updates across references. Choosing a surrogate key while forgetting business constraints can allow two records to represent the same object. This lesson explains the nature of both identification approaches, selection criteria, and how to apply them in an evolvable data model.

## 1. How Should an Entity Be Identified?

An **entity** is a business object or concept that has its own identity and can be distinguished from other objects of the same kind. Examples include a customer, a product, an order, or an employee. Entities typically have lifecycles, attributes, and relationships with other entities.

When identifying an entity, ask:

- Can this object exist independently in the business domain?
- Does it need to be distinguished from other objects of the same type?
- Can it be created, updated, deactivated, or tracked historically?
- Do other processes need to reference this exact object again?
- Which attributes describe the object, and which merely describe a role or a single participation?

For example, a customer can change their name, email, or address and still remain the same customer. If the customer's identifier is tied directly to email, changing email can make the system mistakenly assume the old customer disappeared and a new customer appeared. The identifier should express the entity's identity, while email is an attribute mutable under business rules.

### Distinguishing Entities and Value Objects

Not every concept in a model needs an independent identifier.

| Concept | How It Is Identified | Examples |
|---|---|---|
| Entity | Has its own identity, must be distinguished over time | Customer, Order, Product |
| Value object | Identified by the entirety of its values; usually lacks an independent lifecycle | Date range, monetary amount with currency, coordinates |
| Attribute | A characteristic of an entity or value object | Display name, creation date, quantity |
| Associative entity | Represents a relationship with its own attributes or lifecycle | Order line, enrollment, employee assignment |

For example, the current address on a customer profile can be a value object. However, the shipping address captured on an order has its own historical significance: it must stay intact even if the customer later changes addresses. Depending on the business domain, the address snapshot can be part of the order or an object with its own identifier if it needs independent management and referencing.

A many-to-many relationship can also become an associative entity. For example, Student enrolling in Course produces an Enrollment with enrollment date, status, and grade. Storing only a list of course codes on the student makes it hard to represent multiple attempts or the history of each enrollment.

## 2. Key and Identifier Concepts

Before comparing both key types, distinguish these common terms:

- **Superkey:** one or more attributes capable of uniquely identifying each record; the attribute set may contain redundant attributes.
- **Candidate key:** a minimal superkey, meaning removing any attribute from the key removes the uniqueness guarantee.
- **Primary key:** the candidate key selected as the official identifier for a row in a table.
- **Surrogate key:** a technical identifier generated to represent a record, usually carrying no business meaning.
- **Natural key:** one or more attributes that carry inherent business meaning and can identify an object under defined rules.
- **Alternate key:** a candidate key not chosen as the primary key, yet still usable for unique identification.
- **Foreign key:** an attribute or set of attributes referencing a protected key in another table.

For example, an employee has an employee number unique within an organization. If the employee number is defined as immutable and non-reusable, the combination `(organization_id, employee_no)` can be a natural key. The table can still use `employee_id` as a surrogate primary key; in that case, the business combination must be protected with `UNIQUE`.

A key is valid only within a defined scope. An employee number may be unique within one company but not across the entire conglomerate; a SKU may be unique within one supplier yet collide with another supplier's SKU. Therefore, explicitly document uniqueness scope rather than assuming a code is system-wide unique.

## 3. Natural Keys

A **natural key** uses data with business meaning to identify an object. The key can be a single attribute or a combination of multiple attributes.

For example:

- Employee number within an organization.
- Country code according to a defined standard set.
- Product code within a supplier's scope.
- Contract number within an issuing unit's scope.
- Combination of organization code and dossier code if each dossier is unique only within that organization.

The advantage of a natural key is that it is human-understandable and can be reconciled against business records or external systems. Seeing an employee number lets operators immediately tell which employee a record represents without looking up another mapping table.

However, a value that looks natural is not necessarily a good identifier. Emails can change, phone numbers can be reassigned, names can collide, addresses can change, and product codes can be reused or changed by supplier policy. Data that is meaningful to users is not synonymous with data stable enough to serve as a key.

### Conditions for a Natural Key to Be Suitable

A good natural key should meet the following conditions:

1. **Unique within a clear scope:** two distinct objects cannot share the same key value within the applicable scope.
2. **Stable:** the value rarely changes across the object's referencing lifecycle.
3. **Non-reusable:** when an object becomes inactive, the old code is not assigned to a new object if the system still holds historical references.
4. **Available on time:** determinable at object creation, or governed by a clear rule for any pre-code phase.
5. **Non-null and unambiguous:** the value has consistent formatting, normalization rules, and semantics.
6. **Free of unnecessary sensitive information:** do not use personal national IDs, secrets, or easily leaked data as a widely exposed key.
7. **Governed by an owner:** clear authority over who issues codes, who can modify them, and which system is the source of truth.

Uniqueness and stability must be confirmed through business rules or data contracts, not merely by inspecting a current sample dataset.

### Simple and Composite Natural Keys

A simple natural key consists of one attribute, such as `country_code` when the code set and scope are well defined. A composite key consists of multiple attributes, such as `(organization_id, employee_no)`.

Composite keys accurately express business scope, yet can make every foreign key wider. If another table references an employee, it must store both `organization_id` and `employee_no`. This may make sense when key components carry meaning in the model; however, if the combination is long, volatile, or appears in many relationships, maintenance cost rises.

Do not add an attribute to a key merely because it appears on a screen or API. Keys must be minimal and grounded in genuine uniqueness rules.

## 4. Surrogate Keys

A **surrogate key** is a system-generated identifier carrying no business meaning. Examples include a numeric `customer_id`, a UUID `product_id`, or an `order_id` generated by an identity service.

Surrogate keys are often chosen as primary keys because they remain stable even when business attributes change. A customer's email can change while `customer_id` stays the same; a SKU may be standardized or changed by a supplier while the product record's `product_id` stays unchanged if the business treats it as the same entity.

Common benefits:

- Shorter and simpler than long composite keys.
- Not directly coupled to mutable business numbering rules.
- Easy to reference across multiple tables when one entity has multiple external identifiers.
- Reduces propagation of business key changes across relationships.
- Supports creating records before business codes are assigned.
- Reduces exposure of sensitive or meaningful data in URLs, logs, and integration messages.

Surrogate keys do not automatically solve business uniqueness. If the customer table has an auto-generated `customer_id` without proper uniqueness rules for customer codes or verified identifiers, the system can still store two records representing the same customer. A surrogate key only answers "which record is this in the system?"; it does not answer "does this record duplicate an existing business object?".

### Ways to Generate Surrogate Keys

| Generation Method | Characteristics | Considerations |
|---|---|---|
| Sequential number / sequence | Short, readable, usually ordered by creation within a single issuer | Hard to issue independently across multiple nodes without partitioning; can leak scale or creation order |
| UUID | Needs no simple global counter; suits sharing IDs across many components | Longer than integers; some generation schemes produce index-unfriendly write ordering |
| Time-ordered ID with distributed component | Supports multi-node generation and rough chronological sorting | Requires managing layout, clocks, allocation ranges, and collision risks by design |
| Random code with validation | Unpredictable and convenient for public identifiers | Must check collisions; unpredictability does not replace access control |

No single ID generation algorithm fits every system. Decide based on distributed requirements, offline generation, key size, sortability, readability, information leakage risk, and DBMS support. An ID is not an authorization mechanism; knowing an ID must never imply permission to access the record.

## 5. Comparing Natural Keys and Surrogate Keys

| Criterion | Natural Key | Surrogate Key |
|---|---|---|
| Origin | Data with business meaning | System-generated |
| Explainability | Usually easy for business users to understand | Usually carries no meaning |
| Stability | Depends on business rules and issuing source | Can stay stable when business attributes change |
| Length | Can be short or a long composite | Usually designed compact or fixed-length |
| Uniqueness scope | Must be defined by business domain | Usually unique within the system or ID-issuing scope |
| Integration | Convenient when multiple systems share a business code | Requires sharing IDs or mapping IDs across systems |
| Security and privacy | May expose business details or structure | Can reduce information exposure, though not a security control |
| Business changes | Can cascade reference updates if used as PK | Usually minimal impact on relationships when business codes change |
| Business duplicate control | Expressed directly via unique key | Still requires separate constraints on business identifiers |

In many systems, the practical choice is **using a surrogate key as the primary key while still protecting natural keys with UNIQUE constraints**. This decouples technical identity from business uniqueness rules.

Using a natural key directly as the primary key remains sound when the business code is genuinely stable, compact, clearly scoped, and tightly governed. Avoid forcing one rigid rule across all tables.

## 6. Criteria for Choosing a Key for an Entity

The following decision process can be used:

### Step 1: Establish Business Identity

Write down: "When are two records considered the same object?" and "When are they definitely two different objects?" If the team does not agree, do not choose a key yet.

For example, two profiles with the same email could be a returning user re-registering, two users sharing an email, or duplicate data entry. Merge rules must be clarified before treating email as a natural key.

### Step 2: List Candidate Keys

Find attributes or attribute combinations capable of unique identification. For each candidate, note:

- Uniqueness scope.
- Who issues and governs it.
- Can it change or be reused?
- Is it available at record creation?
- Can it be null, duplicated, malformed, or require normalization?
- Does it contain sensitive data?
- Do other systems depend on it?

### Step 3: Evaluate Stability and Cost of Change

Do not only ask "is this value unique right now?". Ask "if this value changes in three years, how many systems, tables, messages, and reports are impacted?". If a code can change or be reissued, using it as a PK usually raises evolution costs.

### Step 4: Choose the Primary Identifier

Choose a natural key when business rules are stable, scope is clear, the value is non-sensitive, and propagating it as a reference incurs low cost. Choose a surrogate key when the business identifier can change, is long, multi-part, arrives late, depends on external systems, or is unsuitable to propagate.

### Step 5: Protect Remaining Keys

Whichever primary key is chosen, retain other candidate keys as `UNIQUE` constraints when required by business rules. If uniqueness applies only within a scope, use the corresponding column combination. If rules vary over time or status, model that exact condition accurately and verify DBMS support.

### Suggested Evaluation Matrix

Score each candidate from 0 to 2: 0 = fails, 1 = conditional or carries risk, 2 = passes. This is a discussion tool, not a replacement for business rules.

| Criterion | Question | Max Score |
|---|---|---:|
| Unique | Does it distinguish every object within scope? | 2 |
| Stable | Does it stay constant throughout the referencing lifecycle? | 2 |
| Non-reusable | When an old object deactivates, is the code kept away from new objects? | 2 |
| Available | Is the value present when creation and linking occur? | 2 |
| Minimal, simple | Are the components, length, and normalization rules easy to manage? | 2 |
| Safe | Does it avoid exposing sensitive data and unnecessary details? | 2 |
| Governable | Is there an issuing owner, change policy, and quality control? | 2 |

A candidate with a high score should still be rejected if it violates a mandatory requirement—such as non-uniqueness or reusability when history requires separation. Never use points to offset a critical identification flaw.

## 7. Design Example: Customers and Products

Suppose a sales system manages customers and products. The team agrees:

- Each customer has a stable internal identifier.
- Email can change, and not every customer has a dedicated email.
- Product codes are managed per supplier.
- Product codes can change when a supplier changes coding rules.
- Historical orders must continue referencing the exact product sold.

Illustrative design:

~~~sql
CREATE TABLE customer (
    customer_id BIGINT PRIMARY KEY,
    email VARCHAR(320),
    display_name VARCHAR(160) NOT NULL
);

CREATE TABLE supplier (
    supplier_id BIGINT PRIMARY KEY,
    supplier_name VARCHAR(200) NOT NULL
);

CREATE TABLE product (
    product_id BIGINT PRIMARY KEY,
    supplier_id BIGINT NOT NULL,
    supplier_sku VARCHAR(100) NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    CONSTRAINT fk_product_supplier
        FOREIGN KEY (supplier_id) REFERENCES supplier(supplier_id),
    CONSTRAINT uq_product_supplier_sku
        UNIQUE (supplier_id, supplier_sku)
);
~~~

In this example:

- `customer_id` and `product_id` are surrogate keys used as primary keys.
- `email` is not chosen as a key because it can change, is optional, and may not be unique under agreed rules.
- `(supplier_id, supplier_sku)` is a business candidate key within supplier scope; `UNIQUE` enforces that uniqueness.
- If a supplier changes a SKU, `product_id` remains intact so older orders continue referencing the exact product record.
- If an old SKU can be reused for a different product, store code history or an effective-dated product identifier entity; do not assume a current `UNIQUE` constraint solves historical reuse.

Orders can reference `product_id` while also storing snapshots of name and price at purchase time. Thus, the relationship to the current product and the historical transaction meaning stay clearly separated.

### When a Natural Key Is a Good Choice

Suppose a country table uses a well-defined standard code set where codes span the entire standard, remain stable, and are version-governed. If these conditions hold, the country code can serve as a natural primary key. Even then, documentation must specify which standard is used and how standard updates are handled.

### When a Composite Key Reflects the Entity's Nature

An order line item is normally identified only within an order's scope. If the business guarantees line sequence numbers do not repeat within an order, the composite key `(order_id, line_no)` can be the line's natural identifier:

Assuming the `customer_order` and `product` tables have already been defined in the corresponding transaction model section, the order line table can be declared as follows:

~~~sql
CREATE TABLE order_line (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT pk_order_line PRIMARY KEY (order_id, line_no),
    CONSTRAINT fk_line_order
        FOREIGN KEY (order_id) REFERENCES customer_order(order_id),
    CONSTRAINT fk_line_product
        FOREIGN KEY (product_id) REFERENCES product(product_id),
    CONSTRAINT ck_line_quantity CHECK (quantity > 0)
);
~~~

Here, `order_id` is a foreign key to the order; `line_no` is a meaningful sequence number within the order. If order lines need independent referencing across multiple systems or have a separate lifecycle after order transfers, the team may consider adding a surrogate `line_id` while retaining `UNIQUE(order_id, line_no)`. Decisions must come from referencing needs and business rules.

## 8. Scenarios Requiring Careful Consideration

### External Identifiers and Internal Identifiers

A system may receive a customer ID from a CRM, a user ID from an identity provider, and an internal ID. Do not use a single field to represent all of them if they have different issuers, scopes, or lifecycles.

Each identifier can be stored as a pair `(issuer, external_id)`, where `issuer` identifies the issuing party. One party may issue multiple ID types; specify scope and identifier type clearly if needed. Mapping needs rules for when an external code changes or one account links to multiple identities.

### Business Identifier Changes

If an employee code changes due to an organizational transfer or data standardization, determine whether this is the same employee or a new employment relationship. If it is the same entity, the internal identifier should stay unchanged and the business code can be stored in an effective-dated identifier table. If it is a new relationship or role, the model needs a separate entity to retain history.

### Merging and Splitting Entities

When discovering two duplicate customer profiles, do not simply change one profile's key and delete the other. Determine the canonical profile, store a mapping from the old ID to the canonical ID, resolve references, and preserve traceability. When splitting one profile into two entities, determine which data, relationships, and historical events belong to each new entity.

### Sensitive Data and Predictable IDs

National IDs, account numbers, or phone numbers may look unique, yet should not become widely exposed keys if that leaks data. Random or hard-to-guess surrogate keys can reduce record-order inference, yet access permissions must still be verified independently on every request.

## 9. Keys Across Data Model Families

The concept of identifiers appears across multiple data organization paradigms, though implementations differ.

| Model Family | Common Identification Patterns | What Needs Clarification |
|---|---|---|
| Relational | PK, candidate key, `UNIQUE`, and FK | Uniqueness scope, nullability, referential integrity, and impact when keys change |
| Document | Document ID field and business keys inside payload | Collection-level vs. cluster-wide ID uniqueness; embed vs. reference; schema versioning |
| Graph | Node ID and business properties on nodes/edges | Which entity a node represents; whether edges have separate IDs; how duplicate nodes are detected |
| Analytical | Surrogate keys for dimensions, business keys for reconciliation, and fact grain | Change history, time-versioned dimension records, and avoiding row multiplication on joins |

In an analytical warehouse, a dimension can use surrogate keys to distinguish versions of the same business object. For example, when a customer's address changes and reports must analyze history by the address active at each period, each dimension version can have its own surrogate key alongside a shared business key and effective dates. Facts reference the dimension version matching the event timestamp.

In a document store, a document can have a technical ID while also containing business codes. Embedding a child object does not by itself decide whether the child has an independent identity. If it needs independent referencing, updating, or lifecycle management, establish clear IDs and aggregate boundaries.

In a graph, a node's internal ID may differ from its business code. A User node may have multiple external identifiers; per-issuer uniqueness constraints prevent creating duplicate nodes during data synchronization.

## 10. Verifying Key Choices

Before finalizing the model, test against data and scenarios:

1. **Key collision:** attempt to create two distinct objects with the same key value within the same scope.
2. **Missing value:** attempt to create a record when the natural identifier is not yet available or is null.
3. **Code change:** change email, SKU, or employee number and check historical relationships.
4. **Code reuse:** deactivate an object and attempt to reissue its code to a new object.
5. **Referencing:** create child data referencing the entity and verify behavior when the entity is deactivated.
6. **Synchronization:** receive the same message or external identifier multiple times; verify idempotency and merge capability.
7. **Merge/split:** simulate two duplicate records and one record needing a split into two; verify reference mapping.
8. **Privacy:** check whether IDs appearing in URLs, logs, exports, and integration messages expose unnecessary data.

For example, the following query can detect duplicate SKUs within the same supplier before adding a unique constraint:

~~~sql
SELECT supplier_id, supplier_sku, COUNT(*) AS duplicate_count
FROM product
GROUP BY supplier_id, supplier_sku
HAVING COUNT(*) > 1;
~~~

Results must be resolved according to business rules before applying the constraint. Do not automatically delete duplicate records before identifying orders and historical relationships referencing them.

## 11. Checklist and Practice Exercises

### Key Selection Checklist

- [ ] Entity and business identity have been defined.
- [ ] Uniqueness scope of each candidate key has been identified.
- [ ] Natural keys have been evaluated for stability and reusability.
- [ ] Surrogate keys have a clear issuer and generation rule.
- [ ] Primary key is minimal, non-null, and stable across the referencing lifecycle.
- [ ] Other business identifiers remain protected by `UNIQUE` when needed.
- [ ] Composite keys accurately reflect business scope and contain no redundant attributes.
- [ ] External identifiers are separated from internal identifiers.
- [ ] Rules for code changes, merges, splits, and history retention have been reviewed.
- [ ] IDs are not treated as authentication or authorization mechanisms.
- [ ] Critical queries and migrations have verification scenarios.

### Exercises

**Exercise 1 — Choosing a Key for Employees**

An organization has multiple branches. Each branch issues its own employee numbers; employees can transfer branches, and old codes must be retained for auditing.

Propose:

- Which entity needs identification?
- Is `(branch_id, employee_no)` a stable key for an employee?
- Should `employee_id` be used as a surrogate key?
- How should code and branch history be stored?
- What rule prevents old codes from being misassigned?

**Exercise 2 — Choosing a Key for Products**

Multiple suppliers can use the same SKU. One supplier can change a SKU, yet sold products must continue to be recognized.

Determine the primary key, candidate keys, unique constraints, and snapshot data needed in order lines.

**Exercise 3 — Evaluating Email as a Customer Key**

An application lets users change email, use a work or personal email, and invite multiple members sharing a group email address.

Explain why email may fail the criteria for a natural key, then propose an internal identifier and suitable uniqueness rules.

**Exercise 4 — Identifiers in an Analytical Warehouse**

A customer changes residential region and reports need to analyze revenue by region as of order placement time.

Describe how to use business keys and surrogate keys for the customer dimension, define effective windows, and explain which version the fact table should reference.

### Self-Assessment Criteria

Your work meets expectations when you can explain:

- Why an object is considered an entity and needs its own identity.
- Which candidate keys are truly unique, minimal, and within what scope.
- Why a natural key or surrogate key was chosen as the primary key.
- How business constraints remain protected when using a surrogate key.
- What happens when business codes change, are reused, or entities are merged/split.
- How the choice impacts relationships, integration, history, and model evolvability.

A good identifier design distinguishes **entity identity** from **the codes that the business or other systems use to refer to it**. Primary keys give systems stable references; business keys protect semantics and uniqueness under real-world rules. When both roles are clearly established, the data model becomes easier to integrate, verify, and evolve.
