# Simple, Composite, and Multivalued Attributes

In the **DATABASE_DATA_MODELING** module, data modeling starts with understanding business objects, the meaning of data, and how rules are enforced. After identifying entities, the next step is to describe the characteristics that the system needs to record. Those characteristics are represented by **attributes**.

An attribute can be a single value, a structure made up of multiple components, or a collection of multiple values. Properly distinguishing these three forms helps the model accurately reflect business semantics, avoid cramming multiple pieces of information into a single field, avoid creating hard-to-control repeating structures, and choose an appropriate storage representation when transitioning to logical, document, graph, or analytical models.

This lesson focuses on three forms of attributes:

- **Simple attribute:** does not need to be decomposed into independent components within the scope of the current model.
- **Composite attribute:** can be decomposed into smaller components, each having its own distinct meaning.
- **Multivalued attribute:** an entity can have multiple values for the same type of attribute.

## 1. What does an attribute describe?

An attribute describes a characteristic of an entity or a relationship. For example, a Customer has an identifier, display name, date of birth, and contact address; an Order has a placement timestamp, status, and notes; an Order Line has a quantity and unit price at the time of purchase.

Every attribute needs a clear definition. Do not just write names like “status”, “type”, “date”, or “code”. Specify:

- What does the attribute describe in the business domain?
- In what unit, format, and domain is the value measured or represented?
- Is the value required, and if missing, what does that mean?
- Can an entity have one value or multiple values?
- Into which components can the value be decomposed?
- Who or which system creates and updates the value?
- Does the value change over time, need history tracking, or only require the current state?
- Is the attribute source data recorded directly or a value derived from other data?

For example, the “shipping address” attribute needs to specify whether it is the address at the time the order was placed or the current address in the customer profile. If past orders must always be delivered to the address confirmed at purchase time, this value must be stored as a snapshot attached to the order. Merely referencing the customer's current address can alter historical meaning.

### Attributes and value domains

A **value domain** is the set of allowed values according to business semantics. A domain is not merely a technical type like VARCHAR or INTEGER. For example:

| Attribute | Business domain | Possible implementation type |
|---|---|---|
| Order quantity | Integer greater than 0 | INTEGER with CHECK |
| Date of birth | Valid date, possibly unknown | DATE, allowing NULL if business permits |
| Country code | Code belonging to the chosen code set | CHAR/VARCHAR with rules and reference table |
| Monetary price | Non-negative amount, paired with a currency | DECIMAL and currency_code |
| Order status | A defined set of statuses | ENUM, VARCHAR with CHECK, or lookup table |
| Rating score | Number within the published rating scale | SMALLINT/DECIMAL with CHECK |

The technical data type must be expressive enough to represent the business domain without losing information. Conversely, a type that is too permissive without constraints can allow meaningless data. For example, an INTEGER `quantity` column can still accept negative numbers if there is no CHECK constraint or corresponding protection logic.

## 2. Simple attributes

A **simple attribute** is an attribute treated as a single value that does not need to be split into independent components within the scope and purpose of the model. Examples include quantity, color code from an agreed catalog, creation date, status, or identifier.

“Simple” does not mean the value consists of only one character or cannot be physically parsed. A phone number consists of a country code, area code, and subscriber number, but if the system only validates and sends messages using the full normalized number, it can be treated as a simple attribute in that model. If the business needs to search by country code, analyze by region, or store an extension, the phone number may require a more detailed structure.

Simplicity depends on usage. An attribute can be simple in one model yet composite in another. Therefore, you should not apply a rigid decomposition rule merely because a value can be split into substrings.

### Signs an attribute should be treated as simple

- Users typically read, write, and validate the entire value as a single unit.
- Internal parts have no independent business rules or lifecycle.
- There is no need to filter, sort, validate, or report separately on individual components.
- Splitting the value does not make the model clearer or provide necessary capabilities.

Examples:

| Entity | Simple attribute | Meaning |
|---|---|---|
| Order | placed_at | Timestamp when the order was placed |
| Order line | quantity | Quantity of the product on the line |
| Product | sku | Product code within defined rules |
| Customer | display_name | Display name used as a single string |
| Review | rating_score | Rating score according to the specified scale |

A simple attribute still requires a data type, value domain, requiredness, and normalization rules. For instance, an SKU code is a string rather than a number if leading zeros are significant. You should not convert a code like “00125” into the number 125 and lose its original formatting.

## 3. Composite attributes

A **composite attribute** is an attribute that can be divided into components with distinct meanings. Each component can be used, validated, or presented independently.

For example, an address can consist of:

- Street number and street name.
- Ward/commune.
- District.
- Province/city.
- Postal code.
- Country.

A person's name can consist of given name, middle name, and family name depending on naming conventions. A time interval can consist of a start timestamp and an end timestamp. Contact information can consist of channel, value, and usage label.

~~~mermaid
flowchart TD
    A["Shipping address"] --> B["Street number, street name"]
    A --> C["Ward / commune"]
    A --> D["District"]
    A --> E["Province / city"]
    A --> F["Postal code"]
    A --> G["Country"]
~~~

When modeling, a composite attribute can be represented as a group of components in a conceptual diagram. Components can be further decomposed if there is practical meaning and need. However, you should not break things down into overly granular pieces if those parts are never used individually.

### When should you decompose?

You should decompose when one or more of the following conditions apply:

- Users need to search or filter by a component.
- Each component has its own format, value domain, or validation rules.
- A component can be updated independently.
- The system needs to standardize or reconcile individual parts against a standard catalog.
- Reports need to aggregate by component.
- Integrating systems exchange individual components per a data contract.

For example, if you need to filter customers by province/city to allocate sales territories, storing the entire address in a single string will cause difficulties. Separating province/city into a component with a standardized definition supports filtering and reconciliation much better.

### When should you keep it as a single value?

If an address is only stored to print on shipping labels, there is no need to filter by parts, and the system has no standard address catalog, a free-form address string may be appropriate. If later you need analysis by province/city, the team can add standardized components or an address parsing pipeline.

Do not confuse a “composite attribute” with “multiple independent attributes”. If an entity has a billing address and a shipping address, those may be two composite attributes serving different roles. If a person has multiple shipping addresses, that is instead a multivalued attribute or a set of Address entities related to that person. You must distinguish the internal structure of a single value from the number of allowed values.

### Components with independent meaning and entity boundaries

A component does not automatically become an entity just because it has multiple fields. An address can be a value object attached to a customer; however, if the address is shared, has verification status, effective-date history, or needs to be referenced independently, it may need to be modeled as an entity.

Ask: does the component have its own identity, an independent lifecycle, relationships with multiple entities, and a need to be referenced elsewhere? If not, keeping it as part of a composite value is usually simpler.

## 4. Multivalued attributes

A **multivalued attribute** is an attribute for which an entity can have multiple values of the same type. For example:

- A customer has multiple phone numbers.
- An employee has multiple certifications.
- A product has multiple images.
- An article has multiple tags.
- A user belongs to multiple groups.

In conceptual diagrams, a multivalued attribute is often denoted by a double oval in certain ERD notations. The visual notation may vary across tools, but the meaning remains that an entity has a collection of values for that attribute.

~~~mermaid
flowchart TD
    C["Customer"] --> N["Display name"]
    C --> P[["Phone numbers (multivalued)"]]
    C --> E["Primary email"]
~~~

The rules for the collection of values must be clearly defined:

- What is the maximum number of values allowed?
- Is at least one value required?
- Are duplicate values allowed?
- Is there an ordering or not?
- Is there a primary/preferred value?
- Does each value have its own label or status?
- Does the value have an expiration/effective period or change history?

For example, a customer may have multiple phone numbers, and each number may have a type (mobile, landline), label (personal, work), verification status, and verification timestamp. In that case, the “phone number” attribute is not just a list of strings. An associative entity such as `ContactPoint` may be needed to manage each value and its metadata.

### Do not confuse multivalued attributes with composite attributes

The two concepts answer two different questions:

- **Composite:** what components make up a single value?
- **Multivalued:** how many values of the same type can an entity have?

For example, a single address is composite because it has a street number, street, city, and country. A customer having multiple addresses is multivalued because there are multiple distinct addresses. A customer having multiple addresses, where each address consists of multiple components, is a multivalued attribute where each element is itself a composite value.

~~~mermaid
flowchart TD
    C["Customer"] --> A1["Address 1"]
    C --> A2["Address 2"]
    C --> A3["Address 3"]
    A1 --> S1["Street number / street"]
    A1 --> D1["District / city"]
    A1 --> K1["Country"]
    A2 --> S2["Street number / street"]
    A2 --> D2["District / city"]
    A2 --> K2["Country"]
~~~

## 5. Representing the three attribute forms in conceptual models

When building an ERD, represent attributes according to their meaning, not the chosen storage mechanism:

| Attribute form | How to describe | Example |
|---|---|---|
| Simple | An attribute name and value domain | quantity, placed_at, rating_score |
| Composite | A parent attribute and child components | address consisting of street, ward, city, country |
| Multivalued | Notation or annotation indicating a collection of values | phone_numbers, certifications, product_images |

An entity can simultaneously have all three forms. For example, a Customer has `customer_code` (simple), `legal_name` (composite depending on naming conventions), and `contact_points` (multivalued). The model must explicitly state which attributes are required, which can be missing, and the constraints on each component or element.

For a composite value, determine which components are mandatory and which are optional. For instance, an international address may not have a postal code in some countries. Do not put NOT NULL on every component just because one specific sample address has all fields filled.

For a multivalued attribute, document cardinality (minimum/maximum count), uniqueness rules, and ordering if the business requires it. If a list has a priority order, model the position or primary flag explicitly; do not rely on arbitrary query result ordering.

## 6. Transitioning from conceptual to relational models

In a relational model, each attribute must be mapped into one or more columns or tables depending on its structure and rules.

### Simple attributes

A simple attribute is typically mapped to a single column with an appropriate data type:

~~~sql
CREATE TABLE customer (
    customer_id BIGINT PRIMARY KEY,
    customer_code VARCHAR(40) NOT NULL,
    display_name VARCHAR(160) NOT NULL,
    birth_date DATE,
    CONSTRAINT uq_customer_code UNIQUE (customer_code)
);
~~~

Here `customer_code`, `display_name`, and `birth_date` are simple columns. Data type, nullability, and constraints must reflect the business value domain. For example, `birth_date` can allow NULL if a date of birth is not required.

### Composite attributes

A composite attribute is typically decomposed into multiple columns if its components need to be queried or controlled separately:

~~~sql
CREATE TABLE customer_address (
    address_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    address_type VARCHAR(20) NOT NULL,
    street_line VARCHAR(200) NOT NULL,
    ward VARCHAR(120),
    district VARCHAR(120),
    city VARCHAR(120) NOT NULL,
    postal_code VARCHAR(20),
    country_code CHAR(2) NOT NULL,
    CONSTRAINT fk_address_customer
        FOREIGN KEY (customer_id) REFERENCES customer(customer_id)
);
~~~

In this example, address is modeled as a table because a customer can have multiple addresses. Inside each address, the components are represented as columns. If each customer has only one address and the address has no separate lifecycle, the address columns can be placed directly in the customer table. If the address is a shipping snapshot, they can reside in the order structure to preserve history.

### Multivalued attributes

In a normalized relational model, you should not store a list of independent values in a single delimited-string column such as `"090..., 091..., 028..."`. Instead, create a separate table with one row per value:

~~~sql
CREATE TABLE customer_phone (
    customer_id BIGINT NOT NULL,
    phone_number VARCHAR(32) NOT NULL,
    phone_type VARCHAR(20) NOT NULL,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    verified_at TIMESTAMP,
    CONSTRAINT pk_customer_phone
        PRIMARY KEY (customer_id, phone_number),
    CONSTRAINT fk_phone_customer
        FOREIGN KEY (customer_id) REFERENCES customer(customer_id)
);
~~~

This table represents a one-to-many relationship from customer to phone numbers. The composite primary key prevents the same number from appearing repeatedly for one customer under the assumptions of the example. If phone numbers can be shared or have multiple historical records for the same number, the key and temporal model must be adjusted accordingly. If each customer can only have one primary number, an additional mechanism may be needed to enforce this rule, such as a unique filtered/partial index depending on the DBMS or a design that stores the primary identifier explicitly.

### Why shouldn't you cram a list into a single column?

A column like `phones = "090...,091..."` creates difficulties when:

- Finding all customers with a specific number.
- Ensuring a number is not duplicated within the same customer.
- Attaching type, verification status, or expiration to each number.
- Updating or deleting a single number without string parsing.
- Joining with lookup tables or phone verification systems.
- Counting the number of phone numbers per customer.

If the list is merely auxiliary data read/written together with an aggregate and does not require constraints or querying individual elements, an array structure in a document model may be appropriate. The choice must follow usage patterns and consistency requirements.

## 7. Representation in document, graph, and analytical models

The same business attribute can be represented differently across model families. The semantics must remain consistent even when storage structures differ.

| Model family | Simple attribute | Composite attribute | Multivalued attribute |
|---|---|---|---|
| Relational | Single column | Multiple columns or value-object table | Child table with FK |
| Document | Scalar field | Nested object | Array or nested collection |
| Graph | Node/edge property | Multiple properties or structured value node | Multiple edges or set of related nodes |
| Analytical | Dimension/fact column | Component columns by grain | Bridge table or multivalued dimension |

### Document example

A customer document can represent address and phone numbers as follows:

~~~json
{
  "customerId": "cus_8f2a",
  "displayName": "Nguyen An",
  "address": {
    "streetLine": "12 Le Loi",
    "city": "Da Nang",
    "countryCode": "VN"
  },
  "phones": [
    {
      "number": "+84901234567",
      "type": "MOBILE",
      "isPrimary": true,
      "verified": true
    },
    {
      "number": "+84236345678",
      "type": "WORK",
      "isPrimary": false,
      "verified": false
    }
  ]
}
~~~

The `address` object represents a composite attribute. The `phones` array represents a multivalued attribute, in which each element is itself a multi-field structure. This approach is convenient if phone numbers are read and updated together with the customer profile. If individual numbers need to be managed independently, referenced by multiple entities, or have a long history, they can be separated into their own collection.

### Graph example

In a graph model, a customer can connect to multiple contact points via edges. Each contact point can be a node if it requires identity, verification, or sharing across profiles:

~~~mermaid
flowchart LR
    C["(:Customer)"] -->|HAS_CONTACT| P1["(:ContactPoint)"]
    C -->|HAS_CONTACT| P2["(:ContactPoint)"]
    P1 --> T1["type: MOBILE"]
    P2 --> T2["type: WORK"]
~~~

If contact points are just simple attributes, storing many edges or nodes may introduce unnecessary complexity. Only turn a value into a node when it has relational significance or its own lifecycle.

### Analytical model example

When analyzing customers by city, address components must be standardized into a dimension with consistent definitions. When analyzing by multiple certifications or multiple interests, a fact or dimension may require a bridge table to avoid row duplication during joins. The grain of the fact and the allocation of measures must be defined if one record links to multiple values.

For example, if an order is tagged with three campaign tags, joining the order table directly with the tag table can triple-count revenue. The analytical model must define whether revenue is allocated proportionally, counted in full for each tag, or attributed solely to a primary tag.

## 8. Rules to define for an attribute

Classifying an attribute as simple, composite, or multivalued is only the first step. Each attribute needs the following rules:

| Rule | Question | Example |
|---|---|---|
| Requiredness | Can the value be missing? | Phone number optional, customer code required |
| Cardinality | What is the minimum/maximum count of values? | Customer has 0..N contact numbers |
| Uniqueness | Can values repeat? | Verified email may be unique per policy |
| Ordering | Do the values have a meaningful order? | Prioritized list of addresses |
| Unit | In what unit is the value measured? | Weight in grams or kilograms |
| Precision | How many digits are needed? | Price uses DECIMAL per currency rules |
| Normalization | Are there casing, whitespace, or area-code rules? | Country code uppercase per chosen code set |
| History | Must old values and effective times be stored? | Confirmed shipping address |
| Data source | Who is authorized to create or modify it? | Product code issued by the catalog system |

### Null, empty, and unknown

Do not treat NULL, empty string, and default values as equivalent:

- **NULL:** no value recorded, unknown, or not applicable depending on convention.
- **Empty string:** a string value with length zero.
- **Default value:** a value assigned when no input is provided; must have a clear business meaning.
- **Not applicable:** a semantic state; can be represented by NULL with a convention, a dedicated status, or a more suitable model.

For example, a NULL contract end date may mean the contract has not ended. If you need to distinguish “end date unknown” from “contract has no end date”, a single nullable field may not be enough; an additional status or rule is required.

For multivalued attributes, an empty set can differ from an unknown set. If a customer has confirmed they have no secondary phone number, that is an empty set. If the data has not yet been collected, the unknown state may need to be distinguished. The model must reflect this distinction when the business cares about it.

### Ordering and primary value

A multivalued collection may inherently be unordered. If the UI needs sorting, determine whether that order is a business order or purely a display order. If there is a primary value, define the rule for selecting a single primary value or allowing no primary value yet.

Do not rely on array element position or returned row order if the system makes no ordering guarantees. Store `position`, `priority`, or `is_primary` when needed.

## 9. Common modeling mistakes

1. **Combining multiple values into one string:** loses the ability to validate, search, and update individual values.
2. **Over-decomposing:** creating columns for components with no independent meaning, making the model hard to read and data entry cumbersome.
3. **Treating every nested structure as an entity:** adding IDs and tables for data that only lives with its owner and has no separate lifecycle.
4. **Treating every list as a simple multivalued attribute:** ignoring per-element metadata such as type, status, expiration, and ordering.
5. **Ignoring cardinality:** failing to specify minimum/maximum counts, leading to inconsistent UIs and data.
6. **Using technical types instead of business domains:** for example, storing codes with leading zeros as numbers, or storing money as FLOAT.
7. **Equating NULL with empty:** preventing the system from distinguishing unknown, not applicable, and having no value.
8. **Not storing snapshots:** altering historical meaning when source attributes change.
9. **Duplicating information without a source of truth:** for example, storing addresses in multiple places without defining which is canonical and which is a snapshot.
10. **Ignoring element uniqueness rules:** allowing a phone number or certification to repeat within the same entity when business rules forbid it.

## 10. Process for analyzing an attribute

When encountering an attribute in business requirements, follow these steps in order:

1. Identify the entity or relationship that the attribute describes.
2. Write a short definition and valid/invalid examples.
3. Determine whether the attribute is simple, composite, or multivalued given the model's goals.
4. If composite, list the components and the reason they need separate access.
5. If multivalued, define cardinality, duplicates, ordering, primary value, and element metadata.
6. Define value domain, unit, precision, normalization, and requiredness.
7. Identify source data, derived data, creation source, and history-tracking needs.
8. Check edge cases and related rules.
9. Choose an appropriate logical representation; defer physical types and optimizations until workload is known.
10. Document the decision so others can review and verify it.

### Attribute dictionary template

| Documentation field | Content |
|---|---|
| Attribute name | Standard name, consistent across the team |
| Definition | Exact business meaning |
| Owner | Entity or relationship owning the attribute |
| Form | Simple, composite, or multivalued |
| Components | List of sub-parts if composite |
| Cardinality | Minimum and maximum count if multivalued |
| Value domain | Valid values, units, and format |
| Requiredness | Required, optional, or status-dependent |
| Rules | Uniqueness, ordering, default, validation |
| Source | System or role authorized to update |
| History | Whether changes and effective times are stored |
| Implementation notes | Reserved for logical/physical phases, not dictating the definition |

## 11. Practice exercises and evaluation criteria

### Exercise 1 — Customer profile

A customer has a legal name, display name, date of birth, multiple phone numbers, and multiple addresses. One address can be marked as default.

Classify each attribute as simple, composite, or multivalued. Define the components of the address, cardinality of phone numbers and addresses, the rule for choosing the default address, and which data requires a snapshot when creating an order.

### Exercise 2 — Product

A product has an SKU, name, dimensions, color, multiple images, and multiple certifications. Dimensions consist of length, width, height, and unit of measurement.

Determine:

- Which attributes are simple?
- Are dimensions a composite attribute?
- Is color single-valued or multivalued according to business needs?
- Do images and certifications have their own metadata?
- When should a certification become an entity with its own identity?

### Exercise 3 — Relational model design

From the customer profile in Exercise 1, propose tables and foreign keys to store multiple addresses and phone numbers. Write at least three constraints: no duplicate phone numbers within a customer, at most one active default address, and country code belonging to a valid domain.

### Exercise 4 — Transitioning to document and analytical models

Represent the same customer profile as a document. Then propose a way to analyze customers by province/city and by phone number type. Explain why document storage is suitable or unsuitable for each query.

### Self-evaluation rubric

| Criterion | Meets expectations when |
|---|---|
| Classification | Correctly distinguishes internal structure from number of values |
| Semantics | Defines attributes and value domains clearly |
| Cardinality | Specifies minimum/maximum counts and duplication rules |
| Entity boundaries | Only creates separate entities when there is independent identity, lifecycle, or relationships |
| Mapping | Correctly maps to columns, child tables, objects, or arrays |
| Integrity | Includes appropriate constraints and validation mechanisms |
| Evolution | Considers history, snapshots, data sources, and business changes |

A good attribute model does more than store values. It clearly expresses what a value represents, how many elements are allowed, which components need separate access, and how data changes over time. By distinguishing simple, composite, and multivalued attributes, a team can build a clear logical model, choose an appropriate representation for each database family, and validate data against business rules.
