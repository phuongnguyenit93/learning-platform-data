# Dependency Preservation and Normalization Level Trade-Offs

## Learning Objectives

Decomposing a large relation into smaller relations is an important tool for reducing redundancy, limiting update anomalies, and organizing data clearly. Yet a decomposition that "looks well normalized" can still force **a business rule previously checked within a single relation to be checked across multiple relations**. This is the problem of **dependency preservation**.

This lesson belongs to the **Data Dependencies** chapter in the **DATABASE_DATA_MODELING** module. In line with the module's goals, learners must turn business requirements into data models with clear entities, relationships, constraints, and keys; and know how to use normalization, indexes, physical schemas, and relational/document/graph/analytical modeling choices to build structures that are fit for purpose, evolvable, and verifiable. This lesson focuses on the **trade-off between normalization level and the ability to preserve functional dependencies** when designing relations.

After this lesson, you will be able to:

1. State precisely the meaning of **functional dependencies** and **dependency preservation** in a decomposition.
2. Distinguish a **lossless-join decomposition** from **dependency preservation**: these are two independent criteria.
3. Check whether a dependency is implied by local dependencies after decomposition using **attribute closure**.
4. Understand why the **3NF** synthesis algorithm can guarantee both dependency preservation and lossless join, whereas **BCNF** decomposition does not in general guarantee preserving all dependencies.
5. Analyze the formal counterexample with \(R(A,B,C)\), \(F=\{AB\to C,\ C\to B\}\), and two BCNF tables.
6. Evaluate practical impacts on **UNIQUE, keys, transactions, triggers, JOINs, redundancy, performance, and evolvability**.
7. Choose a sound design from business requirements, rather than assuming a higher normal form is always better.

## 1. Functional Dependencies Express Business Rules

Given a relation schema \(R(U)\) where \(U\) is the set of attributes. A **functional dependency** (**FD**) has the form:

\[
X \rightarrow Y,\qquad X,Y\subseteq U
\]

It states: in **every valid state** of the relation, if two tuples agree on all attributes in X, they must also agree on the attributes in Y.

\[
\forall t_1,t_2\in r(R),\quad
t_1[X]=t_2[X]\ \Longrightarrow\ t_1[Y]=t_2[Y]
\]

**Business example:** Each order belongs to one customer; the order ID determines the customer.

\[
MaDon \rightarrow MaKhach
\]

If two rows of the same order have the same MaDon but different MaKhach, the data violates this functional dependency. FDs are stated from **business semantics**, not inferred merely because test data happens to be unique.

Key terminology:

| Term | Meaning |
| --- | --- |
| **Left-hand side (X)** | Determining attribute set |
| **Right-hand side (Y)** | Determined attribute set |
| **Trivial dependency** | \(X\to Y\) with \(Y\subseteq X\) |
| **Superkey** | X such that \(X\to U\) is implied by the FDs under consideration |
| **Candidate key** | Minimal superkey; no component can be dropped while remaining a superkey |
| **Attribute closure \(X^+\)** | All attributes derivable from X using the FDs |
| **Dependency closure \(F^+\)** | The set of all FDs logically implied by F |

In classical relational algebra, these definitions consider tuples with definite values and set semantics. SQL can permit **NULL** and duplicate rows, so when mapping FDs to SQL you must choose clear NULL, key, and domain rules; do not assume a UNIQUE check on a nullable column enforces every mathematical FD identically.

### 1.1. Two Types of Violations Not to Confuse

**A functional dependency violation** is two tuples having the same X value yet different Y values, such as the same MaKhach with different TenKhach in a system specifying each customer ID maps to a single managed name.

**A key violation** is two tuples duplicating a candidate key value (and differing on other attributes). An FD whose left-hand side is **not a superkey** still matters: it can be violated even when all primary keys remain unique.

For example, orders with distinct order IDs yet the same MaKhach and different customer names may not violate the MaDon key; they do violate \(MaKhach\to TenKhach\).

## 2. Why Decompose and Why Evaluate Two Criteria?

Suppose there is a combined table serving sales operations:

~~~~text
CHI_TIET_BAN(
    MaDon, MaKhach, TenKhach,
    MaSP, TenSP, SoLuong
)
~~~~

We set the business dependency set:

\[
\begin{aligned}
MaDon &\rightarrow MaKhach\\
MaKhach &\rightarrow TenKhach\\
MaSP &\rightarrow TenSP\\
(MaDon,MaSP) &\rightarrow SoLuong
\end{aligned}
\]

In this example, each product appears on **at most one line per order**; if business rules allow a product to repeat across multiple lines, a line identifier must be added or the key revised. Under these FDs, **(MaDon, MaSP)** is a candidate key of the combined relation.

A few sample rows:

| MaDon | MaKhach | TenKhach | MaSP | TenSP | SoLuong |
| --- | --- | --- | --- | --- | ---: |
| D01 | K01 | An | P01 | Pen | 2 |
| D01 | K01 | An | P02 | Notebook | 1 |
| D02 | K01 | An | P01 | Pen | 3 |

If customer K01 changes display name, **multiple rows** must be updated. If only one row is updated, the same K01 ends up with two different names, violating the FD. If all lines of a product are deleted, we could lose the product name even though the product catalog still needs to exist. These are examples of **update/deletion/insertion anomalies**.

Decomposing the table to store customer, product, order, and order-line information separately reduces repeated data. However, before decomposing, at least two things must be evaluated:

1. **Lossless join:** From the projections onto the child tables, can the original relation be reconstructed exactly via the corresponding natural join in every valid state?
2. **Dependency preservation:** Can all original FDs be checked by checking appropriate FDs **within each child table**, without joining tables back together to detect violations?

These two questions are different. A decomposition can be **lossless yet fail to preserve dependencies**, or **preserve some FDs while producing spurious tuples on JOIN**.

## 3. Lossless-Join Decomposition

Suppose relation R is split into schemas \(R_1,\ldots,R_n\). Let \(\pi_{R_i}(r)\) be the projection of state r onto the attributes of \(R_i\).

A decomposition is **lossless-join** with respect to dependency set F if for every state \(r\) satisfying F:

\[
r=\pi_{R_1}(r)\bowtie\pi_{R_2}(r)\bowtie\cdots\bowtie\pi_{R_n}(r)
\]

Here \(\bowtie\) is the **natural join** on common attributes, applied in the classical relational model with set semantics.

**Key point:** Losslessness does not say that arbitrary data combinations inserted into the child tables form a valid state of R. It only guarantees that projecting and JOINing **neither drops nor fabricates tuples** for original states that already satisfy the FDs.

### 3.1. Quick Condition for Two-Table Decomposition

If \(R\) is split into \(R_1\) and \(R_2\), a necessary and sufficient criterion for lossless decomposition under F is that at least one of the following two dependencies belongs to \(F^+\):

\[
(R_1\cap R_2)\rightarrow (R_1-R_2)
\]

or

\[
(R_1\cap R_2)\rightarrow (R_2-R_1)
\]

Equivalently: the common attributes form a superkey of **at least one of the two projections**.

For example, \(R(A,B,C)\) with FD \(A\to B\), decomposed into \(R_1(A,B)\) and \(R_2(A,C)\). The intersection is A and A determines B, so the decomposition is **lossless**.

### 3.2. Example of a Decomposition That Generates Spurious Tuples

Consider the original relation:

| A | B | C |
| --- | --- | --- |
| a1 | b1 | c1 |
| a2 | b1 | c2 |

Project onto R1(A,B):

| A | B |
| --- | --- |
| a1 | b1 |
| a2 | b1 |

Project onto R2(B,C):

| B | C |
| --- | --- |
| b1 | c1 |
| b1 | c2 |

Joining R1 and R2 on B produces **four tuples**, including **(a1,b1,c2)** and **(a2,b1,c1)** which never existed in the original relation. These are **spurious tuples**. When B determines neither A nor C, decomposing into AB and BC is not guaranteed lossless.

Thus, merely seeing that every child table has a primary key or achieves some normal form is **not enough** to conclude the decomposition is lossless.

## 4. Dependency Preservation

Given original schema \(R(U)\) with FD set \(F\), and decomposition \(\rho=\{R_1,\ldots,R_n\}\).

On each child table \(R_i\), we have the set of **projected dependencies**:

\[
F_i = \pi_{R_i}(F)
    =\{X\to Y\in F^+\mid X\cup Y\subseteq R_i\}
\]

Union of local dependencies:

\[
G=F_1\cup F_2\cup\cdots\cup F_n
\]

The decomposition **preserves dependencies** when:

\[
G^+=F^+
\]

Because every FD in \(G\) is derived from F, \(G^+\subseteq F^+\) always holds. In practice, it suffices to verify that every FD of a generating set of F — such as the FDs in F or a minimal cover — **can be derived from G**.

### 4.1. Operational Meaning

If dependencies are preserved:

- Every original FD can be derived from constraints checkable **within individual child relations**.
- There is no need to join all child tables just to verify validity of the original FDs.
- Checking and maintaining constraints during inserts, updates, and deletes is usually easier to organize, especially in write-heavy transactional systems.

However, **dependency preservation does not mean SQL automatically enforces every FD with PRIMARY KEY or UNIQUE**. An FD whose left-hand side is not a key may still require triggers, data checks, or a different design. Preservation only states that **the information needed to check the FD sits entirely inside one local relation**, not that a simple declarative syntax exists for it.

### 4.2. Do Not Keep Only Verbatim FDs

When projecting F onto each table, you must include **FDs implied in \(F^+\)**, not only the FDs originally written down. A dependency that does not appear verbatim in F can still be an important local dependency.

For example, if \(A\to B\) and \(B\to C\), then \(A\to C\) follows by transitivity. If a child table contains only A and C, the dependency \(A\to C\) still belongs to the FD projection onto that table even if it was not explicitly listed in F.

### 4.3. Checking Using Attribute Closure

To test whether \(X\to Y\) is derivable from G:

1. Initialize \(X^+=X\).
2. For each FD \(L\to R\) in G, if \(L\subseteq X^+\), add the attributes of R to \(X^+\).
3. Repeat until no new attributes can be added.
4. If \(Y\subseteq X^+\), the dependency is implied; otherwise, it **is not preserved by the local FDs under consideration**.

Example \(G=\{A\to B,\ B\to C\}\). Start with \(A^+=\{A\}\), apply A→B to get \(\{A,B\}\), then B→C to get \(\{A,B,C\}\). Because C is in \(A^+\), we derive \(A\to C\).

This is a **logical check on the schema**, not a SQL SELECT scanning current data. A small violation-free dataset is not enough to prove an FD will always be preserved when new data arrives.

## 5. Synthesizing a 3NF Schema to Preserve Dependencies

**Third Normal Form (3NF)** offers a practical target: there is a 3NF synthesis algorithm that guarantees both **dependency preservation** and **lossless-join decomposition** for the known FD set. This is a strong advantage when data must be strictly validated during write transactions.

### 5.1. Review of the 3NF Condition

A schema R is in **3NF** with respect to FD set F if for every non-trivial FD \(X\to A\) in \(F^+\), where A is a single attribute, **at least one** of the following holds:

1. X is a **superkey** of R; or
2. A is a **prime attribute**, meaning A belongs to **at least one candidate key** of R.

A **prime** attribute is not synonymous with an attribute in the **chosen primary key**. If R has multiple candidate keys, an attribute can belong to an unchosen candidate key and still be a prime attribute.

This condition will be crucial in the 3NF–BCNF counterexample in the next section.

### 5.2. The 3NF Synthesis Algorithm

A commonly used version of the algorithm:

1. **Find a minimal/canonical cover** \(F_c\) equivalent to F. Typically reduce each FD to a single-attribute right-hand side, remove extraneous left-hand attributes, and remove redundant FDs.
2. **For each FD \(X\to A\) in \(F_c\)**, create a sub-schema consisting of \(X\cup\{A\}\). FDs sharing the same left-hand side can be merged into one schema.
3. **Remove any sub-schema wholly contained** within another sub-schema, provided removal does not affect synthesis requirements.
4. **If no sub-schema yet contains a candidate key of R**, add a schema containing that candidate key.
5. Determine the PK, candidate keys, FKs, and business constraints of each table before SQL implementation.

Under the standard conditions of the 3NF synthesis algorithm, the output carries three guarantees:

- Each generated schema achieves **3NF**.
- The dependencies in F are **preserved** via local dependencies.
- The decomposition is **lossless-join**; the step ensuring a schema contains a candidate key plays a key role in the proof.

**Be careful:** these are guarantees of the **correct synthesis algorithm** on an accurately identified FD set, not guarantees for **every arbitrary split of R into tables that happen to be in 3NF**. Missing business FDs or dropping tables improperly can still lose constraints.

### 5.3. Applying to the Order Example

Returning to the relation:

\[
R(MaDon,MaKhach,TenKhach,MaSP,TenSP,SoLuong)
\]

FD set:

\[
F=\{
MaDon\to MaKhach,\
MaKhach\to TenKhach,\
MaSP\to TenSP,\
MaDon\,MaSP\to SoLuong
\}
\]

This set already has single-attribute right-hand sides and, by assumption, no extraneous attribute on the left-hand side of the last FD. It serves as an appropriate minimal cover for the example.

With \(X=\{MaDon,MaSP\}\), the closure computation proceeds:

\[
\begin{aligned}
X^+_0 &= \{MaDon,MaSP\}\\
X^+_1 &= \{MaDon,MaSP,MaKhach,TenSP,SoLuong\}\\
X^+_2 &= \{MaDon,MaSP,MaKhach,TenSP,SoLuong,TenKhach\}
\end{aligned}
\]

Because the closure contains every attribute, **(MaDon, MaSP)** is a superkey. Neither MaDon nor MaSP can be removed while still deriving all attributes, so it is a **candidate key**.

Synthesis creates four relations:

| Child table | Attributes | Dependency preserved at table |
| --- | --- | --- |
| **DON_HANG** | MaDon, MaKhach | \(MaDon\to MaKhach\) |
| **KHACH_HANG** | MaKhach, TenKhach | \(MaKhach\to TenKhach\) |
| **SAN_PHAM** | MaSP, TenSP | \(MaSP\to TenSP\) |
| **DONG_DON_HANG** | MaDon, MaSP, SoLuong | \((MaDon,MaSP)\to SoLuong\) |

No separate key table needs to be added, because DONG_DON_HANG already contains the candidate key **(MaDon, MaSP)** of the original relation.

### 5.4. Why Does This Design Both Preserve Dependencies and Avoid Loss?

**Dependency preservation:** Each FD in F has **all involved attributes inside a single child table**. For instance, to check MaKhach→TenKhach, only KHACH_HANG needs inspection; to check (MaDon,MaSP)→SoLuong, only DONG_DON_HANG needs inspection. No JOIN is needed to tell whether the same customer ID has two names or the same order–product pair has two different quantities.

**Lossless join:** For valid data of R, we can:

- Join DONG_DON_HANG with DON_HANG on MaDon; since MaDon determines MaKhach, no spurious customer IDs are introduced.
- Join next with KHACH_HANG on MaKhach; since MaKhach determines TenKhach, exact names are recovered.
- Join SAN_PHAM on MaSP; since MaSP determines TenSP, exact product names are recovered.

From projections of a state of R satisfying F, the JOIN reconstructs the exact original tuples. The fact that real catalog tables may also hold customers or products with no transactions yet **does not invalidate the decomposition logic**: in a losslessness proof, we examine **projections of the same original relation**, not arbitrary joins over out-of-scope catalog records.

### 5.5. PostgreSQL DDL for the Dependency-Preserving Design

The following SQL script is self-contained and can be run in order on an empty test database:

~~~~sql
CREATE TABLE khach_hang_3nf (
    ma_kh VARCHAR(20) PRIMARY KEY,
    ten_kh VARCHAR(120) NOT NULL
);

CREATE TABLE san_pham_3nf (
    ma_sp VARCHAR(20) PRIMARY KEY,
    ten_sp VARCHAR(120) NOT NULL
);

CREATE TABLE don_hang_3nf (
    ma_don VARCHAR(20) PRIMARY KEY,
    ma_kh VARCHAR(20) NOT NULL,
    CONSTRAINT fk_don_khach_3nf
        FOREIGN KEY (ma_kh)
        REFERENCES khach_hang_3nf(ma_kh)
);

CREATE TABLE dong_don_hang_3nf (
    ma_don VARCHAR(20) NOT NULL,
    ma_sp VARCHAR(20) NOT NULL,
    so_luong INTEGER NOT NULL,
    CONSTRAINT pk_dong_3nf PRIMARY KEY (ma_don, ma_sp),
    CONSTRAINT fk_dong_don_3nf
        FOREIGN KEY (ma_don) REFERENCES don_hang_3nf(ma_don),
    CONSTRAINT fk_dong_sp_3nf
        FOREIGN KEY (ma_sp) REFERENCES san_pham_3nf(ma_sp),
    CONSTRAINT ck_dong_so_luong_3nf CHECK (so_luong > 0)
);

INSERT INTO khach_hang_3nf (ma_kh, ten_kh)
VALUES ('K01', 'An'), ('K02', 'Bình');

INSERT INTO san_pham_3nf (ma_sp, ten_sp)
VALUES ('P01', 'Pen'), ('P02', 'Notebook');

INSERT INTO don_hang_3nf (ma_don, ma_kh)
VALUES ('D01', 'K01'), ('D02', 'K01');

INSERT INTO dong_don_hang_3nf (ma_don, ma_sp, so_luong)
VALUES
    ('D01', 'P01', 2),
    ('D01', 'P02', 1),
    ('D02', 'P01', 3);
~~~~

The PKs guarantee:

- One MaKhach has only one KHACH_HANG row with one current TenKhach.
- One MaSP has only one SAN_PHAM row with one current TenSP.
- One MaDon has only one DON_HANG row with one MaKhach.
- One pair (MaDon, MaSP) has only one DONG_DON_HANG row with one SoLuong.

The FKs protect relationships between order–customer, line–order, and line–product. **FDs and FKs are two distinct constraint types**; both are needed in a complete data model.

Query reconstructing the combined data shape:

~~~~sql
SELECT
    d.ma_don,
    d.ma_kh,
    k.ten_kh,
    ct.ma_sp,
    sp.ten_sp,
    ct.so_luong
FROM dong_don_hang_3nf AS ct
JOIN don_hang_3nf AS d
    ON d.ma_don = ct.ma_don
JOIN khach_hang_3nf AS k
    ON k.ma_kh = d.ma_kh
JOIN san_pham_3nf AS sp
    ON sp.ma_sp = ct.ma_sp
ORDER BY d.ma_don, ct.ma_sp;
~~~~

| ma_don | ma_kh | ten_kh | ma_sp | ten_sp | so_luong |
| --- | --- | --- | --- | --- | ---: |
| D01 | K01 | An | P01 | Pen | 2 |
| D01 | K01 | An | P02 | Notebook | 1 |
| D02 | K01 | An | P01 | Pen | 3 |

If customer K01's name changes, only **one KHACH_HANG row** needs updating; every order referencing K01 continues reading the current name accurately. If storing **the name at transaction time** is required, that is a separate historical data requirement needing a business-meaningful snapshot or versioning model, not duplicating data merely to avoid a JOIN.

### 5.6. Testing Preservation Directly via DDL

The following operations are expected to be rejected by the relevant constraints:

~~~~sql
-- Two records with the same customer ID but different names:
INSERT INTO khach_hang_3nf (ma_kh, ten_kh)
VALUES ('K01', 'Other name');
-- Violates PRIMARY KEY(ma_kh).

-- Two records with the same order ID but different customers:
INSERT INTO don_hang_3nf (ma_don, ma_kh)
VALUES ('D01', 'K02');
-- Violates PRIMARY KEY(ma_don).

-- Two records with the same order and product pair:
INSERT INTO dong_don_hang_3nf (ma_don, ma_sp, so_luong)
VALUES ('D01', 'P01', 99);
-- Violates PRIMARY KEY(ma_don, ma_sp).

-- Order line referencing a nonexistent order ID:
INSERT INTO dong_don_hang_3nf (ma_don, ma_sp, so_luong)
VALUES ('D99', 'P01', 1);
-- Violates FOREIGN KEY.
~~~~

Run each error-test statement individually; do not include them as successful seed data. Having PKs reject two rows sharing the same left-hand side with different right-hand sides is a **strong enforcement** of the relevant FDs in this example: the left-hand side of each FD is the key of a child table.

**Notable observation:** The four resulting tables not only achieve 3NF, but under the stated FDs they also achieve **BCNF** because every corresponding non-trivial FD left-hand side is a key. This shows that **BCNF does not always lose dependencies**; dependency loss occurs only for **specific FD structures and decompositions**.

## 6. BCNF: Stronger Normalization That Can Lose Dependencies

**Boyce–Codd Normal Form (BCNF)** requires that for **every non-trivial FD** \(X\to Y\) in \(F^+\), **X must be a superkey** of the relation under consideration.

Compared to 3NF:

- **BCNF** accepts only superkeys on the left-hand side.
- **3NF** also accepts cases where the left-hand side is not a superkey **if the right-hand attribute is prime**.

Hence:

\[
BCNF\ \Longrightarrow\ 3NF
\]

but the converse **does not always hold**.

Decomposing on a BCNF-violating FD can produce two schemas and remain **lossless**. However, after decomposing, an original FD can end up spanning attributes across **multiple tables**, so it can no longer be derived from local FD sets.

### 6.1. Classic Counterexample

Given:

\[
R(A,B,C)
\]

and functional dependency set:

\[
F=\{AB\rightarrow C,\quad C\rightarrow B\}
\]

In words:

- The pair **(A,B)** determines C.
- The value **C** determines B.

No other FDs exist beyond those logically implied by these two rules. We assume **A, B, C are definite values**, avoiding SQL-style NULL complications.

### 6.2. Identifying Candidate Keys

Compute the key closures:

\[
\begin{aligned}
(AB)^+ &= \{A,B,C\}
&&\text{(via }AB\to C\text{)}\\
(AC)^+ &= \{A,B,C\}
&&\text{(via }C\to B\text{)}\\
C^+ &= \{C,B\}
&&\text{(does not derive A)}\\
A^+ &= \{A\},\qquad B^+=\{B\}
\end{aligned}
\]

Therefore, the two **candidate keys** are:

\[
\boxed{\{A,B\}\quad\text{and}\quad\{A,C\}}
\]

Attributes **A, B, and C are all prime attributes**, because each appears in at least one candidate key.

### 6.3. Relation R Is in 3NF but Not in BCNF

For \(AB\to C\), AB is a superkey, so it **satisfies both 3NF and BCNF**.

For \(C\to B\):

- C **is not a superkey**, because \(C^+=\{B,C\}\) does not contain A.
- B **is a prime attribute**, because B belongs to candidate key AB.

Thus the FD \(C\to B\) **is allowed in 3NF** yet **violates BCNF**. The overall schema R satisfies **3NF without satisfying BCNF**.

This is not a flaw in the proof: 3NF intentionally permits certain FDs of this sort so dependency preservation remains achievable when BCNF decomposition cannot satisfy both goals.

### 6.4. Decomposing into Two BCNF Relations

Decompose on the violating dependency \(C\to B\):

\[
R_1(C,B),\qquad R_2(A,C)
\]

Check each schema:

- In **R1(C,B)** we have FD \(C\to B\). C is the key of R1, so **R1 is in BCNF**.
- In **R2(A,C)**, no non-trivial FD with a non-superkey left-hand side is implied by F. Under the given FDs, **R2 is in BCNF**.

**Lossless check:** The attribute intersection is \(R_1\cap R_2=\{C\}\); F contains \(C\to B\), so C determines \(R_1-R_2=\{B\}\). Therefore decomposing into CB and AC is **lossless-join**.

### 6.5. Yet Dependency \(AB\to C\) Is No Longer Preserved

Project the FD set onto each table:

~~~~text
R1(C,B):  C → B
R2(A,C):  no non-trivial FDs need to be added
~~~~

The local dependency set available to check is:

\[
G=\{C\to B\}
\]

To test \(AB\to C\), compute the closure under **G**, not the original F:

\[
(AB)^+_G=\{A,B\}
\]

No FD in G with left-hand side C is triggered because C is not yet in the closure. Hence **C is not derived**:

\[
G\not\models AB\to C
\]

Summary:

| Property of decomposition \(R_1(C,B),R_2(A,C)\) | Result |
| --- | --- |
| Both tables achieve BCNF | **Yes** |
| Decomposition is lossless-join under F | **Yes** |
| Preserves FD \(C\to B\) | **Yes** |
| Preserves FD \(AB\to C\) | **No** |
| Fully preserves F | **No** |

In other words, **BCNF is gained** while **the ability to check a business FD using local FDs alone is lost**.

## 7. Seeing the Failure with Data and SQL

The counterexample becomes even clearer if we insert into the two child tables rows that **are both valid under local constraints**, yet when JOINed produce data violating the original FD.

### 7.1. Data After Decomposition

Table R2(A,C):

| A | C |
| --- | --- |
| a1 | c1 |
| a1 | c2 |

Table R1(C,B):

| C | B |
| --- | --- |
| c1 | b1 |
| c2 | b1 |

These tuples do not violate local FDs:

- In R1, each C determines one B; **c1→b1** and **c2→b1** are both valid. Multiple C values may map to the same B.
- In R2, each (A,C) pair is unique and no dependency requires A to determine C.

JOINing on C yields:

| A | B | C |
| --- | --- | --- |
| a1 | b1 | c1 |
| a1 | b1 | c2 |

Two tuples share **(A,B)=(a1,b1)** yet have different C values. They **violate \(AB\to C\)**.

This does not contradict "lossless-join decomposition": the tables just inserted are **two child relations valid under local constraints**, but they **are not projections of an original state satisfying F**. Losslessness only specifies what happens **when starting from a valid original state**.

### 7.2. PostgreSQL DDL Reproducing the Counterexample

The following SQL snippet is a standalone scenario:

~~~~sql
-- R1(C,B): C → B, so C is the key.
CREATE TABLE r_cb_bcnf (
    c VARCHAR(10) PRIMARY KEY,
    b VARCHAR(10) NOT NULL
);

-- R2(A,C): pair (A,C) identifies each row of this relation.
CREATE TABLE r_ac_bcnf (
    a VARCHAR(10) NOT NULL,
    c VARCHAR(10) NOT NULL,
    PRIMARY KEY (a, c),
    FOREIGN KEY (c) REFERENCES r_cb_bcnf(c)
);

INSERT INTO r_cb_bcnf (c, b) VALUES
    ('c1', 'b1'),
    ('c2', 'b1');

INSERT INTO r_ac_bcnf (a, c) VALUES
    ('a1', 'c1'),
    ('a1', 'c2');

SELECT ac.a, cb.b, ac.c
FROM r_ac_bcnf AS ac
JOIN r_cb_bcnf AS cb ON cb.c = ac.c
ORDER BY ac.a, cb.b, ac.c;
~~~~

All INSERTs above are valid under the declared PKs and FK. Yet the JOIN result contains **(a1,b1,c1)** and **(a1,b1,c2)**, violating \(AB\to C\).

Notably, we even added an **FK from AC to CB** so every C in AC has a matching CB row. The FK protects referential existence yet **still does not preserve \(AB\to C\)**.

### 7.3. Why Can't We Simply Add UNIQUE to One of the Two Tables?

- R1 only has B and C, so it **lacks A** to check \(AB\to C\).
- R2 only has A and C, so it **lacks B** to check \(AB\to C\).
- Adding **UNIQUE(C)** on R2 is **too strict**: it forbids two different A values from linking to the same C, even though that is completely valid under the original F.
- Adding **UNIQUE(A)** on R2 is also too strict, because F does not state A alone determines C.

Example valid original state:

| A | B | C |
| --- | --- | --- |
| a1 | b1 | c1 |
| a2 | b1 | c1 |

It satisfies \(AB\to C\) because the two AB pairs differ, and satisfies \(C\to B\) because the same C determines the same B. If C were forced unique in R2, we would reject this valid state. Therefore, **forcing an improper key to stand in for a lost dependency** corrupts the model.

### 7.4. What Price Must Be Paid to Keep BCNF?

If you keep the two BCNF tables above, enforcing \(AB\to C\) requires a **cross-table** checking mechanism:

- Whenever inserting/updating R2(A,C) or updating R1(C,B), verify that no **two different C values** produce the same AB pair after joining.
- If using triggers, you must account for **concurrent transactions**, check timing, appropriate locking, or sufficiently strong isolation levels; naive check-then-write triggers suffer race conditions.
- You could maintain an **auxiliary table or mapping** with a unique constraint on AB, though the extra table must be kept consistent and can diminish the benefits of the initial decomposition.
- Or accept keeping the relation in **3NF** when preserving and enforcing the dependency outweighs the benefit of reaching BCNF.

Dependency preservation is a logical design criterion; deciding how to enforce it also involves **operational cost, transactions, and DBMS capabilities**.

## 8. Dependency Preservation Does Not Mean Every FD Becomes UNIQUE

An easily overlooked point is that **mathematical preservation** and **SQL constraint enforcement** are not the same concept.

In the initial schema \(R(A,B,C)\):

\[
F=\{AB\to C,\ C\to B\}
\]

R is in 3NF and both FDs sit within **one relation**, so no information is missing when checking locally. However, **C is not a superkey**; the dependency \(C\to B\) cannot be accurately protected merely by a UNIQUE(C) constraint without blocking valid states where multiple A values share the same C.

### 8.1. SQL Example: Keys Do Not Automatically Enforce Non-Key FDs

~~~~sql
CREATE TABLE r_3nf_vi_du (
    a VARCHAR(10) NOT NULL,
    b VARCHAR(10) NOT NULL,
    c VARCHAR(10) NOT NULL,
    CONSTRAINT pk_r_3nf PRIMARY KEY (a, b),
    CONSTRAINT ak_r_3nf UNIQUE (a, c)
);

INSERT INTO r_3nf_vi_du (a, b, c) VALUES
    ('a1', 'b1', 'c1'),
    ('a2', 'b2', 'c1');
~~~~

These operations **are permitted by PRIMARY KEY(A,B) and UNIQUE(A,C)**, because the two AB pairs differ and the two AC pairs differ. Yet the same **C = c1** has both **B = b1** and **B = b2**, violating \(C\to B\).

We can detect it with a local query:

~~~~sql
SELECT c
FROM r_3nf_vi_du
GROUP BY c
HAVING COUNT(DISTINCT b) > 1;
-- Result: c1
~~~~

Because b is declared NOT NULL, COUNT(DISTINCT b) reflects the number of distinct B values for each C in this example. If b were nullable, NULL semantics must be defined and the check adjusted accordingly.

**Conclusion:** The dependency-preserving 3NF schema here can **detect violations within table R itself**, yet **preventing violations at write time** may require a multi-row constraint mechanism such as triggers/transactions or restructuring the tables. This differs from the synthesis example in Section 5, where the left-hand sides of the FDs were chosen as keys of individual small tables so PKs enforce them directly.

### 8.2. Comparing Constraint Mechanisms

| Mechanism | What it checks well | Limitations regarding FDs |
| --- | --- | --- |
| **PRIMARY KEY** | Unique identification, non-NULL | Does not directly express FDs whose left-hand side is not a superkey |
| **UNIQUE** | No duplicate combinations of chosen attributes per DBMS semantics | Can be **too strict** when expressing \(X\to Y\) where X is allowed to repeat |
| **NOT NULL** | An attribute must have a value | Does not express functional determination across tuples |
| **FOREIGN KEY** | Referenced value must have a matching parent row | Does not automatically check all cross-table FDs or "at least one child row" |
| **CHECK** | Conditions on a single row's values, domains, and column combinations | In PostgreSQL cannot directly query other rows to check cross-tuple FDs |
| **Triggers / transactional checks** | Can enforce complex logic, including cross-table rules | Requires proper design of timing, locking, and concurrency handling |
| **Periodic data audits** | Detects violations that slipped into stored data | Does not replace rejecting violations at write time |

If a dependency is **not preserved** by a decomposition, checking cost can be higher because of JOINs or state synchronization across tables. If a dependency **is preserved** yet its left-hand side is not a key, an appropriate enforcement mechanism must still be chosen.

## 9. Comparing Normalization Levels and Trade-Off Goals

### 9.1. 2NF, 3NF, and BCNF Solve Different Problems

| Normal form | Core idea under functional dependencies | Caveats |
| --- | --- | --- |
| **1NF** | Columns hold atomic values under the chosen relational model, no non-relational repeating groups | Does not address FD-driven redundancy |
| **2NF** | In 1NF; no non-prime attribute partially depends on any candidate key | Does not eliminate all transitive dependencies or non-key-LHS FDs |
| **3NF** | For every non-trivial \(X\to A\), X is a superkey **or** A is a prime attribute | Anomalies from non-key-LHS FDs may remain |
| **BCNF** | For every non-trivial FD, the left-hand side is a superkey | Eliminates more FD-driven anomalies, but decomposition may fail to preserve FDs |

**Practical point:** A table in 3NF is not necessarily in BCNF; a set of tables all in BCNF does not automatically prove that **the system-wide decomposition** preserves all original dependencies.

Higher normal forms such as **4NF** or **5NF** further address multivalued dependencies and join dependencies. Reaching BCNF does not automatically resolve every kind of redundancy. This lesson stays focused on **functional dependencies**, as they form the foundation of the 3NF–BCNF trade-off.

### 9.2. The Claim "Higher Normalization Is Always Better" Is Unconditional and Flawed

A design decision must evaluate all of:

1. **Redundancy reduction:** Is data repeating along an FD whose left-hand side is not a key?
2. **Update safety:** Does a business change require modifying one row or many rows?
3. **FD preservation:** Can original rules be checked without cross-table JOINs?
4. **Losslessness:** Do planned JOINs recover exact information?
5. **Query cost:** Do common queries add complex JOINs or UNIONs? Are proper indexes available?
6. **Write cost and concurrency:** Which rules must be enforced across multiple tables and transactions?
7. **Evolvability:** When business keys change, attributes are added, or new sources arrive, which schema is easier to maintain?
8. **DBMS constraint enforcement:** Which rules can be enforced with PK/FK/UNIQUE, and which require triggers or other mechanisms?

For the counterexample \(R(A,B,C)\):

- In **3NF keeping R intact**, both AB→C and C→B can be checked **within a single table**. However, B repeats for the same C across multiple rows, risking inconsistent updates and requiring an appropriate mechanism to protect C→B.
- In **BCNF splitting into AC and CB**, B is stored once per C, making updates to B for a given C simpler. Yet AB→C is **no longer local**, and can be violated even when both child tables satisfy their individual PKs/FKs.

There is no free lunch: **reducing redundancy can increase the cost of protecting another dependency**.

### 9.3. Decision Matrix: 3NF vs. BCNF

| Criterion | Algorithmic 3NF Synthesis | BCNF Decomposition |
| --- | --- | --- |
| Normal form of resulting tables | 3NF, sometimes also BCNF | BCNF |
| Lossless join | Guaranteed by algorithm | Achievable via lossless decomposition |
| Preserves all known FDs | **Guaranteed by algorithm** | **No general guarantee** |
| Anomalies from non-key-LHS FDs | May remain in some 3NF schemas | Eliminated for the FDs considered |
| Single-table FD checking | Can be organized locally | Some original FDs may require JOINs |
| All FDs enforced by UNIQUE/PK alone | **Not guaranteed automatically** | **Not guaranteed automatically**, especially unpreserved FDs |
| JOIN, update, and index cost | Depends on table count and queries | Depends on decomposition; may add tables and cross-table checks |
| When typically preferred | Constraint preservation is critical and you want a guaranteed baseline | Minimizing FD redundancy is top priority and either no critical FD is lost or extra enforcement is in place |

Do not turn this table into a blanket rule "always pick 3NF". If a BCNF decomposition **still preserves all FDs**, BCNF is usually very attractive: stronger normalization without paying a dependency-preservation penalty. The four-table example in Section 5 is one such case.

### 9.4. Query Cost Is More Than Just JOIN Count

One large table with fewer JOINs is not necessarily faster because:

- Repeated data inflates table and index sizes, increasing I/O and update cost.
- Normalized tables can yield smaller indexes and more selective filters.
- Query optimizers and statistics handle JOINs efficiently, especially on properly indexed keys.
- Conversely, many JOINs across large tables and complex reporting pipelines can carry real cost.

Measure **actual queries**, execution plans, write volume, lock contention, storage footprint, and data growth rates. **Do not break a business dependency merely to remove one JOIN in a report.**

### 9.5. Denormalization Is a Separate Decision

A system may intentionally store an extra copy of a customer name or precomputed revenue total for reporting, caching, or an analytical data warehouse. This is **intentional denormalization**, and should be accompanied by:

- Identifying the **source of truth**.
- Rules for updating or refreshing the copy, acceptable staleness, and error-handling strategy.
- Periodic consistency checks, violation monitoring, and repair mechanisms.
- Documentation distinguishing a **historical snapshot** field from an **optimization replica** field.

**Materialized views** or analytical data models can speed up queries without forcing you to drop constraints on transactional write tables. In document or graph databases, the same question applies: is shared information stored in one place or copied across multiple places, and how are business rules verified?

## 10. A Verifiable Process for Choosing Normalization Level

A practical workflow should start from **business constraints**, rather than a preset target like "how many tables to split into".

### Step 1 — Define the Meaning of One Tuple

State clearly what event or entity each row represents: a customer, an order, an order line, or a price record. The same column name can carry different meanings depending on grain. For example, **MaSP→TenSP** may hold for the current product catalog yet not replace storing **TenSP at the time of sale** when the business requires a historical snapshot.

### Step 2 — Gather Functional Dependencies from the Business

Write each FD as a falsifiable question:

- **MaDon→MaKhach:** does an order ID always have the same customer ID?
- **MaKhach→TenKhach:** does the same customer ID always have the same current name?
- **(MaDon,MaSP)→SoLuong:** can a product appear on multiple lines within one order?

Ask about exceptions, effective dates, tenants, code changes, and data imported from multiple systems. Avoid treating constraints that **happen to hold in a test sample** as global functional dependencies.

### Step 3 — Find Keys and Minimal Cover

Compute closures of attribute sets to find superkeys and candidate keys. From confirmed FDs, compute a minimal cover; eliminate extraneous attributes and redundant FDs. If critical FDs are missing from the start, both 3NF and BCNF proofs can lead to a model that violates business reality.

### Step 4 — Generate a Guaranteed 3NF Baseline

Apply the 3NF synthesis algorithm:

- Every FD in the minimal cover gets a schema containing all attributes of that FD.
- Remove redundant sub-schemas per the algorithm's rules.
- Ensure at least one schema contains a **candidate key of the original relation**.

This serves as the reference baseline for comparing alternatives, because it guarantees **losslessness and dependency preservation** for F.

### Step 5 — Try BCNF Decomposition

Identify BCNF-violating FDs, i.e., those whose left-hand side is not a superkey. Decompose step by step on violating dependencies, documenting:

- The intersection of the two child schemas and why the split is **lossless**.
- The FDs projected onto each child table.
- Whether every original FD is still derivable from the union of local FDs, using **attribute closure** or an appropriate preservation test.

Do not stop just because every child table "looks like BCNF": inspect the **overall outcome of the decomposition**.

### Step 6 — Evaluate Any Lost Dependencies

For each unpreserved FD:

1. Is it a **hard business rule** whose violation corrupts transactions or reports?
2. How frequently do operations occur that could violate it?
3. To verify it, how many tables must be JOINed? Are special locks or transaction isolation needed?
4. Is there an alternative BCNF decomposition that preserves that FD?
5. If not, should we **stay in 3NF**, add supporting tables/constraints, or accept supplementary check logic at a clear cost?

### Step 7 — Implement and Verify in SQL

Translate identifiers and references into **PRIMARY KEY**, **UNIQUE**, **NOT NULL**, **FOREIGN KEY**, and value checks with **CHECK**. For FDs that cannot be expressed exactly by these constraints, document the supplementary enforcement method.

Prepare counterexample data: two tuples with the same X but different Y, duplicate composite keys, orphan records, and invalid NULLs. If triggers are needed, test **concurrent** write scenarios, not only sequential INSERTs in a single connection.

### Step 8 — Measure and Maintain

Once correctness is protected:

- Measure JOIN volume, row counts, indexes, query latency, and write overhead.
- Check whether business policy changes invalidate any old FD.
- If creating summary tables or materialized views, monitor freshness and consistency with the primary source.
- Document critical FDs in schema docs, integration tests, and operational data audits.

~~~~mermaid
flowchart TD
    A["Business requirements and FDs"] --> B["Candidate keys, minimal cover"]
    B --> C["3NF synthesis: lossless + preserve"]
    C --> D{"Should we try BCNF?"}
    D -- "No" --> H["Enforce constraints and measure queries"]
    D -- "Yes" --> E["Lossless BCNF decomposition"]
    E --> F{"Are original FDs still preserved?"}
    F -- "Yes" --> H
    F -- "No" --> G["Evaluate cross-table check cost / keep 3NF"]
    G --> H
    H --> I["Test counterexamples and concurrency"]
~~~~

## 11. Self-Check Exercises

The exercises below use mathematical relational semantics with **definite values**; when asking about SQL, assume key columns and FD-checked columns are **NOT NULL** unless stated otherwise.

### Exercise 1 — Distinguishing the Two Criteria

A team splits R into R1 and R2. For every valid state r under F, joining the projections recovers r exactly. However, one original FD cannot be derived from the FDs of individual child tables.

**Question:** Is the decomposition lossless? Is it dependency-preserving?

**Answer:** **Yes, lossless**, because JOINing the projections of every valid state recovers r exactly. **Not dependency-preserving**, because an original FD cannot be derived from the union of local FDs. The two criteria are independent.

### Exercise 2 — Finding Candidate Keys

Given \(R(A,B,C)\), \(F=\{AB\to C,\ C\to B\}\).

**Question:** Which sets are candidate keys? Is C a superkey?

**Answer:** **AB and AC** are the two candidate keys. From AB we derive C; from AC we derive B via C→B. Dropping A from either set fails to derive A; A alone or B alone is also insufficient. **C is not a superkey** because \(C^+=\{C,B\}\), lacking A.

### Exercise 3 — Is the Relation in 3NF or BCNF?

Continuing with \(R(A,B,C)\) and F from Exercise 2.

**Question:** Why is R in 3NF but not in BCNF?

**Answer:** In FD \(AB\to C\), AB is a superkey. In \(C\to B\), C is not a superkey, yet B is a **prime attribute** because it belongs to candidate key AB; therefore this FD is allowed by 3NF. BCNF requires C to be a superkey for \(C\to B\), so R **is not in BCNF**.

### Exercise 4 — Checking Losslessness for a BCNF Decomposition

Decompose \(R(A,B,C)\) into \(R_1(C,B)\) and \(R_2(A,C)\).

**Question:** Why is it lossless under F?

**Answer:** The two schemas intersect at C. The FD **C→B** is implied by F, so the common attribute C determines the attributes present only in R1. By the two-table decomposition criterion, this is a **lossless decomposition**.

### Exercise 5 — Checking Dependencies After Decomposition

In the decomposition from Exercise 4, the available local FD set is \(G=\{C\to B\}\).

**Question:** Is \(AB\to C\) preserved? Compute the closure.

**Answer:** No. Under G, \((AB)^+_G=\{A,B\}\); C is not present to trigger C→B, so C cannot be derived. Therefore \(AB\to C\) **is not preserved**.

### Exercise 6 — Can Two Valid BCNF Tables JOIN into an Invalid State?

Given:

~~~~text
R1(C,B) = {(c1,b1), (c2,b1)}
R2(A,C) = {(a1,c1), (a1,c2)}
~~~~

**Question:** Do both tables satisfy local FDs? Does the JOIN violate any original FD?

**Answer:** Both satisfy local FDs: C determines one B in R1; R2 does not violate key (A,C). Yet JOINing produces **(a1,b1,c1)** and **(a1,b1,c2)**, sharing AB with different C; hence it violates **AB→C**. This illustrates **failing dependency preservation**, not a refutation of losslessness.

### Exercise 7 — Should We Add UNIQUE(C) to Fix It?

After splitting R into R1(C,B) and R2(A,C), a developer wants to place UNIQUE(C) on R2 to stop an AB pair from having multiple C values.

**Question:** Is this approach equivalent to the original FD \(AB\to C\)?

**Answer:** **No.** UNIQUE(C) on R2 forbids two different A values from referencing the same C, whereas the original F allows e.g. **(a1,b1,c1)** and **(a2,b1,c1)**. UNIQUE(C) is an **overly strong** constraint that rejects valid data.

### Exercise 8 — Synthesizing 3NF from a Business FD Set

Given relation:

~~~~text
R(MaDon, MaKhach, TenKhach, MaSP, TenSP, SoLuong)
~~~~

and F consisting of MaDon→MaKhach, MaKhach→TenKhach, MaSP→TenSP, (MaDon,MaSP)→SoLuong.

**Question:** Propose tables so every FD is checked locally. Do we need to add a table containing only a candidate key?

**Answer:** Use **DON_HANG(MaDon,MaKhach)**, **KHACH_HANG(MaKhach,TenKhach)**, **SAN_PHAM(MaSP,TenSP)**, and **DONG_DON_HANG(MaDon,MaSP,SoLuong)**. Each FD sits within one table. No separate key table is needed because DONG_DON_HANG already contains the candidate key **(MaDon,MaSP)** of the original R.

### Exercise 9 — Is "Every Table in 3NF" Enough to Conclude?

An engineer manually splits a table and verifies each individual table is in 3NF.

**Question:** From that alone, can we conclude with certainty that the decomposition is lossless and preserves all FDs?

**Answer:** **No.** The normal form of individual tables does not replace verifying **losslessness** and **dependency preservation** for the overall decomposition. Specifically, the dual guarantee is attached to the **proper 3NF synthesis algorithm**, not an arbitrary split.

### Exercise 10 — When an FD Sits in One Table Yet Is Not a Key

Still with R(A,B,C) in 3NF, someone adds PK(A,B) and UNIQUE(A,C), then claims the FD C→B is now enforced by the DB.

**Question:** Is the claim true? Give a counterexample.

**Answer:** **No.** Two rows **(a1,b1,c1)** and **(a2,b2,c1)** have different AB and different AC, so they violate neither key constraint. Yet they share C while differing on B, violating **C→B**. An additional mechanism is needed to enforce non-key dependencies.

### Exercise 11 — Choosing an Option for a Transactional System

A high-write system must strictly validate the original FDs. BCNF decomposition reduces redundancy but loses a critical FD; no concurrency-safe cross-table check mechanism exists yet.

**Question:** Are we forced to pick BCNF just because it is a higher normal form?

**Answer:** **No.** Keeping a **dependency-preserving 3NF** design is a sound choice until another approach can both enforce the constraint and meet performance goals. If BCNF is still chosen, you must design and verify an enforcement mechanism for the unpreserved FD, especially under concurrent transactions.

### Exercise 12 — Denormalizing for Reporting

To speed up reports, the system stores **TenKhach** alongside order lines even though a normalized customer table already exists. Customer names can change.

**Question:** Is this necessarily wrong? What must be clarified?

**Answer:** Not necessarily wrong if it is **intentional denormalization**. You must clarify whether the name stored on the order line is a **snapshot of the name at transaction time** or a **copy of the current name for optimization**. If it is a snapshot, differing from the current name is not a bug; if it is a copy, you need synchronization rules, consistency checks, and a designated source of truth.

## 12. Summary Table

| Concept | Key takeaway |
| --- | --- |
| **FD \(X\to Y\)** | Same X must determine the same Y across all valid states |
| **Lossless decomposition** | JOINing projections of a valid state recovers the exact original state |
| **Dependency preservation** | Every original FD is derivable from the union of local FDs on child relations |
| **Dependency projection** | Consider all FDs in \(F^+\) whose attributes lie inside the child table |
| **Preservation test** | Compute attribute closure under the **union of local FDs**, not the original F |
| **3NF synthesis** | Standard algorithm guarantees both losslessness and dependency preservation |
| **BCNF** | Every non-trivial FD has a superkey on its left-hand side |
| **3NF vs. BCNF** | 3NF can accept a prime right-hand attribute when the left-hand side is not a superkey |
| **Counterexample \(AB\to C,\ C\to B\)** | R is in 3NF; decomposing into CB and AC achieves BCNF and is lossless, yet loses AB→C |
| **Lossless ≠ preservation** | Two independent requirements; neither implies the other |
| **Preservation ≠ PK/UNIQUE alone suffices** | An FD whose left-hand side is not a key may still need multi-row checks |
| **Normalization level** | Must balance redundancy, constraint checking, queries, transactions, and evolvability |
| **Denormalization** | Requires a clear goal, source of truth, and consistency controls |

**Conclusion:** When deciding to decompose a schema, check **both** **lossless join** and **dependency preservation**. Proper 3NF synthesis gives a starting point carrying both guarantees; BCNF can further reduce FD-driven redundancy but does not always preserve every original FD. Moving from logical modeling to practical SQL, what matters is not the highest normal form label, but **business rules that are clearly documented, verifiable, and faithfully maintained as data and systems evolve**.
