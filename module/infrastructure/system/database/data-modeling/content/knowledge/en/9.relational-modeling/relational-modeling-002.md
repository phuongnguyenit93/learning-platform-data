# Distinguishing Mathematical Relations from SQL Tables with Duplicates or NULLs

## Learning Objectives

The relational model provides an important mathematical foundation for database design. However, the statement “an SQL table is a relation” only holds when accepting several simplifications: **a relation in the classical model is a set of tuples**, whereas **SQL often processes data under multiset (bag) semantics and allows NULL values**. These two differences directly affect how query results are read, how keys are defined, how data is counted, and how business rules are enforced.

After this lesson, you will be able to:

1. Explain why mathematical relations cannot contain duplicate tuples, while SQL tables or query results can have duplicate rows.
2. Predict the results of **SELECT**, **SELECT DISTINCT**, **GROUP BY**, **COUNT**, **JOIN**, and **UNION ALL** when data contains duplicate elements.
3. Explain **NULL** and three-valued logic (**TRUE / FALSE / UNKNOWN**), including the consequences for filtering data and checking constraints.
4. Distinguish how NULL is handled in **comparisons**, **DISTINCT**, **GROUP BY**, **UNIQUE**, **PRIMARY KEY**, and **FOREIGN KEY**.
5. Apply these differences when translating business requirements into a clear, evolvable, and verifiable relational data model.

**Scope:** This lesson belongs to the **Relational Modeling** chapter of the **DATABASE_DATA_MODELING** module. When translating business requirements into entities, relationships, constraints, keys, indexes, and physical schemas, it is necessary to separate **the logical semantics of data** from **the actual behavior of SQL**. Understanding this is also a prerequisite for comparing how data is represented in relational, document, graph, and analytical systems.

## 1. Mathematical Relations: Sets of Tuples with No Duplicates

In the classical relational model, a **relation schema** consists of a relation name, its attributes, and their corresponding domains:

\[
R(A_1:D_1, A_2:D_2, \ldots, A_n:D_n)
\]

A **relation state** at a given point in time is a set of tuples:

\[
r(R) \subseteq D_1 \times D_2 \times \cdots \times D_n
\]

Each tuple assigns a value from the corresponding domain to each attribute. The Cartesian product notation is a formal representation; the meaning of each value is always bound to its attribute name in the schema.

Three properties to remember:

- **No duplicate tuples:** A set does not store the same element twice. If two tuples have equal values across **all attributes**, they are the same tuple, not two distinct tuples.
- **No tuple ordering:** A set of tuples has no “first tuple” or “last tuple” within the meaning of the model.
- **No SQL-style NULL in the classical model:** Every attribute position contains a definite value belonging to the attribute's domain. Representing missing data must be explicitly designed; SQL's NULL is a separate mechanism, not inherently part of classical relational theory.

For example, consider a mathematical relation with only one attribute, **product category code**:

\[
LOAI = \{(10), (20)\}
\]

Writing the element **(10)** again still does not create a relation with three tuples. A relation is a set, so the value **(10)** appears only once.

In this model, the **degree** of a relation is the number of attributes; the **cardinality** is the number of tuples. In the example above, the degree is 1 and the cardinality is 2. This concept differs from the use of “cardinality” to denote 1–1, 1–N, or N–N relationships in entity modeling.

### Why Must a Relation Be Able to Identify Tuples?

Because no two tuples are identical, **the entire set of attributes** is always sufficient to distinguish tuples in a mathematical relation. In good design, we usually need a smaller key: a **candidate key** is a minimal set of attributes whose values distinguish every tuple across all valid states.

For example, for the relation **KHACH_HANG(ma_kh, ten, email)**, if **ma_kh** is a stable and unique identifier, we choose **ma_kh** as the primary key. Two people may share the name **An**, but they cannot share the same **ma_kh**.

## 2. SQL Tables and Query Results: Often Multisets

SQL is inspired by the relational model but follows different operational rules. A **multiset** (*bag*) allows an element to appear multiple times; each element has a **multiplicity** (occurrence count).

For example, the multiset:

\[
B = \{\!\{10, 10, 20\}\!\}
\]

contains three occurrences, in which the value 10 appears twice. The double braces emphasize that this is a **multiset**, not the mathematical set **{10, 20}**.

In SQL:

- A base table can contain two rows that are identical across all columns **if no constraint prevents duplicates**.
- A table with a **PRIMARY KEY** cannot contain two rows identical across all columns because they would collide on the primary key. However, a **SELECT result** from that table can still contain duplicates after selecting only a subset of columns or after a join.
- **SELECT** preserves duplicate occurrences by default; **SELECT DISTINCT** removes duplicate rows from the result.
- You cannot rely on display order without **ORDER BY**, even if the DBMS commonly returns rows in a familiar order.

Standalone SQL example:

~~~~sql
CREATE TABLE ma_nhap_thu (
    ma INTEGER
);

INSERT INTO ma_nhap_thu (ma)
VALUES (10), (10), (20);

SELECT ma FROM ma_nhap_thu;
-- Returns three rows: 10, 10, 20.

SELECT DISTINCT ma FROM ma_nhap_thu;
-- Returns two values: 10, 20.
~~~~

The difference here is not that SQL “stores data wrongly”; the **ma_nhap_thu** table simply declared no rule prohibiting duplicates. If a business requirement demands unique codes, that must be expressed with an appropriate key or constraint, rather than expecting SQL to infer the intent.

## 3. Running Dataset: Customers and Orders

To observe duplicates and NULLs simultaneously, we use two tables. Assumed business rules:

- Each customer has a unique **ma_kh** and a required name.
- Email may not yet be provided; **if provided, it must be unique**.
- Each order has a unique **ma_dh** and belongs to exactly one customer.
- An order has a non-negative total amount and may omit a promo code.

The statements below use **PostgreSQL** syntax and can be run sequentially in a test database.

~~~~sql
CREATE TABLE khach_hang (
    ma_kh INTEGER PRIMARY KEY,
    ten VARCHAR(80) NOT NULL,
    email VARCHAR(254) UNIQUE
);

CREATE TABLE don_hang (
    ma_dh INTEGER PRIMARY KEY,
    ma_kh INTEGER NOT NULL REFERENCES khach_hang(ma_kh),
    tong_tien NUMERIC(12, 2) NOT NULL CHECK (tong_tien >= 0),
    ma_uu_dai VARCHAR(20)
);

INSERT INTO khach_hang (ma_kh, ten, email) VALUES
    (1, 'An',   NULL),
    (2, 'Bình', 'binh@example.com'),
    (3, 'Chi',  NULL),
    (4, 'An',   'an@example.com');

INSERT INTO don_hang (ma_dh, ma_kh, tong_tien, ma_uu_dai) VALUES
    (101, 1, 500000, NULL),
    (102, 1, 200000, 'SALE10'),
    (103, 2, 200000, NULL),
    (104, 3, 500000, 'SALE10');
~~~~

**Customers:**

| ma_kh | ten | email |
| ---: | --- | --- |
| 1 | An | NULL |
| 2 | Bình | binh@example.com |
| 3 | Chi | NULL |
| 4 | An | an@example.com |

**Orders:**

| ma_dh | ma_kh | tong_tien | ma_uu_dai |
| ---: | ---: | ---: | --- |
| 101 | 1 | 500000 | NULL |
| 102 | 1 | 200000 | SALE10 |
| 103 | 2 | 200000 | NULL |
| 104 | 3 | 500000 | SALE10 |

Two customers sharing the name **An** are not duplicate records, because their **ma_kh** values differ. Similarly, two orders with **tong_tien = 200000** are two distinct events despite having the same monetary amount.

> **Presentation Convention:** Result tables in this lesson are sorted for readability. When writing real queries, add **ORDER BY** whenever users or programs need a deterministic order.

## 4. Duplicate Data Appearing During Projection and Joins

### 4.1. Projection in Relational Algebra vs. SELECT in SQL

The **projection** operation of relational algebra extracts a set of attributes from input tuples. Because the output is still a **set**, duplicate tuples after projection are eliminated.

\[
\pi_{ten}(KHACH\_HANG) = \{(An), (Bình), (Chi)\}
\]

However, the SQL query:

~~~~sql
SELECT ten
FROM khach_hang
ORDER BY ten;
~~~~

produces **four rows**: **An, An, Bình, Chi**. Standard SELECT is essentially a column selection that **preserves multiplicity**. To get set-based projection semantics:

~~~~sql
SELECT DISTINCT ten
FROM khach_hang
ORDER BY ten;
-- Three rows: An, Bình, Chi.
~~~~

Note that **DISTINCT evaluates all columns in the SELECT list**, not just the first column mentioned:

~~~~sql
SELECT DISTINCT ma_kh, ten
FROM khach_hang
ORDER BY ma_kh;
-- Still four rows because each ma_kh is a distinct value.
~~~~

Having two rows with the same name **An** is completely valid if the business permits duplicate names. **Duplicate rows across selected columns** does not mean **business records have been duplicated**.

### 4.2. Counting Occurrences

~~~~sql
SELECT ma_kh, COUNT(*) AS so_don
FROM don_hang
GROUP BY ma_kh
ORDER BY ma_kh;
~~~~

| ma_kh | so_don |
| ---: | ---: |
| 1 | 2 |
| 2 | 1 |
| 3 | 1 |

Customer 1 has two orders; preserving both occurrences of **ma_kh = 1** is necessary to count accurately. If you applied **DISTINCT ma_kh** before counting orders, you would lose the actual order count. Thus, not all duplicate occurrences should be eliminated.

### 4.3. JOIN Can Increase Row Count

~~~~sql
SELECT kh.ma_kh, kh.ten, dh.ma_dh
FROM khach_hang AS kh
JOIN don_hang AS dh ON dh.ma_kh = kh.ma_kh
ORDER BY kh.ma_kh, dh.ma_dh;
~~~~

| ma_kh | ten | ma_dh |
| ---: | --- | ---: |
| 1 | An | 101 |
| 1 | An | 102 |
| 2 | Bình | 103 |
| 3 | Chi | 104 |

The name **An** repeats twice because one customer has two orders. If you project only **ten** from the JOIN result, you see **An, An, Bình, Chi**. This repetition comes from the **1–N relationship multiplicity**, not from a duplicated customer record.

In general, if a join key value appears **m** times on the left and **n** times on the right, a standard join can produce **m × n** matching pairs for that value. This is especially critical in financial reporting or data analytics:

- Suppose order 101 has total amount **500000** and two detail lines.
- Joining orders with detail lines produces two rows both carrying **don_hang.tong_tien = 500000**.
- Taking **SUM(don_hang.tong_tien)** immediately after the JOIN can count order 101 as **1000000**, even though the true total is only **500000**.

You should not “fix” this bug with **SUM(DISTINCT don_hang.tong_tien)**: two distinct orders can genuinely have the same total amount and would be undercounted. You must clearly define the **grain** of the data—for example, “one row is one order”—and aggregate at the proper level before or after the JOIN.

### 4.4. UNION and UNION ALL

In SQL, **UNION** removes duplicates from the combined result by default, whereas **UNION ALL** keeps every occurrence.

~~~~sql
SELECT ma_kh FROM don_hang WHERE ma_dh <= 102
UNION
SELECT ma_kh FROM don_hang WHERE ma_dh >= 102;
-- Values: 1, 2, 3 (each value once).

SELECT ma_kh FROM don_hang WHERE ma_dh <= 102
UNION ALL
SELECT ma_kh FROM don_hang WHERE ma_dh >= 102;
-- Five rows: value 1 appears three times; 2 and 3 appear once each.
~~~~

Order 102 satisfies **both branches**, so **UNION ALL** counts it an extra time. Choosing **UNION** versus **UNION ALL** must follow business semantics: are you combining **a set of unique objects** or concatenating **occurrences/events**?

## 5. NULL Is Not an Ordinary Value

In SQL, **NULL** is a marker indicating the absence of a definite value at the position in question. It is commonly used for several different situations:

| Case | Example | Design Question |
| --- | --- | --- |
| Unknown | Customer email not yet collected | Do we need to distinguish “not collected yet” from “has none”? |
| Not applicable | Order does not use a promo code | Does NULL accurately describe the “no code used” case? |
| Not yet computed or occurred | Delivery timestamp does not exist yet | Is a separate delivery status needed? |
| Entry error or missing input | Submitted record lacks a required field | Should the record be rejected instead of accepting NULL? |

These meanings differ at the business level even if they are all stored as NULL. **NULL is not synonymous with 0, an empty string, FALSE, or a default value**.

For example:

- **tong_tien = 0** states that the total amount is definitely zero.
- **tong_tien IS NULL** states that there is no definite total amount in that field.
- **ma_uu_dai = ''** is an empty string; depending on requirements, it may need to be rejected.
- **ma_uu_dai IS NULL** may be chosen to express “no promo code applied”.

In our running example, **ma_uu_dai** allows NULL, while **tong_tien** requires **NOT NULL**. That is a **modeling decision**: the system must know the total amount before saving an order.

## 6. Comparing with NULL and Three-Valued Logic

Classical relational algebra operates over definite values and standard propositional logic. SQL instead uses a third truth value in many expressions: **UNKNOWN**.

For example:

~~~~sql
SELECT ma_kh FROM khach_hang WHERE email = NULL;
-- Returns no rows.

SELECT ma_kh FROM khach_hang WHERE email IS NULL
ORDER BY ma_kh;
-- ma_kh = 1, 3.
~~~~

With the standard **=** operator, both **NULL = 'an@example.com'** and **NULL = NULL** evaluate to **UNKNOWN**. Checking for NULL state uses **IS NULL** and **IS NOT NULL**, which return TRUE or FALSE.

### 6.1. Minimal Truth Tables to Remember

Let **U = UNKNOWN**, **T = TRUE**, **F = FALSE**:

| P | Q | P AND Q | P OR Q |
| --- | --- | --- | --- |
| T | T | T | T |
| T | F | F | T |
| T | U | U | T |
| F | F | F | F |
| F | U | F | U |
| U | U | U | U |

For **NOT**:

| P | NOT P |
| --- | --- |
| T | F |
| F | T |
| U | U |

Two points that commonly cause confusion:

- **FALSE AND UNKNOWN = FALSE**, because regardless of what the unknown operand is, the overall condition is still false.
- **TRUE OR UNKNOWN = TRUE**, because one true operand is enough for the overall condition to be true.

The **WHERE** clause keeps only rows for which the condition evaluates to **TRUE**. Both **FALSE** and **UNKNOWN** fail the filter.

### 6.2. Why Negating a Condition Does Not Yield the Entire Remainder

~~~~sql
SELECT ma_dh
FROM don_hang
WHERE ma_uu_dai = 'SALE10'
ORDER BY ma_dh;
-- 102, 104

SELECT ma_dh
FROM don_hang
WHERE ma_uu_dai <> 'SALE10';
-- No rows: the remaining two codes are NULL so the condition is UNKNOWN.
~~~~

If the requirement is “find orders **not using SALE10**, including orders without a promo code”, you must state it explicitly:

~~~~sql
SELECT ma_dh
FROM don_hang
WHERE ma_uu_dai <> 'SALE10'
   OR ma_uu_dai IS NULL
ORDER BY ma_dh;
-- 101, 103
~~~~

PostgreSQL also provides comparison predicates that treat NULL as a defined case:

~~~~sql
SELECT ma_dh
FROM don_hang
WHERE ma_uu_dai IS DISTINCT FROM 'SALE10'
ORDER BY ma_dh;
-- 101, 103

SELECT ma_dh
FROM don_hang
WHERE ma_uu_dai IS NOT DISTINCT FROM NULL
ORDER BY ma_dh;
-- 101, 103; equivalent to IS NULL in this example.
~~~~

**IS DISTINCT FROM** returns TRUE/FALSE when NULLs are involved: a NULL is distinct from any non-NULL value, and two NULLs are treated as *not distinct* under this comparison. Do not equate this behavior with the **=** operator; when porting SQL across DBMSs, check syntax support and corresponding behavior.

## 7. What Seems Paradoxical: NULL = NULL Is UNKNOWN, Yet DISTINCT Groups NULLs

SQL has operations that must decide which rows are considered **duplicates** for deduplication or grouping. They use a separate rule: when evaluating equality for deduplication in **DISTINCT**, **GROUP BY**, and corresponding set operations, NULLs in the same position are treated as **not distinct** from one another.

### 7.1. DISTINCT with NULL

~~~~sql
SELECT DISTINCT email
FROM khach_hang;
~~~~

The result contains **three displayed values**: **NULL**, **binh@example.com**, and **an@example.com**. The two rows for customers 1 and 3 with NULL emails are collapsed into **one NULL row** in the DISTINCT output.

This **does not mean NULL = NULL evaluates to TRUE**. Those are two different rules:

- In a predicate expression **email = NULL**, the comparison result is **UNKNOWN**.
- In **duplicate elimination**, two rows that both have NULL in the same position are treated as indistinguishable.

### 7.2. GROUP BY with NULL

~~~~sql
SELECT ma_uu_dai, COUNT(*) AS so_don
FROM don_hang
GROUP BY ma_uu_dai
ORDER BY ma_uu_dai NULLS LAST;
~~~~

| ma_uu_dai | so_don |
| --- | ---: |
| SALE10 | 2 |
| NULL | 2 |

SQL groups records with **ma_uu_dai IS NULL** into a single group for aggregation. In reporting tasks, this group can be labeled “No promo code applied” **if that is genuinely the business meaning** of NULL.

### 7.3. COUNT(*) Differs from COUNT(column)

~~~~sql
SELECT
    COUNT(*) AS tong_so_khach,
    COUNT(email) AS co_email,
    COUNT(DISTINCT email) AS email_khac_nhau
FROM khach_hang;
~~~~

| tong_so_khach | co_email | email_khac_nhau |
| ---: | ---: | ---: |
| 4 | 2 | 2 |

- **COUNT(*)** counts all rows.
- **COUNT(email)** counts rows where **email is not NULL**.
- **COUNT(DISTINCT email)** counts **distinct, non-NULL email values**.

Notably, **SELECT DISTINCT email** returns **three rows** (including one NULL row), whereas **COUNT(DISTINCT email)** returns **2** because COUNT ignores NULLs. Keep these two behaviors clear to avoid drawing wrong conclusions about counts.

Common aggregate functions such as **SUM**, **AVG**, **MIN**, and **MAX** also ignore NULL inputs; the exception for counting is **COUNT(*)**, because it does not reference a specific column. If there are no non-NULL values to aggregate, **SUM** returns NULL while **COUNT(column)** returns 0:

~~~~sql
SELECT
    COUNT(ma_uu_dai) AS so_don_co_ma,
    COUNT(DISTINCT ma_uu_dai) AS so_ma_khac_nhau
FROM don_hang;
-- 2, 1
~~~~

When using **COALESCE** to replace NULL with a default value, you must know the data's meaning: turning **unknown** into **0** can skew statistics, whereas turning the sum of an empty row set into **0** is sometimes appropriate for reporting requirements.

## 8. NULL in JOIN, Anti-Join, and NOT IN

### 8.1. INNER JOIN Only Pairs Rows Satisfying a TRUE Condition

In our example, **don_hang.ma_kh** is a **NOT NULL** foreign key, so joining on customer ID works directly. If a JOIN condition compares two nullable columns using **=**, rows with NULL on both sides are **not** matched together: **NULL = NULL** is UNKNOWN, not TRUE.

**LEFT JOIN** preserves unmatched rows from the left side and fills right-side columns with NULL. Therefore, you must be very careful when counting:

~~~~sql
SELECT
    kh.ma_kh,
    COUNT(*) AS so_dong_sau_join,
    COUNT(dh.ma_dh) AS so_don
FROM khach_hang AS kh
LEFT JOIN don_hang AS dh ON dh.ma_kh = kh.ma_kh
GROUP BY kh.ma_kh
ORDER BY kh.ma_kh;
~~~~

| ma_kh | so_dong_sau_join | so_don |
| ---: | ---: | ---: |
| 1 | 2 | 2 |
| 2 | 1 | 1 |
| 3 | 1 | 1 |
| 4 | 1 | 0 |

Customer 4 **has no orders**, yet **COUNT(*) = 1** because LEFT JOIN still produces one result row for that customer. Meanwhile, **COUNT(dh.ma_dh) = 0**, because the order key column in that row is NULL. Counting child records via a non-NULL key of the child table is usually the right approach for this task.

### 8.2. The NOT IN Trap When the List Contains NULL

~~~~sql
SELECT ma_kh
FROM khach_hang
WHERE ma_kh NOT IN (1, 2, NULL);
-- No rows returned, not even customers 3 and 4.
~~~~

For **ma_kh = 3**, the comparisons “3 != 1” and “3 != 2” are true, but comparing with NULL yields UNKNOWN. The entire **NOT IN** expression fails to evaluate to TRUE, so the row is filtered out. On real data, the list inside **NOT IN** may come from a subquery and unexpectedly contain NULL.

If you want to find customers **who have never placed an order**, you can write:

~~~~sql
SELECT kh.ma_kh, kh.ten
FROM khach_hang AS kh
WHERE NOT EXISTS (
    SELECT 1
    FROM don_hang AS dh
    WHERE dh.ma_kh = kh.ma_kh
)
ORDER BY kh.ma_kh;
-- Result: customer 4, An.
~~~~

**NOT EXISTS** checks whether a matching row exists; it does not fall into the trap where “a single NULL in the list makes NOT IN evaluate to UNKNOWN”. Even so, you must still ensure the matching condition inside the subquery expresses the exact business rule.

### 8.3. JOIN Errors Cannot Always Be Fixed with DISTINCT

When an order has multiple detail lines, a JOIN generates multiple rows. If you deduplicate after the JOIN, you risk:

- **Losing valid data**, if two order lines happen to have the same price yet represent different products.
- **Masking a broken join key**, if the JOIN produces wrong combinations but DISTINCT happens to reduce the row count.
- **Miscounting**, if COUNT or SUM is computed at the wrong grain.

The safe workflow is to first determine **what a single row represents**, which key guarantees uniqueness at that level, and only then aggregate or deduplicate when explicitly required.

## 9. How Does NULL Affect Keys and Constraints?

SQL table design must state clearly **within what scope duplicates are forbidden**, **which columns are mandatory**, and **what NULL means**.

### 9.1. PRIMARY KEY Always Requires a Definite Identifier

A **PRIMARY KEY** requires key values to be unique and **non-NULL**. For composite keys, no key component may be NULL. In our example, **khach_hang.ma_kh** and **don_hang.ma_dh** are primary keys.

This aligns with tuple identification in the relational model, but **it does not mean every column in the table is non-NULL**: a customer's email can still be missing.

### 9.2. UNIQUE and NULL Must Be Checked per DBMS

In **PostgreSQL**, a standard **UNIQUE** constraint allows multiple rows to contain NULL in the constrained column. Thus, having two rows in **khach_hang** with NULL email is valid, even though two customers cannot share the same definite email.

~~~~sql
-- Valid in the PostgreSQL example because both emails are NULL:
SELECT ma_kh, email
FROM khach_hang
WHERE email IS NULL
ORDER BY ma_kh;
-- 1, NULL
-- 3, NULL
~~~~

If email is **mandatory and unique**, the schema needs **NOT NULL UNIQUE**:

~~~~sql
-- Alternative structure example; do not run directly
-- against sample data that already contains NULL emails:
CREATE TABLE khach_hang_bat_buoc_email (
    ma_kh INTEGER PRIMARY KEY,
    email VARCHAR(254) NOT NULL UNIQUE
);
~~~~

When email is nullable, **UNIQUE(email)** does not automatically make email a **candidate key in the sense of an always-present identifier**, because multiple rows can lack an email. Different DBMSs or constraint configurations handle NULL in UNIQUE differently; always verify the target system before assuming behavior.

### 9.3. FOREIGN KEY and NULL

A foreign key **can allow NULL** if the column is not declared NOT NULL. Under standard single-column foreign key behavior, **NULL** means there is no parent row to look up and validate. For example, a support ticket might not yet be assigned to an agent:

~~~~sql
-- Standalone illustrative example:
-- phieu_ho_tro.ma_nv_phu_trach can be NULL,
-- but when present it must reference an existing employee.
-- ma_nv_phu_trach INTEGER NULL
--     REFERENCES nhan_vien(ma_nv)
~~~~

If the business rule states “every order **must** belong to a customer”, a bare foreign key is not enough; you need **ma_kh NOT NULL REFERENCES khach_hang(ma_kh)** as written in the DDL.

For composite foreign keys, how **partially NULL components** are handled depends on the link matching mode (such as MATCH SIMPLE/MATCH FULL) and DBMS support. Never assume every composite foreign key configuration automatically requires all components to be non-NULL.

### 9.4. CHECK Can Let UNKNOWN Pass Through

An SQL **CHECK** constraint only rejects a row when the expression evaluates to **FALSE**; if the expression evaluates to **TRUE or UNKNOWN**, the row passes the CHECK. Therefore:

~~~~sql
CREATE TABLE kiem_tra_gia (
    gia NUMERIC(12, 2) CHECK (gia > 0)
);

INSERT INTO kiem_tra_gia (gia) VALUES (NULL);
-- Valid in PostgreSQL: (NULL > 0) is UNKNOWN,
-- and CHECK does not reject UNKNOWN.
~~~~

If price must be positive and must exist, combine both constraints:

~~~~sql
CREATE TABLE kiem_tra_gia_bat_buoc (
    gia NUMERIC(12, 2) NOT NULL CHECK (gia > 0)
);
~~~~

This is why domain design cannot stop at “must be greater than 0”; you must also ask “is the absence of a value allowed?”.

## 10. Direct Comparison: Mathematical Relations vs. SQL

| Criterion | Classical Mathematical Relation | Common SQL Table / Result |
| --- | --- | --- |
| Collection type | Set of tuples | Can be a multiset of rows |
| Full-row duplicates | No two identical elements exist | Can appear without constraints; SELECT can produce duplicates |
| Projection | Automatically removes duplicates since output is a set | SELECT keeps duplicates; SELECT DISTINCT removes duplicates |
| Row position | No logical ordering | Ordering not guaranteed without ORDER BY |
| Missing values | No SQL-style NULL | NULL can appear in nullable columns |
| Standard comparisons | Two-valued logic over definite values | Typically TRUE, FALSE, and UNKNOWN |
| Grouping/deduplicating NULLs | SQL-style NULL issues do not arise | NULLs are grouped together in DISTINCT/GROUP BY |
| Keys | Uniqueness based on logical rules, minimal candidate keys | PRIMARY KEY, UNIQUE, NOT NULL express constraints in DDL |
| Counting rows | Cardinality is the number of tuples in the set | COUNT(*) counts rows, including NULLs and duplicates |

You should not conclude that SQL “does not follow the relational model”. SQL is a practical language built on many relational ideas while adopting different rules in specific areas. When analyzing requirements, decide **data semantics and keys** from the logical model first, then examine how the specific SQL dialect enforces them.

## 11. Implications for Data Design and Reporting

Three critical questions when moving from a logical schema to an SQL schema:

### 11.1. Is a “Duplicate” Two Valid Occurrences or a Data Error?

| Situation | Interpretation | Typically Appropriate Design |
| --- | --- | --- |
| Two customers named An | Valid; name is not an identifier | Primary key ma_kh, allowing duplicate names |
| Two order lines with the same product in the same order | Depends on sales rules | If forbidden: UNIQUE(ma_dh, ma_sp); if allowed: add a line identifier |
| Two transactions with the same amount | Valid; amount is not a key | Key by transaction ID, retaining all occurrences |
| Two identical externally imported records | May be duplicate data needing handling | Define business key, source, timestamp, and deduplication rule |
| JOIN result has multiple rows per order | May be a normal 1–N relationship | Choose the right grain before aggregating |

Especially in analytical data warehouses, JOINs and grain choices are a common source of **double-counting revenue**. In document or graph models, an object or edge can also be represented in multiple ways; therefore, defining identifiers, the meaning of each record, and constraints remains essential even outside relational tables.

### 11.2. What Business Information Is NULL Carrying?

When an attribute is allowed to be missing, determine:

1. Is it missing because it is **unknown**, **not applicable**, or **not yet occurred**?
2. Do queries and reports need to distinguish those causes?
3. When must the value become mandatory (e.g., before finalizing an order)?
4. Can **NOT NULL**, **CHECK**, or a dedicated status express it better?

If the business needs to distinguish “not asked yet”, “customer declined to provide email”, and “customer has no email”, a single nullable email column is insufficient. You can add an email collection status controlled by a valid value set, or adjust the model to match information management requirements.

Never automatically replace every NULL with the string “N/A” or the number 0. Doing so can turn a missing-data state into a business-invalid value, causing calculations or filters to return unintended results.

### 11.3. Does the Query Need a Set or a Multiset?

- List of **unique customer IDs** who made purchases: use **DISTINCT** or an appropriate query to retrieve a set of identifiers.
- Number of **orders** per customer: count at the **order** grain; do not deduplicate customer IDs before counting.
- Number of **customers with an email**: use **COUNT(email)**, because it excludes NULL emails.
- Number of **customers** in the table: use **COUNT(*)**.
- Total **revenue** after joining multiple tables: check the grain and row multiplication rather than applying DISTINCT by intuition.
- List of customers **who have not made a purchase**: use **NOT EXISTS** or an equivalent join/check, especially when the subset might contain NULLs.

These choices determine the correctness of results before even discussing indexes or performance.

## 12. Self-Check Practice

These exercises use the customer and order data from Section 3. Predict the output before running the queries.

### Exercise 1 — Does DISTINCT Always Reduce Row Count?

~~~~sql
-- A
SELECT ten FROM khach_hang;

-- B
SELECT DISTINCT ten FROM khach_hang;

-- C
SELECT DISTINCT ma_kh, ten FROM khach_hang;
~~~~

**Question:** How many rows do A, B, and C return respectively, and why?

**Answer:** A returns **4 rows** because the name An appears twice; B returns **3 rows** because An is collapsed; C returns **4 rows** because each **(ma_kh, ten)** pair is distinct. DISTINCT evaluates **the entire output row**, not “people” in an external real-world sense.

### Exercise 2 — NULL and Three-Valued Logic

~~~~sql
-- A
SELECT ma_dh FROM don_hang
WHERE ma_uu_dai = NULL;

-- B
SELECT ma_dh FROM don_hang
WHERE ma_uu_dai IS NULL;

-- C
SELECT ma_dh FROM don_hang
WHERE NOT (ma_uu_dai = 'SALE10');
~~~~

**Question:** Which query finds orders 101 and 103?

**Answer:** Only **B**. A compares with NULL, so the condition is UNKNOWN for every row. C also fails to keep orders 101 and 103: **NOT UNKNOWN** is still UNKNOWN. To express “not using SALE10, including having no code”, use **IS DISTINCT FROM** (PostgreSQL) or **ma_uu_dai <> 'SALE10' OR ma_uu_dai IS NULL**.

### Exercise 3 — Why Counting Orders with COUNT(*) Fails

~~~~sql
SELECT kh.ma_kh, COUNT(*) AS so_don
FROM khach_hang AS kh
LEFT JOIN don_hang AS dh ON dh.ma_kh = kh.ma_kh
GROUP BY kh.ma_kh
ORDER BY kh.ma_kh;
~~~~

**Question:** What is the result for customer 4? Fix the query to count orders accurately.

**Answer:** Customer 4 yields **COUNT(*) = 1** despite having no orders, because LEFT JOIN produces one row with NULLs in the order columns. Change it to **COUNT(dh.ma_dh)** because **ma_dh** is a non-NULL primary key: when there is no matching order, the result is **0**.

### Exercise 4 — Does UNIQUE Allow Two NULL Emails?

Assume we are still using PostgreSQL and the **email VARCHAR(254) UNIQUE** schema from Section 3.

**Question:** Do two customers with NULL email violate UNIQUE? If email must have a value, what needs to be added?

**Answer:** It does not violate standard PostgreSQL UNIQUE; multiple NULLs are accepted. If email is mandatory, add **NOT NULL** alongside **UNIQUE**. Do not assume identical behavior across all DBMSs without checking.

### Exercise 5 — Are Two Identical Order Totals Duplicate Revenue?

~~~~sql
SELECT
    SUM(tong_tien) AS tong_dung,
    SUM(DISTINCT tong_tien) AS tong_khong_phu_hop
FROM don_hang;
~~~~

**Question:** What do the two expressions return, and why is the second one inappropriate for calculating revenue?

**Answer:** **SUM(tong_tien) = 1400000**; **SUM(DISTINCT tong_tien) = 700000** because it keeps only the two distinct values 200000 and 500000. Two different orders with the same monetary amount are still separate sales events and must all be summed. Applying DISTINCT to the **monetary value** loses transaction count information.

### Exercise 6 — Writing a Query for Customers Without Orders

**Requirement:** Return the ID and name of customers who have no orders; the expected result is customer **4 — An**. Write a query that does not depend on NOT IN behavior when the subset contains NULL.

**Reference Answer:**

~~~~sql
SELECT kh.ma_kh, kh.ten
FROM khach_hang AS kh
WHERE NOT EXISTS (
    SELECT 1
    FROM don_hang AS dh
    WHERE dh.ma_kh = kh.ma_kh
)
ORDER BY kh.ma_kh;
~~~~

## 13. Summary

| Concept | Rule to Remember |
| --- | --- |
| Mathematical relation | **Set** of tuples; no duplicate tuples and no classical SQL-style NULL |
| SQL SELECT | Defaults to **multiset semantics**: can return duplicate rows |
| DISTINCT | Removes duplicate rows across **the entire SELECT column list** |
| UNION ALL | Keeps all occurrences; UNION usually removes duplicates |
| NULL | Marker for a missing definite value; not 0, empty string, or FALSE |
| Three-valued logic | Condition expressions can evaluate to TRUE, FALSE, or UNKNOWN |
| WHERE | Keeps rows only when the condition is TRUE |
| IS NULL | Checks NULL state; do not use **= NULL** |
| GROUP BY/DISTINCT with NULL | NULLs are placed in the same group or collapsed during deduplication |
| COUNT(*) | Counts rows, including rows with NULLs and duplicates |
| COUNT(column) | Counts rows with a **non-NULL** column value |
| PRIMARY KEY | Unique and non-NULL |
| Nullable UNIQUE | NULL behavior must be verified per DBMS |
| CHECK | UNKNOWN expressions are not rejected like FALSE |
| JOIN | Can multiply row counts; distinguish events and grain |

When designing a data model, clarify **what each tuple represents**, **which attribute set uniquely identifies it**, **which information a record is permitted to omit**, and **whether a query needs to count events or retrieve distinct values**. These questions connect relational theory with how SQL operates, keeping normalization, key design, query writing, index selection, and data model evaluation grounded in a verifiable logical foundation.
