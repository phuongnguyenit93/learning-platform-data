# Converting One-to-One and One-to-Many Relationships into Foreign Keys

## Learning Objectives

An entity–relationship (ER) diagram describes **entities** and the **multiplicities of relationships** between them, whereas a relational model requires enforceable tables, keys, and constraints. When mapping a **one-to-one (1:1)** or **one-to-many (1:N)** relationship to SQL tables, the most critical decision is **which table holds the foreign key**, followed by determining whether the relationship is mandatory and whether it requires uniqueness.

This lesson belongs to the **Relational Modeling** chapter of the **DATABASE_DATA_MODELING** module. The goal of the module is to build the skill of turning business requirements into clear data models—from entities, relationships, and constraints to normalization, keys, indexes, and physical schemas—and comparing relational, document, graph, and analytical models to select structures that are suitable, evolvable, and verifiable.

After this lesson, you will be able to:

1. Read multiplicities **0..1, 1..1, 0..N, 1..N** accurately and determine which side is “one” and which side is “many”.
2. Map a **1:N** relationship into a **foreign key on the N side**, distinguishing mandatory and optional relationships.
3. Map a **1:1** relationship using an **FK combined with UNIQUE** or a **shared primary key**, choosing the FK placement direction that fits the data lifecycle.
4. Explain accurately what **FOREIGN KEY**, **NOT NULL**, and **UNIQUE** can and cannot enforce, especially total participation on the **referenced side**.
5. Recognize cases requiring a **composite foreign key**, a relationship history table, or an alternative model driven by business requirements.
6. Validate the design with SQL statements, sample data, constraint-violating operations, and JOIN queries.

## 1. Reading Multiplicity and Optionality Correctly Before Placing a Foreign Key

A **relationship** in ER modeling specifies how instances of two entity types can relate to each other. Two pieces of information must be kept distinct:

- **Maximum multiplicity (cardinality):** at most one or many associated instances.
- **Minimum multiplicity (optionality):** whether at least one associated instance is mandatory.

| Notation | How to Read | Business Example |
| --- | --- | --- |
| **0..1** | Zero or at most one | An employee may not yet have an account issued |
| **1..1** | Mandatory, exactly one | Each order must belong to exactly one customer |
| **0..N** | Zero or many | A customer may have zero orders or many orders |
| **1..N** | At least one, potentially many | An active class must have at least one student |

**Example 1 — 1:N:** Each **DON_HANG** belongs to exactly one **KHACH_HANG**, while a customer can place **0..N** orders. We say **KHACH_HANG is the 1 side**, and **DON_HANG is the N side**.

**Example 2 — 1:1:** Each **TAI_KHOAN_NOI_BO** belongs to exactly one **NHAN_VIEN**, while an employee may have no account yet or at most one account. This is 1:1, yet participation is **asymmetric**: the account must have an employee, whereas the employee might not yet have an account.

### Reading an ER Diagram in Mermaid

~~~~mermaid
erDiagram
    KHACH_HANG ||--o{ DON_HANG : dat
    NHAN_VIEN ||--o| TAI_KHOAN : duoc_cap
~~~~

In this crow's-foot notation, **o{** means 0..N, **o|** means 0..1, and **||** means exactly one. Therefore:

- Each order belongs to **exactly one customer**, while each customer has **0..N orders**.
- Each account belongs to **exactly one employee**, while each employee has **0..1 account**.

When reading diagrams from other documentation, identify the exact notation used by the tool; never infer multiplicity merely from whether a line is drawn on the left or right.

## 2. What Does a Foreign Key Actually Guarantee?

A **foreign key (FK)** is an attribute or set of attributes in a **referencing table** (*child table*) pointing to an eligible key in a **referenced table** (*parent table*). For example:

~~~~text
KHACH_HANG(ma_kh PK, ho_ten)
DON_HANG(ma_dh PK, ma_kh FK, ngay_dat)

DON_HANG.ma_kh → KHACH_HANG.ma_kh
~~~~

In the design above:

- The FK ensures that any non-NULL **DON_HANG.ma_kh** value matches an existing customer code.
- **NOT NULL** on DON_HANG.ma_kh ensures an order cannot omit its customer code.
- The FK does not forbid **multiple orders having the same ma_kh**; that is precisely what 1:N requires.
- The FK **does not force every customer to have an order**: a customer who has never purchased remains valid.

If an FK permits NULL, SQL normally does not require rows containing NULL to match a parent record under standard checking rules. Thus, **an FK does not inherently express a mandatory relationship**; you must add NOT NULL whenever every child record must participate in the relationship.

An FK also **does not automatically express all multiplicities on the parent side**. For instance, merely adding an FK on DON_HANG cannot guarantee that every registered customer has at least one order. An “at least one child record” rule is a reverse existence constraint, which typically must be handled through business workflows or appropriate cross-table mechanisms.

## 3. Rules for Mapping a 1:N Relationship

### 3.1. Place the FK on the Many-Side Table

For a 1:N relationship between entities **A** (1 side) and **B** (N side), the standard relational mapping is:

1. Create table A with primary key **PK(A)**.
2. Create table B with its own primary key **PK(B)**.
3. **Add PK(A) into B** as one or more FK columns referencing A.
4. If **every B must belong to an A**, declare the required FK components as **NOT NULL**.
5. If **B may exist without an A**, allow the FK to be NULL when appropriate for the business.
6. **Do not place UNIQUE on the FK in B** if a single A is allowed to have multiple Bs.

Illustration:

~~~~text
KHACH_HANG(ma_kh PK, ho_ten)
            1
            |
            | place key ma_kh on the N side
            v
DON_HANG(ma_dh PK, ma_kh FK, ngay_dat)
            N
~~~~

Sample SQL:

~~~~sql
CREATE TABLE khach_hang (
    ma_kh VARCHAR(20) PRIMARY KEY,
    ho_ten VARCHAR(120) NOT NULL
);

CREATE TABLE don_hang (
    ma_dh VARCHAR(20) PRIMARY KEY,
    ma_kh VARCHAR(20) NOT NULL,
    ngay_dat DATE NOT NULL,
    CONSTRAINT fk_don_hang_khach
        FOREIGN KEY (ma_kh)
        REFERENCES khach_hang (ma_kh)
);
~~~~

A single customer **KH01** can appear in hundreds of DON_HANG rows; that does not violate the FK. Orders remain distinct thanks to the primary key ma_dh.

### 3.2. Why Not Put the Order FK Inside KHACH_HANG?

If you place a **ma_dh** column inside KHACH_HANG, each customer row only has room for one order code. Using a single-valued column like that is equivalent to modeling “a customer can have at most one order”, contradicting the requirement that customers can place multiple orders.

Workarounds such as storing a string like **DH01,DH02,DH03** in one customer cell also break querying, FK enforcement, and normalization. The proper way is to let **multiple DON_HANG rows reference the same KHACH_HANG**, as the child table of a 1:N relationship.

### 3.3. Optionality on the Many Side

An **NHAN_VIEN** (employee) might temporarily not be assigned to any **PHONG_BAN** (department), but each assigned employee belongs to at most one current department. A department can have many employees.

~~~~sql
CREATE TABLE phong_ban (
    ma_phong VARCHAR(20) PRIMARY KEY,
    ten_phong VARCHAR(120) NOT NULL
);

CREATE TABLE nhan_vien (
    ma_nv VARCHAR(20) PRIMARY KEY,
    ho_ten VARCHAR(120) NOT NULL,
    ma_phong VARCHAR(20),
    FOREIGN KEY (ma_phong) REFERENCES phong_ban(ma_phong)
);
~~~~

Here **ma_phong can be NULL** to represent “unassigned”. If the requirement changes to “every employee must belong to exactly one department”, allowing NULL is no longer appropriate; you must declare **ma_phong NOT NULL** and likely migrate or fix existing records before applying the constraint.

Avoid using dummy values like **'NONE'** or **'0'** as a fake department code just to avoid NULL, unless the organization genuinely manages a real department with that code.

## 4. Rules for Mapping a 1:1 Relationship

A 1:1 relationship means **each instance on either side links to at most one instance on the other side**. A plain FK alone **is not enough**: without a uniqueness constraint, multiple child rows could reference the same parent row, turning it into 1:N.

### 4.1. FK Combined with UNIQUE

For example, each **NHAN_VIEN** is issued at most one **TAI_KHOAN** (account), and every account must belong to exactly one employee.

~~~~text
NHAN_VIEN(ma_nv PK, ho_ten)
TAI_KHOAN(ma_tk PK, ma_nv FK UNIQUE NOT NULL, ten_dang_nhap)
~~~~

SQL:

~~~~sql
CREATE TABLE nhan_vien (
    ma_nv VARCHAR(20) PRIMARY KEY,
    ho_ten VARCHAR(120) NOT NULL
);

CREATE TABLE tai_khoan (
    ma_tk BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_nv VARCHAR(20) NOT NULL UNIQUE,
    ten_dang_nhap VARCHAR(60) NOT NULL UNIQUE,
    CONSTRAINT fk_tai_khoan_nhan_vien
        FOREIGN KEY (ma_nv)
        REFERENCES nhan_vien (ma_nv)
        ON DELETE RESTRICT
);
~~~~

Each constraint has a distinct job:

| Constraint | What It Guarantees |
| --- | --- |
| TAI_KHOAN.ma_nv is an FK | Every account must point to a real employee when a code is present |
| TAI_KHOAN.ma_nv NOT NULL | Every account must have an employee code |
| TAI_KHOAN.ma_nv UNIQUE | No two accounts can point to the same employee |
| TAI_KHOAN.ma_tk PRIMARY KEY | Each account has its own identifier |
| NHAN_VIEN.ma_nv PRIMARY KEY | Each employee has a unique identifier |

Thus, **each account belongs to exactly one employee**, and **each employee has at most one account**. An employee without an account remains valid; UNIQUE on TAI_KHOAN does not force creating accounts for all employees.

### 4.2. Choosing FK Direction Based on Mandatory Participation and Lifecycle

In a 1:1 relationship, **the FK can be placed in either table**, but the chosen direction affects the number of NULL values, record creation order, and ability to express mandatory participation.

| Situation | Common Choice | Reason |
| --- | --- | --- |
| An employee may lack an account; an account must have an employee | Place UNIQUE NOT NULL FK in TAI_KHOAN | Avoids a nullable column in NHAN_VIEN; mandatory on the account side |
| An employee may be assigned a parking spot; a spot may also be empty | Place nullable UNIQUE FK on one side based on lifecycle, or a separate assignment table if history is needed | Both sides are optional |
| Detailed profile has no meaning separate from the employee | Use a **shared primary key**, where the profile's PK is also its FK | Expresses identity tightly coupled to the employee |
| Two data parts are always created together with identical lifecycle and security | Consider storing in the same table | Avoids unnecessary splitting |

Do not choose the FK direction simply because one table is drawn on the left or right. Ask **which table can exist first**, **which object mandates the other**, **how deletes/updates propagate**, and **which table holds sensitive data needing protection**.

### 4.3. Shared Primary Key

If **HO_SO_NHAN_VIEN** (employee profile) has at most one record per employee and needs no independent identifier:

~~~~sql
CREATE TABLE ho_so_nhan_vien (
    ma_nv VARCHAR(20) PRIMARY KEY,
    ngay_sinh DATE,
    dia_chi VARCHAR(250),
    CONSTRAINT fk_ho_so_nhan_vien
        FOREIGN KEY (ma_nv)
        REFERENCES nhan_vien (ma_nv)
        ON DELETE CASCADE
);
~~~~

The **ho_so_nhan_vien.ma_nv** column plays **two roles**: PK of the profile and FK to the employee. Because it is the PK, ma_nv cannot be NULL or duplicated; because it is an FK, ma_nv must reference a real employee. Consequently, an employee has **0 or 1 profile**, and each profile belongs to **exactly one employee**.

This is a clean mapping when the supplementary record is identified by its owner. However, a **shared PK does not automatically force every employee to have a profile**. Enforcing participation on both sides requires another mechanism or considering merging the data when appropriate.

### 4.4. Nullable UNIQUE FK and Multiple NULL Values

Suppose **CHO_DO** (parking spot) has a **ma_nv** column indicating the employee currently assigned to the spot, while spots can be empty:

~~~~sql
CREATE TABLE cho_do (
    ma_cho VARCHAR(20) PRIMARY KEY,
    ma_nv VARCHAR(20) UNIQUE
        REFERENCES nhan_vien(ma_nv)
);
~~~~

In PostgreSQL, a standard UNIQUE constraint **allows multiple rows with ma_nv = NULL**. Therefore, multiple empty spots are valid, while an employee cannot be assigned two spots with a non-NULL ma_nv.

If the business wants to state that **every parking spot is always assigned to exactly one employee**, then ma_nv must be NOT NULL. However, that requirement might be unrealistic if spots sit empty during operations. Allowing NULL is a decision driven by **minimum multiplicity**, not a technical flaw.

## 5. What FK, UNIQUE, and NOT NULL Do Not Guarantee

### 5.1. They Do Not Guarantee the Parent Side Has Children

In 1:N:

~~~~text
KHACH_HANG (1) ← (N) DON_HANG
~~~~

The FK from DON_HANG ensures **each order has a valid customer**, not that **every customer has at least one order**.

Similarly, in 1:1, a UNIQUE NOT NULL FK on TAI_KHOAN guarantees **an account always belongs to an employee** and **an employee has at most one account**, but it **does not** guarantee **every employee has an account**.

This is the difference between **total participation on the FK-bearing side** and **total participation on the referenced side**.

### 5.2. They Do Not Automatically Express 1..N on the Parent Side

Suppose a problem requires “every **started LOP_HOC** must have at least one **HOC_VIEN** (student)”, while each student belongs to exactly one class:

- The FK in HOC_VIEN checks that a student references an existing class.
- NOT NULL on HOC_VIEN.ma_lop ensures every student has a class.
- No simple FK constraint on the student table automatically guarantees **every started class has at least one student**.

Therefore, you must check when transitioning the class status to **da_khai_giang**, inside a transaction or appropriate DB mechanism; you must also guard against transferring or deleting the last student while a class is active.

A query to detect started but empty classes might look like:

~~~~sql
-- Syntax illustration assuming two tables lop_hoc and hoc_vien.
SELECT l.ma_lop
FROM lop_hoc AS l
WHERE l.trang_thai = 'da_khai_giang'
  AND NOT EXISTS (
      SELECT 1
      FROM hoc_vien AS hv
      WHERE hv.ma_lop = l.ma_lop
  );
~~~~

The query above **detects** violations if data already exists; by itself it does not **prevent** writes. You must establish an enforcement mechanism to protect data under concurrent transactions.

### 5.3. 1:1 Mandatory on Both Sides

A 1:1 requirement may state “every A must have exactly one B and every B must have exactly one A”. Placing a UNIQUE NOT NULL FK on B only enforces **every B has exactly one A** and **every A has at most one B**; it does not yet enforce **every A has at least one B**.

There are three ways to handle this depending on needs:

1. **Merge into one table** when both parts share the same identity, the same lifecycle, all attributes are required or permitted together, and there is no clear reason to separate them.
2. **Split into two tables with a shared PK** and use a transactional creation workflow, checking the mandatory condition at the appropriate business state.
3. **Split with specialized cross-table constraints**, such as triggers or deferred constraints if supported and properly implemented by the DBMS; concurrency conditions and check timing must be carefully addressed.

**Do not blindly add two circular FKs pointing at each other**, because doing so complicates inserts, deletes, and data management while still requiring careful understanding of constraint checking behavior. When the business genuinely mandates bidirectional existence at all times, the design should be reviewed specifically.

## 6. Where Should Relationship Attributes Be Placed?

### 6.1. Attributes of a 1:N Relationship

Suppose an employee belongs to one current department and has **ngay_nhan_phong** (start date). If this is the start date of **the current department**, the relationship attribute can sit alongside the FK on the N-side table:

~~~~text
PHONG_BAN(ma_phong PK, ten_phong)
NHAN_VIEN(ma_nv PK, ma_phong FK, ngay_nhan_phong)
~~~~

However, if you need **the history of an employee transferring across multiple departments**, a single current ma_phong column and ngay_nhan_phong only describe the present and **are insufficient for prior assignments**. In that case, you can create a relationship event table:

~~~~text
LICH_SU_PHAN_CONG(
    ma_phan_cong PK,
    ma_nv FK,
    ma_phong FK,
    tu_ngay,
    den_ngay
)
~~~~

This table stores **multiple association occurrences over time**. You must clearly define whether date ranges may overlap, whether an employee can be in multiple departments simultaneously, and how the current assignment is identified.

### 6.2. Attributes of a 1:1 Relationship

For instance, a parking spot is assigned to an employee along with **ngay_bat_dau** (start date). If only current information is needed, ngay_bat_dau can be placed in the FK-bearing table or in a one-to-one PHAN_CHO_DO table. If you need to record parking spot changes over time, a dedicated history model with event identification is needed.

**Choosing which table holds an attribute** should depend on whether the information belongs to an entity or to **an occurrence of the relationship**. Do not place historical attributes on a current-state entity and hope an FK will capture past transitions.

## 7. When Not to Use Simple 1:1 or 1:N Mapping

| Real-World Requirement | Point to Re-examine |
| --- | --- |
| An order contains many products, and a product appears in many orders | This is **N:N**, typically requiring a detail/junction table |
| An employee changes departments multiple times and history is needed | The relationship **changes over time**, requiring a history table |
| Department codes are unique only within a tenant | The FK may need **multiple columns**, including tenant_id |
| Both sides of a 1:1 are mandatory | A one-way FK does not guarantee both directions have minimum 1 |
| Multiple people share a single account | No longer 1:1; re-check business multiplicity |
| An invoice has multiple line numbers unique only within the invoice | This may be a **weak entity** with composite PK (ma_hd, so_dong), not just a simple FK |

Table count is not a measure of correctness. The goal of mapping is to preserve **entity semantics**, **relationship multiplicities**, **participation constraints**, and query needs while keeping the model easy to extend as requirements evolve.

## 8. Mapping When the 1-Side Key Has Multiple Columns

Not every entity has a single-column primary key. Suppose a system serves multiple companies (*tenants*); department code **KT** can exist in multiple companies, so the department identifier is **(tenant_id, ma_phong)**.

A department within a tenant can have many employees; each employee belongs to a department of the same tenant:

~~~~text
PHONG_BAN(tenant_id, ma_phong, ten_phong)
PK = (tenant_id, ma_phong)

NHAN_VIEN(tenant_id, ma_nv, ma_phong, ho_ten)
PK = (tenant_id, ma_nv)
FK (tenant_id, ma_phong)
    → PHONG_BAN(tenant_id, ma_phong)
~~~~

The 1:N mapping here still follows the rule of **pushing the 1-side key down to the N side**, but you must carry over **all components** of the key.

~~~~sql
CREATE TABLE phong_ban (
    tenant_id BIGINT NOT NULL,
    ma_phong VARCHAR(20) NOT NULL,
    ten_phong VARCHAR(120) NOT NULL,
    CONSTRAINT pk_phong_ban PRIMARY KEY (tenant_id, ma_phong)
);

CREATE TABLE nhan_vien (
    tenant_id BIGINT NOT NULL,
    ma_nv VARCHAR(20) NOT NULL,
    ma_phong VARCHAR(20) NOT NULL,
    ho_ten VARCHAR(120) NOT NULL,
    CONSTRAINT pk_nhan_vien PRIMARY KEY (tenant_id, ma_nv),
    CONSTRAINT fk_nv_phong
        FOREIGN KEY (tenant_id, ma_phong)
        REFERENCES phong_ban (tenant_id, ma_phong)
);
~~~~

**Do not split** a composite FK into a separate FK on tenant_id and a separate FK on ma_phong: each individual column does not identify a department; worse, if pointing to different parent tables, they do not ensure the department–tenant pair belongs to the same row.

### Mapping 1:1 with a Composite Key

If each employee in the model above has at most one supplementary profile:

~~~~sql
CREATE TABLE ho_so_nhan_vien (
    tenant_id BIGINT NOT NULL,
    ma_nv VARCHAR(20) NOT NULL,
    ngay_sinh DATE,
    dia_chi VARCHAR(250),
    CONSTRAINT pk_ho_so_nv PRIMARY KEY (tenant_id, ma_nv),
    CONSTRAINT fk_ho_so_nv
        FOREIGN KEY (tenant_id, ma_nv)
        REFERENCES nhan_vien (tenant_id, ma_nv)
        ON DELETE CASCADE
);
~~~~

This is a **composite shared primary key** model: the same pair (tenant_id, ma_nv) serves as the profile's PK and as the FK to the employee. It guarantees every profile has exactly one valid employee and every employee has at most one profile. An employee without a profile is still permitted to exist.

### Referencing an Alternate Key

If **KHACH_HANG** has PK id and business code **ma_khach UNIQUE NOT NULL**, then DON_HANG can also reference **ma_khach**:

~~~~sql
-- Standalone DDL used to illustrate an FK pointing to an alternate key.
CREATE TABLE khach_hang_theo_id (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_khach VARCHAR(20) NOT NULL UNIQUE,
    ho_ten VARCHAR(100) NOT NULL
);

CREATE TABLE don_hang_theo_ma (
    ma_dh VARCHAR(20) PRIMARY KEY,
    ma_khach VARCHAR(20) NOT NULL
        REFERENCES khach_hang_theo_id(ma_khach)
);
~~~~

An FK does not have to point to a PK if the target column has a qualifying unique constraint in the DBMS. However, if business codes change frequently, referencing a stable id may be simpler. **The 1:N multiplicity** stays the same whether the FK uses the primary key or an alternate key.

## 9. Complete Practical Example: 1:N and 1:1 in PostgreSQL

The SQL in this section is **a standalone script**; run it from scratch on an empty test database. If you already created tables with the same names in earlier illustrative snippets, use a different schema or test database. The DDL snippets in earlier sections primarily explain individual scenarios and are not meant to be run consecutively together.

### 9.1. Defining the Model and Multiplicities

| Relationship | Side A | Side B | Rule |
| --- | --- | --- | --- |
| Customer places orders | KHACH_HANG | DON_HANG | Each order has **1** customer; each customer has **0..N** orders |
| Employee is issued account | NHAN_VIEN | TAI_KHOAN | Each account has **1** employee; each employee has **0..1** account |

Diagram marking PK, FK, and UK (UNIQUE constraint):

~~~~mermaid
erDiagram
    KHACH_HANG ||--o{ DON_HANG : dat
    NHAN_VIEN ||--o| TAI_KHOAN : duoc_cap

    KHACH_HANG {
        varchar ma_kh PK
        varchar ho_ten
    }
    DON_HANG {
        varchar ma_dh PK
        varchar ma_kh FK
        date ngay_dat
        decimal tong_tien
    }
    NHAN_VIEN {
        varchar ma_nv PK
        varchar ho_ten
    }
    TAI_KHOAN {
        bigint ma_tk PK
        varchar ma_nv FK,UK
        varchar ten_dang_nhap UK
    }
~~~~

### 9.2. Creating Tables and Constraints

~~~~sql
CREATE TABLE khach_hang (
    ma_kh VARCHAR(20) PRIMARY KEY,
    ho_ten VARCHAR(120) NOT NULL
);

CREATE TABLE don_hang (
    ma_dh VARCHAR(20) PRIMARY KEY,
    ma_kh VARCHAR(20) NOT NULL,
    ngay_dat DATE NOT NULL,
    tong_tien NUMERIC(12, 2) NOT NULL,
    CONSTRAINT ck_don_hang_tong_tien CHECK (tong_tien >= 0),
    CONSTRAINT fk_don_hang_khach
        FOREIGN KEY (ma_kh)
        REFERENCES khach_hang (ma_kh)
        ON DELETE RESTRICT
);

CREATE TABLE nhan_vien (
    ma_nv VARCHAR(20) PRIMARY KEY,
    ho_ten VARCHAR(120) NOT NULL
);

CREATE TABLE tai_khoan (
    ma_tk BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_nv VARCHAR(20) NOT NULL,
    ten_dang_nhap VARCHAR(60) NOT NULL,
    CONSTRAINT ak_tai_khoan_nhan_vien UNIQUE (ma_nv),
    CONSTRAINT ak_tai_khoan_dang_nhap UNIQUE (ten_dang_nhap),
    CONSTRAINT fk_tai_khoan_nhan_vien
        FOREIGN KEY (ma_nv)
        REFERENCES nhan_vien (ma_nv)
        ON DELETE RESTRICT
);
~~~~

In DON_HANG, **ma_kh is not UNIQUE** because a customer can place multiple orders. In TAI_KHOAN, **ma_nv is UNIQUE** because an employee can have at most one account.

### 9.3. Inserting Valid Data

~~~~sql
INSERT INTO khach_hang (ma_kh, ho_ten) VALUES
    ('KH01', 'Nguyễn An'),
    ('KH02', 'Trần Bình'),
    ('KH03', 'Lê Chi');

INSERT INTO don_hang (ma_dh, ma_kh, ngay_dat, tong_tien) VALUES
    ('DH01', 'KH01', DATE '2026-10-01', 200000),
    ('DH02', 'KH01', DATE '2026-10-02', 350000),
    ('DH03', 'KH02', DATE '2026-10-03', 100000);

INSERT INTO nhan_vien (ma_nv, ho_ten) VALUES
    ('NV01', 'Mai Minh'),
    ('NV02', 'Vũ Lan'),
    ('NV03', 'Hoàng Khoa');

INSERT INTO tai_khoan (ma_nv, ten_dang_nhap) VALUES
    ('NV01', 'mai.minh'),
    ('NV03', 'hoang.khoa');
~~~~

The system allows:

- Two orders DH01 and DH02 both belonging to KH01 (**1:N**).
- Customer KH03 having no orders yet (**0..N on the customer side**).
- Employee NV02 having no account yet (**0..1 on the employee side**).

### 9.4. Verifying with JOIN Queries

**Count orders per customer**, including customers who have not purchased yet:

~~~~sql
SELECT
    kh.ma_kh,
    kh.ho_ten,
    COUNT(dh.ma_dh) AS so_don
FROM khach_hang AS kh
LEFT JOIN don_hang AS dh ON dh.ma_kh = kh.ma_kh
GROUP BY kh.ma_kh, kh.ho_ten
ORDER BY kh.ma_kh;
~~~~

| ma_kh | ho_ten | so_don |
| --- | --- | ---: |
| KH01 | Nguyễn An | 2 |
| KH02 | Trần Bình | 1 |
| KH03 | Lê Chi | 0 |

Choose **COUNT(dh.ma_dh)** because ma_dh is a non-NULL primary key on the child table. If you use COUNT(*) on a LEFT JOIN, customer KH03 still produces a result row with NULL order columns and would mistakenly be counted as having one order.

**List each employee's account**, including those without one:

~~~~sql
SELECT
    nv.ma_nv,
    nv.ho_ten,
    tk.ten_dang_nhap
FROM nhan_vien AS nv
LEFT JOIN tai_khoan AS tk ON tk.ma_nv = nv.ma_nv
ORDER BY nv.ma_nv;
~~~~

| ma_nv | ho_ten | ten_dang_nhap |
| --- | --- | --- |
| NV01 | Mai Minh | mai.minh |
| NV02 | Vũ Lan | NULL |
| NV03 | Hoàng Khoa | hoang.khoa |

The NULL value in NV02's result column happens because **LEFT JOIN found no matching account**; it does not mean the TAI_KHOAN table contains a record with a NULL ma_nv. In fact, TAI_KHOAN.ma_nv is NOT NULL.

### 9.5. Testing Violating Data

The statements below **intentionally fail**; run each one individually against the loaded data to observe constraint enforcement:

~~~~sql
-- FK violation: customer KH999 does not exist.
INSERT INTO don_hang (ma_dh, ma_kh, ngay_dat, tong_tien)
VALUES ('DH99', 'KH999', DATE '2026-10-04', 1000);

-- NOT NULL violation: every order must have a customer.
INSERT INTO don_hang (ma_dh, ma_kh, ngay_dat, tong_tien)
VALUES ('DH98', NULL, DATE '2026-10-04', 1000);

-- 1:1 UNIQUE violation: NV01 already has an account.
INSERT INTO tai_khoan (ma_nv, ten_dang_nhap)
VALUES ('NV01', 'mai.minh.phu');

-- FK violation: NV999 does not exist.
INSERT INTO tai_khoan (ma_nv, ten_dang_nhap)
VALUES ('NV999', 'nv.khong.ton.tai');

-- NOT NULL violation: an account must have an employee.
INSERT INTO tai_khoan (ma_nv, ten_dang_nhap)
VALUES (NULL, 'khong.co.nhan.vien');
~~~~

Conversely, **a new order DH04 with ma_kh = KH01** is valid because the customer–order relationship is 1:N; the same customer code appearing in multiple orders matches the business rules:

~~~~sql
INSERT INTO don_hang (ma_dh, ma_kh, ngay_dat, tong_tien)
VALUES ('DH04', 'KH01', DATE '2026-10-04', 50000);
~~~~

## 10. Delete and Update Policies on Referenced Keys

When adding an FK, decide **what happens if a 1-side record is deleted or its key changes**.

| Policy | Behavior | Usage Guidance |
| --- | --- | --- |
| **ON DELETE RESTRICT** | Blocks deleting a 1-side record still referenced | Customers with finalized orders, employees with retained records |
| **ON DELETE NO ACTION** | Prevents transaction from ending with an FK violation; check timing can differ from RESTRICT with deferred constraints | Transactions updating multiple tables |
| **ON DELETE CASCADE** | Deletes FK-side rows when the 1-side record is deleted | Subordinate data that genuinely need not survive independently |
| **ON DELETE SET NULL** | Sets the FK in child records to NULL | **Optional** links where the FK column allows NULL |
| **ON UPDATE CASCADE** | Automatically updates child FKs when parent key changes | Business codes permitted to change |

In the DON_HANG.ma_kh NOT NULL example, using **SET NULL** when deleting a customer would conflict with the rule that orders must have a customer. **CASCADE** could wipe out historical orders, so do not pick it merely for convenience.

In 1:1, if TAI_KHOAN must belong to an employee, deleting an employee who has an account needs a clear policy: block deletion, delete the account alongside the employee, or use an inactive status. No single policy fits every system.

**ON UPDATE CASCADE** can be appropriate if an FK references a mutable business code. However, technical identifiers used as PKs should generally remain immutable; changing keys can ripple across many tables and integrations.

## 11. Foreign Keys, Unique Constraints, and Indexes

**Key constraints** express data correctness; **indexes** serve lookup performance and can help enforce constraints.

In PostgreSQL:

- PRIMARY KEY and UNIQUE typically create corresponding unique indexes.
- Declaring a FOREIGN KEY on a child table **does not automatically create an index on the FK column**.
- For 1:N, consider an index on the many-side FK when queries frequently filter by the 1 side or when parent deletes/updates are frequent.
- For 1:1, the index created by UNIQUE on the FK column already supports queries looking up the child row by parent key.

Example for DON_HANG:

~~~~sql
CREATE INDEX ix_don_hang_ma_kh
    ON don_hang (ma_kh);
~~~~

This is a **physical decision** and does not turn 1:N into 1:1. Conversely, adding **UNIQUE(ma_kh)** to DON_HANG is a **logical constraint** change that accidentally restricts each customer to at most one order.

Do not create indexes on every FK out of habit. Evaluate table size, actual queries, existing indexes, execution plans, and write overhead before deciding.

## 12. Quick Decision Table When Mapping Relationships

Before turning an ER connector line into an FK column, clearly identify **maximum multiplicity**, **minimum multiplicity**, and **which table carries the FK**. The table below assumes A is the parent/referenced side and B is the child/FK-bearing side.

| Business Relationship | Rule in Table B | What SQL Enforces Directly | What Still Needs Consideration |
| --- | --- | --- | --- |
| A 1 — B N, every B must have A | FK to A **NOT NULL**, **not UNIQUE** | Every B has an existing A; multiple Bs share A | Must every A have at least one B? |
| A 1 — B N, B may lack A | FK to A **nullable**, **not UNIQUE** | Every B has 0 or 1 A; each A has many Bs | What does NULL mean in the business? |
| A 1 — B 1, B must have A | FK to A **UNIQUE NOT NULL** | Every B has exactly one A; each A has at most one B | Is every A required to have a B? |
| A 1 — B 1, B may lack A | FK to A **UNIQUE nullable** | Every B has at most one A; each A has at most one B | NULL semantics and link assignment timing |
| B uses A's identifier for a 1:1 extension | PK(B) is also FK to A | B always has A and A has at most one B | Mandatory existence of B for A |
| Every A must have at least one B | FK in B as 1:N, plus parent-side existence check | Enforces B → A direction | Cross-table/transaction rule needed for A → at least one B |

**How to read this:** An FK in B pointing to a row in A identifies **one** A for each B. To enforce the reverse direction “an A has at most one B” in 1:1, you need **UNIQUE on B's FK**. To enforce “B must have A”, you need **NOT NULL on B's FK**. Meanwhile, “A must have B” is a separate rule that does not arise automatically from those two constraints.

### Counterexample for 1:1

Suppose we have:

~~~~text
NHAN_VIEN:
NV01, NV02

TAI_KHOAN:
TK01 → NV01
~~~~

Row TK01 has a valid NOT NULL FK, and UNIQUE(ma_nv) is also valid. Yet NV02 does not have an account. If the requirement is **0..1 account per employee**, the data is valid. If the requirement is **1..1 account per employee**, the data violates a business rule **not enforced by a simple FK and UNIQUE alone**.

## 13. Common Design Mistakes

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Placing the FK on the 1 side when the relationship is 1:N | Each 1-side row can only point to one N-side row | Move the FK to the N side |
| Placing UNIQUE on the N-side FK | Accidentally turns 1:N into at most 1:1 | Remove UNIQUE if the business allows multiple Bs per A |
| Mapping 1:1 with an FK without UNIQUE | Multiple B rows can point to the same A | Add UNIQUE or use a PK that is also an FK |
| Mapping a mandatory relationship with a nullable FK | B can exist without A | Add NOT NULL matching minimum multiplicity |
| Adding NOT NULL to an optional relationship's FK | Cannot create records before the link is assigned | Allow NULL if the business genuinely permits it |
| Assuming UNIQUE NOT NULL FK enforces bidirectional mandatory 1:1 | Side A can still exist without B | Merge tables or add A-side enforcement |
| Using a single-column FK for a tenant-scoped composite parent key | Fails to pinpoint the right parent, risks cross-tenant leaks | Reference the entire composite key |
| Storing comma-separated child IDs in the parent table | Cannot validate each ID via standard FKs | Use rows in an N-side child table |
| Using ON DELETE CASCADE out of convenience | Risks losing transactional data needed for audit trails | Define lifecycle and delete policies |
| Using SET NULL with a mandatory NOT NULL FK | Delete action conflicts with the constraint | Use another policy or revisit optionality |
| Storing historical attributes alongside a current-state FK | Loses prior associations | Create a history/event table when needed |
| Assuming any two tables with two FKs form an N:N relationship | Confuses 1:1 or 1:N with an N:N junction table | Verify multiplicities and the identity of the association event |

### Special Case: A Junction Table Appears When History Is Needed

The relationship “employee belongs to department” at a **single point in time** is usually 1:N, which can use an FK on NHAN_VIEN. However, “which departments an employee **has belonged to**” can be N:N over history. An employee has belonged to many departments, a department has had many employees, and each assignment can have start/end dates. Therefore, an associative history table is appropriate.

This **does not invalidate** the 1:N mapping rule. It shows that before mapping, you must clarify the **point in time and event scope** described by the business statement.

## 14. Workflow from ER to Relational Schema

You can apply the following workflow to a real problem:

1. **Write both directions of the business rule.** For example, “each order has exactly one customer” **and** “each customer can have many orders”. Never write just one direction.
2. **Determine minimum and maximum multiplicity on each side.** Explicitly note 0..1, 1..1, 0..N, or 1..N.
3. **Identify each entity's keys.** Ensure the referenced side has a PK or suitable unique key.
4. **If 1:N, place the FK on the N side.** Do not place UNIQUE on the FK unless business rules change.
5. **If 1:1, choose the FK direction.** Prefer the direction that expresses the mandatory side via a NOT NULL FK and avoids unnecessary NULLs; consider a shared PK.
6. **Map minimum multiplicity to NOT NULL where appropriate.** For optional links on the FK-bearing side, permit NULL as designed.
7. **Address remaining total-participation rules.** If the parent side must have children, define checks during creation, state transitions, deletion, or reassignment.
8. **Specify key-change and deletion policies.** Choose RESTRICT, CASCADE, SET NULL, or an appropriate lifecycle solution.
9. **Check composite keys and data scope.** In multi-tenant systems, prevent cross-boundary references caused by missing key components.
10. **Create counterexamples and test in SQL.** Test orphan child records, duplicate FKs in 1:1, valid repeated FKs in 1:N, and unlinked records.
11. **Evaluate queries and indexes.** After the logical model is sound, measure common queries and add indexes if needed.

## 15. Self-Check Exercises with Answers

### Exercise 1 — Publishers and Books: 1:N

Each book must have exactly one publisher; each publisher can have 0 or many books. Given two tables NHA_XUAT_BAN(ma_nxb, ten_nxb) and SACH(ma_sach, tieu_de).

**Requirement:** State the 1 side, N side, FK placement, and required constraints.

**Answer:** NHA_XUAT_BAN is the 1 side, SACH is the N side. Add SACH.ma_nxb **NOT NULL REFERENCES NHA_XUAT_BAN(ma_nxb)**. **Do not place UNIQUE** on SACH.ma_nxb because multiple books can share a publisher. Each publisher is not required to have books.

### Exercise 2 — Inferring Multiplicity from DDL

~~~~sql
CREATE TABLE a (
    id BIGINT PRIMARY KEY
);

CREATE TABLE b (
    id BIGINT PRIMARY KEY,
    a_id BIGINT NOT NULL UNIQUE REFERENCES a(id)
);
~~~~

**Question:** Is the enforced relationship between A and B 1:N or 1:1? Can an A exist without a B?

**Answer:** This is **1:1 with B mandatory and A optional**: every B points to exactly one A; every A has at most one B. An A can exist without a B because no constraint forces A to appear in table B.

### Exercise 3 — Missing UNIQUE in 1:1

Suppose table TAI_KHOAN(ma_tk PK, ma_nv NOT NULL FK) is missing UNIQUE on ma_nv, while the requirement states each employee has at most one account.

**Question:** What bad data can occur? How do you fix it in SQL?

**Answer:** Two accounts with different ma_tk values could share the same ma_nv. Once existing data has no duplicates, you can add:

~~~~sql
ALTER TABLE tai_khoan
ADD CONSTRAINT ak_tai_khoan_nhan_vien UNIQUE (ma_nv);
~~~~

If the table already contains duplicate data, resolve violating records before adding the constraint.

### Exercise 4 — Optional Relationship on the N Side

An employee may not yet be assigned to a department; a department can have many employees. Given PHONG_BAN(ma_phong PK), NHAN_VIEN(ma_nv PK, ma_phong).

**Question:** Should NHAN_VIEN.ma_phong be declared NOT NULL? Is UNIQUE needed?

**Answer:** Do not set NOT NULL if unassigned employees are still allowed; ma_phong should be a **nullable** FK. Do not add UNIQUE because many employees can share a department. Only if the rule changes to “every employee must have a department” should you consider NOT NULL after cleaning existing data.

### Exercise 5 — Parking Spots: 1:1 Optional on Both Sides

An employee has at most one parking spot; a parking spot has at most one employee; many spots may be empty. Table CHO_DO(ma_cho PK, ma_nv) stores the assigned employee.

**Question:** What constraints are needed on ma_nv? Can there be two rows with ma_nv = NULL?

**Answer:** You need **UNIQUE(ma_nv)** and an FK to NHAN_VIEN(ma_nv), while allowing ma_nv to be **NULL** to represent empty spots. Under standard PostgreSQL UNIQUE, **multiple NULLs are allowed**. Two empty spots do not violate 1:1; an employee cannot be assigned two spots with a non-NULL employee code.

### Exercise 6 — 1:1 Mandatory on Both Sides

Every employee must have exactly one profile, and every profile must belong to exactly one employee. Table HO_SO_NHAN_VIEN(ma_nv PK FK) already exists.

**Question:** Can a new NHAN_VIEN be created without a HO_SO_NHAN_VIEN? Why?

**Answer:** **Yes**, because a PK that is also an FK on the profile table only blocks **profiles without an employee** and **two profiles for the same employee**; it does not force every employee to have a profile. If the business mandates both sides, consider merging tables or controlling creation and deletion through transactions and appropriate cross-table constraints.

### Exercise 7 — Tenant-Scoped Composite FK

Department codes are unique only within each company. PHONG_BAN has PK(tenant_id, ma_phong), and NHAN_VIEN has tenant_id and ma_phong.

**Question:** Which columns must the FK of NHAN_VIEN include? Can ma_phong alone be used?

**Answer:** You need **FOREIGN KEY (tenant_id, ma_phong) REFERENCES PHONG_BAN(tenant_id, ma_phong)**. Using ma_phong alone omits an identifying component and risks mistakenly referencing a same-named department in another company.

### Exercise 8 — Distinguishing COUNT on LEFT JOIN

KHACH_HANG has KH01 and KH02; DON_HANG only has two orders, both belonging to KH01. Query:

~~~~sql
SELECT kh.ma_kh, COUNT(*) AS so_don
FROM khach_hang AS kh
LEFT JOIN don_hang AS dh ON dh.ma_kh = kh.ma_kh
GROUP BY kh.ma_kh;
~~~~

**Question:** Why is KH02 counted as 1? What needs to be fixed?

**Answer:** LEFT JOIN creates one result row for KH02 despite having no orders, with NULLs in all DON_HANG columns. COUNT(*) counts that row. Replace **COUNT(*)** with **COUNT(dh.ma_dh)**, because ma_dh is a non-NULL primary key and is present only when an actual order exists.

### Exercise 9 — 1:N Relationship Changing Over Time

Each employee belongs to only one department **at a time**, but the system must preserve every past department transfer.

**Question:** Is a single NHAN_VIEN.ma_phong column sufficient for history? What model should be added?

**Answer:** The ma_phong column only shows the current assignment and does not store old departments. Add **LICH_SU_PHAN_CONG(ma_phan_cong PK, ma_nv FK, ma_phong FK, tu_ngay, den_ngay)** or an equivalent effective-interval table design. Define overlap rules and how the current assignment is determined to uphold “one department at a time”.

### Exercise 10 — Avoid Using CASCADE Blindly

Each order belongs to one customer. When deleting a customer, a developer proposes ON DELETE CASCADE to automatically delete all orders.

**Question:** What constraints should be reviewed before deciding?

**Answer:** Review requirements for purchase history, accounting, reporting, refunds, and retention policies. If finalized orders must remain, block physical deletion of customers with orders, or use an inactive status / appropriate retention solution. Only use CASCADE when the system genuinely permits deleting child data as well.

## 16. Summary

| Case | Core Mapping |
| --- | --- |
| **1:N** | Place the **1-side** key in the **N-side** table as an FK |
| **1:N, N side must have parent** | **NOT NULL** FK, not UNIQUE |
| **1:N, N side may lack parent** | **Nullable** FK, not UNIQUE |
| **1:1** | FK on one side **with UNIQUE**, or shared PK |
| **1:1, FK side requires the other side** | **UNIQUE NOT NULL** FK |
| **1:1, FK side is optional** | **UNIQUE nullable** FK |
| **Shared primary key** | Auxiliary table's PK is also an FK to the main table |
| **Parent must have child records** | Child-side FK **is not enough**; another rule is needed |
| **Composite parent key** | Child-side FK references **all components** |
| **Relationship with history** | May need a junction/event table instead of a current-state FK |

When translating **one-to-one** or **one-to-many** relationships into a relational schema, determine multiplicity and optionality in **both directions** before adding columns. For 1:N, the FK normally sits on the N side; for 1:1, the FK must be paired with UNIQUE or use a shared primary key. Then apply NOT NULL, referential policies, and cross-table checks when needed to preserve business meaning. Expressing these constraints accurately provides the foundation for normalization, index selection, and verifiable physical schema design.
