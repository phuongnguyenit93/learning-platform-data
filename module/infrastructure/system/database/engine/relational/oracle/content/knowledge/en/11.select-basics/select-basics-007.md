# ORDER BY, NULL Ordering, and Deterministic Sorting Requirements

In Oracle Database, a `SELECT` statement does not automatically promise to return rows in disk storage order, insertion order, primary key order, or the order a previous run happened to display. If an application requires results ordered by latest date, highest score, ascending name, or stable pagination, you must specify that order using **ORDER BY**.

A proper sorting requirement must also answer three questions:

1. **Sort by which keys and in which direction?** This can be one column, multiple columns, or a computed expression.
2. **Where do NULL values go?** Oracle has different defaults between ASC and DESC; declare NULL placement explicitly when NULL has business meaning.
3. **How are rows with equal sort-key values handled?** If multiple rows tie on every ORDER BY key, their relative order is not guaranteed. For deterministic results, add a tie-breaker key, typically the primary key.

This lesson covers ORDER BY syntax, NULL ordering, multi-key sorting, expressions and collation, pagination, top-N, analytic functions, index impact, and building deterministic ordering for Java/JDBC applications.

## 1. SELECT Results Have No Default Order

A heap table in Oracle is organized by blocks and segments, not as a list that preserves insertion order. The following query:

~~~sql
SELECT ma_don_hang, ma_khach_hang, ngay_dat
FROM don_hang;
~~~

carries no guarantee that results will follow order ID, order date, or INSERT order. Output order can change after:

- The optimizer chooses a different execution plan.
- An index is created, dropped, or modified.
- Optimizer statistics are updated.
- Data is inserted, updated, deleted, or segments are reorganized.
- The query runs in parallel or under a different workload environment.

Even if a SELECT today happens to return rows in primary-key order, that is not a SQL ordering contract. **Only an ORDER BY in the final query block returning results to the application determines the returned order.**

Example:

~~~sql
SELECT ma_don_hang, ngay_dat
FROM don_hang
ORDER BY ngay_dat DESC, ma_don_hang DESC;
~~~

The query requests newer order dates first; when multiple orders share the same date, larger order IDs come first. If the combination of the two keys yields a unique order, the result will have a deterministic order for the same dataset.

## 2. Basic ORDER BY Syntax

General structure:

~~~sql
SELECT select_list
FROM table_or_view
WHERE condition
GROUP BY group_expression
HAVING group_condition
ORDER BY sort_expression [ASC | DESC] [NULLS FIRST | NULLS LAST];
~~~

In a query without GROUP BY/HAVING, WHERE can be omitted as well. ORDER BY generally comes after filtering, grouping, and HAVING clauses.

- **ASC**: ascending order; this is the default if neither ASC nor DESC is specified.
- **DESC**: descending order.
- **NULLS FIRST**: places NULL values before non-NULL values.
- **NULLS LAST**: places NULL values after non-NULL values.

Examples:

~~~sql
-- Price ascending.
SELECT ma_san_pham, ten_san_pham, don_gia
FROM san_pham
ORDER BY don_gia ASC;

-- Price descending.
SELECT ma_san_pham, ten_san_pham, don_gia
FROM san_pham
ORDER BY don_gia DESC;
~~~

For numeric data, ASC typically puts smaller numbers first and DESC puts larger numbers first. For datetime data, ASC puts earlier timestamps first and DESC puts newer timestamps first. For strings, results also depend on comparison/collation rules.

### 2.1. ORDER BY Using a SELECT Alias

You can assign an alias to an expression in the SELECT list and sort by that alias:

~~~sql
SELECT ma_don_hang,
       so_luong * don_gia AS thanh_tien
FROM chi_tiet_don_hang
ORDER BY thanh_tien DESC, ma_don_hang ASC;
~~~

Aliases make SQL easier to read when expressions are long. Within the same query block, ORDER BY can reference a select-list alias under Oracle rules. Do not try to use an alias in WHERE of the same query block as though it had already been evaluated before SELECT.

### 2.2. ORDER BY by Column Position

Oracle permits using column positions from the select list:

~~~sql
SELECT ma_don_hang, ngay_dat, trang_thai
FROM don_hang
ORDER BY 2 DESC, 1 ASC;
~~~

`2` refers to the second column (`NGAY_DAT`), and `1` refers to the first column (`MA_DON_HANG`). This shorthand is brief, but fragile when someone reorders columns in SELECT. In application code and business specifications, prefer **column names or aliases** for clarity.

### 2.3. Expressions in ORDER BY

You can sort by computed expressions:

~~~sql
SELECT ma_nhan_vien,
       ho_ten,
       luong
FROM nhan_vien
ORDER BY luong * 12 DESC, ma_nhan_vien ASC;
~~~

The example above sorts by hypothetical annual salary, then by employee ID. You can use CASE, datetime functions, arithmetic operators, or string functions as sort keys. Ensure data types and conversions are explicit; do not rely on implicit conversion among numbers, dates, and strings.

## 3. Multi-Key Sorting: Left-to-Right Precedence

When ORDER BY lists multiple expressions, Oracle compares them from left to right:

1. Compare the first key.
2. If tied, compare the second key.
3. If still tied, compare the third key.
4. Continue until a distinguishing key differs or the list ends.

Example sorting employees by department, salary descending, and employee ID ascending:

~~~sql
SELECT ma_nhan_vien,
       ma_phong,
       ho_ten,
       luong
FROM nhan_vien
ORDER BY ma_phong ASC,
         luong DESC,
         ma_nhan_vien ASC;
~~~

Results are ordered by department ID ascending. Within each department, higher earners appear first. If two employees have the same salary, the smaller employee ID comes first.

### 3.1. Each Key Has Its Own Direction

There is no requirement that all keys share the same direction:

~~~sql
SELECT ma_don_hang,
       trang_thai,
       ngay_dat,
       tong_tien
FROM don_hang
ORDER BY
    CASE trang_thai
        WHEN 'PENDING' THEN 1
        WHEN 'PAID' THEN 2
        WHEN 'SHIPPED' THEN 3
        WHEN 'CANCELLED' THEN 4
        ELSE 5
    END ASC,
    ngay_dat DESC,
    ma_don_hang ASC;
~~~

Business ordering is defined via CASE, followed by newest date first and order ID as a tie-breaker. This expresses a custom status order rather than hoping alphabetical string order matches business priority.

### 3.2. The Final Key Should Distinguish Rows

If order ID is a primary key, e.g.:

~~~sql
ORDER BY ngay_dat DESC, ma_don_hang DESC
~~~

then no two distinct rows can share the exact same full sort-key tuple, because `MA_DON_HANG` is unique. This provides **total ordering** over the result set.

Conversely:

~~~sql
ORDER BY ngay_dat DESC
~~~

defines order only across distinct dates. If multiple orders share the same `NGAY_DAT`, their relative order is not guaranteed.

A composite key can be used instead of a single column, provided the combination distinguishes every row in the output. In JOIN queries where one order appears multiple times due to multiple line items, adding only order ID may not be enough; you may also need product ID or the line-item primary key.

## 4. NULL Ordering in Oracle

NULL indicates a value that is unknown, unprovided, or not applicable under the data model. It is not zero, a meaningful empty string, or a default date.

Oracle applies default rules:

| Sort direction | Default NULL position |
| --- | --- |
| **ASC** | **NULLS LAST** |
| **DESC** | **NULLS FIRST** |

In other words, Oracle treats NULL as larger than non-NULL values for default ordering purposes. This often surprises developers when applications expect NULLs at the end of every list.

### 4.1. ASC and NULLS LAST

~~~sql
SELECT ma_nhan_vien, ho_ten, ngay_nghi_viec
FROM nhan_vien
ORDER BY ngay_nghi_viec ASC;
~~~

Under default ASC, earlier dates appear first and NULLs appear last. That is often what you want when a NULL termination date means the employee is still active or the termination date is undecided.

To make the intent explicit in code:

~~~sql
SELECT ma_nhan_vien, ho_ten, ngay_nghi_viec
FROM nhan_vien
ORDER BY ngay_nghi_viec ASC NULLS LAST,
         ma_nhan_vien ASC;
~~~

Explicitly writing `NULLS LAST` spares readers from having to remember Oracle's defaults.

### 4.2. DESC Puts NULL First by Default

~~~sql
SELECT ma_nhan_vien, ho_ten, ngay_nghi_viec
FROM nhan_vien
ORDER BY ngay_nghi_viec DESC;
~~~

In Oracle, DESC defaults to `NULLS FIRST`. If NULL means "not yet terminated" and should appear at the bottom of the list, write:

~~~sql
SELECT ma_nhan_vien, ho_ten, ngay_nghi_viec
FROM nhan_vien
ORDER BY ngay_nghi_viec DESC NULLS LAST,
         ma_nhan_vien ASC;
~~~

Do not assume DESC automatically places NULL last just because other UIs or database engines may be configured that way.

### 4.3. NULLS FIRST and NULLS LAST Per Key

Each sort expression can specify its own NULL placement:

~~~sql
SELECT ma_cong_viec,
       ngay_hoan_tat,
       muc_uu_tien
FROM cong_viec
ORDER BY ngay_hoan_tat DESC NULLS LAST,
         muc_uu_tien ASC NULLS FIRST,
         ma_cong_viec ASC;
~~~

Here:
- Recently completed tasks come first; NULL completion dates come last.
- Within the same completion timestamp, numerically lower priority values come first.
- NULL priority comes first within the second sort key.
- Task ID acts as the final tie-breaker.

NULL placement is evaluated per key when preceding keys tie; `NULLS LAST` on the first key does not carry over automatically to subsequent keys.

### 4.4. NULL Is Not Equivalent to a Fallback Value

You can use NVL/COALESCE to replace NULL in an expression:

~~~sql
SELECT ma_nhan_vien, ho_ten, diem
FROM nhan_vien
ORDER BY NVL(diem, -1) DESC,
         ma_nhan_vien;
~~~

This pushes NULL scores to the end if valid scores are non-negative. However, it **alters the sort key**: if `-1` is a valid real value or can appear in data, NULL and `-1` collide into the same sort key. Moreover, wrapping a column in a function can affect standard index usage.

If you only want to control NULL placement, prefer:

~~~sql
ORDER BY diem DESC NULLS LAST, ma_nhan_vien
~~~

Use NVL/COALESCE only when business rules genuinely equate NULL to a fallback value, not merely to control NULL position.

## 5. Sorting NULL with CASE for Custom Rules

CASE can build custom priority keys, useful when business ordering goes beyond NULLS FIRST/LAST:

~~~sql
SELECT ma_nhan_vien,
       ho_ten,
       ngay_nghi_viec
FROM nhan_vien
ORDER BY
    CASE
        WHEN ngay_nghi_viec IS NULL THEN 1
        ELSE 0
    END ASC,
    ngay_nghi_viec DESC,
    ma_nhan_vien ASC;
~~~

The CASE key puts rows with a termination date first and NULL rows last. Within the dated group, the most recent date comes first; employee ID breaks ties.

You can put NULLs first by swapping 1 and 0:

~~~sql
ORDER BY
    CASE WHEN ngay_nghi_viec IS NULL THEN 0 ELSE 1 END,
    ngay_nghi_viec DESC,
    ma_nhan_vien;
~~~

When the rule is simply putting NULLs first or last, `NULLS FIRST`/`NULLS LAST` is shorter and more direct. CASE is suited to multi-bucket status rules or prioritizing specific values.

## 6. Sorting Strings: Collation and NLS

String ordering is not simply A before B as a human eye sees it. It depends on how Oracle compares characters and on collation/NLS settings.

Factors that can influence ordering:
- Uppercase vs. lowercase letters.
- Vietnamese diacritics and accents.
- Linguistic ordering rules.
- Session NLS settings.
- Expressions or collations applied directly in the query.

### 6.1. NLS_SORT and NLS_COMP

You can inspect session settings:

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN ('NLS_SORT', 'NLS_COMP')
ORDER BY parameter;
~~~

`NLS_SORT` specifies the linguistic sort sequence; `NLS_COMP` governs how Oracle applies linguistic comparison in relevant contexts. Exact behavior depends on session configuration and Oracle version.

Do not assume development environment defaults predict production string order, especially when a database is shared by multiple applications or session pools.

### 6.2. NLSSORT for Explicit Sort Rules

You can generate an explicit linguistic sort key with NLSSORT:

~~~sql
SELECT ho_ten
FROM nhan_vien
ORDER BY NLSSORT(ho_ten, 'NLS_SORT=BINARY_CI'),
         ma_nhan_vien;
~~~

`BINARY_CI` illustrates binary case-insensitive ordering. For Vietnamese data, pick an appropriate linguistic rule and test thoroughly on your target Oracle version and collation; do not assume `BINARY_CI` automatically handles every Vietnamese diacritic rule as desired.

Other Oracle-supported linguistic sorts can be used, provided you verify valid sort names in your deployment environment.

### 6.3. A Tie-Breaker Is Still Needed After NLSSORT

Two distinct strings can yield equal sort keys under case-insensitive or accent-insensitive collation rules. Therefore:

~~~sql
ORDER BY NLSSORT(ho_ten, 'NLS_SORT=BINARY_CI'),
         ma_nhan_vien;
~~~

still needs employee ID to produce a deterministic order when two names collate identically.

### 6.4. Avoid Sorting Numbers Stored as Strings

Suppose column `MA_THU_TU` is a VARCHAR2 containing `'2'`, `'10'`, `'100'`. An ORDER BY on the string puts `'10'` before `'2'` because that is character order, not numeric order.

~~~sql
SELECT ma_thu_tu
FROM du_lieu_import
ORDER BY ma_thu_tu;
~~~

If values truly represent numbers, store them as NUMBER. When dealing with imported numeric strings, convert explicitly and guard against invalid values:

~~~sql
SELECT ma_thu_tu
FROM du_lieu_import
ORDER BY TO_NUMBER(ma_thu_tu);
~~~

This works only if every value converts cleanly to NUMBER. For dirty data, validate/normalize first or use CASE/`VALIDATE_CONVERSION` where supported by your version to prevent conversion errors.

## 7. ORDER BY with GROUP BY and Aggregate Functions

After GROUP BY, ORDER BY typically sorts groups by an aggregate expression or grouping key:

~~~sql
SELECT ma_phong,
       COUNT(*) AS so_nhan_vien,
       AVG(luong) AS luong_trung_binh
FROM nhan_vien
GROUP BY ma_phong
ORDER BY so_nhan_vien DESC NULLS LAST,
         ma_phong ASC;
~~~

Groups with more employees come first; ties break by department ID ascending. In this example `COUNT(*)` never returns NULL, yet `NULLS LAST` still illustrates explicit syntax.

You can sort directly by an aggregate expression:

~~~sql
SELECT ma_phong,
       SUM(luong) AS tong_luong
FROM nhan_vien
GROUP BY ma_phong
ORDER BY SUM(luong) DESC, ma_phong;
~~~

When an aggregate alias exists, preferring the alias makes the SQL easier to read. If ORDER BY contains an expression not valid after GROUP BY, Oracle may raise an error; ensure sort keys are compatible with grouping expressions.

### 7.1. ORDER BY After DISTINCT

With `SELECT DISTINCT`, Oracle enforces rules restricting ORDER BY expressions: sort expressions must appear in the SELECT list under the corresponding rules. For example:

~~~sql
SELECT DISTINCT ma_phong
FROM nhan_vien
ORDER BY ma_phong;
~~~

is unambiguous. If you want `SELECT DISTINCT` over one set of columns while sorting by an unselected expression, restructure the query block—for instance, put `DISTINCT` in an inline view and sort in the outer block if semantically valid. Never assume every table column can be referenced in ORDER BY after DISTINCT.

## 8. ORDER BY in Subqueries, Views, and Set Operators

### 8.1. ORDER BY in an Inner Query Block Does Not Guarantee Outer Order

An inline view or view may contain sorting logic for row limiting or a specific computation, but **never rely on inner sorting to guarantee the outer query block's output order**.

~~~sql
SELECT ma_don_hang, ngay_dat
FROM (
    SELECT ma_don_hang, ngay_dat
    FROM don_hang
    ORDER BY ngay_dat DESC
)
WHERE ROWNUM <= 10;
~~~

This is the classic top-N pattern: ORDER BY sits in the inline view to select the top 10 rows before ROWNUM is applied in the outer query block. However, if multiple orders share `NGAY_DAT`, the 10 rows at the cutoff are still nondeterministic without a tie-breaker key.

To guarantee deterministic final output order, add an outer ORDER BY:

~~~sql
SELECT ma_don_hang, ngay_dat
FROM (
    SELECT ma_don_hang, ngay_dat
    FROM don_hang
    ORDER BY ngay_dat DESC, ma_don_hang DESC
)
WHERE ROWNUM <= 10
ORDER BY ngay_dat DESC, ma_don_hang DESC;
~~~

### 8.2. ORDER BY at the End of a Compound Query

With `UNION`, `UNION ALL`, `INTERSECT`, or `MINUS`, ORDER BY is placed at the end of the entire compound query to sort the combined result:

~~~sql
SELECT ma_khach_hang AS ma
FROM khach_hang
WHERE trang_thai = 'ACTIVE'
UNION
SELECT ma_khach_hang AS ma
FROM khach_hang_lich_su
ORDER BY ma;
~~~

Aliases from the first select list are normally used to reference output columns. Do not place an isolated ORDER BY between branches expecting final order to hold. If a branch needs internal ordering for top-N selection, wrap it in a subquery block and sort the outer combined result separately.

### 8.3. ORDER BY Inside a View Does Not Create an Ordering Contract for Callers

A view represents a stored query. Even if a view definition allows an ORDER BY in a specific context, callers should still declare ORDER BY on their own outer SELECT:

~~~sql
SELECT ma_khach_hang, ho_ten
FROM v_khach_hang
ORDER BY ho_ten ASC NULLS LAST, ma_khach_hang;
~~~

Never treat an observed order when selecting from a view as a fixed contract if the outer query has no ORDER BY.

## 9. ORDER BY Inside Analytic Functions vs. Result ORDER BY

Analytic functions such as `ROW_NUMBER`, `RANK`, `DENSE_RANK`, `LAG`, and `LEAD` can take an ORDER BY inside the `OVER` clause:

~~~sql
SELECT ma_nhan_vien,
       ma_phong,
       luong,
       ROW_NUMBER() OVER (
           PARTITION BY ma_phong
           ORDER BY luong DESC, ma_nhan_vien
       ) AS thu_hang_trong_phong
FROM nhan_vien;
~~~

ORDER BY inside OVER defines evaluation order **within the analytic window** and how ranks/row numbers are assigned. It does not automatically guarantee the final row order returned to the client.

To stabilize both ranking and display order:

~~~sql
SELECT ma_nhan_vien,
       ma_phong,
       luong,
       ROW_NUMBER() OVER (
           PARTITION BY ma_phong
           ORDER BY luong DESC, ma_nhan_vien
       ) AS thu_hang_trong_phong
FROM nhan_vien
ORDER BY ma_phong,
         thu_hang_trong_phong;
~~~

### 9.1. ROW_NUMBER vs. RANK

- **ROW_NUMBER** assigns a unique number to each row in window order. If window keys tie, which row gets which number is nondeterministic without a tie-breaker key.
- **RANK** assigns tied rows the same rank and leaves a gap before the next rank.
- **DENSE_RANK** assigns tied rows the same rank without leaving gaps.

Example:

~~~sql
SELECT ma_nhan_vien,
       diem,
       RANK() OVER (ORDER BY diem DESC NULLS LAST) AS hang,
       DENSE_RANK() OVER (ORDER BY diem DESC NULLS LAST) AS hang_day
FROM ket_qua_thi
ORDER BY diem DESC NULLS LAST, ma_nhan_vien;
~~~

Here RANK/DENSE_RANK evaluate only score, so equal scores share the same rank. The outer ORDER BY adds employee ID for stable display. Adding employee ID inside RANK's ORDER BY would prevent equal scores from tying—changing business semantics rather than merely breaking display ties.

## 10. Top-N and Stable Pagination

Applications frequently need the 10 highest-priced products, the 20 newest orders, or page 3 of a customer list. These operations require deterministic ordering.

### 10.1. FETCH FIRST and OFFSET/FETCH

Oracle supports the row limiting clause in modern releases (since Oracle 12c):

~~~sql
SELECT ma_san_pham, ten_san_pham, don_gia
FROM san_pham
ORDER BY don_gia DESC NULLS LAST,
         ma_san_pham
FETCH FIRST 10 ROWS ONLY;
~~~

This returns at most 10 rows ordered by price descending, NULL last, and product ID as tie-breaker. Without a unique key, if several products share the same price at the top-10 boundary, which rows are picked can vary.

Fetching a page with OFFSET/FETCH:

~~~sql
SELECT ma_khach_hang, ho_ten, ngay_dang_ky
FROM khach_hang
ORDER BY ngay_dang_ky DESC NULLS LAST,
         ma_khach_hang DESC
OFFSET 20 ROWS FETCH NEXT 10 ROWS ONLY;
~~~

This skips 20 rows and fetches at most 10 rows. Sorting by `NGAY_DANG_KY` without customer ID allows customers registered on the same date to shift positions between runs.

### 10.2. WITH TIES

~~~sql
SELECT ma_san_pham, ten_san_pham, don_gia
FROM san_pham
ORDER BY don_gia DESC NULLS LAST
FETCH FIRST 10 ROWS WITH TIES;
~~~

`WITH TIES` also returns additional rows whose sort-key values equal the row at the top-N boundary. Use this when business logic wants to **retain all tied rows** rather than cutting off at strictly N rows.

If you add a unique product ID to ORDER BY, distinct rows can no longer share the full sort key, so `WITH TIES` will no longer keep price-tied rows together. Choose sort keys according to intent: tie-preserving on score/price vs. total order for pagination.

### 10.3. Top-N with ROW_NUMBER

You can use an analytic function to control row count:

~~~sql
SELECT ma_san_pham, ten_san_pham, don_gia
FROM (
    SELECT ma_san_pham,
           ten_san_pham,
           don_gia,
           ROW_NUMBER() OVER (
               ORDER BY don_gia DESC NULLS LAST,
                        ma_san_pham
           ) AS rn
    FROM san_pham
)
WHERE rn <= 10
ORDER BY rn;
~~~

`ROW_NUMBER` with a unique tie-breaker produces a deterministic top 10 over the same dataset. If ties should be preserved, use `RANK`/`DENSE_RANK` on the score/price key instead of `ROW_NUMBER`.

### 10.4. Keyset Pagination

Large OFFSET values can force Oracle to find and discard many rows before returning the requested page. For a list sorted by `NGAY_DAT DESC` and `MA_DON_HANG DESC`, the next page can resume after the last key of the previous page:

~~~sql
SELECT ma_don_hang, ngay_dat, trang_thai
FROM don_hang
WHERE ngay_dat < :last_ngay_dat
   OR (
        ngay_dat = :last_ngay_dat
        AND ma_don_hang < :last_ma_don_hang
      )
ORDER BY ngay_dat DESC,
         ma_don_hang DESC
FETCH FIRST 20 ROWS ONLY;
~~~

This is the keyset pagination pattern for non-NULL sort keys. It uses the last page's final key values to continue, avoiding scanning past all earlier rows via OFFSET.

If `NGAY_DAT` can be NULL, design predicate branches and `NULLS FIRST`/`LAST` rules carefully. Never compare with `= NULL`; handle `IS NULL` and define the next-page cursor logic cleanly. In many systems, choosing non-nullable (`NOT NULL`) sort keys keeps pagination much simpler.

Keyset pagination still requires a unique, stable sort order and properly bound cursor keys. If data mutates between requests, new rows may appear before or after the cursor depending on sort keys. When consistency across multiple pages is required, consider transaction/read consistency or a designated snapshot/SCN.

## 11. Creating Deterministic Order: Total Order and Tie-Breakers

A query has deterministic ordering when its sort keys distinguish every row in the result set. This is essential for:

- Pagination without duplicate or skipped rows from arbitrary ties on the same snapshot.
- Repeatable top-N queries.
- Stable report ordering.
- CSV/Excel exports comparable across runs.
- Automated tests that do not depend on accidental order.
- APIs with clear client contracts.

### 11.1. Non-Deterministic Example

~~~sql
SELECT ma_don_hang, ngay_dat
FROM don_hang
ORDER BY ngay_dat DESC;
~~~

If 50 orders share the same `NGAY_DAT`, Oracle does not guarantee the relative order of those 50 orders. Today's execution plan may display them by physical row order or index order; the next run may differ.

### 11.2. Adding a Unique Key

~~~sql
SELECT ma_don_hang, ngay_dat
FROM don_hang
ORDER BY ngay_dat DESC NULLS LAST,
         ma_don_hang DESC;
~~~

If `MA_DON_HANG` is a primary key, the combined key distinguishes every row. `NULLS LAST` also fixes the position of unknown dates.

### 11.3. When a JOIN Produces Multiple Rows per Entity

~~~sql
SELECT d.ma_don_hang,
       ct.ma_san_pham,
       ct.so_luong
FROM don_hang d
JOIN chi_tiet_don_hang ct
  ON ct.ma_don_hang = d.ma_don_hang
ORDER BY d.ngay_dat DESC,
         d.ma_don_hang DESC,
         ct.ma_san_pham ASC;
~~~

Here `MA_DON_HANG` alone is not unique in the output because each order has multiple detail lines. If `(MA_DON_HANG, MA_SAN_PHAM)` is the primary key of the detail table, those three sort keys uniquely distinguish every output row.

### 11.4. Key Combinations Must Match Transformed Data

If a query uses `GROUP BY`, `DISTINCT`, or `UNION`, the base table's primary key may no longer appear in the result set. Pick a tie-breaker appropriate to **each post-transformation row**, such as the grouping columns or aggregate aliases plus a group-distinguishing key.

You cannot arbitrarily add unselected columns to ORDER BY after DISTINCT. You may need an inline view to carry the required keys into the appropriate query block.

## 12. ORDER BY and Indexes: Sorting Can Be Resource-Intensive

Oracle can sometimes use an index to deliver rows in sorted order without a separate sort operation, though that is **not guaranteed simply because an ORDER BY column is indexed**.

Example:

~~~sql
CREATE INDEX ix_don_hang_ngay_ma
    ON don_hang (ngay_dat DESC, ma_don_hang DESC);
~~~

Query:

~~~sql
SELECT ma_don_hang, ngay_dat
FROM don_hang
ORDER BY ngay_dat DESC, ma_don_hang DESC;
~~~

may leverage the index if the access path, filter predicates, index structure, and NULL requirements align. The optimizer can still pick another plan if it estimates lower cost.

### 12.1. What Affects Using an Index for Ordering?

- Do the sort columns appear as a leading prefix of the index in matching order?
- Can ASC/DESC directions be satisfied by a forward or backward scan?
- Does the query wrap columns in expressions like NVL, CASE, NLSSORT, or functions?
- Do WHERE conditions change the access path?
- Does the sort key include columns absent from the index?
- Are NULLs and composite index structure compatible with the required output?
- Does the optimizer estimate full scan + sort to be cheaper than index access?

A single-column B-tree index typically does not store entries for rows where **every indexed column is NULL**. In a composite index, a row with at least one non-NULL key column may still have an entry. Therefore, do not assume NULL rows vanish from every index; inspect the index definition.

### 12.2. Inspecting the Execution Plan

You can run EXPLAIN PLAN in a practice environment:

~~~sql
EXPLAIN PLAN FOR
SELECT ma_don_hang, ngay_dat
FROM don_hang
ORDER BY ngay_dat DESC NULLS LAST,
         ma_don_hang DESC;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

In the plan, you may see operations such as **SORT ORDER BY**, **SORT ORDER BY STOPKEY**, or an access path that satisfies ordering. Exact details depend on Oracle version and the actual plan. EXPLAIN PLAN shows an estimated plan; for production diagnostics, inspect actual cursor plans and runtime statistics when authorized.

### 12.3. Sorting Uses Memory and TEMP

If Oracle must sort large volumes of data, it uses a PGA workarea. When memory is insufficient, sorting spills to the TEMP tablespace. ORDER BY over millions of rows or across wide columns/expressions can consume significant CPU, I/O, and TEMP.

Guidelines:
- Filter data early before sorting when semantics allow.
- Select only needed columns instead of pulling large payloads.
- Use top-N / row limiting when only a subset of rows is needed.
- Design indexes based on actual workload and execution plans.
- Do not create an index for every ORDER BY, as indexes consume storage and add DML overhead.

## 13. Sample Dataset to Practice NULL Ordering and Tie-Breakers

Run in a sandbox schema with table-creation privileges. IDs are fixed so results can be verified easily.

### 13.1. Create the Table

~~~sql
CREATE TABLE nhan_vien_sort (
    ma_nhan_vien NUMBER(6)
        CONSTRAINT pk_nhan_vien_sort PRIMARY KEY,
    ho_ten       VARCHAR2(100 CHAR) NOT NULL,
    ma_phong     NUMBER(4),
    diem         NUMBER(5, 2),
    ngay_vao     DATE,
    ngay_nghi    DATE
);
~~~

### 13.2. Insert Data

~~~sql
INSERT INTO nhan_vien_sort VALUES
    (101, 'An', 10, 9.50, DATE '2022-01-10', NULL);

INSERT INTO nhan_vien_sort VALUES
    (102, 'Binh', 10, 9.50, DATE '2022-01-10', NULL);

INSERT INTO nhan_vien_sort VALUES
    (103, 'Chi', 20, 8.00, DATE '2023-03-15', DATE '2024-02-01');

INSERT INTO nhan_vien_sort VALUES
    (104, 'Dung', 20, NULL, DATE '2023-03-15', NULL);

INSERT INTO nhan_vien_sort VALUES
    (105, 'Giang', 10, 7.25, NULL, DATE '2024-01-31');

INSERT INTO nhan_vien_sort VALUES
    (106, 'Hanh', 30, 9.50, DATE '2022-01-10', DATE '2024-02-01');

INSERT INTO nhan_vien_sort VALUES
    (107, 'Khanh', 30, NULL, NULL, NULL);

COMMIT;
~~~

The dataset intentionally includes:
- Equal scores across employees 101, 102, and 106.
- Matching hire dates.
- NULL scores for employees 104 and 107.
- NULL hire dates for employees 105 and 107.
- Both NULL and known termination dates.

### 13.3. Descending Score with NULLs Last and ID Tie-Breaker

~~~sql
SELECT ma_nhan_vien, ho_ten, diem
FROM nhan_vien_sort
ORDER BY diem DESC NULLS LAST,
         ma_nhan_vien ASC;
~~~

Expected order:

| Rank | ID | Name | Score |
| ---: | ---: | --- | ---: |
| 1 | 101 | An | 9.50 |
| 2 | 102 | Binh | 9.50 |
| 3 | 106 | Hanh | 9.50 |
| 4 | 103 | Chi | 8.00 |
| 5 | 105 | Giang | 7.25 |
| 6 | 104 | Dung | NULL |
| 7 | 107 | Khanh | NULL |

The three rows with score 9.50 are ordered by employee ID ascending. The two NULL rows are also ordered by ID, giving the entire output a deterministic order.

### 13.4. Comparing Default DESC vs. DESC NULLS LAST

~~~sql
-- Oracle defaults to NULLS FIRST for DESC.
SELECT ma_nhan_vien, ho_ten, diem
FROM nhan_vien_sort
ORDER BY diem DESC;

-- Put NULLs at the end.
SELECT ma_nhan_vien, ho_ten, diem
FROM nhan_vien_sort
ORDER BY diem DESC NULLS LAST,
         ma_nhan_vien;
~~~

The first query places NULL-score rows at the top under Oracle's default. The second places NULLs at the bottom and adds a secondary key. Both use DESC yet have different display meanings.

### 13.5. Active Employees First

~~~sql
SELECT ma_nhan_vien, ho_ten, ngay_nghi
FROM nhan_vien_sort
ORDER BY
    CASE WHEN ngay_nghi IS NULL THEN 0 ELSE 1 END,
    ngay_nghi DESC,
    ma_nhan_vien;
~~~

Employees with NULL `NGAY_NGHI` appear first; within the terminated group, the most recent termination date comes first. Employee ID guarantees a stable order when dates or NULL states tie.

### 13.6. Stable Pagination

~~~sql
SELECT ma_nhan_vien, ho_ten, diem
FROM nhan_vien_sort
ORDER BY diem DESC NULLS LAST,
         ma_nhan_vien
OFFSET 2 ROWS FETCH NEXT 3 ROWS ONLY;
~~~

The query fetches three rows after skipping the first two, ordered by score descending, NULLs last, and employee ID ascending. Removing employee ID would let tied rows at the page boundary shift between executions.

### 13.7. Clean Up the Practice Table

~~~sql
DROP TABLE nhan_vien_sort PURGE;
~~~

Run only on the sandbox table created for this exercise when the data is no longer needed. `DROP TABLE` is DDL with an implicit commit; `PURGE` bypasses the recycle bin per standard behavior.

## 14. Common Mistakes and Misconceptions

| Symptom | Cause | How to fix |
| --- | --- | --- |
| Result order changes even though data did not change | Missing ORDER BY or tied sort keys | Add ORDER BY with a unique tie-breaker key |
| NULL appears first with DESC | That is Oracle's default | Write `DESC NULLS LAST` if NULL should be last |
| NULL appears last with ASC | That is Oracle's default | Explicitly write `NULLS LAST` to state intent |
| Top 10 shifts between runs | Boundary rows share the same sort key | Add a unique key or use `WITH TIES` to keep ties |
| Pagination skips or duplicates rows | Non-deterministic order or concurrent data mutations | Use total order, keyset pagination, and proper snapshots |
| Number 100 appears before 2 | Numeric column stored as VARCHAR2 | Store as NUMBER or convert explicitly |
| Vietnamese names sort differently across environments | Different `NLS_SORT`/`NLS_COMP` or collation | Lock down linguistic sort rules; use `NLSSORT` when needed |
| ORDER BY inside a view does not guarantee caller order | Outer query block lacks ORDER BY | Place ORDER BY on the final SELECT |
| `ROW_NUMBER` assigns differing numbers across tied rows | Window ORDER BY lacks a tie-breaker | Add a distinguishing key to ORDER BY inside OVER |
| Only OVER has ORDER BY, so final output is unsorted | Analytic order differs from final result order | Add an outer ORDER BY |
| ORDER BY consumes TEMP | Large sort exceeds PGA workarea | Narrow the dataset, use top-N/indexes, and inspect the plan |
| ORDER BY expression skips expected index | Sort key wraps column in a function/expression | Check the plan; consider function-based index if workload warrants |

## 15. ORDER BY Design Principles for APIs and Reports

An API returning lists should document its sort contract explicitly, for example:

- Newest first: `NGAY_TAO DESC NULLS LAST, ID DESC`.
- Highest score first: `DIEM DESC NULLS LAST, ID ASC`.
- Ascending name: `NLSSORT(TEN, collation_rule), ID ASC`.
- Unprocessed first: status `CASE`, `NGAY_TAO ASC, ID ASC`.

Never write just "sort by date" if dates can be NULL or multiple rows can share the same date. Specify direction, NULL placement, and the tie-breaker key.

For Java/JDBC applications:
- Bind filter and pagination values using `PreparedStatement`.
- Never concatenate column names or ASC/DESC directions directly from untrusted input. Map sort fields through an allowlist.
- For dynamic client sorting, assemble allowed sort expressions; bind variables cannot replace column names or SQL keywords.
- Keep a unique key at the end of ORDER BY for stable pages.
- Verify NULL semantics between Oracle and frontend display logic.
- When multiple pages must stay consistent over time, establish a snapshot or cursor-anchor strategy.

For example, an allowlist in Java can map API field names like `CREATED_AT`, `SCORE`, or `NAME` to fixed SQL expressions; never append raw user strings into ORDER BY. The ASC/DESC direction must likewise be validated against only the two valid choices.

## 16. Mental Checklist When Writing ORDER BY

Before finalizing a SELECT statement, verify:

1. Does the result set require an ordering contract? If so, is ORDER BY in the final query block?
2. Do sort keys match the proper data types and business meaning?
3. Is ASC/DESC clear for every key?
4. Does each key have the right NULLS FIRST/LAST rule?
5. Can multiple rows tie on every key? If so, is a unique tie-breaker included?
6. For top-N or pagination, is output deterministic over the same dataset?
7. If using DISTINCT, GROUP BY, or set operators, are ORDER BY expressions valid in that context?
8. If using analytic functions, are window ORDER BY and final ORDER BY clearly separated?
9. Does string sorting need explicit collation/linguistic rules?
10. Does the execution plan show heavy `SORT ORDER BY`, TEMP spill, or appropriate index access?
11. Does the application dynamically concatenate unvalidated column names or sort directions from input?
12. Does data changing between page requests require consistent snapshots?

## 17. Practice Exercises

1. Write a query listing employees by salary descending, NULL last, then employee ID ascending.
2. Explain why `ORDER BY NGAY_NGHI_VIEC DESC` in Oracle can place employees without a termination date at the top.
3. Write a query putting active (not yet terminated) employees first, followed by terminated employees ordered by most recent termination date.
4. A table has 100 rows sharing the same `NGAY_TAO`. Why does `ORDER BY NGAY_TAO DESC` fail to create a deterministic order?
5. For a JOIN between orders and order details, which keys distinguish every output row?
6. Compare `ORDER BY ... NULLS LAST` with `ORDER BY NVL(col, fallback_value)`. When do the two approaches differ?
7. Write a query getting the top 10 highest-priced products, keeping all products tied in price with the 10th position via `WITH TIES`.
8. Write a `ROW_NUMBER` query returning the top three highest-scoring employees per department, breaking ties by employee ID.
9. Why doesn't `ORDER BY` inside `OVER` automatically sort the final query output?
10. A view contains `ORDER BY`, while the outer SELECT has no `ORDER BY`. Can you guarantee the API's return order?
11. Sort the numeric strings `'2'`, `'10'`, `'100'` in numeric order. How should the data type or expression change?
12. Explain the role of `NLS_SORT` and `NLSSORT` when sorting accented names.
13. Write a pagination query for page 3 with 20 rows per page, ordered by newest `NGAY_DANG_KY` and `MA_KHACH_HANG` descending.
14. Why does adding a unique secondary key make top-N and `OFFSET/FETCH` more stable?
15. When is keyset pagination advantageous over a large `OFFSET`? What condition must be added if the sort key allows `NULL`?
16. A large sort generates high TEMP usage. List the execution plan and workload details to check before adding an index.
17. Why should you never concatenate `ORDER BY column_name` directly from a request parameter into SQL?
18. Distinguish deterministic order on a single snapshot from cross-request consistency when data is concurrently updated.

**ORDER BY defines sort order, NULLS FIRST/LAST defines the position of unknown values, and a unique secondary key creates deterministic order across tied rows.** These three elements are crucial for top-N, pagination, analytic functions, and APIs. Combining proper data types, appropriate NLS rules, and execution plan checks yields results that are both business-accurate and operationally predictable.
