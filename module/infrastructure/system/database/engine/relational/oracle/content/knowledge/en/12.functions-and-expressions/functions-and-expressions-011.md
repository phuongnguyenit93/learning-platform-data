# NVL, NVL2, COALESCE, NULLIF, and Result Type Selection

In Oracle Database, **NULL** represents an unknown, unprovided, or not-applicable value according to the data model. When computing or displaying data, applications frequently need to replace NULL with a default value, pick from multiple fallback sources, test whether a value exists, or turn a sentinel value into NULL to make calculations safer.

Oracle provides four common functions for these scenarios:

- **NVL(expr1, expr2):** returns expr1 if non-NULL; otherwise returns expr2.
- **NVL2(expr1, expr2, expr3):** returns expr2 when expr1 is non-NULL; otherwise returns expr3.
- **COALESCE(expr1, expr2, ...):** returns the first non-NULL expression in the list.
- **NULLIF(expr1, expr2):** returns NULL if both expressions are equal; otherwise returns expr1.

At first glance, all four deal with NULL, yet **their selection conditions, argument counts, and result data-type rules differ**. Focusing only on displayed values while ignoring data types can lead to type conversion errors, unexpected output, or degraded index usage.

## 1. NULL in Oracle and three-valued logic

In SQL, NULL is not zero, not the literal string "NULL", and not simply an empty value comparable with an equals sign. NULL denotes an unknown or absent value in the data model.

~~~sql
SELECT
    CASE WHEN NULL = NULL THEN 'EQUAL'
         ELSE 'NOT EQUAL'
    END AS ket_qua_so_sanh
FROM dual;
~~~

The condition `NULL = NULL` evaluates to **UNKNOWN**, not TRUE. In a searched CASE, a WHEN branch is selected only when the condition evaluates to TRUE, so this example returns `NOT EQUAL`.

To test for NULL, use `IS NULL`:

~~~sql
SELECT *
FROM nhan_vien
WHERE ngay_nghi IS NULL;
~~~

Do not write `WHERE ngay_nghi = NULL`, because that condition never evaluates to TRUE for NULL rows.

SQL uses three-valued logic:

| Expression | Logical Result |
| --- | --- |
| 5 = 5 | TRUE |
| 5 = 7 | FALSE |
| 5 = NULL | UNKNOWN |
| NULL = NULL | UNKNOWN |
| NULL IS NULL | TRUE |
| NULL IS NOT NULL | FALSE |

A `WHERE` clause retains rows only when the condition evaluates to TRUE. Both FALSE and UNKNOWN rows are excluded. `NVL`, `NVL2`, `COALESCE`, and `NULLIF` help handle NULL values inside expressions without altering SQL's three-valued logic rules.

### 1.1. Empty strings in Oracle

For character types such as VARCHAR2, Oracle currently treats a zero-length string as NULL:

~~~sql
SELECT
    CASE WHEN '' IS NULL THEN 'IS NULL'
         ELSE 'NOT NULL'
    END AS ket_qua
FROM dual;
~~~

The result is `IS NULL`. Therefore:

~~~sql
SELECT NVL('', 'Not entered') AS gia_tri
FROM dual;
~~~

returns `Not entered`.

A string containing only spaces, such as `'   '`, is not zero-length; it remains a non-NULL character value. If business logic treats all-space strings as unentered, normalize first, for example using TRIM:

~~~sql
SELECT NVL(TRIM(ho_ten), 'Not updated')
FROM khach_hang;
~~~

TRIM can return an empty string, which Oracle treats as NULL. Do not apply TRIM automatically if leading or trailing spaces are meaningful in your data.

## 2. NVL: replacing NULL with another value

Syntax:

~~~sql
NVL(expr1, expr2)
~~~

- If expr1 is non-NULL, returns expr1.
- If expr1 is NULL, returns expr2.

Example:

~~~sql
SELECT ma_nhan_vien,
       ho_ten,
       NVL(thuong, 0) AS thuong_hien_thi
FROM nhan_vien;
~~~

If column `THUONG` is NULL, the output displays 0. If `THUONG` is 2,500,000, the output remains 2,500,000.

### 2.1. NVL with NUMBER

~~~sql
SELECT NVL(NULL, 0) AS gia_tri
FROM dual;
~~~

In production expressions, clarify the numeric type if multiple NUMBER/BINARY_FLOAT/BINARY_DOUBLE types or literals need conversion:

~~~sql
SELECT NVL(CAST(NULL AS NUMBER(10,2)), 0) AS so_tien
FROM dual;
~~~

NVL applies Oracle's type-conversion rules. When expr1 is a character type, Oracle converts expr2 to the character type of expr1 and returns VARCHAR2 in expr1's character set. When expr1 is numeric, Oracle determines the argument with the highest numeric precedence and converts the other argument accordingly.

Example:

~~~sql
SELECT NVL(CAST(NULL AS NUMBER), 100) AS ket_qua
FROM dual;
~~~

The result has a numeric type. Conversely, if the first column is VARCHAR2:

~~~sql
SELECT NVL(ma_tham_chieu, 0) AS ma_hien_thi
FROM du_lieu_import;
~~~

Oracle converts the number 0 to the string `'0'`, because the first argument is character data. Never assume the result is always NUMBER simply because the second argument is a number.

### 2.2. NVL with DATE

~~~sql
SELECT NVL(ngay_kich_hoat, DATE '2024-01-01') AS ngay_su_dung
FROM tai_khoan;
~~~

Using a DATE literal prevents Oracle from having to parse a date string using the session's `NLS_DATE_FORMAT`.

Avoid:

~~~sql
-- Avoid relying on implicit conversion of date strings.
SELECT NVL(ngay_kich_hoat, '01/01/2024')
FROM tai_khoan;
~~~

The string `'01/01/2024'` may be interpreted differently or rejected depending on date format settings. If the input is a string, convert explicitly:

~~~sql
SELECT NVL(
           ngay_kich_hoat,
           TO_DATE('01/01/2024', 'DD/MM/YYYY')
       ) AS ngay_su_dung
FROM tai_khoan;
~~~

### 2.3. NVL does not support multiple fallbacks directly

NVL takes exactly two arguments. When multiple fallback options are needed, NVL can be nested:

~~~sql
SELECT NVL(email_cong_ty,
           NVL(email_ca_nhan, 'No email')) AS email_lien_he
FROM nhan_vien;
~~~

However, with three or more expressions, COALESCE is usually much easier to read:

~~~sql
SELECT COALESCE(
           email_cong_ty,
           email_ca_nhan,
           email_khac,
           'No email'
       ) AS email_lien_he
FROM nhan_vien;
~~~

## 3. NVL2: picking one of two results based on NULL

Syntax:

~~~sql
NVL2(expr1, expr2, expr3)
~~~

- If expr1 is non-NULL, returns expr2.
- If expr1 is NULL, returns expr3.

Example:

~~~sql
SELECT ma_nhan_vien,
       ho_ten,
       NVL2(ngay_nghi_viec,
            'RESIGNED',
            'ACTIVE') AS trang_thai
FROM nhan_vien;
~~~

If `NGAY_NGHI_VIEC` has a date, the result is `RESIGNED`; if NULL, the result is `ACTIVE`.

**NVL2 never returns expr1.** The first argument is strictly the NULL-check condition; the second and third arguments are the two possible return values.

### 3.1. Comparing NVL and NVL2

| Function | Arguments | Rule |
| --- | --- | --- |
| NVL(a, b) | 2 | If a is NULL return b, otherwise return a |
| NVL2(a, b, c) | 3 | If a is non-NULL return b, if a is NULL return c |

Example with a `BONUS` column:

~~~sql
SELECT ma_nhan_vien,
       NVL(bonus, 0) AS bonus,
       NVL2(bonus, 'Has bonus', 'No bonus') AS nhan_xet
FROM nhan_vien;
~~~

Someone with `BONUS = 0` is still **non-NULL**, so NVL2 returns `Has bonus`. If business rules treat a bonus of 0 as no bonus, check both NULL and 0, for instance using CASE:

~~~sql
CASE
    WHEN bonus IS NULL OR bonus = 0 THEN 'No bonus'
    ELSE 'Has bonus'
END
~~~

NULL and 0 represent two different states; never conflate them just because the UI wants identical display text.

### 3.2. Result data type of NVL2

For NVL2, expr1 decides which branch is chosen, while **the result data type is primarily determined by expr2 and expr3**:

- If expr2 is a character type, Oracle returns VARCHAR2 in expr2's character set; expr3 is converted to the corresponding type under character conversion rules (with exceptions for national character types).
- If expr2 is numeric, Oracle picks the numeric type with the highest precedence between expr2 and expr3, and converts the other argument accordingly.
- For other types, Oracle's type compatibility rules apply; avoid arbitrarily mixing DATE, NUMBER, and strings.

Example:

~~~sql
SELECT NVL2(
           CAST(NULL AS NUMBER),
           100,
           0
       ) AS ket_qua_so
FROM dual;
~~~

Because the first argument is NULL, the value is 0; the result data type remains numeric per the branch arguments.

~~~sql
SELECT NVL2(
           DATE '2024-01-01',
           'Activated',
           'Not activated'
       ) AS trang_thai
FROM dual;
~~~

The first argument is non-NULL, so it returns `Activated`.

Never infer NVL2's return type from expr1. For complex expressions, use `DUMP`, `VSIZE`, or result-set metadata to check the actual Oracle/driver type.

## 4. COALESCE: picking the first non-NULL value

Syntax:

~~~sql
COALESCE(expr1, expr2, ...)
~~~

COALESCE returns **the first non-NULL expression**, evaluated from left to right. It requires at least two expressions and accepts more than two.

Example:

~~~sql
SELECT ma_khach_hang,
       COALESCE(
           so_dien_thoai,
           email,
           'No contact info'
       ) AS thong_tin_lien_he
FROM khach_hang;
~~~

If `SO_DIEN_THOAI` has a value, it returns the phone number; if NULL, it picks `EMAIL`; if both are NULL, it returns the default string.

### 4.1. Argument order defines priority

~~~sql
SELECT COALESCE(email_cong_ty, email_ca_nhan, email_khac)
       AS email_duoc_chon
FROM nhan_vien;
~~~

If both work email and personal email exist, COALESCE picks work email because it appears first. Reordering arguments changes the result. It does not select the "best" or "newest" value—it strictly follows the written order.

### 4.2. COALESCE and CASE

COALESCE has semantics equivalent to a searched CASE:

~~~sql
COALESCE(a, b, c)
~~~

is equivalent in value selection to:

~~~sql
CASE
    WHEN a IS NOT NULL THEN a
    WHEN b IS NOT NULL THEN b
    ELSE c
END
~~~

COALESCE uses **short-circuit evaluation**: Oracle evaluates arguments from left to right and does not evaluate subsequent arguments once a non-NULL expression is found. This helps with multi-source fallbacks, though you should never write expressions with side effects or rely on evaluation order of custom functions to control transactions.

### 4.3. Data type rules in COALESCE

Oracle must determine a single common data type across all arguments. If expressions are numeric or convertible per numeric rules, Oracle applies **numeric precedence** to determine the result type. For character or other types, all expressions must be compatible under Oracle's type-conversion rules.

Numeric example:

~~~sql
SELECT COALESCE(
           CAST(NULL AS NUMBER),
           10,
           20.5
       ) AS gia_tri
FROM dual;
~~~

String example:

~~~sql
SELECT COALESCE(
           email_cong_ty,
           email_ca_nhan,
           CAST('No email' AS VARCHAR2(100))
       ) AS email
FROM nhan_vien;
~~~

Never mix a DATE, a NUMBER, and a string expecting Oracle to dynamically pick a type at runtime based on the first non-NULL value. **The result type is determined when parsing the SQL expression**, not per row at runtime.

To guarantee an explicit target type, CAST arguments to compatible types:

~~~sql
SELECT COALESCE(
           CAST(so_tien_thuc_te AS NUMBER(12,2)),
           CAST(so_tien_du_kien AS NUMBER(12,2)),
           CAST(0 AS NUMBER(12,2))
       ) AS so_tien
FROM don_hang;
~~~

### 4.4. How COALESCE differs from NVL

| Criterion | NVL | COALESCE |
| --- | --- | --- |
| Argument count | Exactly 2 | 2 or more |
| Selection rule | If expr1 is NULL return expr2 | Return first non-NULL expression |
| Data type | Conversion rules driven by expr1 and numeric precedence | Common expression type rules, numeric precedence for numeric arguments |
| Branch evaluation | Should not be relied on to control evaluation order | Oracle documents short-circuit evaluation |
| Equivalent syntax | Expressible via CASE | Shorthand for multi-branch CASE |

Example where NVL and COALESCE return the same value in a simple case:

~~~sql
SELECT NVL(CAST(NULL AS NUMBER), 5) AS bang_nvl,
       COALESCE(CAST(NULL AS NUMBER), 5) AS bang_coalesce
FROM dual;
~~~

However, never assume the two functions are always identical in data types, expression evaluation, or handling of complex arguments.

## 5. NULLIF: turning equal values into NULL

Syntax:

~~~sql
NULLIF(expr1, expr2)
~~~

- If `expr1 = expr2` is TRUE, returns NULL.
- If the two expressions differ, returns expr1.
- If comparison is UNKNOWN due to NULL, the function does not treat them as equal; it returns expr1, so if expr1 is NULL the result remains NULL.

NULLIF is semantically equivalent to:

~~~sql
CASE
    WHEN expr1 = expr2 THEN NULL
    ELSE expr1
END
~~~

The first argument of NULLIF **cannot be a bare NULL literal**. Pass an expression with a concrete data type.

### 5.1. Example: filtering out sentinel values

A legacy system might store 0 to indicate "not yet graded", even though 0 should not be treated as an actual score:

~~~sql
SELECT NULLIF(diem, 0) AS diem_hop_le
FROM ket_qua_thi;
~~~

If `DIEM` equals 0, the result is NULL; otherwise, the score is preserved. Use this only when the data convention genuinely defines 0 as a sentinel. If 0 is a valid score, NULLIF destroys real data.

### 5.2. NULLIF to avoid division by zero

An application calculating a ratio:

~~~sql
SELECT doanh_thu / NULLIF(so_don, 0) AS doanh_thu_moi_don
FROM thong_ke;
~~~

If `SO_DON = 0`, `NULLIF(so_don, 0)` returns NULL; dividing by NULL returns NULL instead of raising a division-by-zero error. If `SO_DON` is already NULL, the result is also NULL.

If a report wants to display 0 instead of an undefined ratio:

~~~sql
SELECT NVL(
           doanh_thu / NULLIF(so_don, 0),
           0
       ) AS doanh_thu_moi_don_hien_thi
FROM thong_ke;
~~~

However, distinguish carefully:
- `SO_DON = 0`: no orders exist to calculate an average.
- `SO_DON IS NULL`: order count is unknown.
- Result 0: a display convention chosen for reporting.

Using NVL to turn the result into 0 is a **presentation/business decision**, not a mathematical fact that revenue per order equals 0.

### 5.3. Data type of NULLIF

NULLIF returns the data type of expr1, following applicable conversion and comparison rules. With numeric arguments of differing types, Oracle applies numeric precedence. For character arguments, comparison types and collations must be compatible.

~~~sql
SELECT NULLIF(
           CAST(10 AS NUMBER(8,2)),
           CAST(10 AS NUMBER(8,2))
       ) AS ket_qua
FROM dual;
~~~

The result is NULL, yet the expression retains the numeric type matching the first argument.

## 6. Comparison table of the four functions

| Function | Condition | Return Value | Argument Count |
| --- | --- | --- | --- |
| NVL(a,b) | Is a NULL? | a if present, else b | 2 |
| NVL2(a,b,c) | Is a non-NULL? | b if a is non-NULL, c if a is NULL | 3 |
| COALESCE(a,b,c,...) | Scan left to right | First non-NULL value | 2 or more |
| NULLIF(a,b) | Does a equal b? | NULL if equal, else a | 2 |

Example on the same input values:

~~~sql
WITH du_lieu AS (
    SELECT CAST(NULL AS NUMBER) AS a,
           10 AS b,
           20 AS c
    FROM dual
)
SELECT NVL(a, b) AS ket_qua_nvl,
       NVL2(a, b, c) AS ket_qua_nvl2,
       COALESCE(a, b, c) AS ket_qua_coalesce,
       NULLIF(b, c) AS ket_qua_nullif
FROM du_lieu;
~~~

Results:
- `NVL(a,b)` returns 10 because a is NULL.
- `NVL2(a,b,c)` returns 20 because a is NULL, selecting the third argument.
- `COALESCE(a,b,c)` returns 10 because b is the first non-NULL value.
- `NULLIF(b,c)` returns 10 because 10 differs from 20.

Changing `a` to 5 makes NVL return 5, NVL2 return `b = 10`, COALESCE return 5, while `NULLIF(b,c)` remains 10. Four functions solve four distinct needs.

## 7. Result type selection: the most error-prone area

Oracle resolves expression data types during SQL parse/compile time. Runtime NULL values never cause Oracle to switch return types row by row. Therefore, whenever using NULL functions, check both **values** and **data types**.

### 7.1. NVL with a VARCHAR2 column and a NUMBER value

Suppose `MA_THAM_CHIEU` is VARCHAR2:

~~~sql
SELECT NVL(ma_tham_chieu, 0) AS ma_hien_thi
FROM du_lieu_import;
~~~

Because the first argument is character data, 0 is converted to a string. If Java reads it via `getString`, that works; if it calls `getBigDecimal`, do not assume the column was NUMBER.

Conversely:

~~~sql
SELECT NVL(so_luong, '0') AS so_luong_hien_thi
FROM chi_tiet_don_hang;
~~~

If `SO_LUONG` is NUMBER, `'0'` converts to a number. With a non-numeric string, conversion fails.

### 7.2. Errors from implicit conversion

~~~sql
SELECT NVL(
           CAST(NULL AS NUMBER),
           'not a number'
       )
FROM dual;
~~~

Oracle must convert the second argument to a numeric type per NVL rules; a string that cannot parse as a number raises a conversion error, typically `ORA-01722` or a related error depending on expression and version.

Never assume that because a current row has a non-NULL expr1, a mistyped expr2 will never fail. Expression data types must be compatible at parse time.

### 7.3. CAST to lock in target data types

To guarantee a NUMBER result with specific precision/scale:

~~~sql
SELECT COALESCE(
           CAST(tien_thuc_te AS NUMBER(12,2)),
           CAST(tien_du_kien AS NUMBER(12,2)),
           CAST(0 AS NUMBER(12,2))
       ) AS tong_tien
FROM don_hang;
~~~

To guarantee a VARCHAR2 result:

~~~sql
SELECT COALESCE(
           CAST(ma_tham_chieu AS VARCHAR2(30)),
           CAST(ma_legacy AS VARCHAR2(30)),
           CAST('NO CODE' AS VARCHAR2(30))
       ) AS ma_hien_thi
FROM du_lieu_import;
~~~

CAST is useful when:
- Columns have differing NUMBER precision/scale.
- Output must have a consistent type for JDBC or views.
- Bare NULL literals lack type metadata.
- NLS-dependent implicit conversions must be avoided.
- Expressions appear in UNION, CASE, COALESCE, or computed columns.

Do not CAST carelessly if it truncates precision or introduces unnecessary conversions.

### 7.4. Typed NULLs in expressions

A standalone NULL literal carries no target data type. When combining multiple expressions, CAST it so Oracle resolves the intended type:

~~~sql
SELECT COALESCE(
           CAST(NULL AS DATE),
           DATE '2024-01-01'
       ) AS ngay_mac_dinh
FROM dual;
~~~

Similarly with TIMESTAMP:

~~~sql
SELECT NVL(
           CAST(NULL AS TIMESTAMP(3)),
           TIMESTAMP '2024-01-01 08:30:00.000'
       ) AS thoi_diem
FROM dual;
~~~

Explicit typing clarifies the data-type contract between SQL and applications.

## 8. NULL functions in calculations, aggregations, and reports

### 8.1. Arithmetic with NULL

In Oracle, arithmetic operations with a NULL operand normally yield NULL:

~~~sql
SELECT 100 + NULL AS ket_qua
FROM dual;
~~~

The result is NULL. If business rules treat an unentered surcharge as 0:

~~~sql
SELECT gia_co_ban + NVL(phu_phi, 0) AS tong_gia
FROM san_pham;
~~~

Use NVL only when NULL genuinely means zero fee. If NULL means "not yet determined", substituting 0 will skew reports.

### 8.2. How COUNT, SUM, and AVG handle NULL

Aggregate functions normally ignore NULLs in the argument column, while `COUNT(*)` counts all rows:

| Expression | Behavior with NULL |
| --- | --- |
| COUNT(*) | Counts all rows |
| COUNT(cot) | Counts rows where COT is non-NULL |
| SUM(cot) | Sums non-NULL values; returns NULL if no non-NULL values exist |
| AVG(cot) | Averages non-NULL values; returns NULL if none exist |
| MIN(cot), MAX(cot) | Ignores NULL; returns NULL if none exist |

Example:

~~~sql
SELECT COUNT(*) AS tong_hang,
       COUNT(thuong) AS so_hang_co_thuong,
       SUM(thuong) AS tong_thuong,
       NVL(SUM(thuong), 0) AS tong_thuong_hien_thi
FROM nhan_vien;
~~~

`NVL(SUM(thuong), 0)` turns a NULL total into 0. This differs from:

~~~sql
SELECT SUM(NVL(thuong, 0))
FROM nhan_vien;
~~~

If the table has at least one row and every `THUONG` is NULL, `SUM(NVL(THUONG,0))` returns 0. If zero input rows exist, `SUM` still returns NULL because there are no rows to sum. By contrast, `NVL(SUM(THUONG),0)` returns 0 even when zero rows match.

### 8.3. AVG(NVL(cot,0)) differs from NVL(AVG(cot),0)

~~~sql
SELECT AVG(diem) AS trung_binh_bo_qua_null,
       AVG(NVL(diem, 0)) AS trung_binh_tinh_null_bang_0,
       NVL(AVG(diem), 0) AS trung_binh_hien_thi
FROM ket_qua_thi;
~~~

- `AVG(DIEM)` skips rows where score is NULL.
- `AVG(NVL(DIEM,0))` counts each NULL score as 0 in the denominator, provided rows exist.
- `NVL(AVG(DIEM),0)` only replaces a NULL AVG result with 0 at output.

These three expressions can yield vastly different numbers. Decide whether NULL is excluded from the denominator, treated as 0, or leaves the entire metric undefined.

### 8.4. Using NULLIF in ratios

~~~sql
SELECT ma_phong,
       SUM(doanh_thu) / NULLIF(SUM(so_don), 0) AS doanh_thu_moi_don
FROM thong_ke_phong
GROUP BY ma_phong;
~~~

If total orders equal 0, the denominator becomes NULL and the ratio is NULL instead of raising division by zero. If a report needs to display a hyphen for undefined ratios, you can wrap it with character-typed NVL/COALESCE, though the result type then becomes VARCHAR2; never use a display string in place of numeric columns needed for downstream calculations.

## 9. Filter predicates: NVL and indexes

Using NVL in `SELECT` for display is usually straightforward. Wrapping a column in a function inside `WHERE` requires checking index impact.

Example:

~~~sql
SELECT *
FROM nhan_vien
WHERE NVL(ma_phong, 0) = :ma_phong;
~~~

Column `MA_PHONG` is wrapped in NVL. A standard B-tree index on `MA_PHONG` cannot be used via direct index equality like `MA_PHONG = :ma_phong`, because the evaluated predicate is `NVL(MA_PHONG,0)`.

If business logic wants rows matching `:ma_phong` and also wants NULL rows when `:ma_phong = 0`, write it explicitly:

~~~sql
SELECT *
FROM nhan_vien
WHERE ma_phong = :ma_phong
   OR (ma_phong IS NULL AND :ma_phong = 0);
~~~

Verify that 0 is never a valid department code when using it as a sentinel for NULL. The rewritten query may use an OR access path or a different plan; there is no guarantee the optimizer always picks an index.

### 9.1. Function-based index

If a workload frequently queries by the same NVL expression and measurements justify it, consider a function-based index:

~~~sql
CREATE INDEX ix_nv_phong_nvl
ON nhan_vien (NVL(ma_phong, 0));
~~~

Queries must use the matching expression:

~~~sql
SELECT *
FROM nhan_vien
WHERE NVL(ma_phong, 0) = :ma_phong;
~~~

Evaluate:
- Whether 0 could ever collide with a real department ID.
- Storage and `INSERT`/`UPDATE`/`DELETE` overhead added by the index.
- Whether the query expression exactly matches the index expression.
- Required privileges and settings for function-based indexes.
- Whether the actual execution plan improves.

Never create a function-based index merely because NVL appears in one query. Measure workload and plans first.

### 9.2. NULL in B-tree indexes

A single-column Oracle B-tree index does not store entries for rows where the indexed column is entirely NULL. A composite index still stores an entry if at least one key component is non-NULL. Therefore, do not assume all indexes handle NULL lookups identically or that every `IS NULL` query forces a full table scan.

Index structure, predicates, proportion of NULL rows, and optimizer statistics determine the access path.

## 10. Choosing the right function by business scenario

| Need | Often Suitable Function | Example |
| --- | --- | --- |
| Replace one NULL column with a default | NVL | NVL(thuong, 0) |
| Pick a label based on whether a column is NULL | NVL2 | NVL2(ngay_nghi, 'Inactive', 'Active') |
| Pick the first populated value from multiple sources | COALESCE | COALESCE(email_cong_ty, email_ca_nhan, email_khac) |
| Turn a sentinel value into NULL | NULLIF | NULLIF(diem, 0) |
| Guard against a zero denominator | NULLIF | doanh_thu / NULLIF(so_don, 0) |
| Replace a NULL aggregate result on output | NVL / COALESCE | COALESCE(SUM(tien), 0) |
| Multiple complex conditions with distinct branch logic | CASE | Multi-state classification |
| Strict control over output data type | CAST combined with functions | COALESCE(CAST(a AS NUMBER(12,2)), CAST(b AS NUMBER(12,2))) |

### 10.1. When should you use CASE?

CASE fits when conditions go beyond simple NULL checks:

~~~sql
SELECT ma_nhan_vien,
       CASE
           WHEN ngay_nghi IS NULL THEN 'ACTIVE'
           WHEN ngay_nghi < DATE '2024-01-01' THEN 'LEFT BEFORE 2024'
           ELSE 'LEFT FROM 2024'
       END AS nhom_trang_thai
FROM nhan_vien;
~~~

CASE supports multiple branches, compound conditions, and explicit return types. NVL2 only checks NULL/non-NULL on a single expression; COALESCE only picks the first non-NULL value.

## 11. Sample dataset for practice

Run these statements in a sandbox schema with table-creation privileges. The dataset intentionally mixes NULL, 0, empty strings, and normal values to highlight differences across the functions.

### 11.1. Create the table

~~~sql
CREATE TABLE nhan_vien_null_demo (
    ma_nv       NUMBER(6)
        CONSTRAINT pk_nv_null_demo PRIMARY KEY,
    ho_ten      VARCHAR2(100 CHAR) NOT NULL,
    thuong      NUMBER(12,2),
    diem        NUMBER(5,2),
    email_cty   VARCHAR2(150 CHAR),
    email_cn    VARCHAR2(150 CHAR),
    ngay_nghi   DATE,
    so_don      NUMBER(8)
);
~~~

### 11.2. Load sample data

~~~sql
INSERT INTO nhan_vien_null_demo
VALUES (101, 'An', 2500000, 9.50, 'an@congty.test',
        'an.ca.nhan@test', NULL, 5);

INSERT INTO nhan_vien_null_demo
VALUES (102, 'Binh', NULL, 0, NULL,
        'binh@test', DATE '2024-02-01', 0);

INSERT INTO nhan_vien_null_demo
VALUES (103, 'Chi', 0, NULL, NULL,
        NULL, NULL, NULL);

INSERT INTO nhan_vien_null_demo
VALUES (104, 'Dung', 1250000, 7.25, 'dung@congty.test',
        NULL, DATE '2023-12-31', 2);

INSERT INTO nhan_vien_null_demo
VALUES (105, 'Giang', NULL, NULL, '', '',
        NULL, 0);

COMMIT;
~~~

In Oracle, the two `''` values on row 105 are stored and interpreted as NULL for VARCHAR2. The dataset distinguishes:
- `THUONG` NULL vs. `THUONG = 0`.
- `DIEM` NULL vs. `DIEM = 0`.
- `EMAIL` NULL vs. `EMAIL` with a real string.
- `SO_DON` NULL vs. `SO_DON = 0`.

### 11.3. Replacing NULL with 0 via NVL

~~~sql
SELECT ma_nv,
       ho_ten,
       thuong,
       NVL(thuong, 0) AS thuong_hien_thi
FROM nhan_vien_null_demo
ORDER BY ma_nv;
~~~

Rows 102 and 105 have `THUONG` NULL, so they display 0. Row 103 genuinely has `THUONG = 0` and also displays 0, even though the underlying data differs. If a report must distinguish missing data from zero, do not expose only the NVL-substituted column.

### 11.4. Picking the first populated email via COALESCE

~~~sql
SELECT ma_nv,
       COALESCE(
           email_cty,
           email_cn,
           'No email'
       ) AS email_lien_he
FROM nhan_vien_null_demo
ORDER BY ma_nv;
~~~

- Row 101 selects work email.
- Row 102 selects personal email.
- Rows 103 and 105 return the default string.
- Row 104 selects work email.

### 11.5. Classifying leave dates via NVL2

~~~sql
SELECT ma_nv,
       NVL2(ngay_nghi,
            'LEFT',
            'ACTIVE') AS trang_thai
FROM nhan_vien_null_demo
ORDER BY ma_nv;
~~~

Rows with `NGAY_NGHI` NULL are classified as `ACTIVE`; rows 102 and 104 have leave dates, so they are classified as `LEFT`.

### 11.6. Turning score 0 into NULL via NULLIF

~~~sql
SELECT ma_nv,
       diem,
       NULLIF(diem, 0) AS diem_sau_nullif
FROM nhan_vien_null_demo
ORDER BY ma_nv;
~~~

- Row 101 keeps 9.50.
- Row 102 has score 0, so it becomes NULL.
- Rows 103 and 105 were already NULL, so they remain NULL.
- Row 104 keeps 7.25.

Turn 0 into NULL only if data conventions define 0 as "ungraded". If 0 is a valid score, the query distorts the data.

### 11.7. Safe division with NULLIF

~~~sql
SELECT ma_nv,
       thuong,
       so_don,
       thuong / NULLIF(so_don, 0) AS thuong_moi_don
FROM nhan_vien_null_demo
ORDER BY ma_nv;
~~~

For rows 102 and 105, `SO_DON = 0`, so the denominator becomes NULL and no division-by-zero error occurs. Row 103 has both `THUONG` and `SO_DON` NULL, so the result is NULL. Row 101 evaluates `2,500,000 / 5 = 500,000`.

### 11.8. Comparing COALESCE and NVL on aggregate results

~~~sql
SELECT SUM(thuong) AS tong_thuong,
       NVL(SUM(thuong), 0) AS tong_thuong_nvl,
       COALESCE(SUM(thuong), 0) AS tong_thuong_coalesce
FROM nhan_vien_null_demo;
~~~

In this dataset the total bonus is 3,750,000; both NVL and COALESCE return the same value because SUM is non-NULL.

To observe the difference when no values exist to sum, filter to an empty set:

~~~sql
SELECT SUM(thuong) AS tong_thuong,
       NVL(SUM(thuong), 0) AS tong_thuong_hien_thi
FROM nhan_vien_null_demo
WHERE ma_nv < 0;
~~~

SUM returns NULL because zero rows match; NVL converts the result to 0.

### 11.9. Inspecting result data types

You can inspect expression type and internal representation via DUMP in a practice environment:

~~~sql
SELECT DUMP(NVL(CAST(NULL AS NUMBER), 10)) AS dump_nvl_number,
       DUMP(COALESCE(CAST(NULL AS NUMBER), 10)) AS dump_coalesce_number,
       DUMP(NVL2(CAST(NULL AS NUMBER), 10, 20)) AS dump_nvl2_number
FROM dual;
~~~

DUMP shows internal type codes and byte representation. Specific output depends on the expression's data type; never use DUMP strings as an API data format.

### 11.10. Cleaning up the sandbox table

~~~sql
DROP TABLE nhan_vien_null_demo PURGE;
~~~

Drop the practice table created in this lesson only when you are sure the data is no longer needed. `DROP TABLE` is DDL with implicit commit; `PURGE` bypasses the recycle bin per standard behavior.

## 12. JDBC and return data types

NULL functions frequently appear in `SELECT` queries read by Java applications over JDBC. Crucially, **the Oracle type of the expression determines the JDBC type observed**, not merely the Java type the developer wishes for.

### 12.1. Reading a nullable NUMBER value

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class NhanVienRepository {
    private final DataSource dataSource;

    public NhanVienRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public BigDecimal layThuong(long maNv) throws SQLException {
        String sql = """
            SELECT thuong
            FROM nhan_vien_null_demo
            WHERE ma_nv = ?
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, maNv);

            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    return null;
                }
                return rs.getBigDecimal("THUONG");
            }
        }
    }
}
~~~

`getBigDecimal` returns Java `null` for SQL NULL, preserving the "no value" state. If the query uses `NVL(thuong, 0)`, Java receives 0 instead of `null`; the application layer can no longer distinguish the two states from that column alone.

### 12.2. Reading a NULL-substituted result

~~~java
String sql = """
    SELECT NVL(thuong, 0) AS thuong_hien_thi
    FROM nhan_vien_null_demo
    WHERE ma_nv = ?
    """;
~~~

The result has a numeric type per NVL rules; use `getBigDecimal("THUONG_HIEN_THI")` when monetary precision is required. Do not call `getString` and parse back when you can read the numeric type directly.

### 12.3. Distinguishing NULL from 0 when reading primitives

In JDBC, primitive getters like `getInt()` return 0 when the column is NULL. You must call `wasNull()` immediately after the getter to tell them apart:

~~~java
int soDon = rs.getInt("SO_DON");
boolean soDonBiNull = rs.wasNull();

if (soDonBiNull) {
    // Order count unknown.
} else {
    // Order count present, including 0.
}
~~~

Alternatively, use object getters like `getObject` with a driver/version-compatible class, or `getBigDecimal` for numbers. Never treat a primitive 0 as proof that the database stored 0.

### 12.4. Binding fallback values with explicit types

~~~java
String sql = """
    SELECT COALESCE(email_cty, email_cn, ?) AS email_lien_he
    FROM nhan_vien_null_demo
    WHERE ma_nv = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "No email");
    ps.setLong(2, maNv);
    // Execute and read results...
}
~~~

Bind variables separate input data from SQL text. Still, ensure all COALESCE arguments have compatible types; if the last argument is a string while earlier columns have another type, CAST or convert explicitly.

### 12.5. Never concatenate user strings into SQL expressions

Never construct SQL by concatenating user input directly into NVL/COALESCE/NULLIF. Use `PreparedStatement` for values. Column names and function names cannot be bound with `?`; if the application allows column selection, map against an explicit allowlist.

## 13. Performance and maintainability impact

NVL, NVL2, COALESCE, and NULLIF are lightweight functions, yet how you place them can affect the optimizer, index usage, type conversions, and SQL readability.

### 13.1. Avoid wrapping columns in WHERE predicates unnecessarily

For example:

~~~sql
WHERE NVL(ma_phong, 0) = 10
~~~

differs from:

~~~sql
WHERE ma_phong = 10
~~~

If the goal is simply to find `MA_PHONG` equal to 10, NVL is unnecessary. Wrapping the column in a function can prevent a regular index from being used as expected.

### 13.2. Do not replace NULL with arbitrary sentinels

Using 0, -1, `DATE '1900-01-01'`, or `'N/A'` as fallback sentinels can collide with real data. If that sentinel ever becomes a valid value later, NVL/NULLIF/COALESCE expressions will conflate states.

Prefer keeping NULL when it carries distinct meaning. Substitute defaults only at presentation boundaries or when business rules explicitly dictate them.

### 13.3. Avoid NLS-dependent implicit conversions

~~~sql
NVL(ngay_tao, '01/01/2024')
~~~

can depend on `NLS_DATE_FORMAT`. Use a DATE literal or `TO_DATE` with an explicit format mask.

Similarly, converting numbers to strings or vice versa can depend on session number formatting. Explicit CASTs and typed binds keep behavior stable.

### 13.4. COALESCE short-circuits, but do not use it to mask arbitrary errors

COALESCE does not evaluate remaining arguments after finding the first non-NULL value. Even so, never embed functions with side effects or rely on evaluation order to perform updates, logging, or transaction control inside SQL expressions. SQL should express computations; side effects belong in procedures or application code with clear control flow.

### 13.5. Inspect the execution plan instead of guessing

~~~sql
EXPLAIN PLAN FOR
SELECT ma_nv
FROM nhan_vien
WHERE NVL(ma_phong, 0) = 10;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

The plan may show a full table scan, index access, or function-based index scan depending on data, indexes, and statistics. `EXPLAIN PLAN` is an estimate; for production analysis, inspect the actual cursor plan and runtime statistics as authorized.

## 14. Common misconceptions

**NVL and COALESCE are always completely identical.** False. COALESCE accepts multiple arguments and documents short-circuit evaluation; NVL has its own specific type-conversion rules.

**NVL2 returns expr1 if expr1 is non-NULL.** False. NVL2 uses expr1 as the condition and returns either expr2 or expr3.

**COALESCE picks the largest or newest value.** False. It picks the first non-NULL argument in written order.

**NULLIF(a,b) returns b if a differs from b.** False. When they differ, NULLIF returns expr1.

**0 and NULL are the same.** False. 0 is a defined numeric value; NULL is the absence of a value in the model.

**Empty strings are always distinct from NULL in Oracle.** False for zero-length VARCHAR2 strings; Oracle treats empty strings as NULL. A string of spaces remains non-NULL.

**NVL(col, '0') always returns VARCHAR2.** False. The return type follows conversion rules driven by the first argument and numeric/data-type precedence.

**As long as the first row is non-NULL, mistyped later arguments are fine.** False. Oracle must parse and resolve types across the entire expression up front.

**AVG(NVL(col,0)) equals NVL(AVG(col),0).** False. The first includes NULL rows in the denominator as 0; the second only replaces a NULL aggregate output.

**NVL in WHERE never affects indexes.** False. Wrapping a column can change the access path; check the plan and evaluate function-based indexes if needed.

**getInt() returning 0 proves the database holds 0.** False. JDBC primitive getters return 0 for SQL NULL; check `wasNull()` or use object getters.

**NULLIF always solves every division-by-zero error.** It works when the divisor is compared against 0 and types are compatible; you must still verify calculation logic and result types.

## 15. Function selection workflow

When writing a NULL-handling expression, follow these steps:

1. Determine what NULL means: unknown, not entered, not applicable, or defined to fall back to another value?
2. If simply replacing one NULL value with a fallback, consider NVL.
3. If returning one of two distinct results depending on whether expr1 is NULL, use NVL2.
4. If choosing among multiple fallback sources in priority order, use COALESCE.
5. If turning a sentinel value or zero denominator into NULL, use NULLIF.
6. If logic involves multiple business conditions, use CASE.
7. Verify the result data type; CAST arguments when needed.
8. Check empty-string semantics, NLS settings, and implicit conversions.
9. If the function is in WHERE or JOIN, evaluate index impact and execution plans.
10. In JDBC, preserve SQL NULL state where needed; never let primitive getters erase the difference between NULL and 0.

## 16. Practice exercises

1. Write a query replacing NULL `BONUS` with 0 using NVL, then explain why `BONUS = 0` and `BONUS IS NULL` still differ.
2. Use NVL2 to classify customers with an `EMAIL` versus those without an `EMAIL`. If `EMAIL` is an empty string in Oracle, which branch is taken?
3. Write a COALESCE picking work phone, personal phone, backup phone, and finally a default string.
4. Explain why swapping the first two arguments of COALESCE can change the result.
5. Use NULLIF to turn a quantity of 0 into NULL before computing average unit price.
6. Identify the possible result data types of `NVL(varchar2_col, 0)` and `NVL(number_col, '0')`.
7. Rewrite `NVL(a,b)` using CASE. When should you prefer CASE over NVL?
8. Compare `AVG(score)`, `AVG(NVL(score,0))`, and `NVL(AVG(score),0)` on a dataset containing some NULL rows.
9. Why can `SUM(NVL(amount,0))` and `NVL(SUM(amount),0)` differ when zero rows match?
10. Write a safe revenue-per-order expression when order count may be 0 using NULLIF.
11. Why should `NVL(date_col, '01/01/2024')` be avoided in systems with varying session NLS settings?
12. Use CAST to ensure a COALESCE of three numeric columns returns `NUMBER(12,2)`.
13. Use DUMP to inspect the return type of NVL2 when the result branches are NUMBER.
14. Explain why `NVL(ma_phong,0)=:p` can alter normal index usage.
15. When can a function-based index on `NVL(cot, sentinel)` be useful, and what must you verify about the sentinel?
16. In Java, why must you call `ResultSet.wasNull()` after `getInt()` if you need to distinguish NULL from 0?
17. A score column allows 0 as a valid grade. Why can `NULLIF(diem,0)` corrupt reports?
18. Design a COALESCE expression for activation date, data-entry date, and a default date; specify the result type and priority order.
19. A query returns NUMBER from the raw column but VARCHAR2 after NVL. What can happen to JDBC code calling `getBigDecimal`?
20. For unknown data, why is keeping NULL at the storage layer often better than storing a sentinel and converting it back in every SQL query?

**NVL, NVL2, COALESCE, and NULLIF all handle NULL, yet each serves a distinct purpose.** Picking the right function, understanding type-conversion rules, and preserving the distinction between NULL and 0 or empty strings makes SQL expressions clearer. In Oracle applications, verify output values, data types, index impact, and how JDBC reads NULL so data semantics never shift between the database and the Java layer.
