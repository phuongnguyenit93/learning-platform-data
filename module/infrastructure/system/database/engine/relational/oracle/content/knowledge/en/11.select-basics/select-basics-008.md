# ROWNUM and the Limit-Before-Sort Trap in Oracle Database

## 1. The Problem: "Get the 5 Highest-Paid Employees" Returns Wrong Results

Suppose an employee table has thousands of records. The application requires **returning the 5 highest-paid employees**, with smaller employee IDs coming first on ties. An Oracle beginner might write:

```sql
SELECT employee_id, employee_name, salary
FROM   employees
WHERE  ROWNUM <= 5
ORDER BY salary DESC;
```

This query **does not guarantee** returning the 5 highest-paid employees across the entire table. Oracle may pick **5 rows satisfying `ROWNUM <= 5` in access-path order**, and then **sort only those 5 rows** by `salary DESC`. If the first five rows encountered along the access path do not include the top earners, the result violates the business requirement even though the output appears sorted.

That is the **limit before sort** bug.

The correct way in Oracle 12c and later, including Oracle Database 19c:

```sql
SELECT employee_id, employee_name, salary
FROM   employees
ORDER BY salary DESC NULLS LAST, employee_id ASC
FETCH FIRST 5 ROWS ONLY;
```

Or using traditional `ROWNUM` syntax:

```sql
SELECT employee_id, employee_name, salary
FROM (
    SELECT employee_id, employee_name, salary
    FROM   employees
    ORDER BY salary DESC NULLS LAST, employee_id ASC
)
WHERE ROWNUM <= 5;
```

**Key takeaway:** When you need **Top-N by a ranking criterion**, you must establish the order **before selecting N rows** in query semantics. `ROWNUM` is not an automatic ranking feature and is not evaluated after `ORDER BY` in the same query block.

> The examples below focus on Oracle Database 19c and compare 11g-compatible usage with the `row_limiting_clause` introduced in 12c. Table names and data are lab examples. The optimizer may change physical execution order as long as SQL semantics are preserved; the diagrams below illustrate logical behavior for understanding queries, not a guarantee of a single execution plan.

## 2. What Is `ROWNUM` Actually?

**`ROWNUM`** is a **pseudocolumn** that Oracle assigns to rows selected in a **query block**. It does not exist as a stored column in the table, and it is not a primary key, `ROWID`, insertion order, or post-`ORDER BY` position when `ORDER BY` is in the same query block.

From Oracle documentation:

- The first row accepted into the result under the `ROWNUM` mechanism receives `ROWNUM = 1`.
- The next row receives `ROWNUM = 2`, then 3, 4, and so on.
- Which row arrives first depends on the access path chosen by the optimizer: full table scan, index, join strategy, filter, etc.
- If `ORDER BY` is in the same query block, Oracle can assign `ROWNUM` **before sorting the final output**.

Example:

```sql
SELECT employee_id, employee_name, ROWNUM AS rn
FROM   employees;
```

This SQL numbers rows 1, 2, 3... for **that specific execution**. It does **not** prove `rn = 1` is the first employee created, the highest paid, or the smallest ID.

### 2.1. Three Easily Confused Concepts

| Concept | Definition | Stable as a business key? | What is it used for? |
| --- | --- | --- | --- |
| `ROWNUM` | Sequential row number assigned as Oracle selects rows in a query block | **No** | Limiting rows by access order, Top-N pattern with nested query blocks |
| `ROW_NUMBER()` | Analytic function numbering rows by `OVER (ORDER BY ...)`, optionally partitioned | Not a business key; stable within a snapshot if order is total | Ranking and Top-N / Top-N per group |
| `ROWID` | Pseudocolumn indicating storage row address/identifier per Oracle structure | **Should not** be used as a long-term business key | Locating/accessing rows per Oracle capabilities |

If you need an immutable ID for employees or orders, use a **primary key** backed by an identity column or sequence. Never persist `ROWNUM` from a SELECT as a business ID.

### 2.2. Query Block Is the Unit to Distinguish

Compare:

```sql
-- Only one query block:
SELECT *
FROM   employees
WHERE  ROWNUM <= 5
ORDER BY salary DESC;
```

and:

```sql
-- Two query blocks:
SELECT *
FROM (
    SELECT *
    FROM   employees
    ORDER BY salary DESC
)
WHERE ROWNUM <= 5;
```

In the second query, the inner query block's `ORDER BY` defines the sorted set; `ROWNUM` resides in the **outer query block**, so the limit applies to rows already ordered by the inner block. The optimizer may apply a `STOPKEY` optimization, while preserving output equivalent to the Top-N requirement.

## 3. Why Can `WHERE ROWNUM <= N ORDER BY ...` Be Wrong?

Picture a set of four employees, with no assumption about physical storage order:

| EMPLOYEE_ID | EMPLOYEE_NAME | SALARY |
| ---: | --- | ---: |
| 10 | An | 3,000 |
| 20 | Bình | 8,000 |
| 30 | Chi | 5,000 |
| 40 | Dũng | 10,000 |

Suppose **under one specific execution plan**, Oracle reads rows in the order `10 → 30 → 20 → 40`. With:

```sql
SELECT employee_id, employee_name, salary
FROM   employees
WHERE  ROWNUM <= 2
ORDER BY salary DESC;
```

the following can happen:

```text
Data source along a given access path:
  (10, An,   3000)
  (30, Chi,  5000)
  (20, Binh, 8000)
  (40, Dung, 10000)
           │
           ▼  Limit ROWNUM <= 2
  (10, An,   3000)
  (30, Chi,  5000)
           │
           ▼  ORDER BY salary DESC
  (30, Chi,  5000)
  (10, An,   3000)
```

These are the **first two rows encountered along the access path**, sorted afterward. The true result for **Top-2 highest salaries** must be `(40, Dũng, 10000)` and `(20, Bình, 8000)`.

**Beware:** In reality, an index on `salary` or another plan might coincidentally return the desired result even for the buggy SQL. This "coincidentally right" behavior makes the bug hard to catch: adding an index, refreshing statistics, upgrading the optimizer, or changing data volume can alter which five rows are picked first. Never treat a few passing test runs as proof of semantic correctness.

### 3.1. Diagram of Two Non-Commutative Operations

```text
Wrong for Top-N requirement:

    LIMIT N  ──► SORT
  (pick first)  (sort N rows)

Right for Top-N requirement:

    SORT     ──► LIMIT N
  (sort all)    (take first N rows)
```

Performance-wise, Oracle **does not necessarily have to sort the entire table** in the correct plan. It can use a pre-sorted index or `SORT ORDER BY STOPKEY` to optimize Top-N. What is mandatory is that **the N rows returned match sorting first and limiting second**, not that the physical algorithm buffers every sorted row.

## 4. A Predictable Practice Dataset

To test each form, create a lab table with 12 employees, several tied salaries, and one `NULL` salary.

> Create tables only in a lab schema where you hold `CREATE TABLE`. `CREATE TABLE` is DDL with an implicit commit. If you cannot create tables, use an existing table while adjusting column names, data, and expected results.

```sql
CREATE TABLE rownum_staff_lab (
    employee_id   NUMBER
      CONSTRAINT rownum_staff_lab_pk PRIMARY KEY,
    employee_name VARCHAR2(60 CHAR) NOT NULL,
    dept_code     VARCHAR2(12 CHAR) NOT NULL,
    salary        NUMBER(10,2),
    hired_on      DATE NOT NULL
);

INSERT INTO rownum_staff_lab VALUES
    (101, 'An',    'FIN', 1200, DATE '2024-01-10');
INSERT INTO rownum_staff_lab VALUES
    (102, 'Binh',  'FIN', 3000, DATE '2022-01-15');
INSERT INTO rownum_staff_lab VALUES
    (103, 'Chi',   'IT',  4500, DATE '2025-04-03');
INSERT INTO rownum_staff_lab VALUES
    (104, 'Dung',  'IT',  3000, DATE '2023-04-07');
INSERT INTO rownum_staff_lab VALUES
    (105, 'Em',    'IT',  6000, DATE '2021-01-01');
INSERT INTO rownum_staff_lab VALUES
    (106, 'Giang', 'OPS', 2500, DATE '2024-06-01');
INSERT INTO rownum_staff_lab VALUES
    (107, 'Ha',    'OPS', 4500, DATE '2023-09-10');
INSERT INTO rownum_staff_lab VALUES
    (108, 'Khanh', 'OPS', 1200, DATE '2024-11-01');
INSERT INTO rownum_staff_lab VALUES
    (109, 'Linh',  'FIN', 6000, DATE '2020-02-01');
INSERT INTO rownum_staff_lab VALUES
    (110, 'Minh',  'FIN', NULL, DATE '2024-02-03');
INSERT INTO rownum_staff_lab VALUES
    (111, 'Nam',   'HR',  4500, DATE '2022-07-03');
INSERT INTO rownum_staff_lab VALUES
    (112, 'Oanh',  'HR',  3200, DATE '2022-09-19');

COMMIT;
```

To ensure **deterministic ordering** for a fixed data snapshot, always include a tie-breaker key:

```sql
SELECT employee_id, employee_name, dept_code, salary
FROM   rownum_staff_lab
ORDER BY salary DESC NULLS LAST, employee_id ASC;
```

Logical ordered result:

| Position | EMPLOYEE_ID | Name | SALARY |
| ---: | ---: | --- | ---: |
| 1 | 105 | Em | 6000 |
| 2 | 109 | Linh | 6000 |
| 3 | 103 | Chi | 4500 |
| 4 | 107 | Ha | 4500 |
| 5 | 111 | Nam | 4500 |
| 6 | 112 | Oanh | 3200 |
| 7 | 102 | Binh | 3000 |
| 8 | 104 | Dung | 3000 |
| 9 | 106 | Giang | 2500 |
| 10 | 101 | An | 1200 |
| 11 | 108 | Khanh | 1200 |
| 12 | 110 | Minh | NULL |

When rows are added, deleted, or updated, the natural Top-N changes. In this lab, do not create an index on `salary` just to "force" order for `ROWNUM`: the point is that correctness comes from SQL having `ORDER BY` in the right scope, not from hoping for a specific index/physical access path.

## 5. Wrong and Right Ways to Use `ROWNUM`

### 5.1. Wrong: `ROWNUM` and `ORDER BY` in the Same Query Block

```sql
-- Wrong for the goal: five highest-paid employees across the whole table.
SELECT employee_id, employee_name, salary
FROM   rownum_staff_lab
WHERE  ROWNUM <= 5
ORDER BY salary DESC NULLS LAST, employee_id;
```

The output **may** look sorted by salary, yet there is no guarantee the five rows are `105, 109, 103, 107, 111`. Never infer from descending-looking output that it actually selected the global Top-5.

### 5.2. Right: Inline View Sorts, Outer Query Limits

```sql
SELECT employee_id, employee_name, salary
FROM (
    SELECT employee_id, employee_name, salary
    FROM   rownum_staff_lab
    ORDER BY salary DESC NULLS LAST, employee_id ASC
)
WHERE ROWNUM <= 5;
```

The Top-5 result according to the inner view's criteria is IDs:

```text
105 → 109 → 103 → 107 → 111
```

Here `ROWNUM` is assigned in the outer query block **after the inner view's result is semantically sorted**. This is the classic Oracle Top-N pattern used since before `FETCH FIRST` existed.

**A refinement for the presentation layer:** if the client requires the output to be **guaranteed in sorted presentation order**, add `ORDER BY` to the outermost query block rather than relying solely on intermediate ordering:

```sql
SELECT employee_id, employee_name, salary
FROM (
    SELECT employee_id, employee_name, salary
    FROM   rownum_staff_lab
    ORDER BY salary DESC NULLS LAST, employee_id ASC
)
WHERE ROWNUM <= 5
ORDER BY salary DESC NULLS LAST, employee_id ASC;
```

The inner `ORDER BY` decides **which rows belong to Top-5**. The outer `ORDER BY` is the explicit contract for **final output order**. This repetition can be optimized by the optimizer; do not conflate the two roles.

### 5.3. Alternative Using a CTE

```sql
WITH ranked_source AS (
    SELECT employee_id, employee_name, salary
    FROM   rownum_staff_lab
    ORDER BY salary DESC NULLS LAST, employee_id ASC
)
SELECT employee_id, employee_name, salary
FROM   ranked_source
WHERE  ROWNUM <= 5;
```

A CTE (`WITH` clause) improves readability when the source query is complex. However, `WITH` alone does not make SQL right: what matters is **ROWNUM being in the query block outside the sorted source**.

### 5.4. When You Only Want "Any 5 Rows," Same-Block `ROWNUM` Is Fine

```sql
SELECT employee_id, employee_name, salary
FROM   rownum_staff_lab
WHERE  ROWNUM <= 5;
```

This is valid when you simply want **at most five arbitrary rows** (for instance, testing connectivity or quick preview). Without `ORDER BY`, **there is no guarantee which five rows are returned**, even on the same table with the same SQL across calls.

So saying "ROWNUM is wrong" is too broad. **What is wrong is using ROWNUM for a ranked Top-N without putting the ordering in the proper query block.**

## 6. Why Does `WHERE ROWNUM > 1` Return Nothing?

This is a surprising property of `ROWNUM`.

```sql
SELECT employee_id, employee_name
FROM   rownum_staff_lab
WHERE  ROWNUM > 1;
```

This query returns **zero rows**. Explanation:

1. Oracle evaluates a candidate row that could become the first result row: `ROWNUM = 1`.
2. The condition `ROWNUM > 1` is **FALSE**, so that row is rejected.
3. The next row is still a candidate to be the **first** accepted row, so it again gets `ROWNUM = 1`.
4. The condition keeps evaluating to FALSE; this repeats until all candidate rows are exhausted.

```text
Candidate row A → ROWNUM 1 → 1 > 1?  FALSE → reject
Candidate row B → ROWNUM 1 → 1 > 1?  FALSE → reject
Candidate row C → ROWNUM 1 → 1 > 1?  FALSE → reject
...
No "first result row" is ever accepted,
so ROWNUM never advances to 2.
```

Similar predicates in the same query block suffer the same fate:

```sql
-- Cannot fetch "from the 6th row onward" this way:
WHERE ROWNUM > 5

-- Cannot paginate directly with a ROWNUM range:
WHERE ROWNUM BETWEEN 6 AND 10

-- ROWNUM = 2 also fails to pick "the 2nd row":
WHERE ROWNUM = 2
```

Compare:

```sql
WHERE ROWNUM = 1       -- Can accept the first row.
WHERE ROWNUM <= 5      -- Can accept up to the first five rows.
WHERE ROWNUM < 6       -- Same as <= 5 for integers.
WHERE ROWNUM > 1       -- Zero rows in the same query block.
```

To fetch rows at **positions 6 through 10**, you must **assign row numbers in an inner block** and filter the alias in an outer block, or use `OFFSET/FETCH` or `ROW_NUMBER()`.

## 7. The Modern Approach: `ORDER BY ... FETCH FIRST ... ROWS ONLY`

Since Oracle Database **12c**, `SELECT` includes the `row_limiting_clause`, which is cleaner and less error-prone than nesting `ROWNUM`.

### 7.1. Top-5 with Modern Syntax

```sql
SELECT employee_id, employee_name, salary
FROM   rownum_staff_lab
ORDER BY salary DESC NULLS LAST, employee_id ASC
FETCH FIRST 5 ROWS ONLY;
```

Oracle implements the exact semantics: **take the leading rows according to the declared order**. On the fixed lab table, the result is `105, 109, 103, 107, 111`.

Equivalent syntactic variants:

```sql
FETCH FIRST 5 ROWS ONLY
FETCH NEXT  5 ROWS ONLY
FETCH FIRST 5 ROW  ONLY
```

`FIRST`/`NEXT` and `ROW`/`ROWS` are interchangeable syntactically, though `NEXT` usually reads more naturally after `OFFSET`.

### 7.2. Top-N After Filtering

```sql
-- Five highest-paid IT employees (lab table has fewer than five).
SELECT employee_id, employee_name, salary
FROM   rownum_staff_lab
WHERE  dept_code = 'IT'
ORDER BY salary DESC NULLS LAST, employee_id ASC
FETCH FIRST 5 ROWS ONLY;
```

Semantically, Oracle identifies the rows satisfying `dept_code='IT'`, sorts by salary/ID, and picks at most five rows. Do not write:

```sql
-- Does NOT guarantee Top-5 salaries in IT:
SELECT employee_id, employee_name, salary
FROM   rownum_staff_lab
WHERE  dept_code = 'IT'
AND    ROWNUM <= 5
ORDER BY salary DESC NULLS LAST;
```

If IT had more than five employees, the buggy form could just sort the first five accessed.

### 7.3. `FETCH FIRST n PERCENT ROWS ONLY`

```sql
SELECT employee_id, employee_name, salary
FROM   rownum_staff_lab
ORDER BY salary DESC NULLS LAST, employee_id
FETCH FIRST 25 PERCENT ROWS ONLY;
```

Choose this when requirements specify a **percentage of rows**, not an absolute N. On reports whose total row count fluctuates, the number of returned rows scales with total rows. If an SLA requires at most 20 rows, use `ROWS`, not `PERCENT`.

### 7.4. `OFFSET`/`FETCH` Parameters and Edge Counts

Per the Oracle 19c SQL Language Reference:

- `OFFSET n ROWS` skips `n` rows before starting to return data; omitting OFFSET is equivalent to 0.
- Negative OFFSET values are treated as 0; fractional parts are truncated.
- `FETCH FIRST n ROWS ONLY` returns at most `n` remaining rows; if fewer exist, fewer are returned.
- For `FETCH`, `n = 0` or `n = NULL` returns 0 rows; negative values are also treated as 0.
- If `rowcount` is omitted after `FETCH FIRST` in valid syntax, it defaults to 1 row.

Applications should still **validate page size and offset** at the API layer: do not leave negative/NULL inputs to the SQL engine, and do not allow clients to request millions of rows arbitrarily.

## 8. Handling Ties: `ONLY` or `WITH TIES`?

In the lab table:

```text
SALARY = 6000: employee 105, 109
SALARY = 4500: employee 103, 107, 111
SALARY = 3200: employee 112
...
```

### 8.1. `ONLY` Caps Strictly by Row Count

```sql
SELECT employee_id, employee_name, salary
FROM   rownum_staff_lab
ORDER BY salary DESC NULLS LAST, employee_id ASC
FETCH FIRST 3 ROWS ONLY;
```

Returns three employees: `105`, `109`, `103`. Employees `107` and `111` also earn 4500 yet are excluded because only **three rows** are requested. This is right when the true requirement is "take strictly three employees."

### 8.2. `WITH TIES` Can Exceed N on Tied Sort Keys

```sql
SELECT employee_id, employee_name, salary
FROM   rownum_staff_lab
ORDER BY salary DESC NULLS LAST
FETCH FIRST 3 ROWS WITH TIES;
```

The result has **five** people: both 6000 earners and all three 4500 earners. Because the **third row** has salary 4500, every other row sharing the **exact same ORDER BY expression value** is also included.

| Criterion | `ONLY` | `WITH TIES` |
| --- | --- | --- |
| Goal | At most N rows | At least N rows if enough data exists; may add tied rows at the cutoff |
| On the lab table, `FETCH FIRST 3` by `salary DESC` | 3 | 5 |
| Order within equal-salary group | Indeterminate if sorting only by salary | Indeterminate if sorting only by salary |
| Needs a proper `ORDER BY`? | **Yes**, for stable results | **Yes**, to define the tie key and ranking semantics |

**An important trap:** If you write:

```sql
ORDER BY salary DESC NULLS LAST, employee_id ASC
FETCH FIRST 3 ROWS WITH TIES
```

then every row typically has a **distinct sort-key tuple** because `employee_id` is unique. `WITH TIES` will **not include** extra employees who share the same salary with different IDs. When business rules say "tied on salary," sort only by **salary** for the tie criterion, or use `RANK`/`DENSE_RANK` in a separate query. When business rules require **strictly N rows**, include ID as a tie-breaker.

In either case, when multiple rows share the same sort key, keeping the **display order inside the tied group** stable requires separate presentation handling; never assume a fixed order among tied rows.

### 8.3. `RANK` and `DENSE_RANK` Express "Rank Levels"

```sql
SELECT employee_id,
       employee_name,
       salary,
       RANK() OVER (ORDER BY salary DESC NULLS LAST) AS salary_rank,
       DENSE_RANK() OVER (ORDER BY salary DESC NULLS LAST) AS salary_dense_rank
FROM   rownum_staff_lab
ORDER BY salary DESC NULLS LAST, employee_id ASC;
```

Both 6000 earners get `RANK=1`, while all 4500 earners get `RANK=3` (because two rows precede them); `DENSE_RANK` assigns the 4500 group rank 2 (no skipped rank numbers). Asking for "top three **salary levels**" (`DENSE_RANK <= 3`) differs from "three **people**" or `RANK <= 3`.

## 9. Pagination: Why Direct `ROWNUM > offset` Fails

Common REST API requirement:

```text
Page size = 5
Page 1: positions 1–5
Page 2: positions 6–10
Page 3: positions 11–15
```

### 9.1. Wrong Way

```sql
SELECT employee_id, salary
FROM   rownum_staff_lab
WHERE  ROWNUM BETWEEN 6 AND 10
ORDER BY salary DESC;
```

The query returns no rows because `ROWNUM >= 6` can never become TRUE for the first row of **that same query block**.

### 9.2. Cleanest Approach on Oracle 12c+: `OFFSET` and `FETCH`

```sql
-- Page 1, first 5 rows.
SELECT employee_id, employee_name, salary
FROM   rownum_staff_lab
ORDER BY salary DESC NULLS LAST, employee_id ASC
OFFSET 0 ROWS FETCH NEXT 5 ROWS ONLY;

-- Page 2, skip first 5 rows and take next 5 rows.
SELECT employee_id, employee_name, salary
FROM   rownum_staff_lab
ORDER BY salary DESC NULLS LAST, employee_id ASC
OFFSET 5 ROWS FETCH NEXT 5 ROWS ONLY;

-- Page 3, skip 10 rows and take up to 5 rows.
SELECT employee_id, employee_name, salary
FROM   rownum_staff_lab
ORDER BY salary DESC NULLS LAST, employee_id ASC
OFFSET 10 ROWS FETCH NEXT 5 ROWS ONLY;
```

With static lab data:

| Page | Positions | Expected EMPLOYEE_IDs |
| --- | --- | --- |
| 1 | 1–5 | 105, 109, 103, 107, 111 |
| 2 | 6–10 | 112, 102, 104, 106, 101 |
| 3 | 11–15 | 108, 110 |

Compute offset in the application using:

```text
offset = (pageNumber - 1) * pageSize
```

Pages are 1-based, with `pageNumber >= 1` and `pageSize > 0`. Cap parameter values to prevent invalid input/overflow and protect the database from overly expensive queries.

### 9.3. Traditional `ROWNUM` Pagination

On Oracle 11g or when legacy syntax compatibility is required, use **three levels**:

```sql
SELECT employee_id, employee_name, salary, rn
FROM (
    SELECT ordered_staff.employee_id,
           ordered_staff.employee_name,
           ordered_staff.salary,
           ROWNUM AS rn
    FROM (
        SELECT employee_id, employee_name, salary
        FROM   rownum_staff_lab
        ORDER BY salary DESC NULLS LAST, employee_id ASC
    ) ordered_staff
    WHERE ROWNUM <= 10
)
WHERE rn > 5
ORDER BY rn;
```

This is **page 2 with page size 5**: accept up to 10 ordered rows in one branch, assign `rn=1..10` in the middle layer, and filter `rn > 5` in the outer layer. Outer column `rn` **is already an assigned column from the inner query**, distinct from a fresh outer `ROWNUM` pseudocolumn.

Diagram:

```text
Layer 1 (innermost):
    Sort all rows by salary DESC, employee_id ASC
                      │
                      ▼
Layer 2:
    Receive sorted rows, assign rn = ROWNUM
    WHERE ROWNUM <= :upper_bound   (offset + page_size)
                      │
                      ▼
Layer 3:
    WHERE rn > :lower_bound        (offset)
    ORDER BY rn
```

In real code, use validated bind variables `:upper_bound` and `:lower_bound`; never concatenate numbers from requests into SQL. Put the **upper** bound in the middle layer so you avoid fetching excessive rows only to discard them at the end.

### 9.4. Two Layers Fail If the Alias Is in the Wrong Scope

```sql
-- Wrong: cannot use alias rn created in SELECT
-- inside WHERE of the exact same query block.
SELECT ROWNUM AS rn, employee_id
FROM   rownum_staff_lab
WHERE  rn BETWEEN 6 AND 10;
```

In Oracle, a standard select-list alias cannot be referenced directly in `WHERE` of the same query block. You must create the alias in an **inner query** and filter it in an **outer query**.

## 10. Sort Order Must Be Specific Enough for Stable Pagination

### 10.1. Non-Unique Sort Orders Make Pages "Jump" Even on Static Data

With only:

```sql
ORDER BY salary DESC
```

the three employees earning 4500 tie. Oracle is under no obligation to place `103`, `107`, or `111` first. If a page boundary cuts across this group, calls for page 1 and page 2 can **duplicate or skip** employees because tie order is not guaranteed.

Fix with a **total order**:

```sql
ORDER BY salary DESC NULLS LAST, employee_id ASC
```

`employee_id` is a PK and unique, so on the **same data snapshot** every row has a deterministic position. When sorting by date, add the PK too:

```sql
ORDER BY hired_on DESC, employee_id DESC
```

### 10.2. Data Changing Between Pages Can Still Cause Drift

Even when sorting includes a unique tie-breaker key, `OFFSET` does not "freeze" a result set across multiple HTTP requests.

Suppose the client fetches page 1 of 5 rows. Before the client fetches page 2, a new employee with a very high salary is inserted at the top of the list. Existing rows shift down by one position, causing `OFFSET 5` to **repeat a row already seen on page 1**. Deleting a row near the top causes **skipped rows**.

This is **pagination under concurrent modifications**, distinct from the `ROWNUM` before-sort bug.

Mitigations depending on requirements:

- Have a **total ORDER BY** to make tie ordering deterministic.
- For large/rapidly changing feeds, consider **keyset/seek pagination**.
- If multiple pages must show the same point-in-time image, consider a **consistent snapshot** mechanism, such as querying at a fixed SCN/Flashback Query where privileges and undo retention allow, or another snapshot strategy.
- Accept that real-time browsing sees live changes; document API semantics clearly instead of promising "pages never duplicate" without snapshot control.

### 10.3. Keyset Pagination (Seek Method) by Date and PK

With `hired_on NOT NULL` and `employee_id PK`, sort by:

```sql
SELECT employee_id, employee_name, hired_on
FROM   rownum_staff_lab
ORDER BY hired_on DESC, employee_id DESC
FETCH FIRST 5 ROWS ONLY;
```

The client saves the keys of the **last row** in the result: `last_hired_on` and `last_employee_id`. Next page:

```sql
SELECT employee_id, employee_name, hired_on
FROM   rownum_staff_lab
WHERE  hired_on < :last_hired_on
   OR (hired_on = :last_hired_on
       AND employee_id < :last_employee_id)
ORDER BY hired_on DESC, employee_id DESC
FETCH FIRST 5 ROWS ONLY;
```

This cursor predicate selects rows **coming after** the previous page's last row in descending order. Bind variables `:last_hired_on` and `:last_employee_id` must come from the actual result with matching data types and timezone/precision for timestamps. When sort keys allow `NULL`, mix ASC/DESC directions, or filters change, the seek predicate must be adapted carefully; do not blindly copy this template for every ORDER BY.

**Keyset usually avoids skipping past a large offset**, though it does not create an immutable snapshot on its own and does not solve every anomaly if a record's sort key is updated between requests.

## 11. `ROW_NUMBER()`: When You Need True Ranked Numbering

Oracle provides the analytic function:

```sql
ROW_NUMBER() OVER (ORDER BY salary DESC NULLS LAST, employee_id ASC)
```

Unlike `ROWNUM`, `ROW_NUMBER()` **defines the numbering order right inside `OVER (ORDER BY ...)`**. It can also reset per group with `PARTITION BY`.

### 11.1. Assigning Ranks to Every Row

```sql
SELECT employee_id,
       employee_name,
       salary,
       ROW_NUMBER() OVER (
           ORDER BY salary DESC NULLS LAST, employee_id ASC
       ) AS rn
FROM   rownum_staff_lab
ORDER BY rn;
```

On the lab table, `rn=1` goes to `employee_id=105`, `rn=2` to `109`, `rn=3` to `103`, and so on.

**Two ORDER BY clauses serve two purposes:**

- `ORDER BY` inside `OVER` defines **how `rn` is computed**.
- Outer `ORDER BY rn` defines **the order in which rows are presented to the client**.

Without the outer `ORDER BY`, SQL output still must not be assumed to have a guaranteed display order just because an analytic function assigned numbers.

### 11.2. Top-N with an Analytic Function

```sql
SELECT employee_id, employee_name, salary, rn
FROM (
    SELECT employee_id,
           employee_name,
           salary,
           ROW_NUMBER() OVER (
               ORDER BY salary DESC NULLS LAST, employee_id ASC
           ) AS rn
    FROM   rownum_staff_lab
)
WHERE rn <= 5
ORDER BY rn;
```

The analytic function is computed in the inner query; the filter `rn <= 5` must sit in the outer query in this Oracle 19c pattern. Never place an analytic function directly in `WHERE` of the same query block, because analytic functions are evaluated at a later SQL processing stage.

### 11.3. Why Does `ROW_NUMBER` Still Need a Tie-Breaker?

With only:

```sql
ROW_NUMBER() OVER (ORDER BY salary DESC)
```

two employees earning 6000 must receive two distinct numbers, yet their relative order is left unspecified by the expression. When Top-N cuts across a tied group, which employee is kept can vary across runs. Add `employee_id` for a total order whenever **strictly N rows** are required.

`ROW_NUMBER()` vs. `RANK()`:

| SALARY | Rows in salary group | ROW_NUMBER (per row) | RANK | DENSE_RANK |
| ---: | ---: | --- | ---: | ---: |
| 6000 | 2 | 1, 2 | 1 | 1 |
| 4500 | 3 | 3, 4, 5 | 3 | 2 |
| 3200 | 1 | 6 | 6 | 3 |

If the question is "top three salary levels," `DENSE_RANK <= 3` differs from "first three employees" (`ROW_NUMBER <= 3`).

## 12. Top-N **Per Group**: A Problem Simple `ROWNUM` Cannot Solve

Requirement: **for each department, get the two highest-paid employees**. This is not a single global Top-2.

### 12.1. Wrong: One `ROWNUM` Across the Entire Query

```sql
SELECT dept_code, employee_id, employee_name, salary
FROM   rownum_staff_lab
WHERE  ROWNUM <= 2
ORDER BY dept_code, salary DESC;
```

This yields **at most two rows total**, not two rows per `dept_code`.

### 12.2. Right: `PARTITION BY dept_code`

```sql
SELECT dept_code,
       employee_id,
       employee_name,
       salary
FROM (
    SELECT dept_code,
           employee_id,
           employee_name,
           salary,
           ROW_NUMBER() OVER (
               PARTITION BY dept_code
               ORDER BY salary DESC NULLS LAST, employee_id ASC
           ) AS rn
    FROM   rownum_staff_lab
)
WHERE rn <= 2
ORDER BY dept_code, salary DESC NULLS LAST, employee_id ASC;
```

Oracle restarts numbering **from 1 for each department** because of `PARTITION BY dept_code`.

Expected result on the lab table:

| DEPT_CODE | EMPLOYEE_ID | SALARY | Reason |
| --- | ---: | ---: | --- |
| FIN | 109 | 6000 | Rank 1 FIN |
| FIN | 102 | 3000 | Rank 2 FIN |
| HR | 111 | 4500 | Rank 1 HR |
| HR | 112 | 3200 | Rank 2 HR |
| IT | 105 | 6000 | Rank 1 IT |
| IT | 103 | 4500 | Rank 2 IT |
| OPS | 107 | 4500 | Rank 1 OPS |
| OPS | 106 | 2500 | Rank 2 OPS |

### 12.3. Top Two **Salary Levels** Per Group, Keeping Ties

If business logic wants "every employee in a department's **two highest salary levels**," use `DENSE_RANK`:

```sql
SELECT dept_code, employee_id, employee_name, salary
FROM (
    SELECT dept_code,
           employee_id,
           employee_name,
           salary,
           DENSE_RANK() OVER (
               PARTITION BY dept_code
               ORDER BY salary DESC NULLS LAST
           ) AS salary_level_rank
    FROM rownum_staff_lab
)
WHERE salary_level_rank <= 2
ORDER BY dept_code, salary DESC NULLS LAST, employee_id;
```

The number of rows per department can be **greater than 2** when ties occur. That is an intentional semantic choice, not accidental extra rows.

## 13. Top-N Over JOIN Data: The Limit Counts **Output Rows**, Not Parents

Suppose there are two tables:

```text
ORDERS(order_id, created_at, customer_id)
ORDER_ITEMS(order_id, line_no, sku, quantity)
```

One order can have many items. The SQL:

```sql
SELECT o.order_id, o.created_at, i.line_no, i.sku
FROM   orders o
JOIN   order_items i ON i.order_id = o.order_id
ORDER BY o.created_at DESC, o.order_id DESC
FETCH FIRST 10 ROWS ONLY;
```

fetches **10 rows of the JOIN**, **not 10 orders**. If the newest order has 15 items, the first ten rows may belong to **just one order**, truncating the remaining items of that same order.

If the requirement is **the 10 newest orders together with all of their items**, pick the parents first and then JOIN:

```sql
WITH latest_orders AS (
    SELECT o.order_id, o.created_at
    FROM   orders o
    ORDER BY o.created_at DESC, o.order_id DESC
    FETCH FIRST 10 ROWS ONLY
)
SELECT o.order_id, o.created_at, i.line_no, i.sku
FROM   latest_orders o
LEFT JOIN order_items i
       ON i.order_id = o.order_id
ORDER BY o.created_at DESC, o.order_id DESC, i.line_no;
```

The CTE guarantees the **10 parent orders** are selected in order. The final output can contain **more than 10 rows** due to multiple items per order. `LEFT JOIN` also retains orders with zero items if business rules want them displayed.

**General rule:** Clarify "N of what?" — N joined rows, N parent entities, N distinct groups, or N elements within each group. Placing `FETCH`/`ROWNUM` at the wrong level of granularity easily produces wrong results.

## 14. Top-N After `GROUP BY` and Aggregates

Requirement: "get the three departments with the highest total payroll":

```sql
SELECT dept_code,
       SUM(salary) AS salary_total
FROM   rownum_staff_lab
GROUP BY dept_code
ORDER BY salary_total DESC NULLS LAST, dept_code ASC
FETCH FIRST 3 ROWS ONLY;
```

This is **Top-3 groups after aggregation**, not taking 3 employees first and aggregating afterward.

Contrast with:

```sql
-- WRONG for Top-3 departments by total salary:
SELECT dept_code, SUM(salary) AS salary_total
FROM (
    SELECT dept_code, salary
    FROM   rownum_staff_lab
    WHERE  ROWNUM <= 3
)
GROUP BY dept_code
ORDER BY salary_total DESC;
```

The wrong query only aggregates three arbitrarily fetched employees instead of summing across whole departments.

Logically, the right flow is:

```text
Employee source rows
        │
        ▼
GROUP BY dept_code, SUM(salary)
        │
        ▼
ORDER BY salary_total DESC
        │
        ▼
FETCH FIRST 3 ROWS ONLY
```

`HAVING` (if present) filters groups after aggregation before Top-N is applied. Once again, **which query block holds the limit** determines the meaning.

## 15. `DISTINCT`, `UNION`, and Result Limiting

### 15.1. `DISTINCT` Must Deduplicate All Distinct Values Before Top-N

To get "the three highest distinct salary levels":

```sql
SELECT DISTINCT salary
FROM   rownum_staff_lab
WHERE  salary IS NOT NULL
ORDER BY salary DESC
FETCH FIRST 3 ROWS ONLY;
```

Result: `6000, 4500, 3200`, not three employees. The syntax and semantics of `DISTINCT` resolve duplicates before row limiting at that result level.

Do not write:

```sql
-- Picks 3 arbitrary rows first, then applies DISTINCT:
SELECT DISTINCT salary
FROM (
    SELECT salary
    FROM   rownum_staff_lab
    WHERE  ROWNUM <= 3
);
```

expecting the Top-3 distinct salaries: the subquery content was already truncated in access order.

### 15.2. `UNION ALL` and Per-Branch vs. Overall Limits

Suppose there are two sources: `current_orders` and `archived_orders`. Two distinct requirements:

1. **Top-10 across the union of both sources**: `UNION ALL` inside a CTE/inline view, then **ORDER BY/FETCH on the outer union**.
2. **Top-10 from each source, then combined up to 20 rows**: apply Top-N **separately inside each branch** before `UNION ALL`.

Oracle does not guarantee that an `ORDER BY` placed inside set-operator branches dictates final output order. The final overall `ORDER BY` must sit on the outer query block. When using `FETCH` in a branch, wrap each branch cleanly as an inline view/CTE and apply outer `ORDER BY` as needed.

## 16. Using `ROWNUM` to Stop Early: When Is It Appropriate?

### 16.1. Checking Whether Any Matching Row Exists

```sql
-- At most one row, with no requirement to be "first" in business order.
SELECT employee_id
FROM   rownum_staff_lab
WHERE  dept_code = 'IT'
AND    ROWNUM = 1;
```

Appropriate if the application only wants to know whether **at least one IT row exists**. Depending on the query, `EXISTS` in another statement also expresses existence clearly:

```sql
SELECT CASE WHEN EXISTS (
    SELECT 1
    FROM   rownum_staff_lab
    WHERE  dept_code = 'IT'
) THEN 'Y' ELSE 'N' END AS exists_it
FROM dual;
```

`ROWNUM <= 1` can stop after one matching row. However, if you only need a boolean or are inside complex query logic, `EXISTS` usually states intent more clearly.

### 16.2. Taking a Quick Sample to Inspect Columns

```sql
SELECT employee_id, dept_code, salary
FROM   rownum_staff_lab
WHERE  ROWNUM <= 10;
```

This is an **arbitrary sample in access-path order**, not a **statistically random sample**. It can be biased if data is stored/clustered by some attribute. To get a random or statistically valid sample, use proper sampling mechanisms rather than `ROWNUM`.

### 16.3. Limiting Rows in Updates/Deletes: Warning

```sql
-- DO NOT run on real tables just to test:
-- DELETE FROM some_table WHERE ROWNUM <= 100;
```

This statement can delete **any 100 rows Oracle encounters first**, with no guarantee they are the oldest, newest, or smallest-ID rows. For batch maintenance, select a deterministic set of **business keys** or `ROWID`s using an ordered strategy and appropriate locking/concurrency control, then apply controlled DML. Never put an `ORDER BY` on a conceptual SELECT and assume a `DELETE` automatically respects that priority.

## 17. `ORDER BY` Issues with NULL, NLS/Collation, and Expressions

### 17.1. `NULLS FIRST` and `NULLS LAST`

In standard Oracle behavior:

- `ORDER BY salary ASC` defaults to `NULLS LAST`.
- `ORDER BY salary DESC` defaults to `NULLS FIRST`.

Because the lab table has `salary = NULL` (employee `110`), writing:

```sql
ORDER BY salary DESC
```

puts the person **with no salary value** at the very top. If the goal is "highest salary, and NULL is not a high salary," write it explicitly:

```sql
ORDER BY salary DESC NULLS LAST, employee_id ASC
```

NULL does not equal `0`. `NVL(salary, 0)` changes semantics and can affect index usage; never substitute 0 for NULL just to avoid writing `NULLS LAST` if missing salary does not mean 0.

### 17.2. Sorting Strings by NLS/Collation

When using `ORDER BY employee_name`, order can depend on collation, case sensitivity, and related settings. If pagination must be deterministic, pin down the collation required by the application and add a unique tie-breaker key. Never assume unaccented/accented Vietnamese strings always sort identically across all Oracle environments.

### 17.3. Sorting by Expression

```sql
SELECT employee_id, salary
FROM   rownum_staff_lab
ORDER BY NVL(salary, -1) DESC, employee_id ASC
FETCH FIRST 5 ROWS ONLY;
```

This syntax is valid if NULL should be treated as `-1` during sorting, though semantics differ from `NULLS LAST` if salary can ever be below -1. Expressions in ORDER BY can also affect index/optimizer choices, so pick them based on business semantics rather than merely "it compiles."

## 18. Performance: `STOPKEY` Optimizes Execution Without Changing SQL Meaning

For Top-N limits, the Oracle optimizer can recognize that **it does not need to materialize the entire sorted result** if it can locate the first N rows efficiently.

Operations you may encounter in execution plans:

| Plan operation | Rough interpretation |
| --- | --- |
| `COUNT STOPKEY` | Stops accepting rows from a source once the count limit is reached |
| `SORT ORDER BY STOPKEY` | Optimized sort when only the top N rows in order are needed |
| `WINDOW SORT PUSHED RANK` | Optimized analytic ranking and filtering in certain plans |
| `INDEX RANGE SCAN` / `INDEX FULL SCAN DESCENDING` | Exploits index order when applicable |
| `SORT ORDER BY` | Full sort when required; can consume memory/temp and I/O |

**Do not assume every `FETCH FIRST 10` is cheap:** If a query must join many tables, aggregate, or evaluate expensive expressions before knowing the Top-10, the database may still process vast amounts of data. An index aligned with `WHERE` and `ORDER BY` can help substantially, but you must measure the actual execution plan, selectivity, cardinality, statistics, distribution, and bind values.

### 18.1. A Buggy Query Can Look "Coincidentally Right" After Adding an Index

Suppose an index exists:

```sql
-- Illustrative DDL only; do not blindly create in production.
-- CREATE INDEX staff_salary_idx
--   ON rownum_staff_lab(salary DESC, employee_id ASC);
```

If the optimizer uses the pre-sorted index access path, the buggy `WHERE ROWNUM <= 5 ORDER BY salary DESC` might happen to return the five highest earners in some scenarios. Yet Oracle **never promises that access path**. Later, if the optimizer picks a full scan, the result changes.

**Semantics must be right independently of the execution plan.** Indexes exist to optimize a **correct** SQL statement.

### 18.2. Large `OFFSET` Can Be Expensive

```sql
SELECT employee_id, hired_on
FROM   rownum_staff_lab
ORDER BY hired_on DESC, employee_id DESC
OFFSET 100000 ROWS FETCH NEXT 20 ROWS ONLY;
```

Logically, Oracle must identify and skip a large number of leading rows. Even with an index, larger offsets generally increase query cost and can be unsuitable for large-scale feeds. **Keyset pagination** is often helpful when users only step to the "next page" along a cursor sort key.

### 18.3. `ROWNUM` Can Affect Optimizer Transformations

`ROWNUM` inside a query block can prevent or alter how Oracle **merges inline views**, pushes predicates, or transforms queries. Therefore, when tuning performance, never arbitrarily move `ROWNUM` across query block boundaries just to shorten the SQL. Moving it can **change which rows are limited**, not just the plan.

## 19. `row_limiting_clause` Restrictions in Oracle Database 19c

The Oracle 19c documentation notes several important restrictions when using `OFFSET/FETCH`:

1. **Cannot be combined directly with `FOR UPDATE`** in the same `SELECT` per Oracle 19c restrictions. On newer releases, check the documentation because capabilities can evolve.
2. The select list cannot contain sequence pseudocolumns `CURRVAL` or `NEXTVAL` when using `row_limiting_clause`.
3. A materialized view whose defining query contains `row_limiting_clause` is not eligible for **incremental refresh** per the restrictions documented in 19c.
4. If the select list contains **two columns with the same name**, using `row_limiting_clause` can raise `ORA-00918`. Give output columns distinct aliases.

Example of the duplicate output column error:

```sql
-- Can raise ORA-00918 when the select list has duplicate column names.
SELECT a.id, b.id
FROM   parent_table a
JOIN   child_table b ON b.parent_id = a.id
ORDER BY a.id
FETCH FIRST 10 ROWS ONLY;

-- Use unique aliases:
SELECT a.id AS parent_id,
       b.id AS child_id
FROM   parent_table a
JOIN   child_table b ON b.parent_id = a.id
ORDER BY a.id
FETCH FIRST 10 ROWS ONLY;
```

`PARENT_TABLE`/`CHILD_TABLE` are illustrative names, not part of the lab dataset. These restrictions apply to the **19c SQL Language Reference**; do not assume a 1-to-1 match for Oracle AI Database 26ai or future releases.

## 20. Common Mistakes: Quick Reference Table

| Intent | Buggy SQL or symptom | Root cause | Correct approach |
| --- | --- | --- | --- |
| Get Top-10 by salary | `WHERE ROWNUM <= 10 ORDER BY salary DESC` | Limited before sorting in the same query block | Inline view sort + outer `ROWNUM`, or `FETCH FIRST` |
| Get page 2 | `WHERE ROWNUM > 10` | `ROWNUM=1` for first row is rejected forever | `OFFSET 10` or `rn` alias in outer query |
| Get the 5th row | `WHERE ROWNUM = 5` | No row ever lets `ROWNUM` reach 5 | `ROW_NUMBER` after sort or `OFFSET 4 FETCH NEXT 1` |
| Top-3 per department | `WHERE ROWNUM <= 3` | Only three rows across the whole query | `ROW_NUMBER OVER(PARTITION BY ... ORDER BY...)` |
| "Top 3 salary levels" | `ROW_NUMBER <= 3` | Counts people, not distinct salary levels | `DENSE_RANK` by salary |
| Strictly 3 rows when ties exist at cutoff | `FETCH FIRST 3 ROWS ONLY` | `ONLY` cuts off ties | `WITH TIES` on the exact tie key |
| `WITH TIES` still returns only 3 people | `ORDER BY salary DESC, employee_id` | PK makes every sort key unique | To keep salary ties, sort tie key by salary only |
| Highest salary puts NULL employee first | `ORDER BY salary DESC` | DESC defaults to NULLS FIRST | `ORDER BY salary DESC NULLS LAST` |
| Page shows duplicate/missing rows on static data | `ORDER BY salary DESC` | Duplicate salaries, no tie-breaker | Add a unique key to ORDER BY |
| Page duplicates when new INSERTs arrive | `OFFSET` across multiple requests | Row positions shift between requests | Keyset pagination or consistent snapshot |
| Get 10 newest orders, but see only one order | `JOIN ORDER_ITEMS ... FETCH FIRST 10 ROWS` | Limits joined rows, not parent orders | Select Top-N parents first, then join items |
| Fast yet wrong after optimizer change | Buggy query happened to use sorted index | Relied on access path | Fix SQL semantics first, then tune indexes |
| `ORA-00918` with `FETCH` | Select list has duplicate column names | 19c row limiting clause restriction | Use unique output aliases |
| `ORA-00933` or syntax error on older Oracle | Using `FETCH FIRST` on 11g | Version lacks `row_limiting_clause` | Traditional inline view + `ROWNUM` |

## 21. Reading Business Requirements to Pick the Right Technique

Before writing the SQL, ask five questions:

1. **N of what?** N rows, N parent entities, N groups, N ranks, or N rows per group?
2. **Ranked by what criterion?** Salary, creation date, total revenue, priority, or multiple criteria?
3. **What happens on ties?** Cut strictly at N rows, or return every tied row at the boundary?
4. **Must results stay stable across calls?** Is there a unique tie-breaker? Can data mutate between pages?
5. **Which Oracle release is running?** 11g needs `ROWNUM`/analytic patterns; 12c+ can use `OFFSET/FETCH` when suitable.

Tool selection matrix:

| Requirement | Preferred pattern |
| --- | --- |
| Up to N arbitrary rows, order irrelevant | `WHERE ROWNUM <= :n` |
| Global Top-N by ORDER BY, Oracle 12c+ | `ORDER BY ... FETCH FIRST :n ROWS ONLY` |
| Global Top-N on 11g | `SELECT ... FROM (SELECT ... ORDER BY ...) WHERE ROWNUM <= :n` |
| Page k on Oracle 12c+ | `ORDER BY unique_key ... OFFSET :offset ROWS FETCH NEXT :size ROWS ONLY` |
| Pagination on Oracle 11g | Three-level query with `ROWNUM AS rn` |
| Sequential traversal of a large feed by cursor | Keyset/seek pagination |
| Top N rows within each department | `ROW_NUMBER() OVER (PARTITION BY dept ORDER BY ...)` |
| All tied rows at Top-N cutoff | `FETCH ... WITH TIES` or appropriate `RANK` |
| Top-N after aggregation | `GROUP BY ... ORDER BY aggregate DESC FETCH FIRST N` |
| N parents with all child rows | Select Top-N parents in inner CTE, then JOIN outside |

## 22. Hands-On Comparison Exercises

> Use `ROWNUM_STAFF_LAB` created in section 4. All `SELECT` queries are read-only. Avoid drawing conclusions from a **single coincidental run** of a buggy query; compare using semantics and verified output from SQL with explicit `ORDER BY`.

### Exercise A — Comparing Buggy vs. Correct Queries

```sql
-- A1: Does NOT guarantee Top-5 highest salaries.
SELECT employee_id, salary
FROM   rownum_staff_lab
WHERE  ROWNUM <= 5
ORDER BY salary DESC NULLS LAST, employee_id;

-- A2: Correct Top-5 via inline view + outer ROWNUM.
SELECT employee_id, salary
FROM (
    SELECT employee_id, salary
    FROM   rownum_staff_lab
    ORDER BY salary DESC NULLS LAST, employee_id
)
WHERE ROWNUM <= 5;

-- A3: Correct Top-5 via FETCH.
SELECT employee_id, salary
FROM   rownum_staff_lab
ORDER BY salary DESC NULLS LAST, employee_id
FETCH FIRST 5 ROWS ONLY;
```

**Key takeaway:** A2 and A3 select IDs `105, 109, 103, 107, 111`; A1 **makes no promise** to return those rows, even if it happens to match under the current plan.

### Exercise B — `ROWNUM > 1`

```sql
SELECT employee_id
FROM   rownum_staff_lab
WHERE  ROWNUM > 1;
```

Predict before running: **0 rows**, even though the table has 12 rows. Then explain why Oracle never increments ROWNUM to 2 when no row passes the first condition.

### Exercise C — 5-Row Pagination

```sql
SELECT employee_id, salary
FROM   rownum_staff_lab
ORDER BY salary DESC NULLS LAST, employee_id
OFFSET 5 ROWS FETCH NEXT 5 ROWS ONLY;
```

Prediction: `112, 102, 104, 106, 101`.

Next, rewrite the SQL into the three-level `ROWNUM` pattern and verify the **row set**, not merely the print order.

### Exercise D — Ties

```sql
SELECT employee_id, salary
FROM   rownum_staff_lab
ORDER BY salary DESC NULLS LAST
FETCH FIRST 3 ROWS WITH TIES;
```

Returns **5 rows** because the third row has salary 4500 and two other employees share that salary. Try adding `employee_id` to ORDER BY and explain why the result changes.

### Exercise E — Top-2 Per Group

```sql
SELECT dept_code, employee_id, salary
FROM (
    SELECT dept_code,
           employee_id,
           salary,
           ROW_NUMBER() OVER (
               PARTITION BY dept_code
               ORDER BY salary DESC NULLS LAST, employee_id
           ) AS rn
    FROM rownum_staff_lab
)
WHERE rn <= 2
ORDER BY dept_code, rn;
```

Check total rows: there are 4 departments, each with at least 2 employees → **8 rows** total. This cannot be achieved with a single `ROWNUM <= 2` in a shared query block.

### Exercise F — Top-3 Distinct Salary Levels

```sql
SELECT DISTINCT salary
FROM   rownum_staff_lab
WHERE  salary IS NOT NULL
ORDER BY salary DESC
FETCH FIRST 3 ROWS ONLY;
```

Prediction: `6000, 4500, 3200`. Next, try analytic `DENSE_RANK` to return **all employees** in these top three salary levels and compare row counts.

### Exercise G — Clean Up the Lab After Finishing

```sql
-- ONLY run if you created this table in a lab schema
-- and no longer need the data. DDL cannot be rolled back with ROLLBACK.
DROP TABLE rownum_staff_lab PURGE;
```

Never run `DROP TABLE` on a real application schema. If you want to keep the table for later practice, skip this step.

## 23. Review Questions

**1.** Is the following guaranteed to return the three highest-paid employees? Why or why not?

```sql
SELECT employee_id, salary
FROM   employees
WHERE  ROWNUM <= 3
ORDER BY salary DESC;
```

**2.** Which rows does `WHERE ROWNUM = 5` return if there are 100 candidate rows?

**3.** Why does `SELECT ... FROM (SELECT ... ORDER BY salary DESC) WHERE ROWNUM <= 3` have a different meaning from question 1?

**4.** With `ORDER BY salary DESC` where three employees tie in salary at the cutoff, how do you get **strictly 3 deterministic rows**? How do you **include all tied rows** instead?

**5.** Why can `FETCH FIRST 3 ROWS WITH TIES` return strictly 3 rows after adding a primary key to the end of ORDER BY?

**6.** With `ORDER BY salary DESC`, can a row with `salary=NULL` appear at the top? Write how to fix it.

**7.** To fetch 5 rows on page 3 with page size = 5, what must `OFFSET` equal?

**8.** Does a query joining `ORDERS` with `ORDER_ITEMS` followed by `FETCH FIRST 10 ROWS ONLY` return "10 orders" or "10 joined rows"?

**9.** An API uses `ORDER BY created_at DESC, id DESC OFFSET 20`. Between calls, a new row is inserted at the top of the feed; can pages repeat rows even with a unique tie-breaker?

**10.** State the difference between `ROWNUM` and `ROW_NUMBER() OVER (PARTITION BY dept_code ORDER BY salary DESC)`.

**11.** To get the top 3 departments by total salary, should `FETCH` come before or after `GROUP BY`/`ORDER BY SUM(salary)`?

**12.** Can you use `SELECT ... FOR UPDATE FETCH FIRST 5 ROWS ONLY` directly in Oracle 19c?

<details>
<summary>Suggested answers</summary>

1. **No.** `ROWNUM` limits rows in access-path order within the same query block before the final `ORDER BY` sorts the picked rows.
2. **No rows.** The first candidate row gets ROWNUM 1 and fails; every subsequent candidate row becomes the first candidate again, still getting ROWNUM 1.
3. The inner query's `ORDER BY` establishes the order first, and `ROWNUM` in the outer query block selects the first three rows from the sorted result.
4. **Strictly 3 rows:** add a PK tie-breaker and use `FETCH FIRST 3 ROWS ONLY`. **Include ties:** use `WITH TIES` sorted only by the tie criterion, or the appropriate `RANK` function.
5. `WITH TIES` compares **all ORDER BY expressions**; a unique PK prevents any other row from matching the full sort-key tuple.
6. Yes: under DESC, NULLs sort first by default. Use `ORDER BY salary DESC NULLS LAST, employee_id`.
7. `OFFSET 10`, skipping the first two pages (2 × 5).
8. **10 joined rows**, which may belong to fewer than 10 orders. Select Top-N orders first, then join items afterward.
9. **Yes.** A total order resolves ties; it does not freeze an immutable snapshot across data mutations. Use keyset pagination or snapshots if required.
10. `ROWNUM` is a pseudocolumn numbering rows as selected in a query block; `ROW_NUMBER` is an analytic ranking by ORDER BY that can reset per `PARTITION BY` group.
11. After grouping, summing, and sorting by total salary, then limit to Top-3. Never take the first three employees before aggregating.
12. **No**, per the `row_limiting_clause` restrictions in Oracle 19c; design an alternative query/locking approach and check your active release.

</details>

## 24. Official Oracle Documentation

1. [Oracle Database 19c SQL Language Reference — ROWNUM Pseudocolumn](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ROWNUM-Pseudocolumn.html): definition of `ROWNUM`, the bug when `ORDER BY` is in the same query block, inline view Top-N pattern, and why `ROWNUM > 1` returns no rows.
2. [Oracle Database 19c SQL Language Reference — SELECT (`row_limiting_clause`)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): `OFFSET`, `FETCH FIRST/NEXT`, `ONLY`, `WITH TIES`, deterministic ordering, and restrictions with `FOR UPDATE`/sequences/select lists.
3. [Oracle Database 19c SQL Language Reference — ROW_NUMBER](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ROW_NUMBER.html): analytic numbering, `OVER (ORDER BY...)`, and Top-N per department examples.
4. [Oracle Database 19c SQL Language Reference — RANK](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/RANK.html): ranking with gaps after ties.
5. [Oracle Database 19c SQL Language Reference — DENSE_RANK](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/DENSE_RANK.html): dense ranking without gaps for equal-value groups.
6. [Oracle Database 19c SQL Language Reference — Analytic Functions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Analytic-Functions.html): logical execution position of analytic functions and `PARTITION BY` scope.
7. [Oracle Database 19c SQL Language Reference — Using Subqueries](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Using-Subqueries.html): inline views and nested query blocks.
8. [Oracle Database 19c Data Warehousing Guide — Limiting SQL Rows](https://docs.oracle.com/en/database/oracle/oracle-database/19/dwhsg/): Top-N patterns, offset pagination, and analytic ranking styles.

**Short mnemonic:** `ROWNUM` in the same query block as `ORDER BY` can **pick rows first and sort later**; for true Top-N, use an **inline view with ORDER BY + outer ROWNUM**, or **ORDER BY ... FETCH FIRST N ROWS ONLY** on Oracle 12c+. When you need **ranked numbering overall or per group**, use **ROW_NUMBER() OVER (...)**. In every case, clarify **which set's N rows you want, whether the ordering is unique enough, what the tie policy is, and whether data can mutate between pagination calls**.
