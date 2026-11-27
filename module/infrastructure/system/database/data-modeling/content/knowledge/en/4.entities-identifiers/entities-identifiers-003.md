# Distinguishing Identifiers, Display Names, and Mutable Attributes

When modeling data, three questions must be kept separate: **which object is this**, **what name do users call or see this object by**, and **what characteristics does the object currently have**. These three questions are related, yet not synonymous. A customer can change their name, change their email, or move to a new address while still remaining the same customer. If a name or email is used as the primary key, normal business changes can force the system to cascade updates across many foreign keys and break history.

In **data modeling**, an identifier enables recognizing an entity throughout its lifecycle. A display name helps humans locate and understand the entity. Attributes describe states or characteristics that can change over time. Good design keeps identifiers stable, makes uniqueness rules explicit, and records history whenever the business needs to know how values changed.

This lesson uses a sales system as its running example. A customer has an internal ID, display name, legal name, email, phone number, and address. The customer can change many of those attributes; orders already placed must still point to the exact customer and preserve the information required at transaction time.

## 1. Three Concepts to Keep Separate

### 1.1. Identifiers Answer "Which Object Is This?"

An identifier is a value or set of values used to distinguish one entity from other entities within a defined scope. A good identifier lets the system continue recognizing the same object when its name, address, status, or descriptive characteristics change.

For example, a customer with `customer_id` equal to 4821 can change their display name from "Nguyễn Minh An" to "Minh An Nguyễn". Old orders still reference `customer_id` 4821, because changing a name does not create a new customer.

In relational modeling, the primary key is typically used as the record identifier. However, distinguish among:

- **Entity identity:** the business concept of whether an object remains the same object over time.
- **Identifier:** a value used to recognize the object, such as `customer_id`, contract number, or partner-system ID.
- **Primary key:** the key chosen to uniquely identify a row in a table.
- **Candidate key:** a minimal set of attributes capable of uniquely identifying a row under data rules.

A table may have multiple candidate keys while choosing only one primary key. An external code may be a candidate key within a vendor's scope, yet not necessarily suitable as an internal primary key.

### 1.2. Display Names Answer "What Do Humans Call This Object?"

A display name serves user interfaces, search, communication, and reporting. It can collide across multiple objects, can change, can have multiple spellings, and can depend on language or context.

For example:

- Two different customers can share the same name "Nguyễn Văn An".
- A customer may use a casual name in the UI yet a legal name on invoices.
- A product may have a short name in listings and a full name on the detail page.
- An organization may change its trade name while retaining the same legal entity status.

Therefore, display names are generally not identifying keys. If the business requires a name to be unique within a scope, express that rule with an appropriate constraint; still examine whether the name can change and how renaming affects references.

### 1.3. Mutable Descriptive Attributes

Attributes describe characteristics of an entity: email, phone number, address, status, classification, date of birth, color, or current price. Some attributes are nearly immutable, some change frequently, and some are valid only for a time window.

Do not assume all attributes share the same lifecycle. The shipping address on a completed order is a historical snapshot; the customer's current contact address is an updatable attribute. Both may hold the identical address string while carrying different meanings and mutability rules.

| Component | Question | Customer Example | Typical Characteristics |
|---|---|---|---|
| Identifier | Which object? | `customer_id = 4821` | Stable within the defined scope and lifecycle |
| Display name | How is it shown or called? | "Minh An Nguyễn" | Can collide, change, be translated, or reformatted |
| Descriptive attribute | What traits does the object have? | Email, phone number, address | Mutable; requires domain value rules |
| Snapshot | Which value held true at an event? | Name and address on an invoice | Preserved as finalized at the event |

## 2. Why Identifiers Need Stability

An entity is often referenced from many places. A customer can be referenced by orders, invoices, payments, support tickets, and loyalty programs. If the referencing key relies on a mutable attribute, a simple change propagates across many tables and systems.

Consider a model that uses email as the primary key:

~~~mermaid
flowchart TD
    E[email as primary key] --> O[orders.customer_email]
    E --> P[payments.customer_email]
    E --> S[support_cases.customer_email]
    C[Customer changes email] --> U[Must update every reference]
    U --> R[Risk of missed updates and broken history]
~~~

If a customer changes their email, the system must update every place referencing that email. An import job or external integration might still send the old email. If updates are not atomic, part of the data can end up pointing to the new email while the rest still points to the old email.

With a stable internal key, relationships reference only `customer_id`. Email is updated as an attribute or contact detail with its own lifecycle. Orders do not need their foreign keys altered.

Stable identifiers are also valuable when:

- Names or display codes change due to policy.
- An object has multiple names, aliases, or languages.
- Data is synchronized across multiple systems.
- Change history and auditing must be stored.
- Duplicate records must be merged while preserving old references.
- The object is referenced by long-lived events or documents.

Stability does not mean an identifier must be exposed publicly forever. It means the system has clear rules to recognize the same entity within the chosen scope.

## 3. Types of Identifiers and Scope of Use

### 3.1. Surrogate Keys

A surrogate key is a system-generated technical identifier carrying no direct business meaning. Examples:

- Auto-incrementing integer: `customer_id = 4821`.
- UUID: `550e8400-e29b-41d4-a716-446655440000`.
- ULID or a time-ordered identifier format.

Advantages:

- Does not change when name, email, display code, or business attributes change.
- Independent of numbering rules from business units or external systems.
- Foreign keys are typically short and easy to reference.
- Objects can be created before all business attributes are known.

Costs:

- Requires an extra field and generation mechanism.
- Does not automatically enforce uniqueness of business attributes.
- Users cannot understand the object from the internal ID alone.
- May require a mapping table when integrating with external systems.

Surrogate keys fit well as primary keys in many transactional models. Still, unique constraints remain necessary for contract numbers, product codes, or emails whenever the business requires uniqueness.

### 3.2. Natural Keys

A natural key is an attribute or set of attributes that has real-world meaning and is used by the business to identify an object, for example:

- A vehicle's VIN.
- A publication's ISBN.
- A tax ID within an issuing authority's scope.
- A contract number issued by an organization.

Natural keys can be useful when they are stable, unique, governed by an authoritative source, and unchanging over the required retention lifecycle. However, carefully check uniqueness scope, reissuance rules, error corrections, and potential reuse.

A tax ID or business registration number may need to be paired with country/issuing authority. A product code may be unique only within one supplier. Ignoring scope can cause the system to treat two identical codes from two different sources as the same object.

A natural key can be stored with a unique constraint and used for lookups, while the internal primary key remains a surrogate key. This reduces the dependence of foreign keys on mutable business rules.

### 3.3. Composite Keys

A composite key combines multiple attributes to uniquely identify a row. For example, a product code might be unique only within each store:

**(store_id, local_product_code)**

An order line item might be identified by:

**(order_id, line_number)**

Composite keys accurately reflect business scope. Yet when many other tables must reference that record, foreign keys end up carrying multiple columns. If any component can change, references become complex.

You can use a surrogate key as the primary key while still placing a unique constraint on the natural combination. The choice depends on the number of relationships, component stability, and model readability.

### 3.4. Identifiers from External Systems

A customer may have an ID in the CRM, an ID in the payment platform, and an ID in the accounting system. These IDs should not be treated as sharing a single identifier namespace.

Store external identifiers together with their issuing source:

| Source | External Value | Internal Entity |
|---|---|---|
| CRM-A | C-00981 | `customer_id = 4821` |
| Payment-B | cus_7ab12 | `customer_id = 4821` |
| ERP-C | BP-1045 | `customer_id = 4821` |

`C-00981` is unique only within CRM-A, not necessarily system-wide. Hence, the pair `(issuer, external_id)` is the proper integration identifier. One internal entity can have multiple external identifiers.

### 3.5. Comparing Options

| Identifier Type | When Appropriate | Risks to Manage |
|---|---|---|
| Sequential integer | Centralized database, heavy internal relationships | Predictable; not an authorization mechanism |
| UUID/ULID | Distributed ID generation, multi-node sync, or global ID needs | Index size, generation ordering, and representation |
| Natural key | Stable business code with clear issuing authority | Code changes, reuse, uniqueness scope |
| Composite key | Identification dependent on scope or relationship | Wide foreign keys and difficulty changing components |
| External ID | Integrating with other systems | Collisions across sources, vendor-driven changes |

There is no single best identifier type for every situation. Choose based on entity lifecycle, uniqueness scope, reference count, and integration patterns.

## 4. Display Names Are Not Identifiers

### 4.1. Names Can Collide

Two people can share the same full name. Two organizations can have identical trade names in two countries. Two products can share a common name yet differ by manufacturer or version.

Using name as a key forces an untrue assumption: each name belongs to only one object. Adding a `UNIQUE` constraint on name blocks valid data; dropping the constraint renders name unusable as a unique reference.

Names can still be searched or indexed. That does not make them identifiers. Searching by name often returns one or more matches; users may need additional context to pick the right entity.

### 4.2. Names Can Change and Have Multiple Forms

Names can change due to:

- An individual changing their name or using a different name in communication.
- An organization changing its trade name or restructuring.
- A product being renamed during rebranding.
- Standardization of spelling, punctuation, or formatting.
- Translating names into other languages.
- UI truncation to fit display space.

One entity may require multiple kinds of names:

- Legal name.
- Trade name.
- Display name.
- Abbreviated name.
- Alias or former name.
- Localized names per language.

Do not lump all meanings into a single `name` column if the system must distinguish these cases. Name fields by purpose and specify which name type is used on contracts, invoices, search, or UI.

### 4.3. Normalizing Names for Search

Normalizing names can make search consistent, but keep the original value separate from the value used for searching. For example, the system can store the original display name alongside a normalized form for case-insensitive or whitespace-insensitive search.

Do not overwrite the original name with the normalized result if original formatting carries meaning. Vietnamese diacritics, punctuation, spacing, abbreviations, and name ordering may preserve vital information.

Unicode normalization, collation, and case-insensitive comparisons depend on the DBMS and language requirements. Define search rules explicitly rather than assuming two differently encoded strings are different people or the same person.

### 4.4. Even Unique Names Still Need Dedicated Keys

Some business domains have display names or codes unique within a scope—for example, a unique username on a platform or a unique slug on a website. In such cases:

- Place a unique constraint at the right scope.
- Define normalization and comparison rules.
- Define who may change the value.
- Handle old URLs or aliases when renaming.
- Keep the internal identifier stable so relationships do not depend on the slug.

A unique name may act as a candidate key at a given point in time, yet if renaming is allowed, it remains a poor choice for a long-term primary key.

## 5. Mutable Attributes and Value Lifecycles

### 5.1. Classifying by Stability

When designing attributes, classify them by lifecycle:

| Group | Example | Handling Approach |
|---|---|---|
| Stable identifier | `customer_id` | Unchanged on profile updates |
| Relatively stable attribute | Founding date, date of birth | Correctable if erroneous; consider auditing |
| Frequently changing attribute | Email, phone number, address | Controlled updates; optionally store history |
| Current status | Active, suspended | Define state transitions and modification permissions |
| Event snapshot | Name on an issued invoice | Preserve value as of event time |
| Derived data | Order count, loyalty points | Recomputable or requires sync mechanism |

This classification helps decide whether to update in place, store a history table, emit an event, or capture a snapshot.

### 5.2. Updating Attributes Does Not Change Identity

For example, a customer changes their phone number:

~~~sql
UPDATE customers
SET phone_number = '+84-900-123-456',
    updated_at = now()
WHERE customer_id = 4821;
~~~

The `orders`, `invoices`, and `support_cases` tables continue referencing `customer_id` 4821. Foreign keys do not need updating simply because the phone number changed.

If an attribute is used in integrations or lookups, update replicas or search indexes per policy. Internal relationships, however, should still rely on the stable identifier.

### 5.3. Storing History When Old Values Must Be Known

Storing only the current value suffices if the business only needs the latest information. If you must answer "which address was in effect at delivery time?" or "who changed the legal name and when?", a history model is required.

A history table can be used:

~~~sql
CREATE TABLE customer_name_history (
    customer_name_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    name_type VARCHAR(30) NOT NULL,
    name_value VARCHAR(200) NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    changed_by VARCHAR(100),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);
~~~

`valid_from` and `valid_to` represent the effective time interval of the value. Specify open/closed interval boundaries on both ends and how to prevent two names of the same type from having overlapping effective windows if business rules forbid it.

An audit log table answers a different question: who made which change, when, and what were the before and after values. Effective-dated history and audit logs can coexist, yet should not be confused. Effective history describes business truth over time; audit describes data modification activity.

### 5.4. Transaction Snapshots

An issued invoice must preserve the legal name and address at issuance time. If the invoice only references the customer and always reads the current name, a customer renaming or moving can make historical invoices display inaccurate history.

A model can store:

- `invoice.customer_id` to reference the customer entity.
- `invoice.customer_name_snapshot` to preserve the name on the invoice.
- `invoice.billing_address_snapshot` to preserve the billing address.
- `invoice.issued_at` to establish issuance timestamp.

A snapshot is not redundant duplication if it means "the value locked in during this event." Clearly mark which fields are snapshots and do not automatically update them when the current profile changes.

## 6. Illustrative Schema Design

The following example separates customer identity from name, email, and external identifiers. Syntax follows PostgreSQL.

~~~sql
CREATE TABLE customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL,
    legal_name VARCHAR(250),
    phone_number VARCHAR(40),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE customer_emails (
    customer_email_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    email_address VARCHAR(320) NOT NULL,
    email_normalized VARCHAR(320) NOT NULL,
    verified_at TIMESTAMPTZ,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE customer_external_ids (
    customer_external_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    issuer VARCHAR(80) NOT NULL,
    external_id VARCHAR(200) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (issuer, external_id)
);

CREATE TABLE orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    order_number VARCHAR(40) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE invoices (
    invoice_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    customer_name_snapshot VARCHAR(250) NOT NULL,
    billing_address_snapshot TEXT NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL
);
~~~

This model expresses several decisions:

- `customer_id` is the stable internal identifier.
- `display_name` and `legal_name` serve different purposes and can change.
- Email is separated into a contact entity because a customer can have multiple emails and separate verification history.
- `(issuer, external_id)` identifies an external code within the issuing source's scope.
- Orders reference customers via the internal key.
- Invoices retain name and address snapshots as of issuance time.

The example does not yet include every rule needed. If emails must be unique system-wide, add a unique constraint matching the normalization policy and active status. If only one email may be marked primary per customer, use a partial unique index on `customer_id` filtered by `is_primary`. If an email can be transferred from one account to another, define revocation, verification, and effective-timing policies.

### 6.1. Must Names and Emails Be Unique?

This is a business decision, not a technical default:

- Display names are usually not unique.
- Legal names can collide or change per official documents.
- Email may be required to be unique for login accounts, yet not necessarily unique for an organizational customer or recipient profile.
- Phone numbers can be shared within a family or group.
- External codes are unique only within the issuing source's scope.

If uniqueness is needed, define the exact scope: system-wide, within a tenant, within a country, within an account type, or only among active records. Unique constraints must reflect that exact scope.

### 6.2. Changing Email Without Changing Foreign Keys

When a customer updates their email, the system verifies the new email and adds or activates the new contact entry. Orders continue using `customer_id`. If old email history must be retained, mark the old email inactive or store its effective time range.

Do not replace `customer_id` with the new email or update every foreign key to match the email. Doing so conflates contact details with entity identity.

## 7. Identifier Scope and Uniqueness

### 7.1. Global Identifiers and Scoped Identifiers

A code can be unique in one scope while colliding in another. For example:

- Employee ID is unique within one company, not across the entire conglomerate.
- Product code is unique within one store, not across the entire marketplace.
- Contract number is unique within each year or each branch.
- User ID is unique within a tenant.

When scope is part of business identity, include it in the candidate key or relational model. For example, `(tenant_id, local_user_code)` can be a unique key. A surrogate `user_id` can still serve as the primary key for internal references.

### 7.2. Identifiers That Can Be Reissued or Reused

Some display codes are reused after an object is deleted or expires. If that code appears in historical data, reuse can make old references ambiguous.

Determine:

- Can the code be reused?
- When is the code considered expired?
- Must the code be unique across all history?
- If reissued, must it be disambiguated by time or issuer?
- Do integrated systems store the display code or the internal ID?

Internal identifiers should generally not be reused. Physically deleting a row and letting a new row inherit the same ID can cause old data to point mistakenly to the new entity. For business data requiring history, it is usually better to deactivate or archive records rather than deleting and reissuing identifiers.

### 7.3. Identifiers Are Not Security Mechanisms

Sequential IDs are predictable; UUIDs are harder to guess, yet do not automatically prove the caller has access rights. Access permissions must be checked by user, tenant, and ownership relationships. Never treat hiding IDs as an authorization mechanism.

If a public API needs an unpredictable or stable reference code, a separate public identifier can be used. Public codes still require per-object permission checks. Keep internal primary key and public ID as two fields serving distinct purposes.

## 8. When Entities Are Renamed, Merged, or Split

### 8.1. Renaming Does Not Create a New Entity

If the same organization changes its trade name, identity can remain intact. Update the current name, record history if needed, and preserve relationships. Do not create a new organization merely because its display name changed.

However, if one legal entity ceases to exist and a new legal entity is formed, the business may consider them two distinct entities despite similar names. Determining identity must rest on business meaning, not solely on name strings.

### 8.2. Merging Duplicate Records

In practice, two profiles may be created for the same customer. After verifying duplication, the system can select one record as the canonical record, migrate relationships, and keep a mapping from the old ID to the canonical ID.

A merge workflow requires:

1. Verifying both records truly represent the same entity.
2. Selecting the canonical record and defining how attributes are combined.
3. Migrating dependent relationships inside a transaction or recoverable process.
4. Retaining old ID history and recording who approved the merge.
5. Handling external identifiers and duplicate entries.
6. Updating integrated systems and search indexes.
7. Checking orders, invoices, and reports after the merge.

Do not delete an old ID and forget it. An alias or mapping table can store `old_customer_id`, `canonical_customer_id`, timestamp, and reason. Stale references from external systems may need resolution through this mapping.

### 8.3. Splitting One Record into Multiple Entities

Conversely, one profile might accidentally hold data for two people or two organizations entered by mistake. Splitting records requires determining which data belongs to each entity and which historical relationships must be partitioned.

Not every transaction can simply be split in half automatically. An issued invoice may still belong to the legal party that signed at that time. Record data-correction decisions, preserve evidence, and never silently rewrite event history.

### 8.4. Deduplication Is Not Identity Merging

Two profiles with the same name and address are not guaranteed to be the same person. Two customers sharing an email could be a family sharing a mailbox or an enterprise with multiple contacts. Matching can produce candidate pairs, yet merging must rely on rules and evidence.

Distinguish:

- **Exact match:** exact matching on a trusted identifier within the proper scope.
- **Probabilistic match:** estimating duplication likelihood across multiple attributes.
- **Merge decision:** a verified business decision that two profiles represent the same entity.

Do not automatically merge based solely on similar names or a shareable attribute.

## 9. Common Design Mistakes

**Using name as the primary key.** Names can collide and change. Use a stable identifier and store names as descriptive attributes.

**Using email as a foreign key in every table.** Emails can change, be revoked, or be shared. Reference by internal ID; store emails according to contact and login policies.

**Assuming unique means immutable.** An attribute may be unique right now yet still permitted to change. Unique constraints protect uniqueness, not immutability.

**Using one `name` field for every purpose.** Legal names, trade names, display names, and former names carry different meanings. Name fields by purpose.

**Encoding business meaning into technical IDs.** A code like `HN-2026-00042` embeds branch and year. When organizational structures or numbering rules change, the ID becomes hard to maintain. If human-readable codes are needed, store them as a business identifier with separate rules.

**Treating external IDs as global.** `12345` from two vendors can refer to two different objects. Always store the issuer or namespace.

**Overwriting history with new values.** If invoices, contracts, or events must reflect state at occurrence time, store snapshots or effective-dated history.

**Auto-merging by name.** Identical names do not prove identical identity. Verify with multiple signals and an approval workflow.

**Reusing deleted keys.** This can misdirect historical references. Keep IDs stable and manage archived/inactive states.

**Using unpredictable IDs instead of access checks.** UUIDs do not replace authorization. Every query must still verify permissions on the requested entity.

## 10. Identifier Decision Process

When modeling an entity, you can follow these steps:

1. **Define the entity:** what is the business object, and where are its boundaries relative to neighboring concepts?
2. **Establish identity:** when do two records represent the same object, and when are they distinct objects?
3. **List candidate identifiers:** which internal codes, business codes, external IDs, or attribute combinations can identify it?
4. **Check stability:** can the identifier change, be reissued, reused, or collide across scopes?
5. **Choose the primary key:** select an appropriate key for internal relationships and enforce other uniqueness rules with constraints.
6. **Classify names and attributes:** do display name, legal name, contacts, status, and snapshots serve distinct purposes?
7. **Define history:** is only the current value needed, or must we know who changed it, when, and during which interval a value was effective?
8. **Define uniqueness scope:** system-wide, tenant, issuer, branch, or a time window?
9. **Design change handling:** how are renames, code changes, merges, splits, deactivation, and deletion handled?
10. **Verify:** test duplicate names, email changes, external ID changes, merges, splits, and historical queries.

Decisions should be documented along with assumptions and rationale. If business rules change, the team can assess impact rather than reverse-engineering table structures.

## 11. Model Review Checklist

Before finalizing the design, ask yourself:

- [ ] Entity definition and identity boundaries are clear.
- [ ] Primary key remains stable across name and attribute changes.
- [ ] Candidate keys and uniqueness rules are defined at the proper scope.
- [ ] Display names are separated from legal names, aliases, or localized names when needed.
- [ ] Mutable attributes are not used as long-term foreign keys.
- [ ] External IDs are stored alongside their issuer or namespace.
- [ ] Normalization and comparison rules for names/emails/codes are agreed upon.
- [ ] Snapshots and history are stored for data requiring auditing or event reconstruction.
- [ ] Merge, split, alias, and deactivation workflows are defined.
- [ ] Identifier reuse has a clear policy.
- [ ] APIs do not rely on ID unpredictability in place of authorization.
- [ ] Tests cover renames, email changes, duplicate names, duplicate external IDs, and status changes.

## Conclusion

Identifiers, display names, and descriptive attributes serve three different purposes. An identifier answers which entity is being referenced; a name helps humans recognize and communicate; attributes describe current traits or values at a point in time. Mixing these three concepts leaves the model fragile when data changes and makes transaction history untrustworthy.

Choose identifiers based on the entity's identity and uniqueness scope. Use stable keys for internal relationships, place unique constraints on business codes when required, and store external IDs alongside their issuing source. Separate names by purpose, classify attributes by lifecycle, and retain snapshots or history when business rules demand it. When an entity is renamed, merged, or split, handle it in a controlled manner so all references and historical events retain their exact meaning.
