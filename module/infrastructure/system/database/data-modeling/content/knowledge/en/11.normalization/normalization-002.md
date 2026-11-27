# First Normal Form and Domain-Based Atomicity

**First Normal Form (1NF)** is the foundation for representing data as relations with well-defined rows, attributes, and values. Under common practical interpretation, a column in a given row must represent **a single value belonging to a defined domain**, rather than hiding an entire list of business values inside one cell. However, "a single value" does not mean the value cannot be subdivided technically: **atomicity depends on the semantics and data domain the system needs to process**.

This lesson belongs to the **Normalization** chapter of data modeling. Its goal is to help you recognize structures that make querying, constraints, and updates hard to control, and then select appropriate tables, keys, and relationships. This is the prerequisite step before analyzing functional dependencies, 2NF, 3NF, indexes, physical modeling, or weighing relational databases against document databases.

## 1. What Does Each Row Represent, and What Value Does Each Column Hold?

A relation is described by attributes with defined value domains. For example:

- **customer_id**: customer identifier, belonging to the domain of valid customer IDs.
- **customer_name**: customer name, belonging to the domain of name strings complying with system rules.
- **phone_e164**: a phone number in standard E.164 representation, e.g., **+84901234567**.
- **registered_at**: a registration timestamp, belonging to the domain of temporal values.

For a table with a granularity (*grain*) of **one customer per row**, attributes such as name or registration timestamp can be placed directly in the customer table. However, if a customer has **0, 1, or many phone numbers**, the set of phone numbers is a one-to-many relationship that must be modeled explicitly.

Consider the input table:

| customer_id | customer_name | phone_numbers |
| ---: | --- | --- |
| 101 | An | +84901234567, +84909876543 |
| 102 | Bình | +84907654321 |
| 103 | Chi | *(empty)* |

Here **phone_numbers** holds a list, even though it is stored as a single text string. Seemingly simple questions immediately become difficult to answer:

- How many contact phone numbers does customer 101 have?
- Which customers own the number **+84909876543**?
- How do you prevent entering a duplicate number for the same customer?
- When deleting one number, how do you avoid accidentally deleting the remaining one?
- How do you enforce that each individual number, rather than just the whole string, conforms to a valid format?

If every number is merely a substring, those operations require string parsing and handling whitespace, delimiters, and formatting. Indexes, keys, **UNIQUE** constraints, and foreign keys on individual numbers are also hard to apply directly.

## 2. "Atomic" Is a Domain-Dependent Concept

### 2.1. There Is No Universal Atomicity Test for Every Domain

In the classical relational model, an attribute's value is treated as an element of that attribute's domain. When teaching 1NF, we commonly emphasize that an attribute does not contain **repeating groups** or **multiple values with independent meaning**.

A phone number has a country code and a subscriber number; a date has a year, month, and day; an address has multiple components. The fact that a value can be parsed into parts **does not automatically** make it non-atomic.

Consider different data domains:

| Value | Can Be Considered Atomic When… | Should Be Split or Remodeled When… |
| --- | --- | --- |
| **+84901234567** | The system treats the full number as a single contact method; validates and searches by full number | Components need separate business constraints, or one person has multiple numbers |
| **2026-11-22** | The application works with a single date value | Independent business concepts must be stored, such as fiscal months with dedicated rules |
| **Nguyễn Văn An** | The system only needs to store and display the full name | Family name, middle name, and given name must be managed under explicit rules; avoid assuming all naming cultures share the same structure |
| **Shipping address** | It is a verbatim snapshot of the accepted address at order placement time | Province/state, postal code, or country must be validated or queried separately, or linked to a geographic directory |
| **[number A, number B]** in a phone cell | It is merely a document/value that the application genuinely treats as an indivisible object | Each number needs to be added, deleted, searched, validated, or given its own attributes |

Therefore, the right question is: **"What is the smallest unit of value that the business needs to manage independently within this data domain?"** This is a modeling decision based on how data is used, not a blanket rule that "every string must be split into characters" or "every date must be split into three integers."

### 2.2. Distinguishing a Structured Single Value from a Multi-Value Collection

Two situations are easily confused:

**A single structured value:** a timestamp **2026-11-22T09:30:00+07:00** has multiple parts, yet represents **one point in time** within a temporal domain. A **TIMESTAMP** type or appropriate temporal value type usually models this far better than storing an arbitrary string.

**A collection of independent values:** a customer has two phone numbers, each of which can be added, removed, verified, or labeled separately. The two numbers are **two elements of a relation**, even if users view them in a single UI field.

If an attribute stores JSON or ARRAY in SQL, exercise caution before drawing conclusions. Modern DBMSs permit these types; whether they "satisfy 1NF" depends on the definition of 1NF and how the domain is viewed, so you cannot conclude solely from the data type name. **In practical design**, when inner elements require keys, constraints, or independent updates, a child table usually makes the relational model clearer and easier to verify.

## 3. Turning an In-Cell List into a One-to-Many Relationship

In the customer example, we separate two sets of facts:

1. Customer **101** has the name **An**.
2. Customer **101** has the number **+84901234567** and has the number **+84909876543**.

Each fact "customer has phone number" becomes a row in the **customer_phones** table. The customer's name remains in the **customers** table and is not repeated per phone number.

~~~mermaid
erDiagram
    CUSTOMERS ||--o{ CUSTOMER_PHONES : "has"
    CUSTOMERS {
        bigint customer_id PK
        varchar customer_name
    }
    CUSTOMER_PHONES {
        bigint customer_id PK, FK
        varchar phone_e164 PK
        varchar phone_label
    }
~~~

| customers.customer_id | customer_name |
| ---: | --- |
| 101 | An |
| 102 | Bình |
| 103 | Chi |

| customer_phones.customer_id | phone_e164 | phone_label |
| ---: | --- | --- |
| 101 | +84901234567 | mobile |
| 101 | +84909876543 | work |
| 102 | +84907654321 | mobile |

The **customers** table has one row per customer; the **customer_phones** table has one row per **(customer, phone number)** pair. Customer 103, who has no phone number, can still exist. In this example, the same number cannot be repeated **within the same customer**, whereas whether one number can be attached to two different customers is a separate business rule; you should not blindly impose a system-wide **UNIQUE(phone_e164)**.

### 3.1. SQL Schema with Keys and Constraints

The following example uses PostgreSQL so that phone format patterns can be checked with the regex operator **~**:

~~~sql
CREATE TABLE customers (
    customer_id   BIGINT PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL
);

CREATE TABLE customer_phones (
    customer_id BIGINT NOT NULL
        REFERENCES customers(customer_id),
    phone_e164 VARCHAR(16) NOT NULL
        CHECK (phone_e164 ~ '^\+[1-9][0-9]{1,14}$'),
    phone_label VARCHAR(20) NOT NULL
        CHECK (phone_label IN ('mobile', 'home', 'work')),
    PRIMARY KEY (customer_id, phone_e164)
);

INSERT INTO customers (customer_id, customer_name) VALUES
    (101, 'An'),
    (102, 'Bình'),
    (103, 'Chi');

INSERT INTO customer_phones
    (customer_id, phone_e164, phone_label)
VALUES
    (101, '+84901234567', 'mobile'),
    (101, '+84909876543', 'work'),
    (102, '+84907654321', 'mobile');
~~~

These constraints protect distinct rules:

- **PRIMARY KEY (customer_id, phone_e164)**: prevents entering the same number twice for the same customer.
- **FOREIGN KEY customer_id**: prevents assigning a number to a nonexistent customer.
- **CHECK phone_e164**: checks string structure with a **+** prefix and digit count fitting E.164 representation, though it does **not** prove the number exists or is currently assigned.
- **CHECK phone_label**: restricts the label to the set of values accepted by the system.

There is no need for columns like **phone_1**, **phone_2**, or guessing the maximum number of phones a customer might have. If the business requires identifying each contact-method record across number changes, a **phone_id** surrogate key can be used along with a unique constraint on **(customer_id, phone_e164)**. Key selection must follow the data lifecycle; there is no single answer for every system.

### 3.2. Simple Operations Once Data Has One Row per Number

**Adding a third number** for a customer:

~~~sql
INSERT INTO customer_phones
    (customer_id, phone_e164, phone_label)
VALUES (101, '+84903334444', 'home');
~~~

**Finding customers by full number:**

~~~sql
SELECT c.customer_id, c.customer_name
FROM customer_phones AS p
JOIN customers AS c
    ON c.customer_id = p.customer_id
WHERE p.phone_e164 = '+84909876543';
~~~

**Deleting one specific number** without touching the remaining numbers or the customer record:

~~~sql
DELETE FROM customer_phones
WHERE customer_id = 101
  AND phone_e164 = '+84903334444';
~~~

**Counting numbers per customer, including those with zero numbers:**

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(p.phone_e164) AS phone_count
FROM customers AS c
LEFT JOIN customer_phones AS p
    ON p.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

The result is **An: 2**, **Bình: 1**, **Chi: 0**. You must use **COUNT(p.phone_e164)** instead of **COUNT(*)**, because **LEFT JOIN** still produces a result row with **NULL** in columns from **p** for customers with no phone numbers.

If the UI wants to display multiple numbers on one line, you can **aggregate at the query or application layer**; a single-line display requirement does not force storing all numbers in one cell:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(
        STRING_AGG(p.phone_e164, ', ' ORDER BY p.phone_e164),
        ''
    ) AS phones_for_display
FROM customers AS c
LEFT JOIN customer_phones AS p
    ON p.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

String aggregation in read output serves the UI; managed data remains in individual rows with independent keys and constraints.

## 4. Recognizing Repeating Groups and the Boundaries of 1NF

### 4.1. Delimited Lists in a Single Column

~~~text
article_id | tags
-----------+---------------------------
10         | database,sql,architecture
~~~

If tags are entities that must be searched, renamed, authorized, or reused, the **tags** column is actually representing multiple associations. A suitable model could be:

~~~text
articles(article_id, ...)
tags(tag_id, tag_name, ...)
article_tags(article_id, tag_id)
~~~

Place **PRIMARY KEY (article_id, tag_id)** on the junction table if each tag is attached at most once per article. If you are only storing an immutable JSON descriptor for display or API passthrough, the modeling decision may differ; examine the actual business operations.

### 4.2. Numbered Columns

~~~text
customer_id | phone_1       | phone_2       | phone_3
------------+---------------+---------------+---------
101         | +84901234567  | +84909876543  | NULL
~~~

**phone_1**, **phone_2**, and **phone_3** can all hold valid scalar values in their respective columns. Thus, it is inaccurate to claim that **every** table with numbered columns violates 1NF under every formal definition.

Even so, this structure usually reflects a **business repeating group**: you have to guess a maximum count, add columns when demand grows, struggle to apply uniform constraints to all numbers, inspect multiple columns in queries, and "number 2" often carries no stable meaning. A child table remains better suited for a variable-sized collection of numbers.

Conversely, columns like **home_phone** and **emergency_phone** may reflect **two distinct roles** with fixed rules and cardinality; before splitting, ask whether the business allows multiple numbers per role or needs to track history, priority, and verification status for each contact method.

### 4.3. Multiple Rows Repeating the Parent Entity

Another "quick fix" is repeating customer information on every row:

| customer_id | customer_name | phone_e164 |
| ---: | --- | --- |
| 101 | An | +84901234567 |
| 101 | An | +84909876543 |

Each cell now holds a single value, yet **customer_name** is duplicated. Changing An's name requires updating multiple rows; a customer without a phone number cannot be represented if the key requires a phone number. A table can satisfy a simplistic view of atomic attributes and **still be a poor design**.

That is why 1NF is a starting point: subsequent normal forms and rules for defining *grain*, keys, and functional dependencies address the remaining sources of redundancy. "Splitting a string into multiple rows" must not be mistaken for proof that the entire schema is properly normalized.

## 5. What 1NF Does Not Guarantee on Its Own

| Concept | How 1NF Helps Guide Design | Still Requires Separate Attention |
| --- | --- | --- |
| **Value domain** | An attribute represents a single value from a defined domain | Data types, formatting, **CHECK**, valid lookup lists |
| **Uniqueness** | Each row represents one tuple of values in a relation | Candidate keys, **PRIMARY KEY**, **UNIQUE** in SQL systems |
| **Missing data** | Avoid using a list string as a substitute for relational structure | **NULL**, requiredness, and "unknown" vs. "not applicable" |
| **Redundancy** | Exposes independent values instead of burying them in one cell | Functional dependencies, **2NF**, **3NF**, **BCNF**, and related normal forms |
| **Relational integrity** | Clearly separates entities from individual links | Foreign keys, delete/update rules, and transactions |
| **Performance** | Produces a structured schema that is easy to constrain and query cleanly | Indexes, query plans, data volume, read/write workload |

In the mathematical relational model, a relation is a set of tuples and contains no identical duplicate tuples. Real-world SQL engines can permit duplicate rows if no key or constraint is declared. Therefore, putting one value per cell **does not replace** defining and enforcing uniqueness.

Likewise, 1NF does not simply mean "ban all **NULL**s." Many SQL schemas following 1NF practices still use **NULL** according to SQL semantics; each column must be evaluated on whether missing values are allowed. Specifically for **a customer with no phone number**, **having no row** in **customer_phones** is usually clearer than a row with "phone = NULL".

## 6. Process for Translating Business Requirements into a Schema

1. **Define the grain of each table.** Is "one row" a customer, a phone number belonging to a customer, or a phone call event? Never mix different grains without defining their relationship.
2. **List the value domain and operations for each attribute.** Is this data searched, compared, updated, verified, or authorized as a whole value or per individual element?
3. **Spot hidden collections.** Check for delimited strings, JSON/ARRAY holding lists of entities, numbered columns, and variable-count elements.
4. **Separate entities and associations where needed.** For one-to-many relationships, place multiple rows in a child table; for many-to-many relationships, consider a junction table.
5. **Define keys and constraints based on business rules.** Primary keys enforce uniqueness; foreign keys protect references; data types, **CHECK**, and **UNIQUE** protect value domains.
6. **Test edge cases.** Zero elements, one element, many elements, duplicate elements, invalid values, deleting one element, modifying attributes of the parent entity.
7. **Evaluate queries and access patterns.** Indexes can be added based on frequent queries. If considering embedded documents or denormalization for optimization, define the authoritative source of truth and consistency mechanism.

### Notes on Migrating Legacy Data

Do not assume a comma-based string **SPLIT** is sufficient in all cases. Real data can contain whitespace, delimiters appearing inside content, inconsistent number formats, duplicate values, and missing rows. You should **inventory the source data**, normalize each element to a valid domain, flag malformed records or records needing manual review, and only then load into child tables and enable constraints.

In the phone number example, a safe migration pipeline must decide how to standardize country codes, handle duplicates, interpret primary/priority flags, and represent zero-number cases. **E.164** is also just a number representation; it does not by itself prove the number is in service or able to receive calls.

## 7. Exercise: Product List in an Order

A sales system receives the following table:

| order_id | ordered_at | items |
| --- | --- | --- |
| O-01 | 2026-11-22 | P10:2; P20:1 |
| O-02 | 2026-11-22 | P20:3 |

Assume an element **P10:2** means product P10 with quantity 2, and an order can have multiple line items. After an order is created, the business may update the quantity or cancel a single line item; each line item must validate a positive quantity.

**Tasks:**

1. Explain why **items** is a collection of business values that must be managed independently; point out the difficulty of updating P10 alone.
2. Define the grain for the orders table and the order lines table. Propose primary and foreign keys.
3. Write a constraint to ensure **quantity > 0** on every line.
4. If an order is allowed to have **two lines for the same product** (due to a promotion or different pricing), which key choice is appropriate?

**Suggested Solution:**

~~~text
orders(
    order_id PRIMARY KEY,
    ordered_at
)

order_lines(
    order_id REFERENCES orders(order_id),
    line_no,
    product_id,
    quantity CHECK (quantity > 0),
    PRIMARY KEY (order_id, line_no)
)
~~~

- **orders** has the grain "one order"; **order_lines** has the grain "one line item of an order." Updating P10 happens directly on the relevant row.
- **(order_id, line_no)** is the appropriate key when an order allows multiple lines with the same **product_id**. If the business guarantees at most one line per product per order, **(order_id, product_id)** can also serve as a candidate key.
- In a real system, **product_id** normally needs a foreign key to the products table; pricing information at order placement time may need to be stored on the order line as **historical transaction data**, rather than automatically changing with the current catalog price.

## 8. Key Takeaways

1NF gives relational data a **clear unit of value per domain**. It guides designers away from burying independently managed elements inside a string or repeating group, and encourages representing collections as rows with proper keys, constraints, and relationships. **Atomicity is a decision about data semantics**, not a command to split every value that is technically splittable.

When an attribute actually holds multiple independent facts, determine their grain, extract them into appropriate tables or links, and protect them with constraints. Then continue evaluating functional dependencies, entity lifecycles, and higher normal forms: **satisfying 1NF is a starting condition, not a guarantee that redundant data or write anomalies have been eliminated**.
