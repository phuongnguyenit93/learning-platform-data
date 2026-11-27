# Converting Strong Entities and Weak Entities into Tables

## Learning Objectives

In database design, entity–relationship (ER) diagrams help describe business objects and the relationships among them. However, a relational database requires **concrete tables, columns, keys, and constraints**. An important mapping step is distinguishing a **strong entity** from a **weak entity** so that identification semantics and existence dependencies are not lost.

After this lesson, learners will be able to:

1. Recognize strong entities, weak entities, **owner entities**, **identifying relationships**, and **partial keys**.
2. Convert strong entities into tables with appropriate primary keys and convert weak entities into tables whose primary key combines the owner key and the partial key.
3. Properly define **PRIMARY KEY**, **FOREIGN KEY**, **NOT NULL**, **UNIQUE**, and additional business constraints in SQL.
4. Handle cases where the owner has a composite key, multi-level weak entities, and tables using surrogate keys.
5. Distinguish a weak entity from a strong entity with a foreign key, an N–N junction table, and a lifecycle-dependent table that has an independent identifier.
6. Validate the model with valid data, counterexamples, and insert, update, and delete operations.

**Learning Context:** This lesson belongs to the **Relational Modeling** chapter of the **DATABASE_DATA_MODELING** module. The goal of the module is to build the skill of translating business requirements into clear data models—from entities, relationships, and constraints to normalization, keys, indexes, and physical schemas—while comparing relational, document, graph, and analytical modeling approaches to choose structures that are appropriate, evolvable, and verifiable. This lesson focuses on mapping **the ER model to the relational model**, without yet diving deep into index tuning or non-relational systems.

## 1. From Business Story to Entities

Consider a sales system with the following requirements:

- Each customer has a unique customer code.
- Each order has its own order code and belongs to one customer.
- An order contains multiple **order lines**; each line has a sequence number 1, 2, 3, ... **within that order**.
- Line number 1 can exist across many different orders; a line sequence number alone does not identify an order line.
- An order line has no meaning when separated from the order that owns it.
- Each line stores a product, a quantity, and the **locked-in unit price** at the time of purchase.

Here, **DON_HANG** (Order) is a classic example of a **strong entity**: an order code can identify an order without needing the key of another entity. **DONG_DON_HANG** (Order Line) is a classic example of a **weak entity**: to pinpoint a specific line, you must know both the **order** and the **line number within that order**.

Example:

| Order Code | Line Number | Product | Quantity |
| --- | ---: | --- | ---: |
| DH101 | 1 | SP10 | 2 |
| DH101 | 2 | SP20 | 1 |
| DH102 | 1 | SP20 | 3 |

The key **line number = 1** appears twice, yet each tuple **(order code, line number)** is unique. This indicates that identifying an **order line** must include the owner's key.

## 2. What Are Strong Entities and Weak Entities?

### 2.1. Strong Entity

A strong entity type has its **own identifying key** without needing to borrow a key from an owner entity via an identifying relationship. For example:

- **KHACH_HANG(ma_kh, ho_ten, email)** with candidate key ma_kh.
- **SAN_PHAM(ma_sp, sku, ten_sp)** with candidate key ma_sp.
- **DON_HANG(ma_dh, ma_kh, ngay_dat)** with candidate key ma_dh.

An order may have a foreign key ma_kh referencing a customer, yet it remains a strong entity **under this identification design**: ma_dh alone suffices to identify the order, rather than combining a customer code with a per-customer order sequence number.

This illustrates an important distinction: **having a foreign key** or **having a business dependency on another entity** is not enough to conclude that an entity is weak.

### 2.2. Weak Entity

In classical ER notation, a weak entity type typically has the following characteristics:

1. **No independent full identifying key** in the model under consideration.
2. Has an **owner entity** (or *identifying entity*).
3. Participates **totally** in an **identifying relationship**: every weak instance must be associated with an appropriate owner.
4. Usually has a **partial key** (*discriminator*) to distinguish weak instances **within the scope of the same owner**.

For DONG_DON_HANG:

- The owner is DON_HANG.
- The identifying relationship is “a line belongs to an order”.
- The partial key is **so_dong**.
- The full identifier is **(ma_dh, so_dong)**.

The concept of **total participation** here points from the weak entity to the owner: **every order line must belong to an order**. It does not necessarily mean **every order must have lines at all times**. A system may allow creating an empty draft order and then require at least one line before confirmation.

### 2.3. Partial Key Differs from Primary Key

A **partial key** only distinguishes weak entities **sharing the same owner**. It is not sufficient to identify tuples across the entire weak entity set.

\[
\text{OrderLine Identifier} =
(\text{Order Identifier},\ \text{LineNumber})
\]

Line 1 of DH101 and line 1 of DH102 are **two different lines**. Therefore, you must not place PRIMARY KEY on so_dong alone when converting DONG_DON_HANG into a table.

**Terminology Note:** A partial key is not PostgreSQL's *partial index*. They are two distinct concepts: one in ER modeling and one in SQL index structures.

## 3. Representation in ER Diagrams

In traditional Chen notation:

- Strong entity: single-line rectangle.
- Weak entity: double-line rectangle.
- Identifying relationship: double-line diamond.
- Total participation of the weak entity: double connecting line.
- Partial key: dashed underline (depending on notation variant).

Other ER drawing tools may use solid lines or special symbols for identifying relationships. Therefore, alongside any diagram, always state in words **which attributes form the identifier**.

The Mermaid diagram below highlights **the owner link** and column structure. Mermaid ER does not fully render Chen-style double rectangles or double diamonds; the **(ma_dh, so_dong)** part is the identification criterion to verify.

~~~~mermaid
erDiagram
    KHACH_HANG ||--o{ DON_HANG : dat
    DON_HANG ||--o{ DONG_DON_HANG : so_huu
    SAN_PHAM ||--o{ DONG_DON_HANG : xuat_hien_trong

    KHACH_HANG {
        varchar ma_kh PK
        varchar ho_ten
        varchar email
    }
    DON_HANG {
        varchar ma_dh PK
        varchar ma_kh FK
        date ngay_dat
        varchar trang_thai
    }
    SAN_PHAM {
        varchar ma_sp PK
        varchar ten_sp
        decimal gia_hien_tai
    }
    DONG_DON_HANG {
        varchar ma_dh PK,FK
        int so_dong PK
        varchar ma_sp FK
        int so_luong
        decimal don_gia
    }
~~~~

Interpretation:

- DON_HANG is identified by **ma_dh**.
- DONG_DON_HANG is identified by the pair **(ma_dh, so_dong)**. The ma_dh column is both a **primary key component** and a **foreign key** to DON_HANG.
- Each order line links to a SAN_PHAM, but ma_sp **is not part of the line's identifying key** under this rule. The chosen product can change while editing a draft order without changing the line's identifying number.
- KHACH_HANG and SAN_PHAM are strong entities; being referenced does not turn them into weak entities.

## 4. Rules for Mapping a Strong Entity to a Table

For a strong entity type E, the basic procedure is:

1. **Create one table** corresponding to E.
2. Convert the stored **single-valued attributes** into columns, defining their domains and nullability.
3. Choose one **candidate key** as the PRIMARY KEY.
4. Preserve constraints for any **remaining candidate keys** if the business has multiple valid identifiers.
5. Map relationships with other entities into foreign keys or junction tables depending on multiplicity and relationship properties.

Conceptual example:

~~~~text
Strong entity KHACH_HANG:
  ma_kh (identifier), ho_ten, email

   ↓ maps to

KHACH_HANG(ma_kh PK, ho_ten, email)
~~~~

Illustrative SQL:

~~~~sql
CREATE TABLE khach_hang (
    ma_kh VARCHAR(20) PRIMARY KEY,
    ho_ten VARCHAR(120) NOT NULL,
    email VARCHAR(254)
);
~~~~

In this model, email can be missing, so it should **not** automatically be treated as a candidate key. If the business requires email to be unique when present, a corresponding constraint can be added.

For composite or multi-valued attributes, an appropriate modeling approach must be chosen. For example, if a customer has multiple phone numbers, you generally should not cram them into a comma-separated string cell when the business needs to query individual numbers. That is an attribute-mapping issue, handled separately from the weak-entity identification problem.

## 5. Rules for Mapping a Weak Entity to a Table

Suppose W is a weak entity type, E is the owner entity, and P is the partial key of W. For the common identifying relationship form **each W belongs to exactly one E**:

1. **Create a separate table for W.**
2. Include the attributes of W, including the partial key P, as columns.
3. **Copy the primary key of table E into table W** as a foreign key referencing the owner.
4. **Set the primary key of W to the combination of the owner's key and the partial key.**
5. Enforce **NOT NULL** on the identifying components (an SQL PRIMARY KEY already implies this).
6. Choose delete/update behaviors on the owner that match the data lifecycle.

Written generally:

\[
PK(W) = PK(E) \cup P
\]

The union symbol here means **combining the key attributes**, disambiguating column names if both sides share a name. If E's PK consists of multiple columns, **all components** must be carried over to W.

Example:

~~~~text
DON_HANG(ma_dh PK, ma_kh FK, ngay_dat)
DONG_DON_HANG(
    ma_dh,       -- PK component 1; FK to DON_HANG
    so_dong,     -- PK component 2, partial key
    ma_sp,       -- FK to SAN_PHAM
    so_luong,
    don_gia
)

PK(DONG_DON_HANG) = (ma_dh, so_dong)
FK(DONG_DON_HANG.ma_dh) → DON_HANG.ma_dh
~~~~

### Constraints Achieved This Way

| Requirement | Mapping | Consequence |
| --- | --- | --- |
| Every order has a unique code | PRIMARY KEY on DON_HANG.ma_dh | No two orders share a code |
| Every line belongs to an existing order | FK from DONG_DON_HANG.ma_dh to DON_HANG.ma_dh | No orphan lines can be created |
| A line must have an owner | ma_dh is part of PK, non-NULL | Cannot create a line without an order code |
| Line numbers do not repeat within an order | PK(ma_dh, so_dong) | One order cannot have two line #1s |
| Different orders can reuse line numbers | No table-wide UNIQUE(so_dong) | DH101 and DH102 can both have line 1 |
| Line references a product | FK from ma_sp to SAN_PHAM.ma_sp | Cannot select a nonexistent product |
| Quantity must be positive | CHECK(so_luong > 0) and NOT NULL | Blocks negative, zero, or missing quantities |

**Important:** You do not need to create an extra table solely to represent the **1–N identifying relationship** between order and line if the weak table already holds the owner's key. Splitting out a pointless junction table can dilute or lose the identifying constraint that belongs directly in DONG_DON_HANG.

## 6. Complete and Testable PostgreSQL Example

The DDL below creates four tables to demonstrate strong entities, weak entities, FKs, and value constraints together. The statements use **PostgreSQL** syntax; run them on an empty test database in the order presented.

~~~~sql
CREATE TABLE khach_hang (
    ma_kh VARCHAR(20) PRIMARY KEY,
    ho_ten VARCHAR(120) NOT NULL
);

CREATE TABLE san_pham (
    ma_sp VARCHAR(20) PRIMARY KEY,
    ten_sp VARCHAR(150) NOT NULL,
    gia_hien_tai NUMERIC(12, 2) NOT NULL,
    CONSTRAINT ck_sp_gia CHECK (gia_hien_tai >= 0)
);

CREATE TABLE don_hang (
    ma_dh VARCHAR(20) PRIMARY KEY,
    ma_kh VARCHAR(20) NOT NULL,
    ngay_dat DATE NOT NULL,
    trang_thai VARCHAR(20) NOT NULL DEFAULT 'nhap',
    CONSTRAINT fk_don_khach
        FOREIGN KEY (ma_kh) REFERENCES khach_hang(ma_kh)
        ON DELETE RESTRICT,
    CONSTRAINT ck_don_trang_thai
        CHECK (trang_thai IN ('nhap', 'xac_nhan', 'huy'))
);

CREATE TABLE dong_don_hang (
    ma_dh VARCHAR(20) NOT NULL,
    so_dong INTEGER NOT NULL,
    ma_sp VARCHAR(20) NOT NULL,
    so_luong INTEGER NOT NULL,
    don_gia NUMERIC(12, 2) NOT NULL,
    CONSTRAINT pk_dong_don PRIMARY KEY (ma_dh, so_dong),
    CONSTRAINT fk_dong_don
        FOREIGN KEY (ma_dh) REFERENCES don_hang(ma_dh)
        ON DELETE CASCADE,
    CONSTRAINT fk_dong_san_pham
        FOREIGN KEY (ma_sp) REFERENCES san_pham(ma_sp)
        ON DELETE RESTRICT,
    CONSTRAINT ck_dong_stt CHECK (so_dong > 0),
    CONSTRAINT ck_dong_so_luong CHECK (so_luong > 0),
    CONSTRAINT ck_dong_gia CHECK (don_gia >= 0)
);
~~~~

**Meaning of the three distinct choices:** DON_HANG is a strong entity even though **ma_kh** is a mandatory FK. DONG_DON_HANG is a weak entity because its key **contains the owner's ma_dh** plus the partial key **so_dong**. Meanwhile, **ma_sp** is an FK to another strong entity and does not participate in identifying the line under the example's business rules.

### 6.1. Loading Data

~~~~sql
INSERT INTO khach_hang (ma_kh, ho_ten) VALUES
    ('KH01', 'Nguyễn An'),
    ('KH02', 'Trần Bình');

INSERT INTO san_pham (ma_sp, ten_sp, gia_hien_tai) VALUES
    ('SP10', 'Notebook', 120000),
    ('SP20', 'Pen', 45000);

INSERT INTO don_hang (ma_dh, ma_kh, ngay_dat, trang_thai) VALUES
    ('DH101', 'KH01', DATE '2026-10-01', 'xac_nhan'),
    ('DH102', 'KH02', DATE '2026-10-02', 'nhap');

INSERT INTO dong_don_hang
    (ma_dh, so_dong, ma_sp, so_luong, don_gia)
VALUES
    ('DH101', 1, 'SP10', 2, 115000),
    ('DH101', 2, 'SP20', 1, 45000),
    ('DH102', 1, 'SP20', 3, 45000);
~~~~

### 6.2. Querying Line Identity and Totals

~~~~sql
SELECT
    dh.ma_dh,
    kh.ho_ten,
    dd.so_dong,
    sp.ten_sp,
    dd.so_luong,
    dd.don_gia,
    dd.so_luong * dd.don_gia AS thanh_tien
FROM dong_don_hang AS dd
JOIN don_hang AS dh ON dh.ma_dh = dd.ma_dh
JOIN khach_hang AS kh ON kh.ma_kh = dh.ma_kh
JOIN san_pham AS sp ON sp.ma_sp = dd.ma_sp
ORDER BY dh.ma_dh, dd.so_dong;
~~~~

| ma_dh | ho_ten | so_dong | ten_sp | so_luong | don_gia | thanh_tien |
| --- | --- | ---: | --- | ---: | ---: | ---: |
| DH101 | Nguyễn An | 1 | Notebook | 2 | 115000 | 230000 |
| DH101 | Nguyễn An | 2 | Pen | 1 | 45000 | 45000 |
| DH102 | Trần Bình | 1 | Pen | 3 | 45000 | 135000 |

From this, the total for DH101 is **275000**, and DH102 is **135000**. The historical unit price of SP10 is **115000** on the order line, even though the current list price is **120000**. Preserving historical information is one reason to place **don_gia** inside DONG_DON_HANG instead of always reading from SAN_PHAM.

### 6.3. Testing Constraints with Counterexamples

The following statements are designed to **fail when run individually** after the data load step:

~~~~sql
-- Composite primary key error: line 1 of DH101 already exists.
INSERT INTO dong_don_hang (ma_dh, so_dong, ma_sp, so_luong, don_gia)
VALUES ('DH101', 1, 'SP20', 1, 45000);

-- FK error: order DH999 does not exist.
INSERT INTO dong_don_hang (ma_dh, so_dong, ma_sp, so_luong, don_gia)
VALUES ('DH999', 1, 'SP10', 1, 115000);

-- FK error: product SP999 does not exist.
INSERT INTO dong_don_hang (ma_dh, so_dong, ma_sp, so_luong, don_gia)
VALUES ('DH101', 3, 'SP999', 1, 10000);

-- CHECK error: quantity must be greater than 0.
INSERT INTO dong_don_hang (ma_dh, so_dong, ma_sp, so_luong, don_gia)
VALUES ('DH101', 3, 'SP10', 0, 115000);

-- NOT NULL error: a weak line must have an order code.
INSERT INTO dong_don_hang (ma_dh, so_dong, ma_sp, so_luong, don_gia)
VALUES (NULL, 3, 'SP10', 1, 115000);
~~~~

**Valid case to test:** Adding line number 2 to DH102 is valid even though DH101 already has line number 2, because the primary key checks **the pair (ma_dh, so_dong)**.

~~~~sql
INSERT INTO dong_don_hang (ma_dh, so_dong, ma_sp, so_luong, don_gia)
VALUES ('DH102', 2, 'SP10', 1, 120000);
~~~~

Note that the examples use **ON DELETE CASCADE** for order lines solely to illustrate lifecycle dependency. In systems that must retain invoices or accounting history, physically deleting orders may be prohibited by business policy, and using CASCADE must be reconsidered.

## 7. When the Owner's Key Is a Composite Key

The weak-entity mapping rule does not restrict the owner to having a single-column key. When the owner has a **composite primary key**, the weak entity must receive **all key components** of the owner.

Suppose invoice numbers are only unique **within each company**:

~~~~text
HOA_DON(tenant_id, so_hd, ngay_lap)
PK = (tenant_id, so_hd)

DONG_HOA_DON(tenant_id, so_hd, so_dong, noi_dung, so_tien)
PK = (tenant_id, so_hd, so_dong)
FK (tenant_id, so_hd) → HOA_DON(tenant_id, so_hd)
~~~~

An illustrative table:

| tenant_id | so_hd | so_dong | noi_dung |
| ---: | --- | ---: | --- |
| 1 | HD001 | 1 | Service A |
| 1 | HD001 | 2 | Service B |
| 2 | HD001 | 1 | Service C |

Invoice number HD001 appears in two tenants; line number 1 also appears across multiple invoices. Only **the triple (tenant_id, so_hd, so_dong)** uniquely identifies an invoice line system-wide.

~~~~sql
CREATE TABLE hoa_don (
    tenant_id BIGINT NOT NULL,
    so_hd VARCHAR(30) NOT NULL,
    ngay_lap DATE NOT NULL,
    PRIMARY KEY (tenant_id, so_hd)
);

CREATE TABLE dong_hoa_don (
    tenant_id BIGINT NOT NULL,
    so_hd VARCHAR(30) NOT NULL,
    so_dong INTEGER NOT NULL CHECK (so_dong > 0),
    noi_dung VARCHAR(200) NOT NULL,
    so_tien NUMERIC(14, 2) NOT NULL CHECK (so_tien >= 0),
    CONSTRAINT pk_dong_hoa_don
        PRIMARY KEY (tenant_id, so_hd, so_dong),
    CONSTRAINT fk_dong_hoa_don
        FOREIGN KEY (tenant_id, so_hd)
        REFERENCES hoa_don (tenant_id, so_hd)
        ON DELETE RESTRICT
);
~~~~

If you drop **tenant_id** from the FK, the system could mistakenly reference an invoice number from another company; moreover, **so_hd** is not a table-wide unique key, so it cannot be a valid FK target in this design.

**Modeling Note:** HOA_DON in this example is treated as an entity type with logical identifier **(tenant_id, so_hd)**. A strong entity having a composite key can certainly occur; classifying it as weak or strong relative to TENANT also depends on **the identifying relationship and business semantics in the source ER diagram**. The core point of this example is that **a weak line inherits the entire owner key**, without arbitrarily shortening it.

## 8. Multi-Level Chains of Weak Entities

A weak entity can also serve as the **owner for another weak entity**. For example, in construction management:

- **DU_AN** has a globally unique project code.
- **HANG_MUC** has a category number unique only within each project.
- **CONG_VIEC** has a task number unique only within each category.

~~~~text
DU_AN(ma_du_an PK)

HANG_MUC(ma_du_an, so_hang_muc, ten_hang_muc)
PK = (ma_du_an, so_hang_muc)
FK ma_du_an → DU_AN.ma_du_an

CONG_VIEC(ma_du_an, so_hang_muc, so_cong_viec, mo_ta)
PK = (ma_du_an, so_hang_muc, so_cong_viec)
FK (ma_du_an, so_hang_muc)
    → HANG_MUC(ma_du_an, so_hang_muc)
~~~~

You must not point CONG_VIEC's FK only to DU_AN: a task must also belong to **the right category** of the project, and the existence of that category must be verified. Each level inherits **the full key of its immediate owner** and appends its own partial key.

~~~~sql
CREATE TABLE du_an (
    ma_du_an VARCHAR(20) PRIMARY KEY
);

CREATE TABLE hang_muc (
    ma_du_an VARCHAR(20) NOT NULL,
    so_hang_muc INTEGER NOT NULL CHECK (so_hang_muc > 0),
    ten_hang_muc VARCHAR(120) NOT NULL,
    PRIMARY KEY (ma_du_an, so_hang_muc),
    FOREIGN KEY (ma_du_an) REFERENCES du_an(ma_du_an)
);

CREATE TABLE cong_viec (
    ma_du_an VARCHAR(20) NOT NULL,
    so_hang_muc INTEGER NOT NULL,
    so_cong_viec INTEGER NOT NULL CHECK (so_cong_viec > 0),
    mo_ta VARCHAR(200) NOT NULL,
    PRIMARY KEY (ma_du_an, so_hang_muc, so_cong_viec),
    FOREIGN KEY (ma_du_an, so_hang_muc)
        REFERENCES hang_muc(ma_du_an, so_hang_muc)
);
~~~~

Multi-level key inheritance is very clear logically, but it makes **keys grow longer**. At the physical step, surrogate keys can be considered for deeper levels to reduce referencing overhead, provided business-identifying constraints remain protected.

## 9. Can a Surrogate Key Be Used for a Weak Entity Table?

In a real system, developers may want to assign a **globally unique id** to each order line to simplify APIs and FKs from other tables. In that case, you can use:

~~~~text
DONG_DON_HANG(
    id PK,
    ma_dh FK NOT NULL,
    so_dong NOT NULL,
    ...
)

UNIQUE(ma_dh, so_dong)
~~~~

This is an **alternative physical implementation** of the same business rule “a line is numbered within an order”:

~~~~sql
CREATE TABLE dong_don_hang_id (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_dh VARCHAR(20) NOT NULL
        REFERENCES don_hang(ma_dh) ON DELETE RESTRICT,
    so_dong INTEGER NOT NULL CHECK (so_dong > 0),
    ma_sp VARCHAR(20) NOT NULL REFERENCES san_pham(ma_sp),
    so_luong INTEGER NOT NULL CHECK (so_luong > 0),
    don_gia NUMERIC(12, 2) NOT NULL CHECK (don_gia >= 0),
    CONSTRAINT ak_dong_don_hang_id UNIQUE (ma_dh, so_dong)
);
~~~~

In this table:

- **id** is a system-generated PK (*surrogate key*).
- **(ma_dh, so_dong)** remains the business candidate key enforced via UNIQUE plus NOT NULL.
- **ma_dh** remains a mandatory FK to the owner.
- You cannot have two lines with the same so_dong in the same ma_dh; nor can you have an orphan line.

**Never** drop UNIQUE(ma_dh, so_dong) just because PK(id) exists: if dropped, two lines with the same sequence number in one order would become valid at the SQL level, violating the business requirement.

### Conceptual Weak Entity vs. Table with an Independent id

In classical ER understanding, a weak entity is **identified via its owner's key combined with a partial key**. When a global id is added and chosen as the PK, the SQL schema gains a technically independent identifier. However, **the existence dependency and per-owner uniqueness of the business rule do not disappear**; you must still keep NOT NULL, the FK, and UNIQUE(ma_dh, so_dong). Thus, when discussing designs, be explicit about whether you are classifying **an entity in the conceptual model** or **the primary key of an implemented table**.

Both approaches have trade-offs:

| Criterion | Composite PK (ma_dh, so_dong) | PK id and UNIQUE(ma_dh, so_dong) |
| --- | --- | --- |
| Business identity representation | Directly inside the PK | Via an alternate key |
| Foreign keys from other tables to the line | Must carry both ma_dh and so_dong | May only need id |
| Key size and index count | No extra id needed | Extra id and UNIQUE constraint |
| Impact of changing line number | Changes the PK and related FKs | PK id stays stable, but business UNIQUE updates |
| Protecting order ownership | Through PK containing ma_dh and FK | Through NOT NULL FK and UNIQUE |
| Logical meaning of a line | Identified within order scope | Still requires a rule identifying lines within order scope |

Which option to choose depends on business rules, how tables reference each other, stability of line numbers, and actual queries. **Adding a surrogate key is not automatically better**, nor is it a reason to drop existing constraints.

## 10. How Does a Weak Entity Differ from a Strong Entity with an FK?

Re-examine DON_HANG(ma_dh, ma_kh, ngay_dat):

- An order **belongs to a customer** in business terms.
- The order has a **globally unique ma_dh**, so identification does not need to combine ma_kh.
- Therefore, in the current model, DON_HANG can be viewed as a **strong entity** even though ma_kh is a mandatory FK.

If the rule changes to “each customer has their own order sequence number, and sequence numbers are reused across customers”, the model can change to:

~~~~text
DON_HANG(ma_kh, so_don_theo_khach, ngay_dat)
PK = (ma_kh, so_don_theo_khach)
FK ma_kh → KHACH_HANG.ma_kh
~~~~

Then an order is only identified by **customer + order number within that customer**, and the order can be modeled as a weak entity owned by the customer in an appropriate ER model.

From these two examples we can extract clear criteria:

| Question | Strong Entity with FK | Classical Weak Entity |
| --- | --- | --- |
| Can it be identified without the owner's key? | Yes, by the entity's own key | No, requires owner key plus partial key |
| Can it have FKs to other entities? | Yes | Yes, in the identifying relationship |
| Can every record be required to have a parent record? | Possibly | Yes, via total participation in the identifying relationship |
| PK in traditional mapping | The entity's own key | Owner key plus partial key |
| Example | Order with a globally unique order code | Numbered line within an order |

**Lifecycle dependency differs from identification dependency.** An attachment with a global id may still be required to belong to a case file and be deleted with it, yet that does not automatically make it a weak entity by ER definition. You must examine **the identification mechanism** of the attachment in the model.

## 11. Is an N–N Junction Table a Weak Entity?

Suppose we have SINH_VIEN(ma_sv) and LOP_HOC(ma_lop), where a student attends multiple classes and each class has multiple students. The **N–N** relationship is commonly mapped to:

~~~~text
DANG_KY(ma_sv, ma_lop, ngay_dang_ky, trang_thai)
PK = (ma_sv, ma_lop)   -- if each student enrolls at most once per class
FK ma_sv → SINH_VIEN.ma_sv
FK ma_lop → LOP_HOC.ma_lop
~~~~

The DANG_KY table **has a PK composed of two FKs**, yet it does not have to be labeled a weak entity in every ER notation. It is a **junction table** or representation of an **associative entity**. The two concepts are related but not identical:

- A classical weak entity typically has **an identifying relationship with one owner** and a partial key distinguishing instances within that owner.
- An N–N junction table records **an association between entities**, usually keyed by combining the keys of **the participating sides**.
- An associative entity may both depend for existence on the participating sides and carry its own attributes like enrollment date and grade; depending on the model and notation, classification may vary.

If students are allowed to re-enroll in a class across multiple terms, the key **(ma_sv, ma_lop)** is no longer enough. You must add **ma_dot** or an enrollment identifier and appropriate constraints. Regardless of whether it is called a weak entity or an associative entity, **the key must accurately reflect the business event**.

## 12. Where Do Attributes of an Identifying Relationship Go?

Suppose the identifying relationship DON_HANG — DONG_DON_HANG also carries “the timestamp when the line was added to the order”. Each line belongs to **exactly one** order; this information is tied to the existence of that line within the order. When mapping, the attribute can usually be placed directly in:

~~~~text
DONG_DON_HANG(
    ma_dh,
    so_dong,
    ma_sp,
    so_luong,
    don_gia,
    thoi_diem_them
)
~~~~

There is no need for a separate table containing only ma_dh, so_dong, and thoi_diem_them if **each line has a single identifying relationship with its owner** and there is no requirement to separate lifecycles or independent histories.

Conversely, if a record can link **multiple entities of the same kind** or the relationship has an independent lifecycle, a junction table or separate entity may be required. For example, the history of **splitting an order line across delivery shipments** can represent independent shipping events; you should not cram a list of shipments into one column of the order line.

## 13. Integrity and Lifecycle: What Does an FK Guarantee?

### 13.1. Total Participation from the Weak Entity to the Owner

In the DONG_DON_HANG model:

- **NOT NULL(ma_dh)** requires every line to have an order code.
- **FOREIGN KEY(ma_dh) REFERENCES DON_HANG(ma_dh)** requires the order code to exist.
- **PRIMARY KEY(ma_dh, so_dong)** requires line identification to be sufficient and non-duplicate.

These three conditions are the standard way to enforce **total participation in an identifying relationship**.

However, they **do not guarantee every order has at least one line**. That is the reverse requirement: from the owner to the set of child records. If the rule is “an order in status xac_nhan must have lines”, it must be checked during the state transition, typically inside a **transaction** with concurrency control, or via an appropriate database mechanism.

### 13.2. Foreign Keys and NULL

A single-column foreign key can accept NULL if the referencing column allows NULL. This is **inappropriate for a weak entity that must have an owner**.

With composite FKs, SQL's default **MATCH SIMPLE** usually allows skipping the referential check if any component is NULL. Therefore, identifying columns of a weak entity should be declared NOT NULL or placed directly in the PRIMARY KEY. When the business requires “either all components are absent or all are present”, consider MATCH FULL and actual DBMS support.

### 13.3. Choosing Behavior When the Owner Is Deleted

| FK Policy | Behavior on Weak Records | When Appropriate |
| --- | --- | --- |
| ON DELETE CASCADE | Deletes weak rows when owner is deleted | Purely subordinate data, no independent history needed |
| ON DELETE RESTRICT | Blocks deleting owner while weak rows exist | Orders, invoices, data requiring audit trails |
| ON DELETE NO ACTION | Rejects FK-violating state; check timing depends on DBMS/constraint | Transactions modifying multiple rows |
| ON DELETE SET NULL | Sets weak FK to NULL | **Usually inappropriate** for NOT NULL identifying FKs |
| Application-level soft delete | Keeps records, marks inactive/canceled | Need historical queries and want to avoid physical deletes |

Being “weak” does not automatically mandate CASCADE. **Owner-dependent identification** and **data retention policy** are two separate decisions.

### 13.4. Updating the Owner Identifier or Partial Key

If you change a referenced ma_dh, you must preserve the lines' foreign keys. You can use ON UPDATE CASCADE in appropriate scenarios, or treat order codes as immutable. If you change so_dong, you are changing **a PK component**, affecting every other table referencing that line. This is why some systems choose a **stable id** for lines physically while maintaining UNIQUE(ma_dh, so_dong) for business rules.

### 13.5. Keys, Indexes, and Queries

In PostgreSQL, a PRIMARY KEY creates a unique index. The PK(ma_dh, so_dong) index typically supports queries searching lines by ma_dh because ma_dh is the leading column. PostgreSQL **does not automatically create indexes on every FK in a child table**; if you frequently filter lines by product, consider a dedicated index:

~~~~sql
CREATE INDEX ix_dong_don_hang_ma_sp
    ON dong_don_hang (ma_sp);
~~~~

Indexes must be based on queries and write-update costs. That belongs to optimizing the **physical schema**, whereas PK and FK decisions must first preserve **logical semantics**.

## 14. Mapping Workflow Applicable to New Problems

When given an ER diagram or a verbal requirement description, you can follow this sequence:

1. **List entities and the meaning of each instance.** Does a record represent a customer, an order, an order line, a hotel room, or an enrollment?
2. **Identify independent identifiers.** Which entities have candidate keys sufficient for identification without borrowing an owner's key through an identifying relationship?
3. **Spot weak entities.** Find entities that require knowing an owner to identify an instance, along with an identifying relationship with total participation.
4. **Determine partial keys.** Ask: “Within the scope of a single owner, which attributes distinguish weak instances?”.
5. **Map strong tables.** Put single-valued attributes, the primary key, and any other candidate keys into the table with corresponding domains and constraints.
6. **Map weak tables.** Copy **the full owner key** as an FK, add the partial key to form a composite PK; mark required columns NOT NULL.
7. **Map remaining relationships.** For example, an order line referencing a product becomes an additional FK; an N–N relationship may require a junction table.
8. **Decide lifecycle and key mutation rules.** Specify owner delete policies, code updates, sequence edits, and historical data handling.
9. **Check constraints not expressible by simple PK/FK.** For instance, a confirmed order must have at least one line, or the owner must belong to the same tenant.
10. **Test with counterexamples, then optimize physically.** Test nonexistent owner codes, duplicate partial keys within one owner, and identical partial keys across different owners.

### Checklist Before Finalizing the Schema

| Question | Sign of a Correct Model |
| --- | --- |
| If the owner's key is removed, can the weak table still identify each row? | **No**, under ER partial-key identification |
| Can two different owners have the same partial key value? | **Yes**, when business rules allow it |
| Can two weak rows of the same owner share the same partial key? | **No** |
| Can a weak row lack an owner? | **No**, if it participates totally in the identifying relationship |
| Does the row's FK reference the entire owner key? | **Yes**, even if the parent key has multiple columns |
| Is owner data unnecessarily duplicated on every weak row? | Avoid when that attribute depends on the owner's key, unless historical snapshots are explicitly modeled |
| If using a generated id, is there still a UNIQUE constraint on owner + partial key? | **Yes**, if the business rule still holds |
| If the owner is deleted, what happens to children and history? | An explicit policy matching the lifecycle exists |

## 15. Common Mistakes

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Treating every table with an FK as a weak entity | Misclassifying DON_HANG just because it has ma_kh | Examine **identification mechanism**, not merely FK presence |
| Using so_dong as a standalone PK | Two orders cannot both have line number 1 | Use PK(ma_dh, so_dong) |
| Using table-wide UNIQUE(so_dong) | Wrong uniqueness scope | Use composite UNIQUE or PK scoped by owner |
| Using PK(id) only and dropping UNIQUE(ma_dh, so_dong) | Allows duplicate line numbers in the same order | Keep the business alternate key |
| Allowing ma_dh NULL on a weak line | Line can exist without an owner | Enforce NOT NULL and FK |
| Parent has a composite key but FK references only one column | Cannot pinpoint the right owner; risks cross-tenant leaks | Pass all parent key components |
| Using ma_sp in the line key without checking business rules | Cannot place the same product on two lines of an order | Identify lines with a stable partial key such as so_dong |
| Defaulting to ON DELETE CASCADE | Risks accidentally deleting historical data | Decide retention policy first |
| Assuming an FK guarantees every parent has children | Orders with zero lines can still exist | Add transaction/state controls when needed |
| Choosing a frequently reordered display field as the partial key | Every reordering triggers key updates | Separate stable identification from display position if needed |

### Additional Example: Hotels and Room Numbers

A hotel has a unique code **ma_ks**, and rooms are numbered **101**, **102** within each hotel. **PHONG** is a weak entity if the business identifies rooms by **(ma_ks, so_phong)**.

~~~~text
KHACH_SAN(ma_ks PK, ten_ks)
PHONG(ma_ks, so_phong, loai_phong, trang_thai)
PK(PHONG) = (ma_ks, so_phong)
FK(PHONG.ma_ks) → KHACH_SAN.ma_ks
~~~~

Room 101 at KS01 and room 101 at KS02 are allowed to coexist. Whether **so_phong** is a string or an integer depends on room-coding rules (some hotels use A101, B02), and does not change the requirement of **uniqueness within a hotel**.

### Additional Example: Employee Dependents

If an employee has multiple dependents, the system can assign **so_nguoi_phu_thuoc** within the scope of that employee:

~~~~text
NHAN_VIEN(ma_nv PK, ho_ten)
NGUOI_PHU_THUOC(ma_nv, so_nguoi_phu_thuoc, ho_ten, moi_quan_he)
PK = (ma_nv, so_nguoi_phu_thuoc)
FK ma_nv → NHAN_VIEN.ma_nv
~~~~

You should not use the **dependent's ho_ten** as the partial key if two dependents could share a name. A stable internal sequence number is usually safer. If the business later switches to identifying dependents with a global code, re-evaluate the classification and constraints rather than keeping the old model out of habit.

## 16. Practice Exercises with Answers

### Exercise 1 — Mapping Hotels and Rooms

Requirement: Each hotel has a unique ma_ks. Each room has a so_phong unique only within its hotel; every room must belong to a hotel. Identify strong/weak entities, partial key, PK, and FK.

**Answer:**

~~~~text
KHACH_SAN(ma_ks PK, ten_ks)                 -- strong entity
PHONG(ma_ks, so_phong, loai_phong)          -- weak entity
PK(PHONG) = (ma_ks, so_phong)
FK(PHONG.ma_ks) → KHACH_SAN.ma_ks
Partial key of PHONG = so_phong
~~~~

In SQL, set NOT NULL on ma_ks and so_phong; the composite PRIMARY KEY already implies NOT NULL for both columns.

### Exercise 2 — Why Can DON_HANG Still Be a Strong Entity?

Requirement: Each order has a system-wide unique ma_dh and always has ma_kh referencing a customer. A colleague claims DON_HANG is a weak entity simply because it has the FK ma_kh.

**Answer:** That remark is inaccurate. DON_HANG already has an independent identifier **ma_dh**. The foreign key and mandatory customer ownership reflect an association and existence dependency, not a need for **customer key + partial key** to identify the order. Under the given rules, DON_HANG can be modeled as a strong entity.

### Exercise 3 — Primary Key with the Wrong Scope

Proposal:

~~~~sql
CREATE TABLE dong_don_sai (
    ma_dh VARCHAR(20) NOT NULL REFERENCES don_hang(ma_dh),
    so_dong INTEGER PRIMARY KEY,
    ma_sp VARCHAR(20) NOT NULL
);
~~~~

**Question:** Where is this design wrong? How should it be fixed?

**Answer:** Placing PK on so_dong alone prevents two different orders from both having line number 1. Change it to **PRIMARY KEY(ma_dh, so_dong)** while keeping the FK on ma_dh, or use id as PK together with **UNIQUE(ma_dh, so_dong)**.

### Exercise 4 — Using a Surrogate Key While Preserving Business Rules

Proposal:

~~~~sql
CREATE TABLE dong_don_id_sai (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_dh VARCHAR(20) NOT NULL REFERENCES don_hang(ma_dh),
    so_dong INTEGER NOT NULL,
    ma_sp VARCHAR(20) NOT NULL
);
~~~~

**Question:** Even with PK(id), what is missing from this schema relative to the requirement “each line number appears at most once per order”?

**Answer:** It is missing **UNIQUE(ma_dh, so_dong)**. Add:

~~~~sql
ALTER TABLE dong_don_id_sai
ADD CONSTRAINT ak_dong_don_theo_don
UNIQUE (ma_dh, so_dong);
~~~~

Also add CHECK(so_dong > 0) if the numbering rule requires positive line numbers.

### Exercise 5 — Composite FK to Prevent Cross-Tenant Mix-Ups

Given HOA_DON(tenant_id, so_hd, ngay_lap) with PK(tenant_id, so_hd), and DONG_HOA_DON where so_dong is unique only within an invoice.

**Question:** What are the primary key and foreign key of DONG_HOA_DON?

**Answer:** **PK(tenant_id, so_hd, so_dong)** and **FOREIGN KEY(tenant_id, so_hd) REFERENCES HOA_DON(tenant_id, so_hd)**. Dropping tenant_id loses the condition that distinguishes invoices belonging to different tenants.

### Exercise 6 — Two Levels of Weak Entities

DU_AN has ma_du_an; each category has so_hang_muc within a project; each task has so_cong_viec within a category.

**Question:** If you only set PK(ma_du_an, so_cong_viec) on CONG_VIEC, what is missing?

**Answer:** **so_hang_muc** is missing. Task number 1 can appear in two different categories of the same project. The correct PK under the assumptions is **(ma_du_an, so_hang_muc, so_cong_viec)**; the composite FK to HANG_MUC must include **(ma_du_an, so_hang_muc)**.

### Exercise 7 — Choosing a Delete Policy

An order has already been invoiced and must be retained for history. Order lines are weak entities. A designer argues that because they are weak entities, the FK must use ON DELETE CASCADE.

**Answer:** Incorrect. A weak entity relies on its owner for identification, but **how history is retained** is a separate rule. For orders that must remain auditable, you can choose **RESTRICT** or prevent physical deletion via status/permissions; CASCADE is only sensible when the business allows deleting both the order and its lines.

### Exercise 8 — Total Participation and Empty Orders

The system uses PRIMARY KEY(ma_dh, so_dong) and FOREIGN KEY(ma_dh) on DONG_DON_HANG. However, an order in status **xac_nhan** can still exist with zero lines.

**Question:** Is this an FK bug? Where should it be enforced?

**Answer:** No. The FK only checks that **every line has a valid order**, not that **every order has lines**. The condition “only confirm orders that have at least one line” must be checked during the state transition, ideally within a transaction that prevents unintended concurrent modifications.

### Exercise 9 — Distinguishing a Junction Table from a Weak Entity

SINH_VIEN and LOP_HOC have an N–N relationship through DANG_KY(ma_sv, ma_lop, ngay_dang_ky). Each student enrolls at most once per class.

**Question:** Why does DANG_KY have PK(ma_sv, ma_lop) yet does not necessarily get depicted as a weak entity in every ER notation?

**Answer:** DANG_KY can be a **junction table** for an N–N relationship or an **associative entity**. A key formed by two FKs reflects the identity of **the association between two sides**, whereas a classical weak entity typically has one owner and a partial key. Conceptual classification depends on entity semantics and ER notation; a composite PK of two FKs alone is not enough to conclude it is a weak entity.

## 17. Key Rules to Remember

| Concept | How to Verify |
| --- | --- |
| **Strong entity** | Has its own identifying key, without borrowing an owner's key through an identifying relationship |
| **Weak entity** | Requires an owner and a partial key for identification in classical ER modeling |
| **Owner entity** | The entity providing the identifying key component for a weak entity |
| **Identifying relationship** | The relationship used as the basis to identify each weak instance |
| **Total participation of a weak entity** | Every weak record must be attached to an appropriate owner |
| **Partial key** | Distinguishes weak records only within the scope of the same owner |
| **PK of a traditional weak table** | Owner key **plus** partial key |
| **FK of a weak table** | References the full owner key, with required components |
| **Owner with composite key** | Propagates **all** key components to the weak table |
| **Multi-level weak entities** | Each level inherits its direct owner's key and adds its own partial key |
| **Surrogate PK for a weak table** | Still retain NOT NULL FK and UNIQUE on owner + partial key if required by business rules |
| **Having an FK does not imply weak** | Examine the identification mechanism, not just links or lifecycle dependency |
| **ON DELETE CASCADE** | A lifecycle policy, not a mandatory requirement for weak entities |

When converting ER diagrams into tables, start by asking **what information identifies an instance and within what scope that information is unique**. For strong entities, pick an independent primary key from suitable candidate keys. For weak entities, use **owner key plus partial key** for identification, while configuring foreign keys and non-NULL conditions. From that foundation, normalization analysis, business constraints, indexes, and physical schemas will have a clear basis for verification and evolution.
