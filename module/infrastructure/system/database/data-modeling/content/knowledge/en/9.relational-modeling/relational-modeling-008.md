# Mapping Supertype and Subtype Structures to Table Alternatives

## Learning Objectives

In the Extended Entity–Relationship (**EER**) model, an object can belong to a **supertype** while simultaneously belonging to one or more **subtypes**. Subtypes inherit common characteristics and add their own attributes, relationships, or rules. When translating EER into a relational database, you must choose a table organization that **preserves identity, shared attributes, and business constraints**.

This lesson belongs to the **Relational Modeling** chapter of the **DATABASE_DATA_MODELING** module. The overall goal of the module is to build the skill of translating business requirements into clear data models—from entities, relationships, and constraints to normalization, keys, indexes, and physical schemas—while comparing relational, document, graph, and analytical modeling approaches to select structures that are suitable, evolvable, and verifiable.

After this lesson, you will be able to:

1. Distinguish **supertype–subtype**, **specialization**, **generalization**, and the meaning of inheritance in EER.
2. Analyze **disjoint/overlapping** and **total/partial** constraints.
3. Convert the same supertype–subtype hierarchy into three main alternatives: **single table for the whole hierarchy**, **supertype table plus subtype tables**, or **one table per concrete subtype**.
4. Design **primary keys**, **foreign keys**, **UNIQUE**, **NOT NULL**, **CHECK**, and supplementary validation mechanisms for each alternative.
5. Compare query patterns, JOIN/UNION costs, column sparsity, subtype extensibility, lifecycle management, and integrity guarantees across the three alternatives.
6. Propose and verify designs using PostgreSQL SQL examples and business counterexamples.

## 1. Supertypes, Subtypes, and Identity Inheritance

Suppose a system manages **VEHICLES** (`PHUONG_TIEN`) of two kinds:

- **CAR** (`O_TO`): has seat count.
- **MOTORBIKE** (`XE_MAY`): has engine displacement in cc.

Every vehicle has an **identifier**, **license plate**, and **manufacturer**. Shared attributes reside on supertype PHUONG_TIEN; specific attributes reside on subtypes O_TO and XE_MAY.

~~~~text
                         PHUONG_TIEN
                id, bien_so, hang_xe
                        /      \
                       /        \
                    O_TO       XE_MAY
                  so_cho     dung_tich_cc
~~~~

### 1.1. Inheritance in EER Is Not Programming Class Inheritance

In EER, **O_TO is a subset of PHUONG_TIEN**: every car is itself a vehicle, sharing **the exact same identifier** as the supertype instance. Do not think of a car as an independent copy of a vehicle.

\[
O\_TO \subseteq PHUONG\_TIEN,\qquad
XE\_MAY \subseteq PHUONG\_TIEN
\]

If a vehicle has id **101** and belongs to subtype O_TO, the specific attribute **so_cho** describes **that exact vehicle 101**, not a separate entity.

**Specialization** starts from a supertype and divides it into subtypes based on differences. **Generalization** starts from concrete types and recognizes shared attributes/rules to form a supertype. Both lines of thought can lead to the same EER structure.

The following diagram illustrates conceptual inheritance. Do not read it as SQL table creation syntax.

~~~~mermaid
classDiagram
    class PHUONG_TIEN {
      +id: bigint
      +bien_so: string
      +hang_xe: string
    }
    class O_TO {
      +so_cho: integer
    }
    class XE_MAY {
      +dung_tich_cc: integer
    }
    PHUONG_TIEN <|-- O_TO
    PHUONG_TIEN <|-- XE_MAY
~~~~

### 1.2. Business Rules of the Example

To compare mapping alternatives fairly, we **fix the exact same rule set**:

1. Every vehicle has a **unique id**, and a mandatory license plate that is unique **across the entire system**.
2. Every managed vehicle must be either a **car or a motorbike**, with no third kind.
3. A vehicle **cannot be both a car and a motorbike at the same time**.
4. A car has **so_cho** as an integer from 2 to 60; it has no dung_tich_cc attribute in this example's car specification.
5. A motorbike has **dung_tich_cc** as an integer from 50 to 2000; it has no so_cho attribute under this specification.
6. The shared attributes **id**, **bien_so**, and **hang_xe** carry the same meaning across both subtypes.

The ranges 2–60 and 50–2000 are **practice assumptions**, not a claim that all real-world vehicles must satisfy these bounds. If the business manages electric vehicles, specialized machinery, or cars with fewer/more seats, update the requirements and checks instead of keeping assumed limits.

## 2. EER Constraints to Preserve During Mapping

### 2.1. Disjoint and Overlapping

- **Disjoint:** A supertype instance may belong to **at most one** subtype in the specialization group under consideration.
- **Overlapping:** A supertype instance **can belong to multiple** subtypes in the same group.

The **PHUONG_TIEN → O_TO/XE_MAY** example above is **disjoint**: one id cannot appear in both subtypes simultaneously.

Conversely, a **NGUOI → NHAN_VIEN/KHACH_HANG** (Person → Employee/Customer) model can be **overlapping**: one person can be both an employee and a customer. When using separate tables for each subtype, the same person id can appear in both tables; this is **valid data**, not an error duplicate.

### 2.2. Total and Partial

- **Total:** Every supertype instance must belong to **at least one** subtype in the group.
- **Partial:** Some supertype instances may **not yet belong to any subtype**.

Our example managing only cars and motorbikes imposes a **total** constraint: there is no “unclassified” vehicle. However, an asset registration system might record an asset first and classify it later; in that case the specialization can be **partial**.

### 2.3. Four Constraint Combinations

| Specialization Group | Number of Subtypes a Parent Instance May Belong To | Scenario |
| --- | --- | --- |
| **Disjoint + total** | Exactly **1** | A vehicle must be exactly one type in O_TO/XE_MAY |
| **Disjoint + partial** | **0 or 1** | A vehicle may be awaiting classification |
| **Overlapping + total** | **At least 1**, potentially many | A person in an organization must be an employee, a customer, or both |
| **Overlapping + partial** | **0, 1, or many** | A person is stored before roles are assigned |

The two axes **disjoint/overlapping** and **total/partial** are **independent**. Having a single discriminator column accepting only O_TO/XE_MAY easily expresses disjointness, yet does not automatically solve overlapping cases or future subtype additions.

### 2.4. Preserving Object Identity and Keys

The three mapping strategies below must uphold three invariants:

1. **Do not split one vehicle into multiple independent identifiers** merely because it has subtype-specific data.
2. **Do not lose system-wide uniqueness checking** for license plates.
3. **Do not allow subtype rule violations** (a car missing seat count, a motorbike holding car-only attributes, or a vehicle in an invalid type set).

Being able to store data with SQL does not mean every invariant is protected by DDL. Clearly list **which constraints the DBMS checks directly**, **which require triggers/transactions/workflows**, and **which are not enforced by the model**.

## 3. Alternative A: One Table for the Supertype and All Subtypes

This alternative is commonly called **single-table inheritance**, **table-per-hierarchy**, or **one table for the entire hierarchy**.

### 3.1. Structure

Create one PHUONG_TIEN table containing:

- Common columns: id, bien_so, hang_xe.
- A **type discriminator column** such as loai.
- Subtype-specific columns for all subtypes: so_cho, dung_tich_cc.

~~~~text
PHUONG_TIEN_ST(
  id PK,
  bien_so UNIQUE NOT NULL,
  hang_xe NOT NULL,
  loai NOT NULL,
  so_cho,
  dung_tich_cc
)
~~~~

Because a single row belongs to only one subtype in the **disjoint** example, certain subtype columns will be NULL **by design**. Do not interpret all those NULLs as missing input: for a motorbike, so_cho is genuinely **not applicable** in this model.

### 3.2. PostgreSQL: CHECK Protecting Type–Attribute Pairs

~~~~sql
CREATE TABLE phuong_tien_st (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bien_so VARCHAR(20) NOT NULL UNIQUE,
    hang_xe VARCHAR(100) NOT NULL,
    loai VARCHAR(10) NOT NULL,
    so_cho SMALLINT,
    dung_tich_cc INTEGER,
    CONSTRAINT ck_pt_st_loai CHECK (loai IN ('OTO', 'XEMAY')),
    CONSTRAINT ck_pt_st_chi_tiet CHECK (
        (
            loai = 'OTO'
            AND so_cho IS NOT NULL
            AND so_cho BETWEEN 2 AND 60
            AND dung_tich_cc IS NULL
        )
        OR
        (
            loai = 'XEMAY'
            AND dung_tich_cc IS NOT NULL
            AND dung_tich_cc BETWEEN 50 AND 2000
            AND so_cho IS NULL
        )
    )
);

INSERT INTO phuong_tien_st
    (bien_so, hang_xe, loai, so_cho, dung_tich_cc)
VALUES
    ('OTO-MAU-01', 'Toyota', 'OTO', 5, NULL),
    ('XM-MAU-01', 'Honda', 'XEMAY', NULL, 125);

SELECT id, bien_so, hang_xe, so_cho
FROM phuong_tien_st
WHERE loai = 'OTO'
ORDER BY id;
~~~~

The license plates in the example are **synthetic test strings**, not real plate records. Both records are valid because each type holds the exact specific attributes required by the constraints.

**Why must CHECK include IS NOT NULL?** In SQL, a predicate involving NULL can evaluate to **UNKNOWN**; a standard CHECK does not reject UNKNOWN. If you only wrote `so_cho BETWEEN 2 AND 60`, a car row with NULL so_cho could slip through. Adding **so_cho IS NOT NULL** and **dung_tich_cc IS NOT NULL** in their respective branches explicitly enforces presence.

### 3.3. What Is Enforced?

| Business Constraint | Mechanism in Single Table |
| --- | --- |
| One row is one vehicle | PK(id) |
| Unique license plate across both types | UNIQUE(bien_so) on the same table |
| Must belong to one of the two types | loai NOT NULL + value-set CHECK |
| Cannot belong to both types simultaneously | Single discriminator with mutually exclusive CHECK branches |
| Car has valid seat count | CHECK with so_cho IS NOT NULL and range |
| Motorbike has valid engine capacity | CHECK with dung_tich_cc IS NOT NULL and range |
| No inapplicable subtype columns populated | CHECK forces the other type's column IS NULL |

For a **disjoint + total** hierarchy, Alternative A can express the primary conditions directly via **single-row constraints**. No JOIN is required to retrieve common data together with subtype-specific attributes for a vehicle.

### 3.4. Pros and Cons

**Pros:**

- Querying all vehicles or a single subtype is simple; shared and specific data reside in one table.
- One primary key, one place to enforce system-wide uniqueness.
- Disjoint and total constraints are usually easy to express with a discriminator and CHECK when subtypes are finite and mutually exclusive.
- FKs from other tables referencing any vehicle only need to point to PHUONG_TIEN_ST.id.

**Cons:**

- Column count can bloat when there are many distinct subtypes; many “not applicable” NULLs appear.
- Requires maintaining complex CHECK constraints and altering the table whenever adding subtypes or specific attributes.
- Hard to express **overlapping** cases using **only a single-valued discriminator**; requires changing the classification mechanism or choosing another alternative.
- Access permissions, rules, and lifecycles of subtypes may differ, making clean separation difficult in a single table.

**Do not conclude:** “Having NULLs violates normalization.” NULLs for inapplicable attributes **do not by themselves prove** a normalization flaw; analyze functional dependencies, semantics, and queries. Still, high column sparsity remains a signal to reconsider the design.

## 4. Alternative B: One Supertype Table and One Table per Subtype

This alternative is commonly called **class-table inheritance**, **joined-table inheritance**, or **table-per-type** in the sense of **parent table + child tables**.

### 4.1. Structure and Keys

~~~~text
PHUONG_TIEN_JT(id PK, bien_so UNIQUE, hang_xe, loai)
O_TO_JT(id PK, FK → PHUONG_TIEN_JT.id, so_cho)
XE_MAY_JT(id PK, FK → PHUONG_TIEN_JT.id, dung_tich_cc)
~~~~

**The id column in each child table is both PK and FK** to the parent table. This is a **1:1 shared primary key**: one vehicle id has at most one row in O_TO_JT and at most one row in XE_MAY_JT. Do not generate a new independent id in the child table to replace the parent's id.

When reading cars, JOIN O_TO_JT with PHUONG_TIEN_JT on id to get complete information. When querying all vehicles, you can read only the parent table if only shared attributes are needed.

### 4.2. PostgreSQL: Enforcing Type Correctness Across Split Tables

A plain FK from a child table to the parent table's id **only** guarantees the parent record exists. It does not prevent **the same id** from appearing in both O_TO_JT and XE_MAY_JT, nor does it ensure loai in the parent matches the child table.

For the **disjoint** example, we can tighten enforcement using a **composite foreign key (id, loai)**. Each child table has a constant loai column fixed to its type; the composite FK references the matching pair in the parent table:

~~~~sql
CREATE TABLE phuong_tien_jt (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bien_so VARCHAR(20) NOT NULL UNIQUE,
    hang_xe VARCHAR(100) NOT NULL,
    loai VARCHAR(10) NOT NULL,
    CONSTRAINT ck_pt_jt_loai CHECK (loai IN ('OTO', 'XEMAY')),
    CONSTRAINT uq_pt_jt_id_loai UNIQUE (id, loai)
);

CREATE TABLE o_to_jt (
    id BIGINT PRIMARY KEY,
    loai VARCHAR(10) NOT NULL DEFAULT 'OTO',
    so_cho SMALLINT NOT NULL,
    CONSTRAINT ck_ot_jt_loai CHECK (loai = 'OTO'),
    CONSTRAINT ck_ot_jt_so_cho CHECK (so_cho BETWEEN 2 AND 60),
    CONSTRAINT fk_ot_jt_cha
        FOREIGN KEY (id, loai)
        REFERENCES phuong_tien_jt (id, loai)
        ON DELETE CASCADE
);

CREATE TABLE xe_may_jt (
    id BIGINT PRIMARY KEY,
    loai VARCHAR(10) NOT NULL DEFAULT 'XEMAY',
    dung_tich_cc INTEGER NOT NULL,
    CONSTRAINT ck_xm_jt_loai CHECK (loai = 'XEMAY'),
    CONSTRAINT ck_xm_jt_dung_tich
        CHECK (dung_tich_cc BETWEEN 50 AND 2000),
    CONSTRAINT fk_xm_jt_cha
        FOREIGN KEY (id, loai)
        REFERENCES phuong_tien_jt (id, loai)
        ON DELETE CASCADE
);
~~~~

In PostgreSQL, **UNIQUE(id, loai)** on the parent table is required for that pair of columns to be a valid composite FK target, even though **id** is already the PK so uniqueness of the pair is logically redundant. This is a physical trade-off to gain **type-safe referential integrity**.

With this design:

- O_TO_JT cannot point to a parent record with loai = XEMAY.
- XE_MAY_JT cannot point to a parent record with loai = OTO.
- A parent id holds exactly one loai value, so it cannot validly be stored in **both** child tables at the same time.
- A child row cannot exist without a parent, because its PK is also part of the composite FK.

However, **a PHUONG_TIEN_JT row without any row in a child table is still permitted to exist**. This is crucial: the checks above **do not yet enforce the total constraint**.

### 4.3. Inserting Data in One Unified Flow

You can insert the parent and then the child within a single PostgreSQL statement using a writable CTE and **RETURNING**:

~~~~sql
WITH moi_cha AS (
    INSERT INTO phuong_tien_jt (bien_so, hang_xe, loai)
    VALUES ('OTO-JT-01', 'Toyota', 'OTO')
    RETURNING id
)
INSERT INTO o_to_jt (id, so_cho)
SELECT id, 5
FROM moi_cha;

WITH moi_cha AS (
    INSERT INTO phuong_tien_jt (bien_so, hang_xe, loai)
    VALUES ('XM-JT-01', 'Honda', 'XEMAY')
    RETURNING id
)
INSERT INTO xe_may_jt (id, dung_tich_cc)
SELECT id, 125
FROM moi_cha;
~~~~

The parent vehicle and child row are created in one statement without guessing generated id values. Querying full attributes across types:

~~~~sql
SELECT
    pt.id,
    pt.bien_so,
    pt.hang_xe,
    pt.loai,
    ot.so_cho,
    xm.dung_tich_cc
FROM phuong_tien_jt AS pt
LEFT JOIN o_to_jt AS ot ON ot.id = pt.id
LEFT JOIN xe_may_jt AS xm ON xm.id = pt.id
ORDER BY pt.id;
~~~~

| bien_so | hang_xe | loai | so_cho | dung_tich_cc |
| --- | --- | --- | ---: | ---: |
| OTO-JT-01 | Toyota | OTO | 5 | NULL |
| XM-JT-01 | Honda | XEMAY | NULL | 125 |

In the JOIN output, NULL on the unmatched side simply means **there is no row of that subtype**, not evidence of bad data. In a disjoint design, each id has at most one type; in an overlapping design, multiple child tables can simultaneously hold rows.

### 4.4. The Gap in the Total Participation Rule

The following statement **remains valid** under the DDL in Section 4.2:

~~~~sql
INSERT INTO phuong_tien_jt (bien_so, hang_xe, loai)
VALUES ('OTO-JT-CHUA-CO-CON', 'Toyota', 'OTO');
~~~~

Now the parent record declares loai = OTO yet has no corresponding row in O_TO_JT. FKs only enforce the **child → parent** direction; they do not automatically enforce **parent → must have child**.

A query to detect parent rows missing a subtype row:

~~~~sql
SELECT pt.id, pt.bien_so, pt.loai
FROM phuong_tien_jt AS pt
WHERE
    (
        pt.loai = 'OTO'
        AND NOT EXISTS (
            SELECT 1 FROM o_to_jt AS ot
            WHERE ot.id = pt.id
        )
    )
    OR
    (
        pt.loai = 'XEMAY'
        AND NOT EXISTS (
            SELECT 1 FROM xe_may_jt AS xm
            WHERE xm.id = pt.id
        )
    )
ORDER BY pt.id;
~~~~

If **partial** is the intended business meaning, having a parent without a child row can be valid. But if the model is **total**, additional mechanisms are needed:

- **Create parent and child as a single transactional unit**; restrict write paths so a parent cannot be inserted without its child.
- If enforcement is required at the **database level** across all write paths, consider a **deferred constraint trigger checked at transaction commit** or a properly timed DB workflow with appropriate concurrency handling.
- Define clearly when a record moves from “draft” to “fully managed”; if draft states are allowed, the EER specification at that stage may actually be **partial** rather than total.

A **CHECK** constraint on the parent table alone cannot directly query child tables in PostgreSQL to confirm at least one child row exists; do not write a CHECK containing a subquery and assume it is valid. A post-write SELECT check is **detection**, not prevention across concurrent transactions.

### 4.5. Overlapping Systems: One Person with Multiple Roles

The case where the same person can be both an **employee** and a **customer** fits the parent + child table strategy well:

~~~~sql
CREATE TABLE nguoi_ov (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ho_ten VARCHAR(120) NOT NULL
);

CREATE TABLE nhan_vien_ov (
    nguoi_id BIGINT PRIMARY KEY
        REFERENCES nguoi_ov(id) ON DELETE CASCADE,
    ma_nhan_vien VARCHAR(20) NOT NULL UNIQUE
);

CREATE TABLE khach_hang_ov (
    nguoi_id BIGINT PRIMARY KEY
        REFERENCES nguoi_ov(id) ON DELETE CASCADE,
    ma_khach VARCHAR(20) NOT NULL UNIQUE
);

WITH n AS (
    INSERT INTO nguoi_ov (ho_ten)
    VALUES ('Nguyễn An')
    RETURNING id
)
SELECT id FROM n;
~~~~

Once the person's id is obtained, **that same id** can be used to create one row in NHAN_VIEN_OV and one row in KHACH_HANG_OV. This represents **one person holding two roles**, rather than creating two independent people.

**Note on the SQL snippet:** The final statement only creates the person and returns the id; it does not automatically create role rows. A person with no role yet is valid under **overlapping + partial**. If the business mandates every person has at least one role (**overlapping + total**), an additional enforcement mechanism is still needed.

Do not use a single-valued discriminator to forbid someone from holding multiple roles. In an overlapping model, simultaneous presence in multiple child tables **is valid** and does not require an exclusion constraint.

### 4.6. Pros and Cons

**Pros:**

- Clearly separates shared attributes from specific attributes; each child table has independent **NOT NULL** and **CHECK** constraints for its own attributes.
- Provides a single parent table for unified identity, system-wide **UNIQUE(bien_so)** across all vehicles, and a single FK target for related tables.
- Fits well when subtypes have many specialized attributes, specialized relationships, or distinct access permissions.
- Often natural for **overlapping**, since one parent id can appear in multiple child tables without duplicating shared attributes.

**Cons:**

- Querying full attributes usually requires JOINs; polymorphic queries across types may need multiple LEFT JOINs or UNIONs.
- Inserting/updating/deleting one object can touch multiple tables, requiring transactions.
- **Total participation on the parent side is not automatically enforced by FKs**; disjointness across child tables is also not enforced by plain id FKs without extra design.
- PK and related FKs must be managed carefully to avoid orphan or mismatched-type child rows.

## 5. Alternative C: Tables Only for Concrete Subtypes

This alternative is commonly called **table-per-concrete-class**, **concrete-table inheritance**, or **separate tables for each concrete subtype**. There is no shared PHUONG_TIEN table; each O_TO and XE_MAY table stores **both shared and specific attributes**.

### 5.1. Structure

~~~~text
O_TO_CT(
  id PK, bien_so UNIQUE, hang_xe, so_cho
)

XE_MAY_CT(
  id PK, bien_so UNIQUE, hang_xe, dung_tich_cc
)
~~~~

When adding a car, INSERT only into O_TO_CT. When adding a motorbike, INSERT only into XE_MAY_CT. There is no two-row parent–child operation.

### 5.2. PostgreSQL

~~~~sql
CREATE TABLE o_to_ct (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bien_so VARCHAR(20) NOT NULL UNIQUE,
    hang_xe VARCHAR(100) NOT NULL,
    so_cho SMALLINT NOT NULL CHECK (so_cho BETWEEN 2 AND 60)
);

CREATE TABLE xe_may_ct (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bien_so VARCHAR(20) NOT NULL UNIQUE,
    hang_xe VARCHAR(100) NOT NULL,
    dung_tich_cc INTEGER NOT NULL
        CHECK (dung_tich_cc BETWEEN 50 AND 2000)
);

INSERT INTO o_to_ct (bien_so, hang_xe, so_cho)
VALUES ('OTO-CT-01', 'Toyota', 5);

INSERT INTO xe_may_ct (bien_so, hang_xe, dung_tich_cc)
VALUES ('XM-CT-01', 'Honda', 125);
~~~~

Each table has valid constraints **for its own type**. However, there is a major gap:

> **UNIQUE(bien_so) in each table only enforces uniqueness within that table.** The SQL above still permits the exact same license plate to appear once in O_TO_CT and once in XE_MAY_CT, even though the business rule requires system-wide uniqueness.

Similarly, **id** values generated by two separate sequences can collide numerically across the two tables. Two identical id numbers in the two tables **do not automatically represent the same vehicle**, and a single id cannot serve as a unified FK target for all vehicles.

### 5.3. Polymorphic Queries with UNION ALL

To list all vehicles under a shared set of columns:

~~~~sql
SELECT
    'OTO'::TEXT AS loai,
    id,
    bien_so,
    hang_xe,
    so_cho,
    NULL::INTEGER AS dung_tich_cc
FROM o_to_ct

UNION ALL

SELECT
    'XEMAY'::TEXT AS loai,
    id,
    bien_so,
    hang_xe,
    NULL::SMALLINT AS so_cho,
    dung_tich_cc
FROM xe_may_ct

ORDER BY loai, id;
~~~~

**UNION ALL** preserves all records and simply combines rows across different types. Do not substitute UNION merely to “hide” business duplicates: if the same license plate appears in both types, you need **data constraints**, not query-result deduplication.

Aggregations across all vehicles must also combine data from multiple tables:

~~~~sql
SELECT COUNT(*) AS tong_so_phuong_tien
FROM (
    SELECT id FROM o_to_ct
    UNION ALL
    SELECT id FROM xe_may_ct
) AS tat_ca;
~~~~

This counts the number of **stored vehicle rows**, not unique real-world objects. If the same vehicle was mistakenly entered into both tables, this result still counts two rows.

### 5.4. Challenges with Global Integrity and Referencing

With a supertype + subtype table structure, PHUONG_TIEN_JT can be the target of an FK such as:

~~~~text
BAO_TRI(phuong_tien_id FK → PHUONG_TIEN_JT.id)
~~~~

With concrete-only tables, **no shared parent table exists** as an FK target. Options depending on requirements include:

- Creating separate FKs per type in the maintenance table with a “strictly one type populated” constraint, increasing columns and rule complexity.
- Creating a **shared identity registry table** to protect id and license plate, and having concrete tables reference it—which effectively moves toward **reintroducing a supertype table**.
- Relying on custom identity schemes and application checks, while explicitly acknowledging that polymorphic integrity **is not protected by a standard FK**.

No standard SQL FK can automatically “reference either O_TO_CT or XE_MAY_CT based on a discriminator value” using a single referencing column without supporting structures.

### 5.5. Pros and Cons

**Pros:**

- Each type table is self-contained; querying type-specific attributes needs no JOIN.
- Type-specific columns can directly use NOT NULL and CHECK without introducing NULLs for inapplicable types.
- Simple storage when the system always processes **each concrete type independently** and rarely queries or references the shared supertype.

**Cons:**

- Duplicates shared columns and constraints in every table: bien_so, hang_xe, and validation rules.
- **Per-table UNIQUE does not enforce hierarchy-wide UNIQUE**; duplicate records across two types easily arise.
- No shared identifier or unified FK target for all vehicles without adding extra structures.
- Cross-type queries require UNION ALL; adding a new subtype forces updating polymorphic queries and reports.
- Poor fit for **overlapping**: an object with multiple roles must appear in multiple concrete tables, risking duplication or inconsistency of shared attributes.

This approach is reasonable when concrete types truly operate largely independently. However, for our vehicle example requiring **system-wide unique license plates** and external tables referencing PHUONG_TIEN, it is less favorable than the two alternatives that maintain a shared table/identity.

## 6. Comparison Table of the Three Mapping Alternatives

| Criterion | A. Single Table for Hierarchy | B. Supertype + Subtype Tables | C. Table per Concrete Type |
| --- | --- | --- | --- |
| Where shared attributes live | Same table as all specific attributes | Only in the supertype table | Duplicated in each concrete table |
| Shared identifying key | One hierarchy-wide PK | Parent PK; child PK shares parent id | No default shared PK |
| System-wide license plate uniqueness | Easily enforced via one UNIQUE | Easily enforced via UNIQUE on parent | Requires custom mechanism beyond per-table UNIQUE |
| Mandatory specific attributes | CHECK per discriminator; often nullable columns | NOT NULL/CHECK inside each child table | NOT NULL/CHECK inside each concrete table |
| Disjoint | Easy with one discriminator | Requires preventing same id across exclusive children (e.g., typed composite FK) | Requires preventing same object across multiple tables |
| Overlapping | Unnatural with a single discriminator | Natural; one parent id can have multiple role rows | Prone to duplicating shared data |
| Total | Easy per-row check via discriminator + CHECK for disjoint models | Child → parent FK is insufficient; must check parent has child | Stored rows are always in a concrete table, yet no unified parent set exists to verify against |
| Partial | Needs suitable status/type values and column rules | Allows parent with no child rows yet | Cannot represent shared-only records without an extra table |
| Querying one type completely | No JOIN, filter by loai | JOIN parent and type table | No JOIN |
| Querying all types | SELECT one table | SELECT parent or JOIN multiple tables | UNION ALL across tables |
| Shared FK from other business tables | One FK to the shared table | One FK to the parent table | Difficult without a shared identity table |
| Adding a new subtype | Usually ALTER TABLE and CHECK | Create child table, update classification rules if needed | Create new table, update queries and global constraints |
| Risk when changing type | Update discriminator and specific columns | Move rows between child tables in a transaction | May need to move records across tables; hard to preserve shared FKs |

No single alternative is universally optimal. Choose a strategy based not merely on table count, but on **identity constraints**, **overlapping semantics**, **optionality**, **query patterns**, **data lifecycle**, and **likelihood of adding subtypes**.

### 6.1. When to Prefer A

Consider a **single table** when:

- The subtype set is relatively small and distinct, especially **disjoint + total**.
- The number of specific columns is modest and per-type rules express cleanly with CHECK.
- Most queries read shared and specific attributes together.
- You need a single identifier and system-wide uniqueness constraints with minimal JOIN cost.

For our example with two types O_TO and XE_MAY and few specific attributes, Alternative A is straightforward and enforces most rules directly in DDL.

### 6.2. When to Prefer B

Consider **supertype + subtype tables** when:

- Subtypes have many specific attributes or specialized relationships.
- You need to query shared entities and reference the supertype from multiple modules.
- Roles are **overlapping**, where one object belongs to multiple subtypes.
- You want separate permissions or lifecycles for different attribute groups.
- JOINs are acceptable and you have a plan to enforce **total/disjoint** constraints appropriately.

For **NGUOI → NHAN_VIEN/KHACH_HANG** where one person can hold both roles, Alternative B is usually far clearer than a single-valued type column.

### 6.3. When C Can Be Used

Consider **table per concrete type** when:

- Types operate nearly independently with few queries through the supertype.
- Few or no external tables need a shared FK across all types.
- System-wide constraints can be governed by a well-designed mechanism if required.
- Duplicating shared column definitions and updating UNION queries when adding types is acceptable.

Never pick C for a model with many links to “all vehicles” just to avoid JOINs. Integrity maintenance costs and data duplication often outweigh single-type query savings.

## 7. Adding Subtypes, Switching Types, and Evolving Requirements

### 7.1. When a New Subtype Appears

Suppose next year the system adds **XE_TAI** (truck) with **tai_trong_kg**. The model remains disjoint + total across O_TO, XE_MAY, and XE_TAI.

**Alternative A:** Add column tai_trong_kg, expand the loai set, and update the CHECK tying type to attributes. Existing records of older types have NULL in the new column; default queries filtering on type sets must also be reviewed.

**Alternative B:** Create table XE_TAI_JT with PK/FK sharing the parent's id, add payload CHECK, update the parent's type set and total/disjoint checks. Shared queries reading only the parent table may stay unchanged; full polymorphic queries need another JOIN.

**Alternative C:** Create table XE_TAI_CT duplicating shared columns. Every consolidated report must add a XE_TAI_CT branch; hierarchy-wide UNIQUE and polymorphic FKs must be re-evaluated.

Never add a new type only in application code while ignoring **database CHECK constraints**, or INSERTs for the new type will either be rejected or lack required data protection.

### 7.2. When an Instance Switches from One Subtype to Another

Suppose another system allows a business object to **change classification**, such as a membership tier moving from “standard” to “enterprise”. When switching types:

- With **A**, update the discriminator and specific columns in the same row while keeping CHECK satisfied; clear or replace attributes that no longer apply.
- With **B**, insert/delete child table rows and update the parent classification rule inside one transaction, avoiding invalid intermediate states against FKs or extra checks.
- With **C**, you may have to move the row to another table and update all type-specific references; preserving a single cross-table identity is harder.

**Not every type should be mutable**: turning a motorbike into a car makes little business sense; type transitions usually make sense only for **roles, legal statuses, or tiers**. If the essence is a **status changing over time**, consider a state model or classification history instead of an immutable subtype.

### 7.3. Moving from Disjoint to Overlapping

If a person model initially splits into “CUSTOMER” or “EMPLOYEE” and later a person can be both customer and employee, that changes the **EER constraint**, not merely an enum value.

- Alternative A with a single-valued loai column can no longer express it; extensions typically use role flags or split out role tables.
- Alternative B naturally allows the same id to have rows in both KHACH_HANG and NHAN_VIEN; simply **remove the exclusivity constraint** if one was enforced.
- Alternative C easily spawns two independent records for the same person; sharing identity and common attributes must be solved explicitly.

Initial model selection should weigh the likelihood of business rules evolving from disjoint to overlapping, rather than optimizing only for today's data.

## 8. Commonly Misunderstood SQL Constraint Details

### 8.1. PK–PK FKs in Child Tables Do Not Enforce Disjointness

Suppose you only have:

~~~~sql
-- Illustrative structure example; do not run directly alongside Section 4 DDL.
-- O_TO(id PRIMARY KEY REFERENCES PHUONG_TIEN(id), so_cho ...)
-- XE_MAY(id PRIMARY KEY REFERENCES PHUONG_TIEN(id), dung_tich_cc ...)
~~~~

Both child tables guarantee at most one row per id within each table, yet **both tables can simultaneously contain id 101**. If the model is disjoint, this is wrong.

That is why in Section 4 we used a **constant loai in each child table paired with a composite FK (id, loai)** to the parent to block mismatched types. Another option is a trigger enforcing exclusivity, provided it is designed safely for concurrent transactions.

### 8.2. Disjoint Does Not Mean Total

If the DB blocks an id from appearing in **both** child tables, it only enforces **at most one**; an id can still appear in **zero child tables**. To enforce **exactly one**, protect both conditions:

\[
\text{number of subtypes for an id} \leq 1
\]

and

\[
\text{number of subtypes for an id} \geq 1
\]

The first condition is **disjoint**, and the second is **total**. Enforcing the first while forgetting the second is a common mistake when mapping EER to relational tables.

### 8.3. Per-Table UNIQUE Is Not Hierarchy-Wide UNIQUE

~~~~text
O_TO_CT:  bien_so = "X-001"  (valid inside the car table)
XE_MAY_CT: bien_so = "X-001"  (valid inside the motorbike table)
~~~~

If license plates are unique across **all vehicles**, this data violates business rules despite satisfying both individual UNIQUE constraints. Placing UNIQUE on each table only enforces uniqueness **per table**.

For hierarchy-wide uniqueness, you need **a centralized place enforcing the code** or another cross-table enforcement mechanism. Putting codes in a shared registry table is a common design, though at that point the architecture approaches having a supertype table.

### 8.4. CHECK and NULL

In PostgreSQL, a CHECK expression is rejected only when it evaluates to **FALSE**; TRUE and UNKNOWN are accepted. For example, CHECK(so_cho >= 2) **does not** force so_cho to be non-NULL. To make a specific attribute mandatory, use **NOT NULL** in a subtype table or **IS NOT NULL** inside the appropriate CHECK branch in a single table.

### 8.5. Do Not Confuse a Separate Child PK with a Shared Identity

If a subtype uses its **own auto-increment id** instead of the parent's id, the join condition:

~~~~text
O_TO.id = PHUONG_TIEN.id
~~~~

is not automatically valid. Two id values can match numerically by coincidence without **sharing identity**. If a child table still needs its own technical id, it must carry **phuong_tien_id FK UNIQUE NOT NULL** to represent the 1:1 link; however, that is usually more complex than a **shared PK** when the child row is purely a specialized extension of the same parent instance.

### 8.6. PostgreSQL INHERITS Does Not Replace the Three Logical Mapping Alternatives

PostgreSQL supports physical table inheritance via **INHERITS**, but do not assume it is equivalent to PK/FK supertype–subtype EER mapping or the three ORM strategies. Characteristics such as the scope of UNIQUE/PK constraints, FKs, and queries through the parent table must be checked against PostgreSQL's specific inheritance semantics. When requirements call for a single identity and **system-wide** UNIQUE constraints, explicit PK/FK child tables or a single shared table are usually easier to reason about and verify than relying on class-inheritance intuition.

## 9. Connection to Java Code and ORMs

When a Java application uses an ORM, the corresponding strategy names roughly align at a conceptual level:

| Relational Modeling Strategy | Common Java ORM Name | What Still Must Be Verified in the DB |
| --- | --- | --- |
| Single table for entire hierarchy | SINGLE_TABLE | Discriminator, per-type CHECK, conditional NOT NULL |
| Supertype table + subtype tables | JOINED | Shared PK/FK, type correctness, disjoint/total |
| Table per concrete class | TABLE_PER_CLASS | Polymorphic queries, shared identity, hierarchy-wide UNIQUE |

Exact annotations and SQL behavior vary by framework, version, and configuration. **ORM mapping does not replace EER analysis and database constraints**. Even when Java classes use `extends`, inspect the generated SQL, keys used, type-switching behavior, and business constraint violations.

In particular, **overlapping** is a model of role sets and data constraints: one person is simultaneously an employee and a customer. This often should not be forced into a single-inheritance Java class tree; some systems fit much better with a **shared person entity + associated role links** or composition.

## 10. Design Workflow from Business Requirements

When encountering an EER diagram with supertypes and subtypes, follow this sequence:

1. **Identify shared identity.** Is a subtype instance the very same instance as the supertype, or a separate object with a 1:1 link? Do not invent a new id if it is the same object.
2. **Separate shared and specific attributes.** For example, bien_so and hang_xe are shared; so_cho is car-specific; dung_tich_cc is motorbike-specific.
3. **Write subtype membership multiplicities explicitly.** Does each parent belong to exactly one, at most one, at least one, or any number of subtypes?
4. **Determine disjoint vs. overlapping.** Look for scenarios where one object belongs to two subtypes at once; if possible, do not choose a disjoint model.
5. **Determine total vs. partial.** Can a parent record exist without a subtype yet? If yes, what does it mean and for how long?
6. **List hierarchy-wide constraints.** Unique license plates, object codes, shared FKs, shared statuses, delete policies, and history.
7. **Choose a table strategy.** Evaluate Alternatives A, B, and C against requirements to weigh trade-offs in JOINs, UNIONs, sparse columns, keys, and integrity.
8. **Write DDL and mark gaps.** Which rules use PK, FK, UNIQUE, CHECK, or NOT NULL, and which need cross-table mechanisms? Clearly distinguish what is enforced from what is not.
9. **Test with counterexamples.** Test missing specific attributes, child id without parent, mismatched discriminator, parent without child, one id with two types, and duplicate codes across two concrete tables.
10. **Review queries and evolution.** Are all types frequently queried together? Could new subtypes or overlapping roles appear? Which tables reference the supertype?
11. **Optimize physically afterward.** Choose indexes based on data volume, query plans, and write overhead; never compromise logical constraints just to avoid JOINs.

### Minimum Test Suite per Strategy

| Test Case | A. Single Table | B. Parent + Child | C. Per Concrete Type |
| --- | --- | --- | --- |
| Insert two vehicles with the same plate in two types | Shared UNIQUE must block | Parent UNIQUE must block | Two separate UNIQUEs **are insufficient** |
| Create a car without so_cho | CHECK with IS NOT NULL must block | NOT NULL on O_TO_JT must block when child is created | NOT NULL on O_TO_CT must block |
| Create a child row without a parent | No separate child table | FK must block | No separate parent concept |
| One id appearing in both O_TO and XE_MAY | Single-valued discriminator forbids it | Needs disjoint mechanism, e.g., typed composite FK | Needs shared identity check to detect duplication |
| Create parent without creating child | Cannot represent an outside type if total | **Can slip through** without total enforcement | No shared parent table |
| One person is both employee and customer | Poor fit for single-valued discriminator | Two role tables validly pointing to one parent id | Prone to duplicating person details |
| FK from maintenance to any vehicle | References PK of shared table | References PK of parent table | No default shared FK target |

## 11. Practice Exercises with Answers

### Exercise 1 — Identifying Disjoint and Total

A membership card system has two types: **CA_NHAN** (individual) and **DOANH_NGHIEP** (corporate). Every card must belong to one type and cannot belong to both at once.

**Question:** Which constraint combination applies to the hierarchy? Which table alternative expresses it cleanly if each type has very few specific attributes?

**Answer:** **Disjoint + total**: each card belongs to exactly one subtype. A **single table** with discriminator **loai** and per-type CHECK is a good choice when specific attributes are few and column sparsity is low. If the types have many specific attributes/rules, supertype + subtype tables also fit, provided you enforce that each parent has exactly one child.

### Exercise 2 — Checking Type Constraints in a Single Table

A single table has column loai accepting OTO/XEMAY, plus so_cho and dung_tich_cc, with CHECK:

~~~~sql
CHECK (
    (loai = 'OTO' AND so_cho BETWEEN 2 AND 60)
    OR
    (loai = 'XEMAY' AND dung_tich_cc BETWEEN 50 AND 2000)
)
~~~~

**Question:** Is this condition sufficient to guarantee cars always have a seat count and motorbikes never carry a seat count?

**Answer:** **No.** In PostgreSQL, CHECK lets **UNKNOWN** pass, so a NULL so_cho in the car branch is not reliably blocked. The condition also **does not forbid** a motorbike from having a non-NULL so_cho or a car from having a non-NULL dung_tich_cc. You must add **loai NOT NULL**, **IS NOT NULL** for required attributes, and **IS NULL** for inapplicable attributes as shown in Section 3.2.

### Exercise 3 — Why Child Tables with PK=FK Are Not Automatically Disjoint

Given PHUONG_TIEN(id PK), O_TO(id PK FK → PHUONG_TIEN), and XE_MAY(id PK FK → PHUONG_TIEN).

**Question:** Can the same id 101 appear in both child tables if only the constraints above are declared?

**Answer:** **Yes.** Each PK only guarantees uniqueness **within its own child table**, and each FK only guarantees the parent exists. To enforce disjointness, add a shared rule—such as a discriminator on the parent and a **composite FK (id, loai)** from each child table with loai fixed to its type—or an equivalent cross-table mechanism.

### Exercise 4 — Is a Parent Without a Child Valid?

The model PHUONG_TIEN → O_TO/XE_MAY is disjoint + total. The parent + child DDL has a shared PK and FK, but no trigger or workflow forcing child creation.

**Question:** Does inserting a parent row with loai = OTO without inserting into O_TO violate the FK? Is it valid under business rules?

**Answer:** **It does not violate the child → parent FK**, because there is no child row to check yet. However, it **violates the total business rule**: every parent must have a subtype. Add enforcement ensuring parent and child are created together and preventing childless states across all write paths.

### Exercise 5 — Overlapping Person Roles

A person can simultaneously be an **NHAN_VIEN** and a **KHACH_HANG**. Full name should be managed once, and other tables need a shared FK to a person.

**Question:** Which alternative fits best? How should the role tables be keyed?

**Answer:** A **shared NGUOI table + NHAN_VIEN and KHACH_HANG tables** fits well. The same nguoi_id can appear in both role tables; in each role table, **nguoi_id is both PK and FK** to NGUOI(id). This keeps one identifier and one shared name record. Do not apply a single-valued discriminator that forbids holding both roles.

### Exercise 6 — Local UNIQUE vs. System-Wide UNIQUE

Both O_TO_CT and XE_MAY_CT have bien_so UNIQUE NOT NULL.

**Question:** Can two rows exist with the same bien_so = X001, one in each table? Propose a solution if license plates must be unique across all types.

**Answer:** **Yes**, because each UNIQUE only protects its own table. You can add a **shared vehicle identity/registry table with UNIQUE(bien_so)** and have every type reference that code, or adopt Alternative A/B. Using SELECT DISTINCT in reports does not replace write-time constraints.

### Exercise 7 — Querying All Subtypes

Given two tables O_TO_CT(id, bien_so, hang_xe, so_cho) and XE_MAY_CT(id, bien_so, hang_xe, dung_tich_cc).

**Question:** Write a query returning one list with columns loai, bien_so, and hang_xe for both types; should UNION ALL be used?

**Reference Answer:**

~~~~sql
SELECT 'OTO' AS loai, bien_so, hang_xe
FROM o_to_ct
UNION ALL
SELECT 'XEMAY' AS loai, bien_so, hang_xe
FROM xe_may_ct;
~~~~

**UNION ALL** is appropriate when you want to retain all records from both types without using deduplication to mask data errors. For a stable sort order, wrap the result or add an ORDER BY matching combined query syntax.

### Exercise 8 — Should You Choose Table-per-Concrete When There Is a Shared FK?

A system has a **SU_KIEN_BAO_TRI** (maintenance events) table referencing any vehicle regardless of type; vehicle codes must be unique system-wide. O_TO and XE_MAY have very few specific attributes.

**Question:** Which alternative has integrity advantages?

**Answer:** **Single table for the hierarchy (A)** or **supertype + subtype tables (B)** provide a shared FK target and a single place to enforce vehicle code uniqueness. Because the specification is simple, A can avoid JOINs; if types later gain lots of specific data, B may fit better. C would require adding a shared identity mechanism just to match the integrity guarantees of the other two.

### Exercise 9 — Adding a New Subtype

The system adds XE_TAI with tai_trong_kg. Suppose previously there were only O_TO and XE_MAY, disjoint + total.

**Question:** List the schema or query changes required for each alternative.

**Answer:**

- **A:** Add column tai_trong_kg, expand discriminator values, and update the per-type CHECK.
- **B:** Create table XE_TAI with PK/FK sharing parent id, update classification constraints, disjoint/total mechanisms, and full polymorphic detail queries.
- **C:** Create XE_TAI_CT with shared columns, update UNION/reports, and update shared code/FK preservation solutions if any.

In all three cases, check impacts on business logic, existing data, and applications reading the loai field.

### Exercise 10 — Partial Specialization

A system intakes user profiles first, and only after verification assigns role NHAN_VIEN or KHACH_HANG. Some profiles may never receive a role.

**Question:** Should the specialization be considered total or partial? Is it mandatory to create a child row immediately?

**Answer:** Because a user profile can validly exist without a role yet, the specialization is **partial**. With NGUOI + role tables, you do not need to create a child row immediately; a parent row without roles is valid. Do not label it total merely because most profiles will receive a role later.

### Exercise 11 — Counting People vs. Counting Role Assignments

Person id 7 appears in both NHAN_VIEN and KHACH_HANG; person id 8 appears only in KHACH_HANG. The NGUOI table has exactly two people.

**Question:** How many people are there and how many role assignments? If roles are combined with UNION ALL, how many rows result?

**Answer:** There are **2 people**, yet **3 role assignments**: employee for person 7, customer for person 7, and customer for person 8. UNION ALL over the two role tables returns **3 rows**. Never treat role-row count as distinct person count; to count people, COUNT on NGUOI or count distinct ids as required.

### Exercise 12 — Enforcing Type Match on Subtype Attributes

In the joined approach, table O_TO_JT has so_cho NOT NULL and FK(id) to the parent, while the parent has loai.

**Question:** What is still missing to guarantee an O_TO_JT row only references a parent declared as OTO?

**Answer:** FK(id) only checks existence, not **loai**. You can use **CHECK loai='OTO' on the child table** together with a **composite FK (id, loai)** referencing UNIQUE(id, loai) on the parent as in Section 4.2, or an equivalent cross-table type-checking mechanism. You still must address the **total** constraint separately.

## 12. Quick Reference

| Concept | Core Rule |
| --- | --- |
| **Supertype** | Shared entity holding common identity and shared attributes |
| **Subtype** | A subset of the supertype; inherits identity, adds specific attributes/rules |
| **Disjoint** | A parent object belongs to at most one child in the group |
| **Overlapping** | A parent object can belong to multiple children in the same group |
| **Total** | Every parent object must belong to at least one child |
| **Partial** | A parent object may not yet belong to any child |
| **Single table for hierarchy** | Discriminator + shared/specific columns; easy CHECK for disjoint + total in simple groups |
| **Supertype + subtype tables** | Shared PK/FK, shared attributes in parent, specific in children; total requires extra checks |
| **Table per concrete type** | Each table holds both shared and specific attributes; watch hierarchy-wide UNIQUE and FKs |
| **Shared PK** | One object retains a single identity across its subtypes |
| **CHECK with NULL** | Must use NOT NULL/IS NOT NULL properly so UNKNOWN does not slip through |
| **Child → parent FK** | Only verifies parent existence; does not force parent to have a child |
| **Switching or adding types** | Review EER constraints, migrations, queries, and lifecycle |

**Conclusion:** Mapping supertypes and subtypes to tables is not simply picking the fewest tables. What matters is preserving **hierarchy-wide identity**, **uniqueness**, **type-appropriate attributes**, **disjoint/overlapping rules**, and **total/partial participation**. A single table is simple when types are disjoint with few specific attributes; supertype + subtype tables are flexible for multiple roles or rich type-specific behavior; table-per-concrete-type is convenient for independent processing but demands care with system-wide constraints. Choose the strategy based on verifiable requirements first, and only then optimize SQL, indexes, and physical design.
