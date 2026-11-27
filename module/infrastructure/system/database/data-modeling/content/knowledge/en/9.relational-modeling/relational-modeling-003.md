# Candidate Keys, Primary Keys, Alternate Keys, and Foreign Keys

## Learning Objectives

When translating business requirements into a relational logical model, the question “what identifies a record?” is just as important as “what attributes does the record have?”. **Keys** identify tuples, prevent duplicate data that violates rules, and link relations together. A poorly chosen key can lose valid data, permit conflicting records, or create broken references even when SQL statements run without error.

This lesson belongs to the **Relational Modeling** chapter of the **DATABASE_DATA_MODELING** module. Within this module, learners develop the skill of turning business requirements into clear data models—from entities, relationships, and constraints to normalization, keys, indexes, and physical schemas—providing a foundation to compare relational, document, graph, and analytical modeling approaches.

After this lesson, you will be able to:

1. Distinguish **superkeys**, **candidate keys**, **primary keys**, **alternate keys**, and **foreign keys**.
2. Identify candidate keys from **rules holding across all valid data states**, rather than relying on a few sample rows.
3. Prove that a composite key is minimal and recognize when a key must change as business rules evolve.
4. Represent 1–N and N–N relationships, composite foreign keys, and foreign keys referencing both primary keys and alternate keys.
5. Map a logical design to **PRIMARY KEY**, **UNIQUE**, **NOT NULL**, and **FOREIGN KEY** constraints in PostgreSQL.
6. Validate key choices, delete/update actions, and index implications during physical implementation.

## 1. Running Example: Identifying Customers and Orders

Suppose a sales system has the following requirements:

- Each customer has a unique **customer code** issued by the system.
- Each customer must have an **email**, and no two customers share the same email. This is a **lesson-specific assumption**, not a universal rule.
- Two customers can share the same full name.
- Each order has a unique **order number** and belongs to exactly one customer.
- An order has multiple order lines; line numbers start at 1 and are unique **within each order**.
- Each line selects one product, with a positive quantity and the unit price at the time of purchase.

A preliminary logical schema:

~~~~text
KHACH_HANG(id, ma_khach, email, ho_ten)
SAN_PHAM(id, sku, ten_san_pham, gia_niem_yet)
DON_HANG(id, so_don, ma_khach, ngay_dat)
DONG_DON_HANG(don_hang_id, so_dong, san_pham_sku, so_luong, don_gia)
~~~~

If **id**, **ma_khach**, and **email** are all mandatory and unique, all three can identify a customer. However, only **one** is chosen as the primary key; the remaining candidate keys must still be guaranteed unique. Conversely, **ho_ten** cannot serve as an identifier because duplicates are allowed.

## 2. Superkeys and Candidate Keys in the Relational Model

Consider a schema \(R(A_1,A_2,\ldots,A_n)\) with a relation state consisting of a set of tuples satisfying all constraints.

### 2.1. Superkey

An attribute set **K** is a superkey if any two tuples sharing the same values on K must be the exact same tuple in **every valid state**:

\[
\forall t_1,t_2\in r(R),\quad t_1[K]=t_2[K]\Rightarrow t_1=t_2
\]

Under the assumptions for KHACH_HANG:

- **{id}**, **{ma_khach}**, and **{email}** are all superkeys.
- **{id, ho_ten}** is also a superkey because adding a full name to an already unique identifier does not break uniqueness.

The set of all attributes is always a superkey of a pure mathematical relation because a relation is a set of tuples, so no two tuples are completely identical. However, many superkeys contain attributes unnecessary for identification.

### 2.2. Candidate Key

A **candidate key** is a superkey that is **minimal under set inclusion**: removing any component leaves a set that is no longer sufficient to identify tuples.

\[
K\text{ is a superkey}\quad\land\quad
\forall K'\subsetneq K,\ K'\text{ is not a superkey}
\]

In our example:

- **{id}**, **{ma_khach}**, and **{email}** are candidate keys.
- **{id, ho_ten}** is only a superkey, **not** a candidate key, because removing **ho_ten** still uniquely identifies tuples via **id**.

**Minimality does not mean having the fewest columns among all candidate keys.** A three-column composite key is still minimal if dropping any single column loses uniqueness, even when the relation also has another single-column candidate key.

You cannot prove a key solely from a few sample records. Even if every customer currently has a distinct name, **ho_ten** is still not a key when the rules permit duplicate names.

### 2.3. Functional Dependencies Help Identify Keys

A functional dependency \(X\rightarrow Y\) states that X determines the value of Y in every valid state. If **ma_khach** is a candidate key of KHACH_HANG, then:

\[
ma\_khach\rightarrow id,email,ho\_ten
\]

You can compute the **attribute closure** \(X^+\): the set of attributes derivable from X via the functional dependencies. If the closure contains every attribute of R, then X is a superkey under the given functional dependencies; then test removing each attribute of X one by one to verify minimality.

For example, consider the relation DANG_KY(ma_sv, ma_mon, hoc_ky, diem) with the rule that **each student has at most one enrollment record per course per semester**:

\[
(ma\_sv,ma\_mon,hoc\_ky)\rightarrow diem
\]

Assuming no additional functional dependencies, the triple **{ma_sv, ma_mon, hoc_ky}** is a candidate key. Dropping **hoc_ky** causes semesters to collide; dropping **ma_mon** causes courses to collide; dropping **ma_sv** causes students to collide. If the business later allows the same student to enroll in multiple sections of a course in the same semester, a section identifier or enrollment sequence must be added.

## 3. Primary Keys and Alternate Keys

### 3.1. Primary Key (PK)

A **primary key** is **one candidate key** chosen as the official identifier for tuples. An SQL **PRIMARY KEY** constraint enforces that the key is unique and **non-NULL**. A table has at most **one PRIMARY KEY constraint**, though that constraint may span multiple columns.

Suppose we pick **KHACH_HANG.id** as the PK because id is system-generated, compact, and rarely changes. Doing so **does not** permit two customers to share the same customer code or email if business rules state those attributes are unique.

### 3.2. Alternate Key (AK)

An **alternate key** is **each remaining candidate key after one primary key has been chosen**. Alternate keys must still uniquely identify tuples. The word “alternate” describes the PK selection choice; it does **not** imply a weaker key in terms of identifying power.

| Attribute Set | Classification | Reason |
| --- | --- | --- |
| {id} | Candidate key chosen as **PK** | Mandatory, unique |
| {ma_khach} | **Alternate key** | Mandatory, unique business code |
| {email} | **Alternate key** | Mandatory, unique email by assumption |
| {ho_ten} | Not a key | Duplicate names allowed |
| {id, ho_ten} | Superkey, not a candidate key | Contains a redundant attribute |

SQL has no standard **ALTERNATE KEY** keyword. Alternate keys are typically enforced using **UNIQUE** combined with **NOT NULL**, or an equivalent constraint ensuring uniqueness and presence.

~~~~sql
CREATE TABLE khach_hang (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_khach VARCHAR(20) NOT NULL UNIQUE,
    email VARCHAR(254) NOT NULL UNIQUE,
    ho_ten VARCHAR(120) NOT NULL
);
~~~~

**Watch out for NULL:** In PostgreSQL, a standard UNIQUE constraint can allow multiple rows with NULL values. Therefore, **an email that is UNIQUE but nullable** is not sufficient as a candidate key that always provides an identifier. If email is optional, you may still want a rule like “unique when provided”, but distinguish that rule from a mandatory candidate key.

## 4. Foreign Keys: Referential Constraints

A **foreign key (FK)** is an attribute set in a **referencing** relation (child table) pointing to an eligible key in a **referenced** relation (parent table), or satisfying the NULL rules for foreign keys.

In our example:

~~~~text
DON_HANG.ma_khach           → KHACH_HANG.ma_khach
DONG_DON_HANG.don_hang_id   → DON_HANG.id
DONG_DON_HANG.san_pham_sku  → SAN_PHAM.sku
~~~~

Three principles:

1. **An FK does not have to point to a PK.** An FK can reference an alternate key enforced by an appropriate unique constraint. DON_HANG.ma_khach points to KHACH_HANG.ma_khach, even though the customer PK is id.
2. **An FK in the child table does not have to be unique.** Multiple orders can point to the same customer. Placing UNIQUE on DON_HANG.ma_khach would accidentally restrict each customer to at most one order.
3. **An FK does not automatically require a value.** If the child column allows NULL, the FK can accept missing values. The rule “an order must belong to a customer” requires **ma_khach NOT NULL** alongside **FOREIGN KEY**.

When inserting an order with ma_khach = **KH999** while customer KH999 does not exist, the FK must reject the operation. A JOIN between two tables only pairs data on read; it **does not protect referential integrity on write**.

In SQL, the referenced target normally must have a PRIMARY KEY or a suitable UNIQUE constraint. PostgreSQL also supports certain cases backed by non-partial unique indexes. You cannot use a column containing duplicate values as a target and expect an FK to identify the right parent record.

Choosing whether to reference a PK or an alternate key is a design decision: a stable business code can be a good target; if codes frequently change, referencing a stable PK usually reduces update overhead.

## 5. Composite Keys and Minimality

Sample order lines:

| don_hang_id | so_dong | san_pham_sku | so_luong |
| ---: | ---: | --- | ---: |
| 101 | 1 | SP001 | 2 |
| 101 | 2 | SP002 | 1 |
| 102 | 1 | SP002 | 3 |

**so_dong = 1** is not globally unique across the table; **don_hang_id = 101** also repeats. However, the pair **(don_hang_id, so_dong)** is a candidate key under the rule “each line number appears once within the same order”.

~~~~text
DONG_DON_HANG(don_hang_id, so_dong, san_pham_sku, so_luong, don_gia)
PK = (don_hang_id, so_dong)
FK don_hang_id  → DON_HANG.id
FK san_pham_sku → SAN_PHAM.sku
~~~~

This is **one composite primary key**, not two independent primary keys:

~~~~sql
CONSTRAINT pk_dong_don_hang
    PRIMARY KEY (don_hang_id, so_dong)
~~~~

You should not use **(don_hang_id, san_pham_sku)** as the key if the same product is allowed to appear on multiple lines due to split shipments or different discount tiers. Each tuple must be identified according to the **business event** it represents.

## 6. Composite Foreign Keys and Tenant Scope

In a multi-tenant application (*tenant*), department code **KT** may exist across multiple organizations:

~~~~text
PHONG_BAN(tenant_id, ma_phong, ten_phong)
PK = (tenant_id, ma_phong)

NHAN_VIEN(tenant_id, ma_nv, ma_phong, ho_ten)
PK = (tenant_id, ma_nv)
FK (tenant_id, ma_phong)
   → PHONG_BAN(tenant_id, ma_phong)
~~~~

If you only link by ma_phong, an employee in tenant A could accidentally be linked to a department with the same code in tenant B. A composite FK preserves **both tenant_id and ma_phong**, ensuring references stay within the correct organization.

~~~~sql
CREATE TABLE phong_ban (
    tenant_id BIGINT NOT NULL,
    ma_phong VARCHAR(20) NOT NULL,
    ten_phong VARCHAR(100) NOT NULL,
    PRIMARY KEY (tenant_id, ma_phong)
);

CREATE TABLE nhan_vien (
    tenant_id BIGINT NOT NULL,
    ma_nv VARCHAR(20) NOT NULL,
    ma_phong VARCHAR(20) NOT NULL,
    ho_ten VARCHAR(100) NOT NULL,
    PRIMARY KEY (tenant_id, ma_nv),
    FOREIGN KEY (tenant_id, ma_phong)
        REFERENCES phong_ban (tenant_id, ma_phong)
);
~~~~

In a composite FK, you must declare the matching attribute pairs in the exact corresponding order. Two attributes sharing the same data type do not automatically carry the same meaning.

Under **MATCH SIMPLE** (typically the default), when any component of a composite FK is NULL, referential checking can be skipped. **MATCH FULL** (when supported by the DBMS) allows either all components to be NULL or all components to be non-NULL and match a parent key. In the employee example, both tenant_id and ma_phong are **NOT NULL**, so partially NULL FK cases cannot arise.

## 7. ER Diagram for Keys

The diagram uses **PK** (primary key), **UK** (unique constraint for alternate keys), and **FK** (foreign key). All UK attributes in the example are assumed mandatory.

~~~~mermaid
erDiagram
    KHACH_HANG ||--o{ DON_HANG : dat
    DON_HANG ||--o{ DONG_DON_HANG : co
    SAN_PHAM ||--o{ DONG_DON_HANG : duoc_chon

    KHACH_HANG {
        bigint id PK
        string ma_khach UK
        string email UK
        string ho_ten
    }
    DON_HANG {
        bigint id PK
        string so_don UK
        string ma_khach FK
        datetime ngay_dat
    }
    SAN_PHAM {
        bigint id PK
        string sku UK
        string ten_san_pham
        decimal gia_niem_yet
    }
    DONG_DON_HANG {
        bigint don_hang_id PK,FK
        integer so_dong PK
        string san_pham_sku FK
        integer so_luong
        decimal don_gia
    }
~~~~

A customer can have many orders, each order has many lines, and each product can appear in many lines. The diagram allows an order to **temporarily have no lines**; if the rule requires “confirm an order only when it has at least one line”, an extra check is needed during the state transition. An FK does not automatically guarantee the existence of child records.

## 8. Mapping the Logical Model to PostgreSQL

The following statements illustrate a standalone test database. Constraints are explicitly named to make violated rules easy to identify. Tables are created in parent-first, child-second order.

~~~~sql
CREATE TABLE khach_hang (
    id BIGINT GENERATED ALWAYS AS IDENTITY,
    ma_khach VARCHAR(20) NOT NULL,
    email VARCHAR(254) NOT NULL,
    ho_ten VARCHAR(120) NOT NULL,
    CONSTRAINT pk_khach_hang PRIMARY KEY (id),
    CONSTRAINT ak_khach_hang_ma UNIQUE (ma_khach),
    CONSTRAINT ak_khach_hang_email UNIQUE (email),
    CONSTRAINT ck_khach_hang_ten CHECK (btrim(ho_ten) <> '')
);

CREATE TABLE san_pham (
    id BIGINT GENERATED ALWAYS AS IDENTITY,
    sku VARCHAR(40) NOT NULL,
    ten_san_pham VARCHAR(200) NOT NULL,
    gia_niem_yet NUMERIC(12, 2) NOT NULL,
    CONSTRAINT pk_san_pham PRIMARY KEY (id),
    CONSTRAINT ak_san_pham_sku UNIQUE (sku),
    CONSTRAINT ck_san_pham_gia CHECK (gia_niem_yet >= 0)
);

CREATE TABLE don_hang (
    id BIGINT GENERATED ALWAYS AS IDENTITY,
    so_don VARCHAR(30) NOT NULL,
    ma_khach VARCHAR(20) NOT NULL,
    ngay_dat TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_don_hang PRIMARY KEY (id),
    CONSTRAINT ak_don_hang_so UNIQUE (so_don),
    CONSTRAINT fk_don_hang_khach
        FOREIGN KEY (ma_khach)
        REFERENCES khach_hang (ma_khach)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE TABLE dong_don_hang (
    don_hang_id BIGINT NOT NULL,
    so_dong INTEGER NOT NULL,
    san_pham_sku VARCHAR(40) NOT NULL,
    so_luong INTEGER NOT NULL,
    don_gia NUMERIC(12, 2) NOT NULL,
    CONSTRAINT pk_dong_don_hang PRIMARY KEY (don_hang_id, so_dong),
    CONSTRAINT fk_dong_don_hang_don
        FOREIGN KEY (don_hang_id)
        REFERENCES don_hang (id)
        ON DELETE CASCADE,
    CONSTRAINT fk_dong_don_hang_san_pham
        FOREIGN KEY (san_pham_sku)
        REFERENCES san_pham (sku)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    CONSTRAINT ck_dong_so CHECK (so_dong > 0),
    CONSTRAINT ck_dong_so_luong CHECK (so_luong > 0),
    CONSTRAINT ck_dong_don_gia CHECK (don_gia >= 0)
);
~~~~

### 8.1. Reading the Constraints in the DDL

| Constraint | Meaning |
| --- | --- |
| PRIMARY KEY on id | Every customer, product, and order has a unique, non-NULL system identifier |
| UNIQUE + NOT NULL on ma_khach | Customer code is an alternate key |
| UNIQUE + NOT NULL on email | Email is an alternate key under business assumptions |
| UNIQUE + NOT NULL on so_don | Order number is an alternate key even though PK is id |
| FK DON_HANG.ma_khach | Each order references an existing customer code |
| PK (don_hang_id, so_dong) | No duplicate line numbers within the same order |
| FK DONG_DON_HANG.san_pham_sku | Order line points to an existing SKU |
| CHECK so_luong > 0 | Disallows zero or negative quantities |

**Limitations to recognize:** This DDL does not prove that an email can receive messages, does not verify that a SKU is still active for sale, does not ensure every confirmed order has at least one line, and does not enforce payment workflows by itself. Key constraints are a vital part of the model, but they do not replace all business rules.

### 8.2. Sample Data

~~~~sql
INSERT INTO khach_hang (ma_khach, email, ho_ten) VALUES
    ('KH001', 'an@example.com', 'Nguyễn An'),
    ('KH002', 'binh@example.com', 'Trần Bình');

INSERT INTO san_pham (sku, ten_san_pham, gia_niem_yet) VALUES
    ('SP001', 'Notebook', 35000),
    ('SP002', 'Pen', 10000);

INSERT INTO don_hang (so_don, ma_khach) VALUES
    ('DH001', 'KH001'),
    ('DH002', 'KH001');

-- Look up the order id using the alternate key so_don.
-- Do not assume what identity number was generated.
INSERT INTO dong_don_hang
    (don_hang_id, so_dong, san_pham_sku, so_luong, don_gia)
SELECT id, 1, 'SP001', 2, 35000
FROM don_hang
WHERE so_don = 'DH001';

INSERT INTO dong_don_hang
    (don_hang_id, so_dong, san_pham_sku, so_luong, don_gia)
SELECT id, 2, 'SP002', 3, 10000
FROM don_hang
WHERE so_don = 'DH001';

SELECT
    dh.so_don,
    kh.ma_khach,
    kh.ho_ten,
    dd.so_dong,
    dd.san_pham_sku,
    dd.so_luong,
    dd.don_gia
FROM don_hang AS dh
JOIN khach_hang AS kh
    ON kh.ma_khach = dh.ma_khach
JOIN dong_don_hang AS dd
    ON dd.don_hang_id = dh.id
ORDER BY dh.so_don, dd.so_dong;
~~~~

JOIN result:

| so_don | ma_khach | ho_ten | so_dong | san_pham_sku | so_luong | don_gia |
| --- | --- | --- | ---: | --- | ---: | ---: |
| DH001 | KH001 | Nguyễn An | 1 | SP001 | 2 | 35000 |
| DH001 | KH001 | Nguyễn An | 2 | SP002 | 3 | 10000 |

Order DH002 has no detail lines yet, so it does not appear in an **INNER JOIN**. If you need to see orders without lines as well, use **LEFT JOIN**. This difference comes from the join type, not a key error.

### 8.3. Testing Rejected Cases

~~~~sql
-- Intentionally violate alternate key: duplicate customer code.
INSERT INTO khach_hang (ma_khach, email, ho_ten)
VALUES ('KH001', 'another@example.com', 'Another person');

-- Intentionally violate alternate key: duplicate email.
INSERT INTO khach_hang (ma_khach, email, ho_ten)
VALUES ('KH003', 'an@example.com', 'Another person');

-- Intentionally violate FK: no customer with code KH999.
INSERT INTO don_hang (so_don, ma_khach)
VALUES ('DH999', 'KH999');

-- Intentionally violate alternate key: duplicate order number.
INSERT INTO don_hang (so_don, ma_khach)
VALUES ('DH001', 'KH002');
~~~~

**Run each error test individually** rather than using them as seed data. These errors demonstrate that the database protects constraints even when the application skips pre-checks.

## 9. Delete Policies, Update Policies, and Foreign Keys

A proper FK must have explicit rules for when a parent row is deleted or a referenced key changes.

| Policy | Behavior | Example Consideration |
| --- | --- | --- |
| ON DELETE RESTRICT | Blocks deleting parent while child records still reference it | Customer with existing orders, product already sold |
| ON DELETE NO ACTION | Disallows FK-violating state; check timing can differ from RESTRICT if the DBMS supports deferrable constraints | Transactions updating multiple records |
| ON DELETE CASCADE | Deletes child rows when parent row is deleted | Order lines fully dependent on the order if deletion is allowed |
| ON DELETE SET NULL | Sets child FK to NULL | Optional association, nullable FK column |
| ON UPDATE CASCADE | Automatically updates child FK values when parent key changes | Business code permitted to change |

In our example, **deleting a customer who has orders** is blocked to protect history; if deleting an order is permitted, its lines are deleted along with it. In accounting systems, finalized orders generally should not be physically deleted; cancellation or archiving workflows must be decided separately.

When **ma_khach** or **sku** changes, **ON UPDATE CASCADE** can preserve links. If codes are defined as immutable, edits should be controlled instead of relying on CASCADE for routine code changes.

Do not use **ON DELETE SET NULL** on a mandatory FK column marked NOT NULL; the two rules conflict whenever a delete occurs.

**Self-referencing FKs** are also valid: for instance, NHAN_VIEN.ma_quan_ly referencing NHAN_VIEN.ma_nv. The model must decide whether top-level staff can have no manager, and if a tree structure is required, a mechanism must prevent cycles.

## 10. Keys and Indexes: Logical Constraints vs. Physical Structures

**Keys** express uniqueness and referential rules. **Indexes** are structures that accelerate lookups and enforce constraints. In PostgreSQL, **PRIMARY KEY** and **UNIQUE** constraints automatically create corresponding unique indexes, whereas declaring a **FOREIGN KEY on a child table does not automatically create an index on the FK column**.

If you frequently search orders by customer or sales lines by product, you might consider:

~~~~sql
CREATE INDEX ix_don_hang_ma_khach
    ON don_hang (ma_khach);

CREATE INDEX ix_dong_don_hang_san_pham_sku
    ON dong_don_hang (san_pham_sku);
~~~~

Do not add every possible index mechanically. Evaluate query patterns, data size, statistics, execution plans, and write overhead. For example, the composite PK **(don_hang_id, so_dong)** already has an index leading with **don_hang_id**, so many per-order queries can leverage the existing index.

## 11. Natural Keys, System-Generated Keys, and Business Keys

These concepts classify identifiers by **origin and semantic meaning**, which is distinct from their **PK/alternate key** role.

| Concept | Characteristic | Example |
| --- | --- | --- |
| Natural key | Carries real-world business meaning | Well-governed SKU, official classification code |
| System-generated surrogate key | Generated solely for identification, no business meaning required | id BIGINT identity, UUID |
| Business key | Identifier governed by operational rules | ma_khach, so_don |
| Primary key | The candidate key chosen as PK | KHACH_HANG.id |
| Alternate key | A candidate key not chosen as PK | KHACH_HANG.ma_khach |

**Surrogate key and alternate key are not synonymous**, even though both are sometimes loosely translated or confused:

- **Surrogate** describes the **origin/semantics** of the identifier.
- **Alternate** describes its **role relative to the chosen PK**.

A system-generated key is often useful when business codes are long, mutable, multi-part, or collide across data sources. However, a surrogate PK **does not replace UNIQUE on a business code**. If two rows having the same ma_khach is an error, giving those two rows different id values does not fix that error.

Conversely, a natural key can work well if it is short, immutable, and permanently unique. Email, phone number, or person name **do not inherently** satisfy these criteria; some organizations allow multiple people to share an email or one person to have multiple emails.

**Uniqueness scope must be explicit:** an order number might be unique only within a year, or a partner code only within a tenant. In such cases, **(nam, so_thu_tu)** or **(tenant_id, ma_doi_tac)** can be a candidate key, while the sequence number or local code alone is insufficient.

## 12. Common Key Design Mistakes

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Choosing full name as a key because sample data has no duplicates | Collisions when people share names | Choose identifiers based on enduring business rules |
| Having an id PK and dropping UNIQUE on the customer code | Allows duplicate business codes | Maintain alternate key constraints |
| Using UNIQUE without considering NULL | Can accept multiple rows lacking codes | Add NOT NULL for mandatory identifiers |
| Keying order lines by (ma_dh, ma_sp) even when products can repeat | Blocks valid business events | Use (don_hang_id, so_dong) or a line identifier |
| FK missing NOT NULL for a mandatory relationship | Allows child records without a parent | Combine NOT NULL and FOREIGN KEY |
| FK on ma_phong alone in multi-tenant data | Can link to the wrong organization | Use a composite foreign key including tenant_id |
| Choosing CASCADE for transaction history | Easily deletes data that must be retained | Define retention policies, use RESTRICT when needed |
| Assuming an FK auto-creates a child column index | Related queries may become slow | Evaluate indexes based on actual queries |
| Checking uniqueness in the application before INSERT | Two concurrent processes can pass the check simultaneously | Enforce UNIQUE in the DB and handle errors |

### The “Check-Then-Insert” Race Condition

Two processes may concurrently execute:

~~~~sql
SELECT 1
FROM khach_hang
WHERE ma_khach = 'KH010';
-- Both see that no KH010 row exists yet.
~~~~

Then both execute INSERT for KH010. Pre-checking in application code **does not guarantee uniqueness** under concurrent access. The database's **UNIQUE(ma_khach)** constraint is the final safeguard; at least one operation will be unable to commit duplicate codes into a valid state. The application should handle uniqueness errors and return an appropriate response.

## 13. Workflow for Finding and Selecting Keys from Business Requirements

1. **Define the meaning of a tuple.** For instance, one tuple in DONG_DON_HANG represents a specific line of an order.
2. **List potential identifiers** and their uniqueness scope: system-wide, per tenant, per year, or per order.
3. **Write verifiable uniqueness rules.** For example, “two lines in the same order cannot have the same so_dong”.
4. **Confirm edge cases and evolution.** Can items be re-imported, canceled, re-coded, moved across tenants, or registered multiple times?
5. **Prove minimality.** Try removing each component of every superkey one by one.
6. **Choose one candidate key as the PK** based on stability, size, and referencing cost.
7. **Keep constraints on alternate keys**, typically using UNIQUE plus NOT NULL when mandatory.
8. **Declare FKs with the right target and scope**, deciding nullability and update/delete actions.
9. **Test valid and invalid states**, including duplicate codes, missing parents, duplicate lines within the same order, and identical line numbers across different orders.
10. **Then optimize the physical schema**: select data types, indexes, and inspect query plans.

## 14. Self-Check Exercises

### Exercise 1 — Classifying Keys

NHAN_VIEN(id, ma_nv, email, ho_ten) has id, ma_nv, and email as mandatory and unique, while full names can repeat. Choose id as PK.

**Question:** List the candidate keys and alternate keys. Is **{id, ma_nv}** a candidate key?

**Answer:** Candidate keys are **{id}**, **{ma_nv}**, and **{email}**. Alternate keys are **{ma_nv}** and **{email}**. **{id, ma_nv}** is only a superkey because removing ma_nv still leaves it unique; the set is not minimal.

### Exercise 2 — Composite Key for Exam Attempts

DIEM_THI(ma_sv, ma_mon, lan_thi, diem): each student can take a course exam multiple times; lan_thi is the attempt sequence number within each student–course pair.

**Question:** What is the appropriate natural key? Can **(ma_sv, ma_mon)** be used?

**Answer:** **(ma_sv, ma_mon, lan_thi)** is the candidate key under the assumptions. The pair **(ma_sv, ma_mon)** is insufficient because multiple attempts are allowed. Even if id is chosen as PK, you should still place a UNIQUE constraint on the business triple and NOT NULL on its components.

### Exercise 3 — A PK Does Not Guarantee Unique Business Codes

~~~~sql
CREATE TABLE doi_tac (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_doi_tac VARCHAR(30) NOT NULL,
    ten VARCHAR(100) NOT NULL
);
~~~~

**Question:** Does this prevent two partners from sharing the code DT001? How do you fix it?

**Answer:** No. Two rows can have different id values yet identical ma_doi_tac. Add:

~~~~sql
ALTER TABLE doi_tac
ADD CONSTRAINT ak_doi_tac_ma UNIQUE (ma_doi_tac);
~~~~

### Exercise 4 — FK Referencing an Alternate Key

KHACH_HANG(id PK, ma_khach UNIQUE NOT NULL, ho_ten) and DON_HANG(id PK, ma_khach NOT NULL).

**Question:** Write an FK so that customer code in orders references customer code in the customer table, even though it is not the PK.

**Reference Answer:**

~~~~sql
ALTER TABLE don_hang
ADD CONSTRAINT fk_don_hang_khach
FOREIGN KEY (ma_khach)
REFERENCES khach_hang (ma_khach);
~~~~

The referenced key is an alternate key guaranteed to be unique.

### Exercise 5 — Avoiding Cross-Tenant Misreferences

PHONG_BAN(tenant_id, ma_phong, ten_phong) has PK **(tenant_id, ma_phong)**. NHAN_VIEN(tenant_id, ma_nv, ma_phong) must belong to a department of the same tenant.

**Question:** Why is an FK on ma_phong alone wrong? What is the right FK?

**Answer:** Department codes are only unique within each tenant. You need **FOREIGN KEY (tenant_id, ma_phong) REFERENCES phong_ban(tenant_id, ma_phong)**, combined with NOT NULL on the columns when every employee must belong to a department.

### Exercise 6 — Deleting a Customer with Transaction History

An accounting system must retain finalized orders. An administrator proposes ON DELETE CASCADE from orders to customers to quickly wipe data when a customer stops using the service.

**Question:** Should this be accepted immediately?

**Answer:** Not before clarifying retention requirements. Cascading deletion can destroy transaction history; typically RESTRICT, an inactive status, or an appropriate anonymization process is used. Only use CASCADE if the business genuinely permits deleting all child rows.

### Exercise 7 — UNIQUE and Concurrent Access

Two requests simultaneously check that code KH010 does not exist and then concurrently execute INSERT.

**Question:** Is checking in the application sufficient?

**Answer:** No. You need UNIQUE(ma_khach), along with NOT NULL if the code is mandatory, so the database enforces the constraint; the application catches duplicate-write errors and returns a sensible response.

### Exercise 8 — Surrogate Key vs. Alternate Key

SAN_PHAM(id BIGINT PK, sku VARCHAR(40) UNIQUE NOT NULL, ten_san_pham), where id is system-generated.

**Question:** Which column is the surrogate key and which is the alternate key?

**Answer:** id is the surrogate key and also the PK. sku is the alternate key. **Surrogate** describes the identifier's origin, while **alternate** describes a candidate key's role relative to the PK.

## 15. Summary

| Concept | Distinguishing Criterion | Example |
| --- | --- | --- |
| **Superkey** | Attribute set that uniquely identifies tuples; may contain redundant attributes | {id, ho_ten} |
| **Candidate key** | **Minimal** superkey | {id}, {ma_khach}, {email} |
| **Primary key** | The candidate key chosen as PK | KHACH_HANG.id |
| **Alternate key** | Remaining candidate keys, still required to be unique | KHACH_HANG.ma_khach |
| **Foreign key** | Reference to a valid key in the same or another relation | DON_HANG.ma_khach → KHACH_HANG.ma_khach |
| **Composite key** | Multi-component key where every component is necessary | (don_hang_id, so_dong) |
| **Surrogate key** | System-generated identifier, no business meaning required | id identity |
| **Natural/business key** | Identifier governed by business rules | ma_khach, sku |

Keys are only meaningful when derived from **the meaning of each tuple, uniqueness rules, and valid data states**. Identify every candidate key, select one as the PK, protect the alternate keys, and declare FKs to preserve links. From there, normalization, index selection, and physical schema design will have a clear foundation for verification as requirements evolve.
