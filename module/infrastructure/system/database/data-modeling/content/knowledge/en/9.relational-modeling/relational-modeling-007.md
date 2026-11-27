# Representing Multivalued and Composite Attributes

When translating business requirements into a relational model, two statements very commonly appear:

- “A customer has **multiple phone numbers**.”
- “An address consists of **street/house number, district/region, city, postal code, and country**.”

The first statement describes a **multivalued attribute**; the second describes a **composite attribute**. They address **two orthogonal axes**: *how many values does an entity have?* and *what parts make up a single value?* An attribute can be both multivalued **and** composite at the same time—for example, a customer has multiple addresses, and each address consists of multiple components.

This lesson in the **Relational Modeling** chapter of the **DATABASE_DATA_MODELING** module focuses on recognizing semantics accurately, converting conceptual models into tables, keys, and constraints, normalizing repeating value groups, designing indexes, and comparing with document, graph, or analytical models when needed.

## 1. Distinguishing with a Business Example

Suppose a sales system stores customer information:

~~~text
Customer 101: Lan
  Display name: "Nguyễn Thị Lan"
  Phone numbers:
    +84901234567  (mobile, primary)
    +842838221100 (work)
  Shipping addresses:
    Address 1:
      Address line: "12 Nguyễn Huệ"
      City: "TP. Hồ Chí Minh"
      Country: "VN"
    Address 2:
      Address line: "8 Trần Phú"
      City: "Đà Nẵng"
      Country: "VN"
~~~

There are three independent observations:

1. **Phone number is multivalued:** a customer can have 0, 1, or many numbers; each number can have a label and a “primary number” status.
2. **Address is composite:** each address has multiple subfields with distinct meanings and rules.
3. **The list of addresses is a multivalued composite structure:** a customer can have multiple address *tuples*, and the components of one tuple must be kept **together**.

| Concept | Example | Nature | Questions to Ask |
| --- | --- | --- | --- |
| Single-valued attribute | Date of birth (on current profile) | At most one value per entity | Is a value mandatory? |
| Multivalued attribute | Contact phone numbers | A set or list of values per subject | Maximum count? Duplicates allowed? Ordered? |
| Composite attribute | A postal address | One value composed of multiple parts | Which parts need lookup, validation, or independent updates? |
| Composite and multivalued | Shipping addresses | Multiple structured value tuples | Which group of fields belongs to the same address? |
| Structured attribute that is an entity | An OrderLine with product, quantity, and price | Has its own identity/relationships/lifecycle | Should it be separated into an entity instead of treated as an attribute? |

In Chen-style ERDs, multivalued attributes are typically drawn with a **double ellipse**; composite attributes are drawn as **an attribute connected to its component attributes**. Notations differ across tools, so cardinality, optionality, and identity constraints still must be written out explicitly in prose.

## 2. Multivalued Attributes: Not “One String Containing Many Elements”

### 2.1. Definition and Allowed Cardinality

For customer \(c\), let \(Phones(c)\) be that person's set of valid phone numbers. If the business allows multiple numbers, then:

- \( |Phones(c)| = 0 \): customer has not provided a number, **if the business allows it**.
- \( |Phones(c)| = 1 \): has one number.
- \( |Phones(c)| \ge 2 \): has multiple numbers.

“Set” is a common conceptual mental model; in a real system you must decide **whether to track order, label, source, timestamp, and duplicate records**. For instance, phone numbers might be ordered by contact priority; priority order is **its own attribute** on each association, never inferred from physical row position in a table.

Multiplicity can be described using ranges:

| Business Multiplicity | Meaning | Example |
| --- | --- | --- |
| 0..1 | Optional, at most one | Personal tax ID when not everyone has one |
| 1..1 | Mandatory, exactly one | Currency code of a valid monetary amount |
| 0..N | Optional, may have many | Contact phone numbers |
| 1..N | At least one, may have many | A **confirmed** order must have at least one order line |
| 0..K | May have many, capped at K | At most three emergency contacts if policy specifies |

Multiplicity must be defined **by object and point in time**. A draft order may have 0 lines; the same order once confirmed may require 1 or more lines.

### 2.2. Three Easily Confused Storage Approaches

Suppose we store phone numbers in the `customers` table.

**Approach A — pack into a string:**

~~~text
customer_id | phones
101         | "+84901234567,+842838221100"
~~~

Easy to enter initially, yet hard to validate each element, prevent duplicates, attach labels, and search accurately. If data contains the delimiter inside a value, string splitting breaks even more easily.

**Approach B — add repeating columns:**

~~~text
customer_id | phone_1      | phone_2       | phone_3
101         | +84901234567 | +842838221100  | NULL
~~~

This design imposes a hard limit on count, requires schema changes when `phone_4` appears, makes uniqueness checks across all slots awkward, and complicates search queries. Multiple columns sharing the same meaning differing only by sequence number are a sign to revisit the model.

**Approach C — separate into a child relation:**

~~~text
customers
  101 | Nguyễn Thị Lan

customer_phones
  101 | +84901234567  | MOBILE | primary
  101 | +842838221100 | WORK   | secondary
~~~

Each row represents **one value in the context of a customer**. A composite key or surrogate key with a unique constraint prevents duplicates, while metadata columns express labels, priority, and status.

Splitting out a table is the common choice for a multivalued attribute that needs **filtering, constraints, independent updates, or separate referencing**. It does not imply that every parent–child pair must be deleted together; that is a separate decision about lifecycle and retention policy.

## 3. Composite Attributes: Decomposing Components Based on Usage

A composite attribute represents **a single value with internal structure**. For example, `postal_address` has:

~~~text
PostalAddress
├── recipient_name
├── address_line1
├── address_line2 (optional)
├── locality / city
├── region (country-dependent)
├── postal_code (country-dependent)
└── country_code
~~~

If you need to look up by country, validate postal codes, generate shipping labels, or aggregate by city, these components carry distinct semantics and can be stored as separate columns.

### 3.1. Having Structure Does Not Automatically Require a Separate Table

If a customer has **exactly one registered address** and all fields are read and updated together with the profile, you can store:

~~~sql
CREATE TABLE registered_customers (
    customer_id     BIGINT PRIMARY KEY,
    customer_name   TEXT NOT NULL,
    address_line1   TEXT NOT NULL,
    address_line2   TEXT,
    city            TEXT NOT NULL,
    region          TEXT,
    postal_code     TEXT,
    country_code    VARCHAR(2) NOT NULL
                    CHECK (country_code ~ '^[A-Z]{2}$')
);
~~~

The address columns describe **one address** of **one customer**. They do not automatically violate normalization merely because several columns belong to one logical group.

Splitting addresses into a separate table is better when addresses:

- have **multiple records** per customer;
- have **their own identity** or are referenced by multiple objects;
- have **their own lifecycle** such as verification, locking, or history;
- have their own relationship to regions/administrative units;
- require update permissions or workflows different from the customer profile.

### 3.2. Avoid Over-Splitting Components

Splitting `full_name` into `first_name` and `last_name` does not always fit naming conventions worldwide. Nor do addresses in every country follow the same structure of house number, ward, district, and postal code.

Practical rule: **split when a component has business meaning, requires separate validation, or is frequently searched/updated independently**. Keep a free-form field like `address_line1` when data cannot be reliably decomposed. Avoid enforcing local address constraints globally across international customers.

Postal codes should use a **character string**, not an integer: they can contain leading zeros, letters, spaces, or hyphens depending on the country.

### 3.3. When Composite Fields Form an Indivisible Value

A monetary amount is typically understood as a pair **(numeric value, currency code)**. The two fields can live on the same row, yet they must **travel together** and an amount is meaningless without its currency.

~~~sql
CREATE TABLE product_prices (
    product_id   BIGINT PRIMARY KEY,
    amount       NUMERIC(14, 2) NOT NULL CHECK (amount >= 0),
    currency     VARCHAR(3) NOT NULL
                 CHECK (currency ~ '^[A-Z]{3}$')
);
~~~

If price is optional in another model, decide whether both components must be NULL together or non-NULL together. One way to enforce simultaneous presence/absence is:

~~~sql
-- Example when both amount and currency are allowed to be NULL:
CHECK ((amount IS NULL) = (currency IS NULL))
~~~

This constraint prevents having an amount without a currency or vice versa; it **does not replace** currency domain checks, precision rules, or the system's pricing policy.

## 4. Attributes That Are Both Multivalued and Composite

“A customer has multiple addresses” is a classic example. You cannot turn each component into an independent array:

~~~json
{
  "streets": ["12 Nguyễn Huệ", "8 Trần Phú"],
  "cities": ["TP. Hồ Chí Minh", "Đà Nẵng"]
}
~~~

Because adding, deleting, or sorting one array while forgetting the other will mismatch streets with cities. Each **address tuple** must be stored as a cohesive structured unit:

~~~json
{
  "addresses": [
    {
      "line1": "12 Nguyễn Huệ",
      "city": "TP. Hồ Chí Minh",
      "country": "VN"
    },
    {
      "line1": "8 Trần Phú",
      "city": "Đà Nẵng",
      "country": "VN"
    }
  ]
}
~~~

In the relational model, the standard representation is **one row per address**, where each row contains its component columns and a key pointing to the customer.

This highlights an important **grouping constraint**: you must know which components belong to **the same occurrence** of the composite value. Never split into independent `customer_streets` and `customer_cities` tables without a linking key identifying each address tuple.

## 5. Designing a PostgreSQL Schema for Customers, Phones, and Addresses

The following example makes explicit assumptions:

- Each customer can have **0..N phone numbers**.
- For a given customer, the same normalized number appears **at most once**.
- Each customer has **at most one primary phone number**, though they may not have chosen one yet.
- Each customer can have **0..N addresses**; each address has its own identifier and multiple component fields.
- An address has kind `SHIPPING`, `BILLING`, or `OTHER`. For **each address kind** of a customer, **at most one default address** is allowed.
- A phone number can be **shared by multiple customers** (family, switchboard); do not place a system-wide UNIQUE constraint on the number.

### 5.1. Tables and Constraints

~~~sql
-- PostgreSQL. BY DEFAULT allows assigning fixed IDs in learning examples.
CREATE TABLE customers (
    customer_id  BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    display_name TEXT NOT NULL
                 CHECK (btrim(display_name) <> '')
);

CREATE TABLE customer_phones (
    customer_id BIGINT NOT NULL
                REFERENCES customers(customer_id) ON DELETE CASCADE,
    phone_e164  TEXT NOT NULL
                CHECK (phone_e164 ~ '^\+[1-9][0-9]{1,14}$'),
    phone_kind  TEXT NOT NULL DEFAULT 'OTHER'
                CHECK (phone_kind IN ('MOBILE', 'WORK', 'HOME', 'OTHER')),
    is_primary  BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (customer_id, phone_e164)
);

CREATE UNIQUE INDEX uq_customer_one_primary_phone
ON customer_phones (customer_id)
WHERE is_primary;

CREATE TABLE customer_addresses (
    address_id     BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id    BIGINT NOT NULL
                   REFERENCES customers(customer_id) ON DELETE CASCADE,
    address_kind   TEXT NOT NULL
                   CHECK (address_kind IN ('SHIPPING', 'BILLING', 'OTHER')),
    recipient_name TEXT NOT NULL
                   CHECK (btrim(recipient_name) <> ''),
    address_line1  TEXT NOT NULL
                   CHECK (btrim(address_line1) <> ''),
    address_line2  TEXT,
    city           TEXT NOT NULL
                   CHECK (btrim(city) <> ''),
    region         TEXT,
    postal_code    TEXT,
    country_code   VARCHAR(2) NOT NULL
                   CHECK (country_code ~ '^[A-Z]{2}$'),
    is_default     BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE UNIQUE INDEX uq_customer_default_address_by_kind
ON customer_addresses (customer_id, address_kind)
WHERE is_default;

CREATE INDEX idx_customer_addresses_customer_kind
ON customer_addresses (customer_id, address_kind);
~~~

Analysis:

| Mechanism | What It Protects | What It Does **Not** Protect |
| --- | --- | --- |
| PK `customers.customer_id` | Each customer has a unique identifier | Whether a customer is required to have a phone |
| PK `customer_phones(customer_id, phone_e164)` | No duplicate number for the same customer | Does not forbid the same number belonging to multiple customers |
| FK `customer_phones.customer_id` | No orphan phone records | Whether a primary number must exist when a customer is active |
| Unique index with `WHERE is_primary` | At most one primary number per customer | **At least one** primary number |
| PK `customer_addresses.address_id` | Each address record has its own identifier | Whether two identical physical addresses can duplicate |
| Unique index `(customer_id, address_kind)` when `is_default` | At most one default address **per kind** | Whether a customer is required to have a default address |
| Component `CHECK` constraints | Type codes, basic format, non-empty required fields | Verifying real phone reachability or deliverable mail addresses |

The phone regex only validates an **approximate E.164 shape**: a leading `+`, syntactically valid digits, and bounded total length. It does not verify that the number is allocated, active, or matches a specific country's numbering plan. Contact verification workflows may require OTPs, verification statuses, and separate history.

`ON DELETE CASCADE` in this example reflects a policy: when **physically deleting a customer profile**, dependent contact points are deleted along with it. This is **not a mandatory choice** for all systems. If addresses/phone numbers must serve audits or legal records, decide on retention, anonymization, or delete restrictions according to business rules.

### 5.2. Sample Data and Queries

~~~sql
INSERT INTO customers (customer_id, display_name)
VALUES (101, 'Nguyễn Thị Lan');

INSERT INTO customer_phones
    (customer_id, phone_e164, phone_kind, is_primary)
VALUES
    (101, '+84901234567', 'MOBILE', TRUE),
    (101, '+842838221100', 'WORK', FALSE);

INSERT INTO customer_addresses
    (address_id, customer_id, address_kind, recipient_name,
     address_line1, city, country_code, is_default)
VALUES
    (501, 101, 'SHIPPING', 'Nguyễn Thị Lan',
     '12 Nguyễn Huệ', 'TP. Hồ Chí Minh', 'VN', TRUE),
    (502, 101, 'SHIPPING', 'Nguyễn Thị Lan',
     '8 Trần Phú', 'Đà Nẵng', 'VN', FALSE);
~~~

Retrieve a customer's phone numbers:

~~~sql
SELECT phone_e164, phone_kind, is_primary
FROM customer_phones
WHERE customer_id = 101
ORDER BY is_primary DESC, phone_e164;
~~~

Retrieve the default shipping address:

~~~sql
SELECT address_id, recipient_name, address_line1,
       city, region, postal_code, country_code
FROM customer_addresses
WHERE customer_id = 101
  AND address_kind = 'SHIPPING'
  AND is_default;
~~~

Find customers with a specific phone number:

~~~sql
SELECT c.customer_id, c.display_name
FROM customers AS c
JOIN customer_phones AS p ON p.customer_id = c.customer_id
WHERE p.phone_e164 = '+84901234567';
~~~

Because the primary key of `customer_phones` starts with `customer_id`, it efficiently supports looking up phone numbers for **one customer**. If you frequently look up by **phone number first**, consider an inverted index:

~~~sql
CREATE INDEX idx_customer_phones_by_phone
ON customer_phones (phone_e164, customer_id);
~~~

There is no need to create an extra index on `customer_id` alone in `customer_phones` if the composite primary key `(customer_id, phone_e164)` already serves those queries. Evaluate indexes from real queries and `EXPLAIN`, because extra indexes also increase write overhead.

### 5.3. Switching the Primary Phone Number Consistently

With the **at most one primary number** constraint, to switch the primary flag to another existing number, a transaction can clear the old flag first and then set the new flag:

~~~sql
BEGIN;

-- Serialize primary-number changes for the same customer,
-- provided all update paths follow this protocol.
SELECT customer_id
FROM customers
WHERE customer_id = 101
FOR UPDATE;

UPDATE customer_phones
SET is_primary = FALSE
WHERE customer_id = 101 AND is_primary;

UPDATE customer_phones
SET is_primary = TRUE
WHERE customer_id = 101
  AND phone_e164 = '+842838221100';

-- The application must verify that the second UPDATE affected exactly one row.
COMMIT;
~~~

If the target number does not exist, the second UPDATE affects **0 rows**, potentially leaving no primary number. Always verify affected row counts and state conditions, and **rollback** if the operation fails business rules. Locking the customer row serializes cooperating update flows; if any writer bypasses that protocol, another consistency guard is required.

If the business demands that **every activated customer has at least one primary number**, the unique index above **is not sufficient**: it enforces the maximum, not the minimum. An “at least one child row satisfying a condition” rule is a **cross-table/multi-row** constraint, typically requiring a structural adjustment, state transition workflow, and suitable transactional validation.

## 6. Recognizing Relationships with Their Own Attributes

A simple repeating value can often be stored as `(owner_id, value)`, but when **repeating records** carry multiple attributes, relationships, or lifecycles, consider an associative entity model.

### 6.1. Interests or Tags from a Shared Catalog

Suppose each product has multiple tags and a tag is assigned to multiple products. This is a **many-to-many** relationship, not a tag string on Product:

~~~sql
CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    name       TEXT NOT NULL
);

CREATE TABLE tags (
    tag_id BIGINT PRIMARY KEY,
    tag_name TEXT NOT NULL UNIQUE
);

CREATE TABLE product_tags (
    product_id BIGINT NOT NULL REFERENCES products(product_id),
    tag_id     BIGINT NOT NULL REFERENCES tags(tag_id),
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (product_id, tag_id)
);

CREATE INDEX idx_product_tags_tag_product
ON product_tags (tag_id, product_id);
~~~

`product_tags` records **the tag assignment**; `assigned_at` is an attribute of that association. `tags` allows governing tag names and sharing the same tag identifier across multiple products.

If in reality they are just free-form text keywords without a shared catalog, a `product_keywords(product_id, keyword)` table may suffice. Choose the structure based on semantics and query needs, rather than assuming every list requires a shared lookup table.

### 6.2. Order Lines Are Not Just an “Array of Products”

An order has multiple lines; each line contains quantity, locked-in unit price, discount, and potentially the same product appearing on multiple lines depending on context.

~~~sql
CREATE TABLE order_lines (
    order_id    BIGINT NOT NULL,
    line_no     INTEGER NOT NULL CHECK (line_no > 0),
    product_id  BIGINT NOT NULL REFERENCES products(product_id),
    quantity    INTEGER NOT NULL CHECK (quantity > 0),
    unit_price  NUMERIC(14, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

This illustrative table omits the Orders table so no FK is declared on `order_id`; in a complete schema it must have an FK to the corresponding Order. The key `(order_id, line_no)` represents line position **within the order**. Using only `(order_id, product_id)` assumes each product appears at most once per order—which not every system enforces.

The `unit_price` attribute belongs to the **transaction**, and should not be replaced by the product's current price. A repeating structured occurrence with its own history usually deserves to be modeled as a **detail entity**, not merely a multivalued attribute.

## 7. Avoiding Row Multiplication When Querying Multiple Multivalued Attributes

A customer has **2 phones** and **2 addresses**. If you JOIN both child tables and then count, one customer can produce **2 × 2 = 4 rows**:

~~~sql
SELECT c.customer_id, p.phone_e164, a.address_id
FROM customers AS c
LEFT JOIN customer_phones AS p
  ON p.customer_id = c.customer_id
LEFT JOIN customer_addresses AS a
  ON a.customer_id = c.customer_id
WHERE c.customer_id = 101;
~~~

This is a **Cartesian combination of independent elements** from two sets, not an indication that the customer has four phone numbers or four addresses. Computing `COUNT(p.phone_e164)` over this JOIN would yield the wrong count.

### 7.1. Count Each Relationship Separately

~~~sql
SELECT c.customer_id, c.display_name,
       (SELECT COUNT(*)
        FROM customer_phones AS p
        WHERE p.customer_id = c.customer_id) AS phone_count,
       (SELECT COUNT(*)
        FROM customer_addresses AS a
        WHERE a.customer_id = c.customer_id) AS address_count
FROM customers AS c
WHERE c.customer_id = 101;
-- 2 phone numbers, 2 addresses.
~~~

Correlated subqueries, pre-aggregating before joining, or `EXISTS` checks are usually much clearer when inspecting independent child sets. `COUNT(DISTINCT ...)` can patch certain counts, yet it cannot substitute for defining the right **data grain**.

### 7.2. Returning Document-Shaped Results at the Read Layer

An API needing one customer record along with two nested lists can aggregate each set independently first:

~~~sql
SELECT c.customer_id, c.display_name,
       COALESCE(p.phones, '[]'::jsonb) AS phones,
       COALESCE(a.addresses, '[]'::jsonb) AS addresses
FROM customers AS c
LEFT JOIN LATERAL (
    SELECT jsonb_agg(
               jsonb_build_object(
                   'number', ph.phone_e164,
                   'kind', ph.phone_kind,
                   'isPrimary', ph.is_primary
               )
               ORDER BY ph.phone_e164
           ) AS phones
    FROM customer_phones AS ph
    WHERE ph.customer_id = c.customer_id
) AS p ON TRUE
LEFT JOIN LATERAL (
    SELECT jsonb_agg(
               jsonb_build_object(
                   'id', ad.address_id,
                   'line1', ad.address_line1,
                   'city', ad.city,
                   'country', ad.country_code
               )
               ORDER BY ad.address_id
           ) AS addresses
    FROM customer_addresses AS ad
    WHERE ad.customer_id = c.customer_id
) AS a ON TRUE
WHERE c.customer_id = 101;
~~~

Here `jsonb_agg` is a **query output formatting step** for the application, without requiring you to alter how data is stored in the database. Each set is aggregated independently, avoiding multiplying the two child tables together.

## 8. Connection to Normalization and Functional Dependencies

### 8.1. Understanding First Normal Form (1NF) Accurately

In introductions to the relational model, 1NF is commonly described as cells holding **atomic values relative to the chosen domain** and having no repeating column groups. Accordingly, a table with `phone_1, phone_2, phone_3` or a string packing multiple numbers usually signals a model that does not cleanly express a **one-to-many relationship**.

However, “atomic” **depends on the domain and supported operations**. In modern SQL systems, `ARRAY`, `JSON`, or composite types can act as **a single typed value** stored in one cell. Avoid mechanically claiming “all JSON/ARRAY violates 1NF” without stating the relational model context and usage. More practical questions are:

- Do you need to **filter or join** by individual elements?
- Do you need **FK, UNIQUE, CHECK, or indexes** at the element level?
- Do you need to **update a single element** independently or track separate history?
- Do you need to represent **one-to-many/many-to-many** and enforce cardinality bounds?
- Is the composite data genuinely **one value**, or is it hiding multiple entities?

If the answers lean toward relational operations on elements, child tables usually offer clearer integrity enforcement and querying.

### 8.2. Functional Dependencies and Keys

In the `customers` table, we expect:

~~~text
customer_id → display_name
~~~

In `customer_phones`, once a normalized number appears at most once per customer:

~~~text
(customer_id, phone_e164) → phone_kind, is_primary
~~~

There is **no** functional dependency `customer_id → phone_e164`, because one customer can have multiple numbers. Stuffing `phone_e164` into a single customer row as a single attribute breaks alignment with business multiplicity.

For `customer_addresses`, we can use:

~~~text
address_id → customer_id, address_kind, recipient_name,
             address_line1, city, region, postal_code,
             country_code, is_default
~~~

Do not assume **(customer_id, address_line1, city)** is a unique key: there may be two different address kinds/versions or two address records intentionally sharing display fields. Only pick a natural key when it is truly stable and guaranteed unique by rules.

### 8.3. When Two Multivalued Attribute Sets Are Independent

Suppose a system stores **multiple phone numbers** and **multiple certificates** for an employee. The two sets are independent, with no pairwise relationship linking each phone to each certificate. Cramming everything into one table produces:

~~~text
employee_id | phone | certificate
7           | P1    | C1
7           | P1    | C2
7           | P2    | C1
7           | P2    | C2
~~~

This Cartesian-product table creates redundant data. Deleting certificate C2 requires deleting two rows; adding a new phone number may require duplicating every certificate.

This relates to **multivalued dependencies** and the practical reason for separating independent relations, connected to **Fourth Normal Form (4NF)**. The proper representation is:

~~~text
employee_phones(employee_id, phone)
employee_certificates(employee_id, certificate_id)
~~~

Conversely, if each phone number genuinely ties to **a specific verification certificate**, there is a relationship between the two and they cannot be separated arbitrarily. Normalization must be grounded in **true business dependencies**, not merely the presence of multiple columns.

## 9. Optionality, NULL, Empty Lists, and History

### 9.1. Having No Child Row Differs from Having a Child Row with NULL

If a customer **has no phone numbers**, normally the `customer_phones` table simply has no corresponding rows. Do not insert:

~~~text
customer_id=101, phone_e164=NULL
~~~

and treat it as “an unknown number”, especially when keys and constraints already specify that each row represents **a valid number**.

States that may need to be distinguished:

- **Not provided:** no row exists; you can track follow-up request status separately.
- **Not applicable:** business confirms the subject does not need this information.
- **Unverified:** a row exists with a value and a dedicated `verification_status` field.
- **Deactivated:** retain the historical row or add `valid_to`, rather than erasing audit traces.

State clearly whether the system permits 0 numbers/addresses and at which lifecycle stages. If an ACTIVE status requires a verified contact number, that is a **cross-table, state-dependent** condition, not merely `NOT NULL` on the child table.

### 9.2. Values Changing Over Time

Phone numbers, shipping addresses, and recipients can change. If you must know **which number was valid at time t**, a temporal model is needed:

~~~sql
-- Illustrating one approach to storing history of phone usage periods.
CREATE TABLE customer_phone_periods (
    period_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    phone_e164 TEXT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to   TIMESTAMPTZ,
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);
~~~

This example only checks that each row's interval is valid; **it does not yet forbid overlapping intervals** for the same customer/number. If the business requires a number to have only one active period at any point in time, add interval overlap prevention via the DBMS's native mechanism (such as an exclusion constraint in PostgreSQL) or synchronized transactions.

A **shipping address used in an order** typically needs to be stored as a **transaction snapshot** or reference an **immutable address version**. If you only point to the customer's “current” address, a later profile edit can rewrite the historical truth of where an order was shipped.

### 9.3. Minimum Cardinality Is a Set-Level Rule

`UNIQUE ... WHERE is_primary` only caps **at most one primary number**; it does not require **having a primary number**. Likewise, the FK from `customer_phones` to `customers` only ensures each number belongs to an existing customer, **not** that every customer has at least one number.

When the business mandates a minimum **1..N**, define the exact scope (e.g., only for activated accounts) and use a reliable mechanism: adjust structure to check on the same row where appropriate, enforce inside transactional write workflows with end-of-transaction checks, or use constraint triggers carefully designed for inserts, updates, deletes, and concurrency.

Deleting the last phone number or removing the default address can also leave data in violation, even if the record was valid when initially created.

## 10. ARRAY/JSON, Child Table, or Embedded Columns?

Modern DBMSs can store lists and objects in **a single column**. That can be a sensible option depending on the case.

| Criterion | Relational Child Table | ARRAY/JSON in One Column | Component Columns on Same Table |
| --- | --- | --- | --- |
| Representing 0..N values | Natural, one row per value | Natural inside an array | Usually requires repeating columns or fixed cap |
| Single-valued composite attribute | Possible, but adds table/JOIN | Stored as an object | **Very suitable** when structure is stable |
| FK to individual elements | Standard FK | Usually requires custom checking | Can use FK if components are columns |
| Element-level uniqueness | PK/UNIQUE | Depends on data type and logic | Awkward if elements span multiple columns |
| Querying/aggregating by element | JOIN, GROUP BY, index | JSON/ARRAY functions and specialized indexes | Direct column filtering |
| Updating a single element | UPDATE/DELETE target row | Technology-specific document/array update | UPDATE column |
| Child schema evolution | ALTER table to add fields | More flexible, requires logical schema management | ALTER table to add fields |
| Optimizing whole-aggregate reads | Requires JOIN/aggregation | Reads a single document | Reads one row |

Example JSON document in PostgreSQL:

~~~sql
CREATE TABLE customer_preferences (
    customer_id BIGINT PRIMARY KEY REFERENCES customers(customer_id),
    settings JSONB NOT NULL DEFAULT '{}'::jsonb
);

INSERT INTO customer_preferences (customer_id, settings)
VALUES (101, '{"notifications": {"email": true, "sms": false},
               "theme": "dark"}'::jsonb);
~~~

A small **configuration group read together with few cross-element constraints** can be a great fit for JSONB. By contrast, a list of phone numbers used for contacting, verification, searching, uniqueness enforcement, and independent history usually benefits from being separated into a child relation.

If you choose JSONB or ARRAY for phone numbers, explicitly design schema validation, duplicate-element checks, number normalization, concurrent updates, search indexes, and a migration path to a relational table if requirements evolve.

## 11. The Same Requirement Across Document, Graph, and Analytical Models

**Business semantics** do not change when switching storage technology:

| Model | Multivalued | Composite | Points to Verify |
| --- | --- | --- | --- |
| **Relational** | 1–N child table or N–N junction table | Same-row columns or structured table | PK/FK, subject-scoped UNIQUE, multiplicity, transactions |
| **Document** | Array of elements | Object with subfields | Schema validation, element duplicates, document size, atomic updates |
| **Graph** | Multiple edges to contact/address nodes | Node properties or address nodes | Edge types, multiplicity, identity, preventing duplicate edges |
| **Analytics/Warehouse** | Bridge between entity and multiple categories | Dimension of address/region components | Fact grain, risk of metric multiplication when joining multiple child tables |

### 11.1. Document with an Array of Objects

~~~json
{
  "customerId": 101,
  "name": "Nguyễn Thị Lan",
  "phones": [
    {"number": "+84901234567", "kind": "MOBILE", "primary": true},
    {"number": "+842838221100", "kind": "WORK", "primary": false}
  ],
  "addresses": [
    {
      "kind": "SHIPPING",
      "line1": "12 Nguyễn Huệ",
      "city": "TP. Hồ Chí Minh",
      "countryCode": "VN"
    }
  ]
}
~~~

This structure **keeps each address as an object** and multiple numbers as **an array**. If the system supports atomic document writes and frequently reads the entire profile, this organization is convenient. Still, you must enforce “at most one primary phone” across **the entire array** and prevent two concurrent writers from overwriting each other's updates. Never assume standard JSON Schema automatically enforces all cross-element rules.

### 11.2. Graph: Do Not Turn Contact Data into a Graph Without Reason

A user's multiple phone numbers can be an array property on a `Customer` node, or `HAS_PHONE` edges pointing to `Phone` nodes. Choose nodes/edges when phone numbers have **their own relationships**, are **shared**, need network-link traversal queries, or carry edge metadata.

If you only need to store a few numbers for calling, a graph database rarely adds clear value over a child table or document. In all cases, verify links point to the right subject, prevent duplicate edges outside policy, and control cardinality and verification state.

### 11.3. Analytics: Watch the Grain

A revenue fact at the **one OrderLine** grain joins to Customer. If you then join to multi-phone and multi-address tables for grouping without defining the purpose, each OrderLine can be multiplied before `SUM(amount)`.

Pick a sound join strategy: join only the primary phone or the specific transaction address, aggregate at the customer level before joining, use a bridge table with allocation weights when multiple valid groups apply, or deduplicate by **fact_id** matching metric semantics. Never “fix” this with `SUM(DISTINCT amount)`: two distinct transactions with the same monetary amount must still be counted twice.

## 12. Workflow for Turning Requirements into a Schema

When encountering fields like “address”, “phone number”, “tags”, “skills”, or “measurements”, work step by step:

1. **Identify the subject and context:** does the value belong to Customer, Order, employee, contract, or an event?
2. **Determine multiplicity:** 0..1, 1..1, 0..N, 1..N, or a maximum cap K?
3. **Separate meaningful components:** what fields make up an address, and are they required by country or role?
4. **Define element identity:** are two identical numbers treated as the same contact point? Does an address need an `address_id`?
5. **Determine ordering:** if priority or position matters, store a `priority`/`position` column with appropriate constraints; never rely on natural SQL row order.
6. **Find attributes of the relationship:** do labels, assignment timestamp, primary status, validity window, and verifier belong to the element or to the association?
7. **Choose the structure:** single column, multiple component columns, child table, junction table, JSON/ARRAY, or an independent entity.
8. **Write constraints:** PK/FK, CHECK, UNIQUE at the proper scope, min/max cardinality, and delete/update rules.
9. **Design queries and indexes:** reading the whole set, looking up by element, finding a default element, counting, paginating, and aggregating.
10. **Test boundary data and changes over time:** empty set, single value, many values, duplicate numbers, missing components, two concurrent updates, switching the primary value, and transaction history.

If legacy data uses `phone_1, phone_2` or delimited strings, migrating to a child table should follow these steps: define splitting/normalization rules; audit anomalous values; create tables and constraints; migrate data; reconcile **subject counts**, **valid element counts**, and rejected records; cut over read/write paths deliberately; and only then drop legacy columns. Never guess delimiters or normalization rules when data is inconsistent.

## 13. Exercises with Solution Guides

### Exercise 1. Identifying Attribute Types

**Problem:** A student has one student ID, multiple contact emails, one residential address consisting of street–city–country, and multiple certificates (each certificate has a code, issuing organization, and issue date).

**Solution Guide:** Student ID is single-valued and can be a key. Email is a multivalued attribute. Residential address is a single-valued composite attribute if only one current address is required. Certificates are a set of structured items with their own lifecycle, so consider a `student_certificates` table with a surrogate key or composite key reflecting real certificate identification.

### Exercise 2. At Most One Primary Value

**Problem:** A Customer can have multiple emails but at most one primary email. What constraints should the `customer_emails(customer_id, email, is_primary)` table have?

**Solution Guide:** FK to Customer, primary key or UNIQUE on `(customer_id, email)`, `is_primary NOT NULL DEFAULT FALSE`, and a **partial unique index** on `customer_id WHERE is_primary` in PostgreSQL. Those constraints still do not guarantee that a Customer always has a primary email.

### Exercise 3. Two Independent Multivalued Sets

**Problem:** An employee has 3 phone numbers and 4 skills. If you JOIN both child tables directly and then COUNT, how many rows can appear?

**Solution Guide:** **3 × 4 = 12 rows** for one employee. To get phone count = 3 and skill count = 4, aggregate each child table separately or use two subqueries. When reporting by skill, do not JOIN phones unless there is a clear analytical purpose.

### Exercise 4. Composite Attribute or Entity?

**Problem:** An order's shipping address must store recipient, phone number, and street–city–country fields; the order must preserve the address used even if the customer later changes their profile address.

**Solution Guide:** The shipping address here is **transaction data**, needing a snapshot or an immutable version tied to the Order. You can store the address columns on Order or in an `order_shipping_addresses` table with a 1–1 relationship, depending on lifecycle and delivery destinations. Never point only to the mutable current `customer_addresses` row and let later edits rewrite history.

### Exercise 5. Junction Table vs. JSON Array

**Problem:** A Product belongs to multiple categories, and categories are shared across many products; you must filter products by category and guarantee every referenced category exists. What should you use?

**Solution Guide:** `products`, `categories`, and a junction table `product_categories(product_id, category_id)` with two FKs and a composite key is a strong choice. A JSON array of IDs can store the list, but FKs to **each** category and constraint maintenance are much harder; choose it only if specific benefits outweigh those costs.

### Exercise 6. Value Duplication vs. Entity Duplication

**Problem:** Two customers share the same company switchboard number. Should you put a table-wide UNIQUE constraint on `phone_e164`?

**Solution Guide:** **No**, unless the business genuinely forbids sharing numbers. If the rule is simply “each customer cannot store the same number twice”, use UNIQUE or PK on `(customer_id, phone_e164)`. Always define the exact uniqueness scope instead of making any identifier-looking value globally unique.

## 14. Key Takeaways

- **Multivalued** answers *how many elements a subject has*; **composite** answers *what components make up each element*. One attribute can belong to both categories.
- A set of elements needs clear **keys, multiplicity, metadata, and lifecycle**. Child tables or junction tables are usually convenient when elements must be queried and constrained individually.
- A **single** composite value can occupy multiple columns on **the same row**; there is no need to split out a table just because it has structure. A list of composite values must keep each **tuple** of components bound together.
- `UNIQUE`, `NOT NULL`, `CHECK`, and FKs protect different rules. “At most one” does not mean “at least one”, and a foreign key from child to parent does not automatically require the parent to have children.
- Joining two independent multivalued sets can **multiply rows**. Always establish the correct data grain before counting or summing.
- ARRAY/JSON, relational tables, documents, and graphs are all valid storage choices in appropriate contexts; the final decision must rest on **business semantics, constraint enforcement capabilities, query patterns, and how data changes over time**.
