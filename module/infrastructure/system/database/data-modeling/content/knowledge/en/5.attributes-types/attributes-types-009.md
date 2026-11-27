# Enums, Lookup Tables, and Extensible Value Domains

Many data attributes only accept values from a defined set. An order status may be `PENDING`, `CONFIRMED`, or `CANCELLED`; a delivery method may be standard delivery, express delivery, or store pickup. This value set must be controlled to prevent misspelled data, convention violations, or values the system no longer understands.

There are several ways to represent a value set: enums in source code, DBMS enum types, `CHECK` constraints, or lookup/reference tables. Each approach has different costs and evolution capabilities. A value set that stays fixed throughout the application lifecycle may fit an enum; a catalog managed by the business that frequently adds or deprecates values usually needs extensible reference data.

Within the scope of **DATABASE_DATA_MODELING**, this lesson distinguishes closed value sets from extensible value domains, showing how to choose a structure, protect data integrity, and evolve catalogs without breaking historical data or consumers.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish programming-language enums, DBMS enums, `CHECK` constraints, and lookup tables.
- Identify when a value domain should be closed and when it needs to be extensible through data or configuration.
- Design stable value codes, display labels, active statuses, and appropriate foreign keys.
- Choose how to handle deprecated values, unknown values, and new values coming from external systems.
- Plan migrations, data seeding, contract versioning, and testing when a value domain changes.

## 1. What Is a Value Domain?

A **value domain** defines the set of valid values that an attribute can accept. A domain can be described by a data type, numeric range, format pattern, enumerated value set, or a set of reference records.

Examples:

| Attribute | Value domain | Example rule |
|---|---|---|
| `quantity` | Positive integer | `quantity >= 1` |
| `currency_code` | Supported currency code | Must belong to a valid currency catalog |
| `order_status` | Order status set | `PENDING`, `CONFIRMED`, `SHIPPED`, `CANCELLED` |
| `delivery_method` | Delivery method | `STANDARD`, `EXPRESS`, `PICKUP`, and added methods |
| `customer_type` | Customer classification | `PERSON`, `ORGANIZATION` if the domain is defined as closed |

A value domain helps multiple components interpret the same data by the same rules. If an attribute is described as order status yet the system accepts arbitrary strings such as `done`, `finish`, `completed`, or `complete`, filtering, statistics, and business processing become inconsistent.

### 1.1. Closed Sets and Extensible Value Domains

- **Closed set:** a list of values determined by design that only changes through controlled software or schema changes, such as internal statuses with fixed business transitions.
- **Extensible domain:** a list that can be extended, disabled, or configured per organization, market, or time period without necessarily modifying source code and deploying the application for every new value.

Whether a domain is closed or open is a property of its governance process, not just a feature of the storage engine. A lookup table can be governed very strictly and remain nearly closed; a source-code enum can be updated frequently across releases. The key questions are who has authority to make changes, how changes occur, and how consumers react.

### 1.2. Distinguishing Value, Code, and Display Label

A value should have a stable code and a separate display label.

| Component | Example | Purpose |
|---|---|---|
| Code | `EXPRESS` | Stable storage, integration, and comparison |
| Label | `Express delivery` | Display to users |
| Description | `Delivered within a priority time window` | Explain the meaning |
| Sort order | `20` | Ordering in UI or reports |
| Active flag | `true` | Indicates whether the value can be selected for new records |

Do not use a display label as the stored code. Labels can change wording, be translated into other languages, or be adjusted for UI reasons. If you store `Express delivery` across every transaction table, renaming the label to `Priority express delivery` requires modifying historical data and can break integrations. Storing `EXPRESS` lets labels change while the identifier's meaning remains stable.

## 2. Enums in Source Code

A programming-language enum represents a set of named constants. It helps the compiler and IDE catch invalid values, clarifies processing branches, and avoids free-form strings in logic.

Java example:

```java
public enum OrderStatus {
    PENDING,
    CONFIRMED,
    SHIPPED,
    CANCELLED
}
```

Using the enum:

```java
public boolean canShip(OrderStatus status) {
    return status == OrderStatus.CONFIRMED;
}
```

### 2.1. Advantages

- The value set is expressed explicitly in source code.
- The compiler detects many typos or missing processing branches.
- Behavior, attributes, or methods can be attached to each value when appropriate.
- Easy to search and refactor in an IDE.
- Well-suited for value sets that rarely change and are controlled by the development team.

### 2.2. Limitations When a Domain Needs to Expand

When adding a constant to an enum, the application typically needs to be recompiled and redeployed. If a business unit needs to add delivery methods or customer types itself without waiting for a release, pure source-code enums do not meet that requirement well.

Enums can also cause issues when reading data newer than the application version. For example, the database or another service has already written `RETURNED`, while an older instance only knows `PENDING`, `CONFIRMED`, `SHIPPED`, `CANCELLED`. Parsing the enum may throw an error or cause messages to be rejected.

### 2.3. Storing Enums in the Database: Use Names, Not Ordinals

If a Java enum is stored in a numeric column by position (`ORDINAL`), inserting or reordering constants can make old data take on a different meaning. For example, the value `1` originally meant `CONFIRMED`, yet after prepending a constant to the list, `1` may be interpreted as a different status.

When using source-code enums with JPA, usually store stable names:

```java
@Enumerated(EnumType.STRING)
@Column(name = "status", nullable = false, length = 20)
private OrderStatus status;
```

Enum names are also part of the data contract. Renaming a constant can prevent the application from reading rows stored under the old name. If you need to rename one, consider keeping the stored code stable and mapping the code to the enum, or running a controlled migration.

## 3. DBMS Enums and CHECK Constraints

Some database management systems support native enum types. PostgreSQL lets you create an enum type:

```sql
CREATE TYPE order_status AS ENUM (
    'PENDING',
    'CONFIRMED',
    'SHIPPED',
    'CANCELLED'
);

CREATE TABLE sales_order (
    order_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    status order_status NOT NULL DEFAULT 'PENDING'
);
```

The DBMS validates values right when data is written. This is useful when multiple applications write to the same schema and the value set must be enforced at the database layer.

### 3.1. Advantages and Limitations of DBMS Enums

Advantages:

- Invalid values are rejected by the database.
- The column makes the value domain explicit at the schema level.
- The same type can be reused across multiple tables if the meaning is truly identical.

Limitations:

- The ability to modify and remove values depends on the DBMS; some changes require special migrations.
- Enums are tied to a specific DBMS schema and tooling, reducing portability.
- Inconvenient when values carry metadata such as multilingual labels, sort order, descriptions, effective dates, or per-tenant configuration.
- If the catalog is user-administered, requiring a schema change every time a value is added is unsuitable.

### 3.2. CHECK Constraints

For a small, stable value set, `CHECK` is a simple choice:

```sql
CREATE TABLE sales_order (
    order_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('PENDING', 'CONFIRMED', 'SHIPPED', 'CANCELLED'))
);
```

`CHECK` fits closed domains and simple conditions such as positive quantities, percentages from 0 to 100, or statuses belonging to a small list.

When adding a new status, the constraint must be updated via migration. For large tables or systems requiring zero-downtime deployment, account for the ordering of schema and application changes: the database must accept the new value before the application version starts writing it.

### 3.3. CHECK Does Not Replace a State Machine

A constraint checks whether a value belongs to the valid domain. It does not by itself verify whether a status transition is valid in context.

For example, `PENDING`, `CONFIRMED`, `SHIPPED`, and `CANCELLED` are all valid values. However, business rules might only allow:

- `PENDING` → `CONFIRMED` or `CANCELLED`.
- `CONFIRMED` → `SHIPPED` or `CANCELLED`.
- `SHIPPED` cannot transition back to `PENDING`.

To protect transitions, you need business logic, transactions, optimistic locking, or an equivalent control mechanism. The fact that values belong to an enum or lookup table does not mean every transition between them is valid.

## 4. Lookup / Reference Tables

A lookup table stores each valid value as its own record. Business tables reference the catalog code via a foreign key.

Example of a delivery method table:

```sql
CREATE TABLE delivery_method (
    delivery_method_code VARCHAR(30) PRIMARY KEY,
    display_name VARCHAR(100) NOT NULL,
    description TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO delivery_method
    (delivery_method_code, display_name, sort_order)
VALUES
    ('STANDARD', 'Standard delivery', 10),
    ('EXPRESS', 'Express delivery', 20),
    ('PICKUP', 'Store pickup', 30);

CREATE TABLE sales_order (
    order_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    delivery_method_code VARCHAR(30) NOT NULL
        REFERENCES delivery_method(delivery_method_code)
);
```

When adding a new method, you can insert a row into `delivery_method` without altering the structure of `sales_order`. The foreign key guarantees every order references an existing code.

### 4.1. Advantages

- Values can be added through controlled data operations without changing the schema for each new value.
- Metadata can be stored: labels, descriptions, display order, grouping, effective dates, active status, and governance source.
- Multilingual labels can be supported through a separate translation table.
- Foreign keys protect referential integrity.
- Suitable for catalogs configured by business teams, administrators, or tenants.

### 4.2. Costs and Risks

- Requires catalog lifecycle governance, permissions for adding/editing/deprecating, and an approval workflow.
- May require joins or caching when reading display labels.
- If a catalog code is changed or reused, historical data can be misinterpreted.
- Adding a value to the table does not guarantee every application knows how to process the new value.
- If a catalog varies by tenant or over time, scope and effective validity must be included in keys/constraints.

### 4.3. Stable Code, Mutable Label

Treat `delivery_method_code` as a stable code once published. If the display name needs changing, update only `display_name` or translations. Never reuse an old code for a different meaning.

If `EXPRESS` is discontinued, mark `is_active = FALSE` to prevent new selections. Older orders still retain the `EXPRESS` code and can still join to the catalog for historical display. Hard-deleting the catalog row would violate foreign keys or strip historical data of meaning.

A foreign key only confirms that the code exists; it does not check `is_active` or effective dates. When creating a new transaction, the application must verify that the value is currently selectable within the same transaction or use an appropriate database mechanism if multiple write paths exist. Conversely, when reading old transactions, displaying deprecated values must still be allowed. If a document must preserve the exact label at issuance time, store a label snapshot or catalog version on the document; joining to the current label might show the renamed label.

### 4.4. Multilingual Catalogs

If labels must be displayed by language, avoid creating one column per language in the main table when the number of languages can grow. Extract a translation table:

```sql
CREATE TABLE delivery_method_translation (
    delivery_method_code VARCHAR(30) NOT NULL
        REFERENCES delivery_method(delivery_method_code),
    locale VARCHAR(10) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    description TEXT,
    PRIMARY KEY (delivery_method_code, locale)
);
```

The code remains constant for integrations and storage; `locale` determines the displayed label. Define a fallback when a translation is missing, such as using the system default language.

## 5. Extensible Value Domains and Governance Rules

A catalog is considered extensible when new values can be added through a defined process without modifying every consumer at once. Achieving this requires governing more than a single table.

### 5.1. Who Can Add Values?

Identify the owner responsible for the catalog:

- The development team manages technical catalogs that rarely change.
- Business teams manage product categories, delivery methods, or refund reasons.
- Tenant administrators manage organization-specific values.
- External systems supply codes; the internal system stores the source code and maps it to a canonical code.

Management permissions should be tied to approval workflows, auditing, and conflict checks. Do not let arbitrary users create custom codes freely if those codes affect reporting, routing, or billing logic.

### 5.2. Catalog Codes Need Rules

A code should be:

- Unique within a defined namespace.
- Stable once used in transactions or integrations.
- Independent of display language.
- Never reused for a different meaning after deprecation.
- Governed by rules for casing, whitespace, and allowed characters.
- Covered by a synchronization policy if issued by an external system.

For example, `EXPRESS` and `express` should not accidentally become two distinct values simply due to collation or string comparison rules. Normalize codes at data ingestion boundaries and apply appropriate constraints.

### 5.3. Deprecate Instead of Deleting

Commonly useful columns in a catalog:

| Column | Meaning |
|---|---|
| `code` | Stable referenced code |
| `display_name` | Default label |
| `description` | Explanation of meaning |
| `is_active` | Whether it can be selected for new transactions |
| `valid_from`, `valid_to` | Time window during which the value is effective |
| `sort_order` | Display order |
| `source` | Issuing source or governance owner |
| `created_at`, `updated_at` | Administrative timestamps |

`is_active = FALSE` does not mean every historical record referencing that value is invalid. It usually only prevents new creation. If a value is valid only within a time range, distinguish the transaction timestamp from the current timestamp when validating.

### 5.4. Global Values vs. Per-Tenant Values

If each tenant has its own catalog, determine whether codes are globally unique or unique per tenant.

```sql
CREATE TABLE tenant_delivery_method (
    tenant_id UUID NOT NULL,
    code VARCHAR(30) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (tenant_id, code)
);
```

The primary key `(tenant_id, code)` lets two tenants use the same code with different labels or policies. Transaction tables must store `tenant_id` alongside `delivery_method_code` and use a composite foreign key so one tenant cannot reference another tenant's delivery method.

## 6. Unknown, Not Applicable, and Other Values

The following cases have distinct meanings and should not be collapsed into a single `UNKNOWN` string:

- **NULL:** no value present or unknown per the column's semantics.
- **NOT_APPLICABLE:** the attribute does not apply to that record.
- **UNKNOWN:** a value is needed yet could not be determined.
- **OTHER:** a value exists yet is not among the listed specific options.
- **UNSPECIFIED:** the producer did not supply the information; different from the system verifying that it is unknown.

Not every domain needs all of these states. Define their business meaning and reporting behavior before adding them. If using `OTHER`, you may need an extra description field to capture the specific value; otherwise information is lost.

For external integrations, do not automatically map every unrecognized code to `OTHER` if doing so distorts meaning. You can store the raw code, mark it unmapped, and route it to a review queue to update the catalog or mapping.

## 7. Hybrid Model: Code Enum Combined with a Lookup Table

Some domains require both properties: core logic needs type safety, yet labels or configuration need to be data-managed. A hybrid model can be used, provided its limits are clearly understood.

Example with order status:

- A Java enum defines the statuses the application knows and has behavior for.
- An `order_status_catalog` table stores codes, labels, sort order, and active status.
- A database constraint or foreign key ensures only allowed codes are stored.
- When adding a new status, both the catalog and the application must be updated if processing logic depends on the enum.

```java
public enum OrderStatus {
    PENDING,
    CONFIRMED,
    SHIPPED,
    CANCELLED
}
```

```sql
CREATE TABLE order_status_catalog (
    code VARCHAR(20) PRIMARY KEY,
    display_name VARCHAR(80) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE sales_order (
    order_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    status_code VARCHAR(20) NOT NULL
        REFERENCES order_status_catalog(code)
);
```

This model fits when the set of statuses is controlled by software releases while labels, display order, or selectable status need configuration. It does not turn status into a freely extensible domain: if you add `RETURNED` while application code does not know how to handle state transitions, refunds, or inventory, adding a catalog row alone is not enough.

If new values must be permitted without deploying the application, use a value-object/string code validated against the catalog and design consumers capable of handling unknown values. Only do this when the business genuinely allows consumers to handle values generically without value-specific logic.

## 8. Comparing Representation Approaches

| Representation | Where values are validated | Adding new values | Metadata and governance | Best suited when |
|---|---|---|---|---|
| Source-code enum | Compiler and application | Usually requires an application release | Metadata can live in code; hard for business self-service | Small, closed set where logic is tied to each value |
| DBMS enum | Database | Requires schema migration; flexibility depends on DBMS | Limited metadata beyond value names | Closed set requiring direct DBMS protection |
| `CHECK` constraint | Database | Update constraint via migration | Inconvenient for labels, translations, and data governance | Small, stable set or simple domain conditions |
| Lookup/reference table | Foreign key and catalog data | Insert catalog record | Strong for labels, descriptions, validity, tenants, and audit | Catalog is extensible or carries metadata |
| Hybrid model | Application and database | May require updating both code and catalog | Combines type safety and metadata | Core logic is fixed, metadata needs configuration |

There is no single best representation for every attribute. One system may use an enum for internal statuses, a lookup table for delivery methods, and `CHECK` for positive quantities.

## 9. Process for Changing a Value Domain

Adding, changing, or deprecating a value can affect data, applications, APIs, events, reports, and integrations. Manage it like a data contract change.

### 9.1. Adding a New Value

For domains backed by a lookup table:

1. Define the code, meaning, issuing source, scope, and effective date.
2. Verify the code does not already exist and does not conflict with other namespaces.
3. Add the catalog record via migration/seed or an authorized administrative workflow.
4. Update the application and consumers if the new value requires dedicated processing logic.
5. Update API/event schemas or documentation if the code is exposed externally.
6. Test new data, existing data, and older consumer versions.

With enums or `CHECK`, the database must accept the new value before the application starts writing it. Deployment ordering must account for older application instances still running.

### 9.2. Changing Labels or Descriptions

If only presentation changes, keep the code unchanged. Update the label, translations, or description; check caches and screens using them. Historical transactions do not need edits if the code's meaning has not changed.

### 9.3. Deprecating a Value

Typically, mark the value inactive and block new selection while still allowing historical data to be read. If the value must be replaced, create an intentional mapping or conversion rule; do not immediately overwrite the old code with the new code across all records if the two meanings are not strictly equivalent.

### 9.4. Changing Meaning

If the business meaning of a code changes significantly, create a new code. Reusing an old code causes historical records to be interpreted under the new meaning. If two codes must be merged or mapped, store the replacement relationship and effective date.

### 9.5. Renaming a Code

Changing a code can impact foreign keys, integrated data, and emitted events. If the code has already been published, prefer keeping the old code as an alias or mapping during a transition period. If renaming is mandatory, run an ordered migration, update consumers, and retain a mapping history from the old code to the new code.

## 10. API Contracts and Compatibility

When an API returns:

```json
{
  "orderId": "ord_7305",
  "status": "CONFIRMED"
}
```

`status` is part of the contract. Consumers may use a switch/case or their own enum. When the producer adds `RETURN_REQUESTED`, older consumers might:

- Reject parsing the payload because their enum lacks the new value.
- Fall into a default branch and process it incorrectly.
- Ignore the new status while still displaying the order.

Producers must publish a compatibility policy. Consumers should handle unknown values in a way matched to their risk level: controlled rejection, storing the raw code, displaying a generic status, or quarantining the message. Never assume by default that any new status equals `PENDING` or `OTHER`.

If a domain must expand independently of consumer releases, the contract should define the field as a code string backed by a governed catalog and require consumers to handle unknown values per policy. If each value carries distinct business logic, adding a value remains a software change and requires version coordination.

## 11. Data Seeding, Migrations, and Deployment Environments

Lookup tables usually require initial data. Distinguish:

- **Schema migration:** creating tables, foreign keys, indexes, and constraints.
- **Reference-data seed:** inserting initial standard codes.
- **Runtime administration:** catalog changes performed by authorized users after the system is running.

Seeding must be idempotent. Re-running it must not create duplicate records or overwrite administered labels unless intended. Controlled upserts can be used, but you must clearly decide which fields are code-managed and which are user-managed.

PostgreSQL example:

```sql
INSERT INTO delivery_method
    (delivery_method_code, display_name, sort_order, is_active)
VALUES
    ('STANDARD', 'Standard delivery', 10, TRUE),
    ('EXPRESS', 'Express delivery', 20, TRUE)
ON CONFLICT (delivery_method_code) DO NOTHING;
```

`DO NOTHING` avoids overwriting catalog data that has been edited. If a release needs to update standard descriptions, write a dedicated migration explicitly stating which fields are updated and why.

In multi-version application deployments:

1. Deploy the database change allowing the new code.
2. Deploy application versions capable of reading both old and new values.
3. Enable writing the new value once consumers are ready.
4. Monitor parse errors, quarantined messages, and record counts per code.
5. Remove support for old codes only when no data or consumer still depends on them.

With lookup tables, adding data is often separate from schema migrations, yet consumers still must be prepared if the new value carries new semantics.

## 12. Testing and Quality Control

A solid value domain requires testing across multiple layers:

| Layer | What to test |
|---|---|
| Domain/application | Reject invalid codes; handle each status and allowed transition correctly |
| Database | `CHECK`, enum, or FK rejects nonexistent values; prevent deleting referenced catalog entries against policy |
| API/event | Schema validation, unknown values, older and newer versions |
| Migration/seed | Deploy on empty databases and populated databases; run seeds repeatedly safely |
| Reporting | Group and filter by stable code; display labels do not alter aggregations |
| Operations | Cache refresh works; catalog changes have proper auditing and permissions |

Recommended test cases:

- Write a valid code.
- Write a nonexistent code.
- Add a new code and read it with a prepared application version.
- Deprecate a code while still reading historical records referencing it.
- Change a label without altering the code or aggregation results.
- Consumer receives an unknown code and handles it per policy.
- Two administrators simultaneously create the same code; a unique constraint must prevent duplicates.
- Seed runs multiple times without creating duplicate data or unintentionally overwriting configuration.

## 13. Common Mistakes

| Mistake | Consequence | Remedy |
|---|---|---|
| Using free-form strings for rule-governed value sets | Typos and code variants appear in data | Use an enum, `CHECK`, or appropriate lookup table |
| Storing enum ordinals | Adding/reordering constants shifts the meaning of old data | Store stable codes/names, avoid ordinals |
| Using display labels as codes | Renaming labels or translating languages alters data | Separate code from label |
| Deleting referenced catalog entries | Loss of history or FK violations | Mark inactive; retain the catalog record |
| Adding a code to a lookup table when consumers do not understand it | Business logic fails to handle the new value | Coordinate consumer updates or design explicit unknown handling |
| Using enums for user-configurable catalogs | Every minor change requires a release | Use a reference table with permissions and auditing |
| Using a lookup table for statuses needing strict logic without transition checks | Arbitrary status transitions occur despite valid codes | Build a state machine and enforce transitions |
| Reusing a deprecated code for a new meaning | Historical data is misinterpreted | Never reuse codes; create a new code and map if needed |
| Seed overwrites configured labels | Business-administered edits are lost | Partition field ownership and write explicit migrations |

## 14. Process for Choosing a Representation

When designing an attribute with a value set, ask:

1. Is the value set closed and determined by software logic?
2. Does each value have distinct behavior in code?
3. Who has permission to add, relabel, or deprecate values?
4. Are descriptions, translations, sort order, grouping, tenant scope, or effective dates needed?
5. Must historical data continue referencing deprecated values?
6. Might API/event consumers encounter values newer than their version?
7. Must the database serve as the last line of defense rejecting invalid values?

Selection guidelines:

- Choose a **source-code enum** when the set is small, stable, and each value is tied to specific logic.
- Choose a **DBMS enum or CHECK** when the database must protect a closed domain with minimal metadata.
- Choose a **lookup/reference table** when values can be added or deprecated as data, or need metadata, permissions, multilingual labels, or tenant scope.
- Choose a **hybrid model** when core logic requires type safety yet labels/configuration must be data-managed. Define clearly whether adding values requires a code release.

## 15. Design Checklist

- [ ] Value domain and meaning of each code are clearly defined.
- [ ] Decided whether the value set is closed or extensible, along with the rationale.
- [ ] Stable codes are separated from display labels and translations.
- [ ] Uniqueness scope of codes (global, issuer, tenant, or context) is defined.
- [ ] Database/application mechanisms protect valid values.
- [ ] Deprecated values continue to support historical data.
- [ ] Status transition rules are enforced separately from domain checks.
- [ ] Policies exist for NULL, UNKNOWN, OTHER, and unknown values at consumers.
- [ ] Data seeding is idempotent and does not unintentionally overwrite configuration.
- [ ] Migrations are ordered compatibly with running application versions.
- [ ] APIs/events publish how new codes are handled.
- [ ] Catalog changes are audited and tested for old, new, and invalid values.

## Summary

Enums suit closed value sets where logic needs type safety. DBMS enums and `CHECK` constraints let the database reject out-of-domain values, though every change typically requires a schema migration. Lookup tables fit extensible value domains, domains with metadata, or business-administered catalogs. A hybrid model combines code enums with a lookup table when core logic is stable yet labels and configuration need flexibility.

Whichever option you choose, use stable codes, separate display labels, define uniqueness scope clearly, and preserve historical data. Adding a value to a catalog does not automatically make every consumer understand it; API/event compatibility and transition logic must be managed separately.

## Key Terms to Remember

| Term | Meaning |
|---|---|
| Value Domain | The set of valid values an attribute can accept |
| Closed Set | A strictly controlled value set changed via releases or migrations |
| Extensible Domain | A value domain that can be extended or configured via a governance process |
| Enum | An enumerated type of a set of named constants |
| CHECK Constraint | A constraint verifying a condition on a row's data |
| Lookup Table | A table storing catalog values referenced by business data |
| Reference Data | Shared data used to classify or standardize business data |
| Surrogate Code | A stable code used in storage/integration, separate from display labels |
| Deprecation | Marking a value as discouraged for new use while historical data may still read it |
| State Machine | A model of states and the valid transitions between them |
| Seed Data | Initial data required when deploying a schema or new environment |
| Backward Compatibility | The ability for newer or older versions to continue interacting under an agreed contract |
