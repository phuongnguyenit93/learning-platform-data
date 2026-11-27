# Identifiers Across Multiple Organizations and Namespaces

## Learning Objectives

After this lesson, you will be able to explain why a code is unique only within the scope of one organization or system; define the **namespace** and **issuer** of an identifier; design how to store multiple external codes for the same internal entity; and avoid mistakenly merging two objects merely because they share the same code string.

You will also know how to choose internal keys, define uniqueness scope, handle mutable or reused codes, link data across multiple organizations, and verify identification rules in both databases and APIs.

## 1. Why Do Identifiers Need Scope?

A string like `C-001` might be a customer ID in Company A's CRM system, a contract number in Company B's system, or a product code in another catalog. Looking at the value `C-001` alone gives no indication of which object it points to.

An **identifier** is a value used to reference an object within a specific scope. Whenever calling an identifier unique, always ask: unique where, issued by whom, for which object type, and during what timeframe?

Example:

| Issuer | Object Type | Value | Uniqueness Scope |
|---|---|---|---|
| Company A's CRM | Customer | C-001 | Within Company A's CRM |
| Company B's ERP | Customer | C-001 | Within Company B's ERP |
| Product catalog | Product | C-001 | Within the product catalog |
| Store system | Order | C-001 | Within the store system |

Identical values do not mean the same object. Conversely, one real-world object can have multiple different codes across systems.

If a database is designed assuming every code is globally unique, importing data from another organization can cause key collisions. Automatically merging two profiles merely because their codes match can corrupt relationships, history, and access control.

## 2. Namespaces and Identifier Issuers

### 2.1. Namespace

A **namespace** is a conventional scope within which names or identifiers are interpreted and governed. It indicates which system, organization, business domain, or standard a value belongs to.

A namespace can be defined by:

- issuing organization;
- source system;
- object type;
- tenant or business unit;
- identification standard;
- version or effective time window when rules change.

For example, two different CRMs may both issue customer codes incrementing from 1. Namespaces distinguish:

- `crm.company-a.customer` + `1001`;
- `crm.company-b.customer` + `1001`.

An identifier value should be interpreted together with its namespace. In many designs, the true identifying key is a tuple of namespace and value, rather than a lone string.

### 2.2. Issuer

An **issuer** is the organization or system authorized to generate and govern identifiers. The issuer determines numbering rules, uniqueness, how codes are changed, revoked, or reused.

Examples:

- CRM issues customer profile codes.
- Government authority issues business registration numbers.
- Payment provider issues their transaction IDs.
- Warehouse system issues lot/batch codes.
- Internal identity service issues UUIDs for platform entities.

Namespace and issuer are related yet not always identical. One organization can have multiple namespaces for customers, suppliers, and contracts. A namespace can also be governed under a shared standard with multiple participating organizations.

During integration, know which source holds authority to assert a code is valid and where the code can be looked up. A system receiving a code does not automatically gain authority to edit or reissue that code.

### 2.3. Uniqueness Scope

Uniqueness scope defines which set of records cannot share the same identifier. Common scopes include:

- system-wide;
- one organization;
- one tenant;
- one source system;
- one object type within one system;
- one time period or catalog version.

For instance, employee numbers may be unique within one company yet not across subsidiaries. Product codes may be unique within one catalog yet collide in a partner's catalog.

Express the rule as a complete sentence: "Within the same tenant and the same source system, a customer code may belong to at most one active customer profile." This is far clearer than saying "`customer_code` is unique."

## 3. Internal Identifiers and External Identifiers

A system typically needs to distinguish identifiers it manages itself from codes issued externally.

### 3.1. Internal Identifiers

An internal identifier is used by the system to stably reference an entity within its own model. Auto-incrementing integers, UUIDs, or another ID format can be used.

For example, a database can assign `customer_id = 8f...` as the primary key for a customer profile. This key does not need to carry meaning for users and does not depend on a partner's CRM code.

Advantages of internal identifiers:

- the system controls issuance and enforces its uniqueness scope;
- external source codes can change without forcing primary key changes;
- multiple external codes can reference the same internal entity;
- internal relationships do not depend directly on partner system policies.

A properly generated UUID reduces collision risk across systems, yet **does not prove two IDs represent the same real-world person or organization**. If CRM A and CRM B both store the same customer, each system can assign a different UUID to its own profile.

### 3.2. External Identifiers

An external identifier is issued by another organization, system, or standard. It is useful for reconciliation, synchronization, and source data lineage.

For example, an internal customer profile may link to:

- customer ID in the CRM;
- account ID in the customer support system;
- customer code issued by a sales partner;
- enterprise registration ID from a competent authority.

These codes do not necessarily share the same format or trust level. Store the issuing source and scope of each code.

### 3.3. Why Not Use One External Code as the Primary Key?

Directly using a partner's CRM code as the primary key creates coupling:

- the partner switches systems or changes numbering rules;
- the same partner operates multiple tenants;
- codes are reused after profiles are deleted;
- the enterprise merges two source systems;
- a second data source must be added for the same entity.

A stable internal key combined with an external-identifier mapping table is usually easier to evolve. External codes remain preserved for reconciliation without dictating all internal relationships.

## 4. Representing a Scoped Identifier

There are many ways to represent an identifier. What matters is not losing the namespace and uniqueness rules.

### 4.1. Identifier Tuple

A general model can view an identifier as a tuple:

```text
Identifier = (issuer, namespace, entity_type, value)
```

Where:

- **issuer:** the party issuing and governing the code;
- **namespace:** the scope or system the code belongs to;
- **entity_type:** the type of object being identified;
- **value:** the code value.

Depending on the domain, tenant, version, country, or effective time can be added. Not every system needs every component; include only those actually participating in uniqueness or interpretation rules.

Example:

~~~json
{
  "issuer": "company-a",
  "namespace": "crm.customer",
  "entityType": "customer",
  "value": "C-001"
}
~~~

This identifier is distinct from `C-001` issued by Company B's ERP.

### 4.2. Using URIs or Structured Namespace Names

Some systems use prefixed strings to represent namespaces:

~~~text
urn:company-a:crm:customer:C-001
urn:company-b:erp:customer:C-001
~~~

This makes source and scope visible in a single value. However, concatenated strings are safe only with clear encoding and delimiter rules. If component values can contain delimiters, use encoding or store each part in separate columns.

A URI/URN does not by itself make an identifier globally unique. Uniqueness still depends on naming rules, namespace governance, and compliance by all parties.

### 4.3. Per-Tenant and Per-Source-System Namespaces

In a multi-tenant platform, two customers in two tenants can both have code `1001`. Two different scopes must be distinguished:

- tenant is the data scope of the customer using the platform;
- source system is the issuer of the code imported into the platform.

If one tenant connects two CRMs, code `1001` from CRM A and CRM B can still differ. In that case, the identifier scope may be the combination `tenant_id + source_system + entity_type + external_value`.

Do not just add `tenant_id` merely because a multi-tenant architecture has it. Verify the exact issuer and code allocation scope; sometimes the source system already implies the tenant, and sometimes it does not.

## 5. Designing an External Identifier Mapping Table

One internal entity can have multiple external identifiers. Instead of adding one column per system such as `crm_id`, `erp_id`, `partner_id`, use a mapping table.

Relational model example:

~~~sql
CREATE TABLE customers (
    customer_id UUID PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL
);

CREATE TABLE source_systems (
    source_system_id BIGINT PRIMARY KEY,
    issuer_code VARCHAR(100) NOT NULL,
    namespace_code VARCHAR(150) NOT NULL,
    UNIQUE (issuer_code, namespace_code)
);

CREATE TABLE customer_external_identifiers (
    customer_id UUID NOT NULL REFERENCES customers(customer_id),
    source_system_id BIGINT NOT NULL REFERENCES source_systems(source_system_id),
    tenant_key VARCHAR(100) NOT NULL,
    external_value VARCHAR(200) NOT NULL,
    PRIMARY KEY (
        customer_id,
        source_system_id,
        tenant_key,
        external_value
    ),
    UNIQUE (
        source_system_id,
        tenant_key,
        external_value
    )
);
~~~

Meaning:

- `customers.customer_id` is the stable internal identifier.
- `source_systems` describes the issuer and namespace.
- `customer_external_identifiers` maps one or more source codes to the internal profile.
- The `UNIQUE` constraint prevents an external code within the same source system and tenant from being assigned to two different customer profiles.
- The composite primary key prevents repeating the exact same link in the table.

If external codes are unique only within one object type, include the object type in the uniqueness scope or use a dedicated table as in the customer example. If one source system can issue the same string for both customer and supplier, never place a `UNIQUE` constraint lacking entity type on a shared identifier table.

In a generic design, consider how foreign keys across multiple entity types are enforced. An `entity_type` plus `entity_id` column pair in a polymorphic table cannot natively enforce standard foreign keys to multiple tables. Use separate mapping tables per entity type, or a supertype model with a shared key if appropriate.

### 5.1. One Object, Multiple Identifiers

For example, internal customer profile `customer_id = 500` can be mapped as:

| Internal Customer | Issuer/Namespace | Tenant | External Code |
|---|---|---|---|
| 500 | CRM-A / crm.customer | tenant-01 | C-001 |
| 500 | ERP-A / erp.customer | tenant-01 | 000734 |
| 500 | Partner-X / partner.buyer | tenant-01 | BUY-77 |

Three external codes reference one internal profile under confirmed matching rules. Do not conclude they share the same subject merely because names or emails look alike.

### 5.2. An External Code Can Change Over Time

Some source systems permit changing codes, reusing codes, or migrating data to a new namespace. If historical lookup is required, the mapping table can add:

- `valid_from`: when the code becomes effective;
- `valid_to`: when the code expires;
- `recorded_at`: when the system recorded the link;
- `status`: active, retired, disputed;
- `source_reference`: evidence or source record ID.

Then uniqueness rules must also consider effective time. A code may be reused in two non-overlapping periods if issuer policy permits; however, two concurrently active mappings cannot collide if the namespace guarantees uniqueness.

Non-overlapping time-range constraints may require exclusion constraints, triggers, or transactional logic depending on the DBMS. A plain `UNIQUE` constraint cannot express all temporal rules.

## 6. Identification Is Not Entity Resolution

This is a critical distinction when consolidating data across organizations.

- **Identification:** knowing which code references a record within a specific namespace.
- **Entity resolution:** determining whether two or more records represent the same real-world entity.
- **Record consolidation:** deciding how to merge data once sufficient evidence confirms records represent the same entity.

Having different codes does not prove two people are different. Sharing a name, address, or email is also insufficient to prove they are the same person.

### 6.1. Levels of Matching

Different levels of evidence can be used:

1. **Authoritative identifier match:** identical code in a namespace confirmed by the issuer as unique and non-reusable.
2. **Business-rule match:** attribute combination confirmed by the organization as sufficient for matching, such as business registration ID plus issuing country.
3. **Probabilistic match:** name, address, phone number, or other attributes indicate likelihood of being the same entity without certainty.
4. **Undetermined:** insufficient or conflicting data; keep profiles separate until further evidence arrives.

With probabilistic matching, require thresholds, review workflows, and reversibility. Never auto-merge important data solely on similar names or matching email.

### 6.2. Storing Links and Evidence

If reconciliation outcomes must be recorded, an `entity_links` or `identity_matches` table can include fields such as:

- the two records being matched;
- namespace and source code of each record;
- relationship type: `same_as`, `possible_match`, `related_to`;
- status: `proposed`, `confirmed`, `rejected`;
- method and evidence;
- confirming person or service;
- timestamp and change history.

This preserves the distinction between "two codes referencing the same profile" and "two profiles believed to be the same real-world object." Those two ideas are related yet not identical.

### 6.3. Avoiding Erroneous Merges

Before merging profiles, verify:

- do the codes share the same issuer and namespace;
- does the issuer guarantee uniqueness and non-reusability;
- do both profiles represent the same object type;
- do the data share the same timeframe and context;
- is there any conflicting evidence;
- does merging affect access rights, consent, or sensitive data;
- can it be reversed if the conclusion proves wrong.

In multi-organization environments, two units referring to the same person does not imply they are permitted to share all information about that person. Identification rules must go hand in hand with access control and data-usage purpose rules.

## 7. Identifier Types and How to Choose

### 7.1. Surrogate Keys

A surrogate key is a system-generated ID carrying no direct business meaning, such as an integer or UUID.

Appropriate when:

- a stable key independent of source codes is needed;
- multiple namespaces reference the same entity;
- business attributes can change;
- data must be integrated across multiple organizations.

Surrogate keys do not by themselves solve cross-source entity resolution. They only provide a stable identifier within the system managing that key.

### 7.2. Natural Keys

A natural key uses business-meaningful attributes for identification, such as a business registration number within a specific issuing authority and country.

Use only when verified:

- uniqueness scope;
- issuing authority and verification method;
- change or revocation rules;
- reuse rules;
- stability over time.

Email, phone number, name, and address are rarely stable natural keys across all domains. They can change, be shared, be reused, or have varying normalization rules.

### 7.3. Composite Identifiers

A composite identifier consists of multiple components, for example:

```text
(tenant_id, source_system, entity_type, external_value)
```

One component may lack uniqueness, yet the combination is confirmed unique by the issuer and business rules.

Do not confuse a composite key with an arbitrary concatenated string. If stored as a string, delimiters, encoding, normalization, and rule versioning must be handled. In a database, storing separate columns is usually easier to constrain and query.

### 7.4. UUIDs and Global Codes

UUIDs can be generated independently across many systems with negligible collision probability when using a proper algorithm. They are useful for issuing IDs without a central counter.

Nevertheless:

- UUIDs of two separate profiles do not indicate whether they represent the same real-world entity.
- UUIDs do not inherently carry issuer, ownership, or business semantics.
- UUIDs do not replace mapping tables when external codes must be preserved.
- Choose consistent version, generation, serialization, and display conventions.

If a resolvable or cross-organization shareable identifier is needed, URIs/URNs under a governed namespace convention can be used. URI resolution and entity identification remain two separate concerns.

## 8. Normalizing and Comparing Identifier Values

Two strings can look alike while differing in Unicode code points, letter casing, whitespace, or leading zeros. Conversely, two differently written strings may be considered the same code under the issuer's rules.

Before comparing, know the namespace's normalization rules.

### 8.1. Common Issues

- **Letter casing:** is `abc-01` equivalent to `ABC-01`?
- **Whitespace:** should leading/trailing whitespace be trimmed; is internal whitespace significant?
- **Unicode:** accented characters can have multiple equivalent encodings.
- **Leading zeros:** is `00123` distinct from `123`?
- **Separators:** are hyphens or dots part of the code?
- **Country and region codes:** must issuing country codes or organization types be retained?
- **Versioning:** do code formatting rules change over time?

Never automatically strip diacritics, drop leading zeros, or uppercase all values. Doing so can collapse two distinct codes into one or break reverse lookups to the source.

### 8.2. Storing Raw and Normalized Values

If the issuer permits normalization, you can store both:

- **raw_value:** the original received value verbatim;
- **normalized_value:** the value after applying confirmed normalization rules;
- **normalization_rule_version:** rule version;
- **source_payload/reference:** reference to source evidence if needed.

The raw value supports auditing and sending data back to the source system. The normalized value supports comparison. Enforce uniqueness on the normalized field within the proper namespace if business rules dictate.

### 8.3. Data Types

Identifiers should generally be stored as strings if they contain leading zeros, alphabetic characters, or are not used for arithmetic. Never store code `000123` as integer `123` and lose its original formatting.

Data types and lengths must match the contract with the issuer. If codes may grow longer than expected, manage schema expansion and validation accordingly.

## 9. Integrating Multiple Organizations and Tenants

When data crosses organizational boundaries, separate code-issuing authority, data ownership, and referencing rights.

### 9.1. One Organization with Multiple Source Systems

An enterprise may operate a CRM, ERP, support system, and commerce platform. Each system may maintain its own customer records and issue its own IDs.

Determine:

- which system is the authoritative source for each attribute;
- which codes are used for reconciliation;
- relationships among source profiles;
- how to handle a source system being retired or replaced;
- how to preserve mapping history.

You do not have to pick a single system as the authoritative source for every field. The CRM can govern contact details, the ERP can govern payment codes, and the billing system can govern legal names.

### 9.2. Multiple Organizations Sharing One Entity

One supplier can partner with multiple enterprise buyers. Each buyer may assign its own vendor code to the same real-world organization.

Example:

| Managing Organization | Namespace | Vendor Code |
|---|---|---|
| Company A | vendor-master-A | V-120 |
| Company B | vendor-master-B | SUP-88 |
| Company C | procurement-C | 00452 |

If a platform manages a shared partner directory, it can maintain one internal ID for the supplier organization and multiple code mappings per company. However, confirming those codes point to the same organization requires proper evidence; it cannot be inferred solely from similar names.

### 9.3. Tenant Isolation

In a multi-tenant architecture, one tenant's data must be separated and protected from other tenants.

An identifier may be unique only within a tenant. In that case:

- every query must apply tenant context;
- unique keys must include tenant if scope is per-tenant;
- foreign keys and queries must prevent unintended cross-tenant references;
- cache keys and integration messages must carry appropriate tenant context;
- logs and audits must record organizational scope.

Constraint example:

~~~sql
CREATE TABLE tenant_customers (
    tenant_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    external_customer_code VARCHAR(100) NOT NULL,
    PRIMARY KEY (tenant_id, customer_id),
    UNIQUE (tenant_id, external_customer_code)
);
~~~

The schema above fits when external codes are unique within a tenant and the tenant itself is the issuing namespace. If each tenant imports from multiple sources whose codes can collide, `UNIQUE` must add source system or namespace.

Tenant isolation must also be enforced at the query layer, database permissions, or row-level security if supported by the DBMS. Placing `tenant_id` in a table alone without checking every access path is insufficient.

## 10. Managing Identifier Lifecycles

Identifiers can be issued, activated, changed, revoked, expired, or reused. Model the lifecycle rather than storing only a single current value.

### 10.1. Code Changes and Replacement Codes

When a source system changes a customer code, do not silently overwrite it if the old code must remain queryable. Store the new code, effective period, and relationship to the old code.

An old code can be kept as an alias or historical identifier. APIs and reports must know which codes are accepted for lookups and which are historical only.

### 10.2. Revocation and Reuse

An issuer may revoke a code or reuse a code after some time. Distinguish:

- code that never existed;
- currently active code;
- revoked code;
- expired code;
- code reissued to another object.

If codes can be reused, never treat the bare value as a permanent identifier. Add effective timestamps, versions, or a stable source record ID.

### 10.3. Merging and Splitting Profiles

Two profiles can be confirmed as the same entity and require merging. Conversely, a combined profile may need splitting into two objects.

Record:

- old profile ID and surviving profile ID;
- reason and evidence;
- merge or split timestamp;
- how dependent relationships are migrated;
- how external identifiers are handled;
- how old IDs remain queryable;
- approving person or workflow.

Do not remove old IDs from history if other systems still reference them. An alias or redirect table can support lookups, while write rules must prevent continuing to link new records to retired profiles.

## 11. APIs and Data Contracts for Identifiers

When identifiers cross APIs, messages, or files, the contract must specify namespace and uniqueness scope.

An ambiguous payload:

~~~json
{
  "customerId": "1001"
}
~~~

The receiver does not know who issued the code, which tenant it belongs to, or whether it is an internal ID or source code.

A clearer payload:

~~~json
{
  "customer": {
    "internalId": "b4e6b0c0-0f2e-4a00-9d3f-21e3f2e9c123",
    "externalIdentifier": {
      "issuer": "company-a",
      "namespace": "crm.customer",
      "tenant": "tenant-01",
      "value": "1001"
    }
  }
}
~~~

Not every API needs to send all of these fields. If the contract already establishes tenant and issuer at the request level, repeating them inside each object may be omitted. However, the receiver must have enough context to interpret the value accurately.

### 11.1. Avoiding Field Naming Confusion

Names like `id`, `customerId`, `code`, `externalId` easily cause confusion. Explicitly define:

- internal ID vs. source ID;
- business code vs. database key;
- which namespace;
- globally unique vs. tenant-unique;
- whether changes are allowed.

Do not expose internal keys in public APIs if security or architectural evolution concerns apply. Conversely, never assume a UUID is a secret; hard-to-guess IDs do not replace access control.

### 11.2. Idempotency and Message Identifiers

In message integration, identify the event or request separately from the entity identifier. A message can carry:

- `event_id`: unique identifier of the message/event;
- `entity_id`: internal or source object identifier;
- `issuer/namespace`: scope of `entity_id`;
- `occurred_at`: timestamp when the event occurred.

An idempotency key detects whether a request or message has already been processed, preventing duplicate records on retries. Never use `customer_id` as an idempotency key for all operations because one customer can have many distinct events.

## 12. Security and Privacy

Identifiers can reveal information or enable linking data across organizations. A public business identifier may carry low sensitivity, whereas account numbers, ID document numbers, or internal user IDs can be more sensitive.

When designing:

- share only the identifiers needed for integration purposes;
- avoid embedding personal data directly into IDs;
- never use hard-to-guess IDs as an authentication mechanism;
- restrict lookup permissions on mappings between external codes and internal profiles;
- audit linking, merging, and sensitive lookup operations;
- encrypt or protect identifier values per data classification;
- define retention periods and deletion/anonymization workflows per applicable policy.

Knowing that two codes belong to the same person can itself be sensitive information. Identifier mapping tables therefore require proper access permissions rather than default read access for all services.

## 13. Verifying Identifier Design

Use the following scenarios to test the model:

1. Two organizations both issue code `C-001` to two different customers.
2. One tenant imports code `1001` from two source systems.
3. One customer simultaneously holds CRM, ERP, and partner codes.
4. A source system changes a code while old orders must still be retrievable.
5. An issuer reuses a code after a prior profile closes.
6. Two profiles share an email yet have different authoritative identifiers.
7. A message is redelivered multiple times.
8. One tenant attempts to reference another tenant's ID.
9. Two profiles are merged and later discovered to be two distinct objects.
10. Code normalization rules change and legacy values must be handled.

For each scenario, check:

- does the system identify the correct namespace and issuer;
- are unique constraints scoped accurately;
- are erroneous links or merges prevented;
- is identifier history preserved;
- can data be retrieved and reconciled against sources;
- are access rights and tenant isolation protected;
- when errors occur, can operations be corrected or safely reversed.

### 13.1. Pre-Finalization Model Checklist

- [ ] Every identifier has a defined issuer and namespace.
- [ ] Entity type and uniqueness scope are clear.
- [ ] Internal keys are separated from external codes.
- [ ] Rules for changes, revocation, and reuse are documented.
- [ ] Raw values and normalization rules are defined.
- [ ] Multiple external codes can map to one entity under clear policies.
- [ ] Entity resolution workflows carry evidence and status.
- [ ] Database constraints prevent code collisions within the proper scope.
- [ ] APIs and messages carry sufficient identification context.
- [ ] Tenant isolation, access control, and auditing are verified.

## 14. Common Mistakes

- **Assuming codes are globally unique:** a code may be unique only within one organization or namespace. Define scope before creating `UNIQUE`.
- **Using external codes as internal keys:** changes in source systems ripple across all relationships. Consider stable internal keys and mapping tables.
- **Treating UUIDs as global identity:** UUIDs produce low-collision IDs, yet do not prove two profiles represent the same real-world entity.
- **Merging profiles by name or email:** attributes can collide or change. Use matching rules and evidence.
- **Omitting tenant or source system from uniqueness scope:** two sources can issue identical values.
- **Over-normalizing:** stripping leading zeros or diacritics can mutate valid codes. Normalize only per issuer rules.
- **Overwriting old codes:** destroys historical traceability and old message reconciliation.
- **Using polymorphic tables without protecting references:** an `entity_type`/`entity_id` pair lacks native foreign keys across multiple tables.
- **Exposing mapping tables to every service:** enables linking data beyond granted permissions.
- **Using IDs as proof of access rights:** knowing an ID does not mean the caller is authorized to read or modify the object.

## 15. Conclusion

An identifier is meaningful only when you know who issued it, which namespace it belongs to, which object type it identifies, and within what scope it is unique. In multi-organization environments, the same string can be valid across many systems; one internal entity may also need to hold multiple external codes.

Separate internal keys from source identifiers when needed, store mappings with issuer and namespace, define normalization and lifecycle rules, and distinguish referencing a profile from confirming two profiles represent the same real-world entity. These rules enable safe data integration, historical traceability, and model evolution without losing semantics.

## Self-Check

1. Why is the string `C-001` insufficient to identify a customer in a multi-organization environment?
2. Distinguish issuer, namespace, and uniqueness scope with examples.
3. Why do UUIDs not solve the problem of reconciling two profiles from two CRMs?
4. A tenant imports customer codes from two source systems. Which components must the `UNIQUE` constraint include?
5. When should both `raw_value` and `normalized_value` be stored?
6. Distinguish identification, entity resolution, and record consolidation.
7. If an issuer reuses codes after profiles close, what extra data is needed to query history accurately?
8. Design a mapping table for an entity in a multi-tenant system, specifying issuer, namespace, internal key, uniqueness scope, and code-change rules.
