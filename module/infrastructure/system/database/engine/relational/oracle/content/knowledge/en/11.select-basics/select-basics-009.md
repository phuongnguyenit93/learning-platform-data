# OFFSET, FETCH FIRST, WITH TIES, and Pagination in Oracle Database

When a table holds millions of records, applications rarely load the entire result set at once. Instead, the UI displays one page at a time: the first 20 orders, then the next 20 orders. Oracle supports the **row limiting clause** with `OFFSET` and `FETCH FIRST/NEXT` to limit query results; the `WITH TIES` option retains all rows tied at the cutoff boundary. When compatibility with older releases is required, `ROWNUM` or the analytic function `ROW_NUMBER()` can be used.

However, pagination is only accurate when you understand sort ordering. A query with `FETCH FIRST 20 ROWS ONLY` and no `ORDER BY` does not guarantee returning the same 20 rows across runs. Even with `ORDER BY`, if the sort columns are not unique, tied rows can shift positions between runs. With continuously changing data, a large `OFFSET` can also force the database to read and skip many rows before returning the requested page.

This lesson belongs to the **SELECT Basics** chapter in Oracle Database. We will cover syntax, the meaning of each clause, handling ties, counting total rows, offset vs. keyset pagination, and alternatives for legacy systems.

After this lesson, you will be able to:

- Use `FETCH FIRST n ROWS ONLY` and `OFFSET n ROWS FETCH NEXT m ROWS ONLY`.
- Distinguish `ONLY` from `WITH TIES` and understand that ties are evaluated across the entire `ORDER BY`.
- Design deterministic sort orders using a unique key as a tie-breaker when needed.
- Produce paginated results with a total row count using `COUNT(*) OVER()`.
- Choose between offset pagination and keyset/seek pagination based on UI requirements.
- Use `ROWNUM` or `ROW_NUMBER()` when working with older Oracle releases.
- Recognize the impact of concurrent data changes between requests, NULLs, indexes, bind variables, and performance.

> **Version scope:** `OFFSET ... FETCH` and `FETCH FIRST ... WITH TIES` are `row_limiting_clause` syntax introduced in Oracle Database 12c Release 1 (12.1). Examples use modern Oracle SQL; if deploying on 11g or older compatibility targets, see the `ROWNUM`/`ROW_NUMBER()` section. Lab SQL uses only tables you create in a practice schema.

## 1. Why Limit and Paginate Results?

Suppose an `ORDERS` table has 2 million orders. The UI needs to display 25 orders per page, newest first. Instead of fetching 2 million rows and slicing in the application, we ask the database to return only the required slice:

~~~sql
SELECT order_id, customer_id, created_at, total_amount
FROM orders
ORDER BY created_at DESC, order_id DESC
OFFSET 0 ROWS
FETCH NEXT 25 ROWS ONLY;
~~~

This query asks to skip the first 0 rows and fetch at most the next 25 rows in the sorted order.

Terminology:

| Term | Meaning |
| --- | --- |
| **Result set** | The set of rows produced by a SELECT statement after applying filters and query processing |
| **ORDER BY** | Defines row ordering before limiting |
| **OFFSET** | Number of leading rows in the ordered result to skip |
| **FETCH FIRST/NEXT** | Maximum number of rows to retrieve next |
| **ONLY** | Stop at the requested row count |
| **WITH TIES** | Include additional rows whose sort values tie with the last row of the fetched slice |
| **Pagination** | Splitting results into pages so an application loads data on demand |

A page is not a fixed physical chunk of a table. It is **a slice of a query result at a point in time**, under specific filters, sort order, and data state.

### 1.1. Conceptual Processing Flow

~~~text
FROM / JOIN
    |
    v
WHERE
    |
    v
GROUP BY / HAVING (if any)
    |
    v
SELECT expressions
    |
    v
ORDER BY
    |
    v
OFFSET: skip N rows
    |
    v
FETCH: take at most M rows
    |
    +--> ONLY: stop at M
    |
    +--> WITH TIES: also include rows tied with the last row
~~~

This is an intuitive model for reading SQL, not a full description of the optimizer's physical execution order. Oracle can choose different execution plans as long as it preserves the statement's result semantics.

## 2. `FETCH FIRST ... ROWS ONLY`

### 2.1. Fetching the First N Rows

Simple syntax:

~~~sql
SELECT order_id, total_amount
FROM orders
ORDER BY total_amount DESC
FETCH FIRST 5 ROWS ONLY;
~~~

Oracle sorts by `TOTAL_AMOUNT` descending and returns at most 5 rows. Both `FIRST` and `NEXT` keywords can be used in the row limiting clause:

~~~sql
-- Two equivalent forms when there is no OFFSET:
SELECT order_id
FROM orders
ORDER BY order_id
FETCH FIRST 10 ROWS ONLY;

SELECT order_id
FROM orders
ORDER BY order_id
FETCH NEXT 10 ROWS ONLY;
~~~

`FIRST` reads naturally when taking initial rows; `NEXT` is commonly used after `OFFSET` when taking the next slice. They do not represent two different pagination mechanisms.

### 2.2. Without ORDER BY There Is No Guaranteed Business Order

~~~sql
SELECT order_id, total_amount
FROM orders
FETCH FIRST 5 ROWS ONLY;
~~~

This statement runs, but there is no guarantee which 5 rows are returned stably. Oracle does not guarantee row order without `ORDER BY`. Order can vary due to execution plans, indexes, parallel execution, data mutations, or other runtime factors.

Even if a table has a primary key, that **does not mean SELECT automatically returns rows in primary-key order**. To get the orders with the smallest IDs:

~~~sql
SELECT order_id, total_amount
FROM orders
ORDER BY order_id
FETCH FIRST 5 ROWS ONLY;
~~~

### 2.3. Fetching a Single Row

~~~sql
SELECT employee_id, last_name, salary
FROM employees
ORDER BY salary DESC, employee_id
FETCH FIRST 1 ROW ONLY;
~~~

The result is one employee with the highest salary; if multiple people tie on salary, `EMPLOYEE_ID` serves as the secondary sort key to pick one row deterministically.

In Oracle, the following statement is also valid:

~~~sql
SELECT employee_id, last_name
FROM employees
ORDER BY employee_id
FETCH FIRST ROW ONLY;
~~~

When the count is omitted, Oracle defaults to one row. In application code, explicitly writing `FETCH FIRST 1 ROW ONLY` is often clearer.

### 2.4. Fetching by Percentage

Oracle also supports `PERCENT`:

~~~sql
SELECT employee_id, salary
FROM employees
ORDER BY salary DESC
FETCH FIRST 10 PERCENT ROWS ONLY;
~~~

This query requests roughly 10% of the sorted result rows according to Oracle's rounding/row-count rules. This is a proportional limit on the result set, not standard fixed-size pagination. With `PERCENT`, the number of returned rows shifts as the total matching row count changes.

For UIs with pages 1, 2, 3..., `FETCH NEXT :page_size ROWS ONLY` is generally more appropriate than `PERCENT`.

## 3. `OFFSET ... FETCH NEXT ... ROWS ONLY`

### 3.1. Row-Count Pagination Syntax

General template:

~~~sql
SELECT select_list
FROM table_name
WHERE condition
ORDER BY sort_expression
OFFSET offset_rows ROWS
FETCH NEXT fetch_rows ROWS ONLY;
~~~

Where:

- `offset_rows` is the number of rows to skip in the ordered result.
- `fetch_rows` is the maximum number of rows to fetch after skipping.
- `ROWS` can be written `ROW` when the count is one; using `ROWS` consistently improves readability.
- `OFFSET 0 ROWS` means start from the first row.
- `FETCH NEXT 20 ROWS ONLY` takes at most the next 20 rows.

Example for page 1 and page 2 with page size 20:

~~~sql
-- Page 1: skip 0, take 20.
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
OFFSET 0 ROWS FETCH NEXT 20 ROWS ONLY;

-- Page 2: skip 20, take 20.
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
OFFSET 20 ROWS FETCH NEXT 20 ROWS ONLY;
~~~

Page 3 uses `OFFSET 40 ROWS`; page 4 uses `OFFSET 60 ROWS`.

### 3.2. Computing Offset from Page Number

If page numbers start at 1:

\[
\text{offset} = (\text{page number} - 1) \times \text{page size}
\]

Example with page size 25:

| Page | Offset | Fetch |
| ---: | ---: | ---: |
| 1 | 0 | 25 |
| 2 | 25 | 25 |
| 3 | 50 | 25 |
| 4 | 75 | 25 |
| 5 | 100 | 25 |

The application should validate `page_number` and `page_size`:

- Pages usually start at 1; reject 0 or negative values per API rules.
- Cap `page_size` with a maximum limit to prevent requests from loading excessive data.
- Compute offset using a sufficiently large integer type to avoid overflow on deep page requests.
- Never concatenate user values directly into SQL; use bind variables when supported by the driver and SQL statement.

### 3.3. Bind Variables for Offset and Page Size

Example in SQL*Plus or bind-capable tools:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE status = :status
ORDER BY created_at DESC, order_id DESC
OFFSET :offset_rows ROWS
FETCH NEXT :page_size ROWS ONLY;
~~~

`:status`, `:offset_rows`, and `:page_size` are bind variables. In JDBC, supply values via `PreparedStatement` instead of string concatenation:

~~~java
String sql = """
    SELECT order_id, created_at, total_amount
    FROM orders
    WHERE status = ?
    ORDER BY created_at DESC, order_id DESC
    OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, status);
    ps.setInt(2, offset);
    ps.setInt(3, pageSize);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // map row
        }
    }
}
~~~

This example uses modern Oracle JDBC supporting the row limiting clause and positional binds. Test against your specific driver/ORM. Bind variables protect parameter values and encourage cursor sharing; they **do not replace business validation**: the application must still bound offset/page size and reject negative or excessive values per API policy.

### 3.4. Zero Rows Returned When Offset Exceeds Results

Suppose a query has only 73 matching rows and page size is 20:

| Page | Offset | Actual rows returned |
| ---: | ---: | ---: |
| 1 | 0 | 20 |
| 2 | 20 | 20 |
| 3 | 40 | 20 |
| 4 | 60 | 13 |
| 5 | 80 | 0 |

Page 5 returning empty is not an error; it is the natural outcome of the limit. The UI should rely on total row count or check empty pages to handle Next/Previous controls.

## 4. `WITH TIES`: Retaining Tied Rows

### 4.1. The Issue with ONLY

Suppose employees are ranked by salary:

| Employee | Salary |
| --- | ---: |
| An | 90,000 |
| Bình | 85,000 |
| Chi | 85,000 |
| Dũng | 80,000 |

Query:

~~~sql
SELECT employee_name, salary
FROM employees
ORDER BY salary DESC
FETCH FIRST 2 ROWS ONLY;
~~~

Returns only two rows. When multiple people tie at the second position's salary, a tied employee is excluded because the limit stops at two rows.

### 4.2. Using WITH TIES

~~~sql
SELECT employee_name, salary
FROM employees
ORDER BY salary DESC
FETCH FIRST 2 ROWS WITH TIES;
~~~

The result includes:

| Employee | Salary |
| --- | ---: |
| An | 90,000 |
| Bình | 85,000 |
| Chi | 85,000 |

Even though 2 rows were requested, Oracle returns 3 rows because `CHI` has the same sort value as the last fetched row. Actual row count can be **larger** than the requested count.

`WITH TIES` makes sense only with `ORDER BY`; it extends the fetch slice to include all rows tied with the final cutoff row across **the sort expressions**. Without `ORDER BY`, there is no criterion to define ties.

### 4.3. Ties Are Evaluated Across the Entire ORDER BY

This point is crucial. Consider:

~~~sql
SELECT employee_id, employee_name, salary
FROM employees
ORDER BY salary DESC, employee_id
FETCH FIRST 2 ROWS WITH TIES;
~~~

If `EMPLOYEE_ID` is unique, two rows with equal `SALARY` but different `EMPLOYEE_ID` **do not tie across the full ORDER BY**. Consequently, the query may return strictly 2 rows.

If the goal is to get all employees sharing the cutoff salary, sort only by `SALARY`:

~~~sql
ORDER BY salary DESC
FETCH FIRST 2 ROWS WITH TIES;
~~~

If you want those tied results to also have a stable display order, wrap the query:

~~~sql
SELECT employee_id, employee_name, salary
FROM (
    SELECT employee_id, employee_name, salary
    FROM employees
    ORDER BY salary DESC
    FETCH FIRST 2 ROWS WITH TIES
)
ORDER BY salary DESC, employee_id;
~~~

The inner query picks the **salary-tied group**; the outer query merely sorts those selected rows by `employee_id` for stable presentation. This preserves tie semantics without putting a unique key into the inner tie criterion.

### 4.4. `WITH TIES` Is Not "Add a Few Random Rows"

Oracle does not arbitrarily pad page size. It fetches **every row whose ORDER BY values match the final row of the fetch slice**. For instance, when fetching 10, if the 10th row shares the same sort values with the next 40 rows, the result can expand to 50 rows.

This option is useful for:

- Getting the top N salaries without cutting off part of an equal-salary cohort.
- Getting top N products by sales while keeping every product tied at the cutoff.
- Leaderboards, exam scores, or result lists with tie rules.

It is unsuitable if an API strictly requires a fixed row count and payload size must stay within a hard cap.

### 4.5. NULL and Multiple Sort Expressions

If a sort column contains NULLs, Oracle applies NULL ordering per `ORDER BY` rules; for predictable output, specify `NULLS FIRST` or `NULLS LAST` explicitly:

~~~sql
SELECT product_id, rating
FROM products
ORDER BY rating DESC NULLS LAST
FETCH FIRST 10 ROWS WITH TIES;
~~~

When multiple sort expressions exist:

~~~sql
ORDER BY category_id, score DESC
FETCH FIRST 10 ROWS WITH TIES;
~~~

Two rows tie only if all sort expressions produce equal values under their comparison rules. Having the same `SCORE` with a different `CATEGORY_ID` is not a tie under this full ordering.

## 5. Distinguishing Top-N, Top-N Per Group, and Pagination

Requirements that sound similar have different semantics:

| Requirement | Approach |
| --- | --- |
| Get strictly at most the top 10 rows | `FETCH FIRST 10 ROWS ONLY` |
| Get top 10 rows plus tied rows at the boundary | `FETCH FIRST 10 ROWS WITH TIES` |
| Get page 3, 20 rows/page | `OFFSET 40 ROWS FETCH NEXT 20 ROWS ONLY` |
| Get the 3 highest-paid employees **in each department** | `ROW_NUMBER()`/`RANK()`/`DENSE_RANK()` with `PARTITION BY` |
| Get the top 3 distinct salary levels | `DENSE_RANK()` by salary |

`WITH TIES` in the row limiting clause applies to the **boundary of the entire result set**, not automatically per department. For per-group Top-N, use an analytic function:

~~~sql
SELECT department_id, employee_id, salary
FROM (
    SELECT
        department_id,
        employee_id,
        salary,
        RANK() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC
        ) AS salary_rank
    FROM employees
)
WHERE salary_rank <= 3
ORDER BY department_id, salary DESC, employee_id;
~~~

Here `RANK()` lets multiple employees with the same salary share a rank; `salary_rank <= 3` can return more than three rows per department when ties exist. To cap strictly at 3 rows per department, use `ROW_NUMBER()` with a unique tie-breaker.

## 6. Pagination Requires a Stable ORDER BY

### 6.1. Non-Unique Sort Orders Cause Unstable Pages

Example:

~~~sql
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC
OFFSET 0 ROWS FETCH NEXT 20 ROWS ONLY;
~~~

If multiple orders share the same `CREATED_AT`, their relative order is undefined by the query. Running page 1 and page 2 at different moments can cause same-timestamp rows to appear on different pages, repeat, or disappear if physical order/plan shifts.

The typical fix is adding a unique key as a tie-breaker:

~~~sql
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
OFFSET 0 ROWS FETCH NEXT 20 ROWS ONLY;
~~~

If `ORDER_ID` is unique, the pair (`CREATED_AT`, `ORDER_ID`) defines a total order. Rows with identical timestamps are ordered further by ID, stabilizing pagination.

### 6.2. NULLS FIRST/LAST and Business Ordering

If the sort column allows NULL, specify the desired placement:

~~~sql
SELECT task_id, due_date
FROM tasks
ORDER BY due_date ASC NULLS LAST, task_id ASC
FETCH FIRST 25 ROWS ONLY;
~~~

Explicit ordering helps readers and applications know where tasks without a due date belong. For pagination, a unique secondary key remains essential to order rows with matching dates or matching NULLs.

### 6.3. ORDER BY Must Match Product Requirements

A screen might require:

- Newest first: `created_at DESC, id DESC`.
- Name ascending: `name ASC, id ASC`.
- Status priority: `CASE` in `ORDER BY` followed by a unique key.
- Highest score: `score DESC`; if ties must be kept, use `WITH TIES` instead of adding a unique key into the tie criteria.

Never default to `ORDER BY id` for every screen when business logic expects a different order. And never use a cosmetic sort order lacking a tie-breaker in multi-request pagination.

## 7. OFFSET Pagination: Benefits and Performance Limits

### 7.1. Benefits

`OFFSET/FETCH` is easy to understand and integrate:

- Users can jump directly to page 1, 2, 10, or 100.
- The API simply accepts page number and page size.
- The SQL is shorter and clearer than legacy nested `ROWNUM` patterns.
- Well-suited for moderate result sets, internal reports, or UIs requiring arbitrary page jumping.

### 7.2. Drawbacks at Large Offsets

Suppose you want 20 rows on page 50,000:

~~~sql
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
OFFSET 999980 ROWS
FETCH NEXT 20 ROWS ONLY;
~~~

The database may have to traverse many leading rows in sort order before skipping nearly a million rows. The optimizer may use an index, stopkey, or suitable plan, yet **large OFFSETs typically cause work to grow with the number of skipped rows**. You cannot claim every query literally reads 1,000,000 table rows because execution plans and indexes govern physical work; nonetheless, deep offsets are generally far less efficient than seek pagination.

### 7.3. Indexes Aligned with ORDER BY

If a screen frequently filters by status and sorts by date/ID:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE status = :status
ORDER BY created_at DESC, order_id DESC
OFFSET :offset_rows ROWS FETCH NEXT :page_size ROWS ONLY;
~~~

A properly designed index can help Oracle locate and scan rows in filter/sort order:

~~~sql
-- Index design illustration only; inspect workload and execution plans before creating.
CREATE INDEX ix_orders_status_created_id
ON orders (status, created_at DESC, order_id DESC);
~~~

An index does not automatically guarantee every pagination query is fast. Check:

- Selectivity of `STATUS` and number of distinct values.
- Fraction of rows returned, columns read, and clustering factor.
- Actual execution plan and optimizer statistics.
- Index maintenance overhead on inserts, updates, and deletes.
- Whether the index satisfies both filtering and sorting in that exact order.

Never create an index from one example SQL without analyzing the workload.

## 8. Keyset/Seek Pagination: Resuming After the Last Viewed Row

When users mostly click **Next** to continue browsing rather than jumping to arbitrary page numbers, keyset pagination usually outperforms deep offsets.

### 8.1. The Idea

Suppose the order is:

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

After page 1 returns 20 rows, the application keeps the key pair of the last row:

~~~text
last_created_at = 2026-11-14 10:30:00
last_order_id   = 8451
~~~

The next page fetches only rows **coming after** that key pair in descending order:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE status = :status
  AND (
        created_at < :last_created_at
        OR (
            created_at = :last_created_at
            AND order_id < :last_order_id
        )
      )
ORDER BY created_at DESC, order_id DESC
FETCH NEXT :page_size ROWS ONLY;
~~~

Because `ORDER_ID` is unique, the condition pinpoints rows strictly after the previous page boundary. The database does not need to count and skip all earlier rows from the beginning; it can seek directly into the index at the next key if a matching access path exists.

### 8.2. Keyset with an Ascending Key

When sorting solely by an ascending key:

~~~sql
SELECT order_id, customer_id, created_at
FROM orders
WHERE order_id > :last_order_id
ORDER BY order_id
FETCH NEXT :page_size ROWS ONLY;
~~~

This is the simplest pattern. It fits well when:

- Page order rests on a single ordered, stable key.
- Users mainly step forward/backward by cursor.
- The application tracks the last seen key value.

If dynamic multi-column sorting is supported, the application must construct the matching seek predicate for each sort order and direction. You cannot simply change `ORDER BY` while leaving the `WHERE` predicate unchanged.

### 8.3. Keyset with Multiple Columns and NULLs

When sorting by `created_at DESC, order_id DESC` and `created_at` can be NULL, the seek predicate must accurately mirror `NULLS FIRST/LAST`. Comparing `<` against NULL yields UNKNOWN rather than simple TRUE/FALSE; hence section 8.1 assumes `CREATED_AT IS NOT NULL` or a matching constraint.

If a sort column is nullable:

1. Specify NULL ordering explicitly in `ORDER BY`.
2. Build separate seek conditions for NULL and non-NULL segments.
3. Add a unique key as tie-breaker.
4. Test page boundaries where the last row of a page has NULL.

In many systems, choosing non-null sort columns (such as `created_at NOT NULL`) keeps pagination much simpler.

### 8.4. Comparing Offset and Keyset

| Criterion | OFFSET/FETCH | Keyset/seek |
| --- | --- | --- |
| Jump directly to any page | Easy, compute offset from page number | Harder; usually requires a cursor or sequential stepping |
| Deep pages | Can spend effort skipping many rows | Usually much more efficient with a matching index/seek |
| Data changes between requests | Can repeat/skip rows as offset shifts | Less affected by inserts ahead of cursor, though sort-key updates/deletes still matter |
| API | Page number + size | Cursor token holding last key values |
| Dynamic sorting | Easy SQL, but order must still be controlled | Needs a matching seek predicate per sort option |
| Best fit | Back-office UIs, reports, arbitrary page jumps | Feeds, infinite scroll lists, large datasets |

Keyset does not create an immutable snapshot on its own. If a row's sort column is updated, deleted, or permissions/filters change between requests, results can still shift. When business rules require every page to reflect **the exact same data snapshot**, design a dedicated consistency strategy—such as a shared snapshot/SCN within supported limits and appropriate transaction lifetimes; never hold an open transaction arbitrarily across multiple web requests.

## 9. Data Mutating Between Pages: Why Can Rows Repeat or Disappear?

Suppose page 1 fetches 3 rows:

| Position | ID | Created |
| ---: | ---: | --- |
| 1 | 105 | 10:05 |
| 2 | 104 | 10:04 |
| 3 | 103 | 10:03 |

Next, a new order with ID 106 at 10:06 is inserted. When page 2 runs with `OFFSET 3`:

| New position | ID | Created |
| ---: | ---: | --- |
| 1 | 106 | 10:06 |
| 2 | 105 | 10:05 |
| 3 | 104 | 10:04 |
| 4 | 103 | 10:03 |
| 5 | 102 | 10:02 |

Offset 3 skips 106, 105, and 104, then returns 103 and 102; ID 103 **repeats** on page 2 even though it already appeared on page 1. Conversely, deletes or sort-key updates can cause rows to be skipped.

### 9.1. Handling Strategies by Requirement

- If the UI tolerates live updates between pages, document that pagination reflects the latest committed state per request.
- If continuous Next scrolling over changing data is needed, prefer a keyset cursor on stable sort keys.
- If reports require a consistent snapshot, design a snapshot/SCN or materialized result per business rules rather than merely increasing page size.
- If arbitrary page jumping and strong consistency are both required, consider an identified snapshot result set or dedicated reporting solution.

No single pagination pattern fits every system. Choose based on **data volume, navigation pattern, mutation rate, and consistency requirements**.

## 10. Counting Total Rows When Paginating

### 10.1. Using COUNT(*) OVER()

A screen often wants to display "Page 2 of 18, 436 total orders." You can add an analytic count:

~~~sql
SELECT
    order_id,
    created_at,
    total_amount,
    COUNT(*) OVER () AS total_rows
FROM orders
WHERE status = :status
ORDER BY created_at DESC, order_id DESC
OFFSET :offset_rows ROWS
FETCH NEXT :page_size ROWS ONLY;
~~~

`COUNT(*) OVER()` counts the rows **after filtering** in the result set before applying row limiting, repeating that total on each returned row.

Notes:

- When the page returns rows, `TOTAL_ROWS` gives the total matching `WHERE`, not the page's row count.
- If offset exceeds the result and the page is empty, the query returns zero rows to carry `TOTAL_ROWS`; the application cannot read the total from a row.
- An analytic count may require Oracle to process a substantial amount of data to compute the total even when page size is small.

### 10.2. Separate COUNT Query and Page Query

Another option:

~~~sql
SELECT COUNT(*) AS total_rows
FROM orders
WHERE status = :status;

SELECT order_id, created_at, total_amount
FROM orders
WHERE status = :status
ORDER BY created_at DESC, order_id DESC
OFFSET :offset_rows ROWS
FETCH NEXT :page_size ROWS ONLY;
~~~

The advantage is always getting a count even on empty pages; the drawback is that the two queries can observe data at **two slightly different points in time** if data changes in between. If count and page must match consistently, evaluate transaction isolation/snapshot needs and cost.

### 10.3. Is a Total Count Always Necessary?

Many modern APIs return only:

- the page's row list;
- next cursor/page;
- a `has_more` flag computed by fetching one extra row;
- omitting total counts because counting can be expensive.

Example fetching `page_size + 1`:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE status = :status
ORDER BY created_at DESC, order_id DESC
OFFSET :offset_rows ROWS
FETCH NEXT :fetch_size ROWS ONLY;
~~~

If the page size is 20, set `:fetch_size = 21`. The application returns at most 20 rows; if a 21st row comes back, `has_more = true`. This avoids full counting, though it does not by itself solve deep offsets or concurrent data mutations.

## 11. OFFSET/FETCH and WITH TIES in JOIN / GROUP BY Queries

### 11.1. Limiting After a JOIN

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.created_at
FROM customers c
JOIN orders o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
ORDER BY o.created_at DESC, o.order_id DESC
OFFSET 0 ROWS FETCH NEXT 20 ROWS ONLY;
~~~

Here fetch limits **rows of the post-JOIN result set**, not 20 customers. If one customer has 10 orders, that customer can appear across multiple rows.

If the goal is 20 customers along with all of their orders, select the 20 customers first (e.g., via a CTE/subquery), then JOIN afterward. Do not place `FETCH` on the outer query expecting it to cap one source table.

### 11.2. Limiting After GROUP BY

~~~sql
SELECT
    customer_id,
    SUM(total_amount) AS revenue
FROM orders
GROUP BY customer_id
ORDER BY revenue DESC
FETCH FIRST 10 ROWS WITH TIES;
~~~

The result is the top 10 **customer groups** by revenue, retaining tied groups at the boundary. The row limiting clause applies to the aggregated rows, without limiting how many source orders are read.

### 11.3. Limiting Inside a Subquery

~~~sql
WITH top_customers AS (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
    ORDER BY SUM(total_amount) DESC
    FETCH FIRST 10 ROWS WITH TIES
)
SELECT c.customer_name, t.revenue
FROM top_customers t
JOIN customers c
    ON c.customer_id = t.customer_id
ORDER BY t.revenue DESC, c.customer_id;
~~~

The subquery picks the top revenue groups; the outer query joins names and sorts for presentation. As before, having a tie-breaker in the outer sort does not alter the tied group already chosen inside.

## 12. Pagination on Older Oracle Versions: `ROWNUM` and `ROW_NUMBER()`

The row limiting clause was added in Oracle 12c. If an application must run on Oracle 11g or you need to maintain legacy code, two common techniques are `ROWNUM` and analytic `ROW_NUMBER()`.

### 12.1. Limiting to N Rows with ROWNUM

~~~sql
SELECT order_id, created_at
FROM orders
WHERE ROWNUM <= 10;
~~~

`ROWNUM` is a pseudocolumn Oracle assigns as rows are selected within a query block. It is **not a fixed row number stored in the table**.

Common mistake:

~~~sql
-- DOES NOT satisfy the intent to get the 10 newest orders:
SELECT order_id, created_at
FROM orders
WHERE ROWNUM <= 10
ORDER BY created_at DESC;
~~~

Because `ROWNUM` is evaluated in the query block before final sorting by `ORDER BY` in this form, the query can pick 10 arbitrary rows first and sort only those; it does not guarantee the 10 newest orders table-wide.

Correct approach—sort in a subquery, then limit outside:

~~~sql
SELECT order_id, created_at
FROM (
    SELECT order_id, created_at
    FROM orders
    ORDER BY created_at DESC, order_id DESC
)
WHERE ROWNUM <= 10;
~~~

### 12.2. OFFSET Pagination with Nested ROWNUM

To fetch rows from position `:offset + 1` to `:offset + :page_size`:

~~~sql
SELECT order_id, created_at, total_amount
FROM (
    SELECT sorted_rows.*, ROWNUM AS rn
    FROM (
        SELECT order_id, created_at, total_amount
        FROM orders
        ORDER BY created_at DESC, order_id DESC
    ) sorted_rows
    WHERE ROWNUM <= :offset_rows + :page_size
)
WHERE rn > :offset_rows
ORDER BY rn;
~~~

The innermost layer sorts the results; the middle layer assigns `ROWNUM` and stops at the upper bound; the outer layer discards rows with `RN <= offset`. This is a classic legacy pattern, though you must read the layers carefully so `ROWNUM` is never placed in the wrong scope.

### 12.3. Using ROW_NUMBER() OVER(...)

A general approach:

~~~sql
SELECT order_id, created_at, total_amount
FROM (
    SELECT
        order_id,
        created_at,
        total_amount,
        ROW_NUMBER() OVER (
            ORDER BY created_at DESC, order_id DESC
        ) AS rn
    FROM orders
)
WHERE rn BETWEEN :first_row AND :last_row
ORDER BY rn;
~~~

If page size is 20 and page number is 3:

~~~text
first_row = (3 - 1) * 20 + 1 = 41
last_row  = 3 * 20 = 60
~~~

`ROW_NUMBER()` numbers each row in the order specified by the analytic `ORDER BY`. The order must be deterministic; if rows tie, add a unique tie-breaker so numbering does not depend on internal execution order.

### 12.4. Distinguishing ROW_NUMBER, RANK, and DENSE_RANK

| Function | Tie handling | Example ranks for scores 100, 90, 90, 80 |
| --- | --- | --- |
| `ROW_NUMBER()` | Unique number per row | 1, 2, 3, 4 |
| `RANK()` | Tied rows share the same rank; next rank has a gap | 1, 2, 2, 4 |
| `DENSE_RANK()` | Tied rows share the same rank; no gaps | 1, 2, 2, 3 |

For **fixed-row-count** pagination, `ROW_NUMBER()` is typically used. For top N ranks preserving ties, use `RANK()`/`DENSE_RANK()` or `FETCH ... WITH TIES` depending on the exact semantics required.

## 13. Restrictions and Caveats of the Row Limiting Clause

### 13.1. Syntactic Placement

The row limiting clause comes after `ORDER BY`:

~~~sql
SELECT ...
FROM ...
WHERE ...
GROUP BY ...
HAVING ...
ORDER BY ...
OFFSET ... ROWS
FETCH NEXT ... ROWS ONLY;
~~~

Do not place `OFFSET/FETCH` before `WHERE` or between `FROM` and `ORDER BY`. When using subqueries, make sure it is clear which query block the limit applies to.

### 13.2. Column Aliases and Duplicate Names

In queries with duplicate column names from joins, the row limiting clause can trigger restrictions on column names/aliases and inline-view references. Give output columns unique, explicit aliases:

~~~sql
SELECT
    c.customer_id AS customer_id,
    o.order_id AS order_id,
    o.created_at AS order_created_at
FROM customers c
JOIN orders o
    ON o.customer_id = c.customer_id
ORDER BY o.created_at DESC, o.order_id DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Avoid returning two columns with identical names, especially when using `SELECT *` across joins or wrapping a query with a row limiting clause. Explicit column lists and aliases help avoid `ORA-00918` errors under duplicate-column restrictions.

### 13.3. Combining with FOR UPDATE

The row limiting clause has restrictions when combined with certain SQL constructs, including `FOR UPDATE`. When selecting rows for locking/updating, verify version-specific rules and design an appropriate query; never assume `FOR UPDATE` can simply be appended to any `OFFSET/FETCH` query.

### 13.4. Do Not Use FETCH as a Substitute for Filtering

~~~sql
-- Get the first 10 rows from the filtered set:
SELECT order_id, total_amount
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 10 ROWS ONLY;
~~~

`WHERE` determines **which rows qualify**; `FETCH` only limits the number of output rows. To get the top 10 paid orders, filter `STATUS` before limiting to 10. Never fetch 10 rows from the whole table and filter status in application code, as that produces wrong business results.

### 13.5. FETCH Does Not Guarantee a Specific Execution Plan

The Oracle optimizer can use indexes, sorts, stopkeys, or other techniques depending on statistics and the query. `FETCH FIRST 10 ROWS ONLY` defines **result semantics**, not a promise that the database physically reads only 10 rows from storage. To optimize:

- Inspect the actual SQL execution plan.
- Check predicates, order-by columns, indexes, and estimated vs. actual row counts.
- Use bind variables and cap page sizes.
- Test against data distributions representative of production.
- Re-evaluate whenever filters or sort orders change.

## 14. Hands-On Lab: Creating a Table and Paginating

The following steps create a standalone lab table with timestamps and tied scores. Run only in a schema you own; if a table with the same name exists, pick a different name instead of overwriting existing data.

### Step 1 — Create the Sample Table

~~~sql
CREATE TABLE pagination_lab (
    item_id     NUMBER PRIMARY KEY,
    item_name   VARCHAR2(60 CHAR) NOT NULL,
    category    VARCHAR2(20 CHAR) NOT NULL,
    score       NUMBER(6,2) NOT NULL,
    created_at  TIMESTAMP NOT NULL
);
~~~

### Step 2 — Insert Data with Ties

~~~sql
INSERT ALL
    INTO pagination_lab VALUES
        (1, 'Alpha', 'A', 99, TIMESTAMP '2026-11-14 10:00:00')
    INTO pagination_lab VALUES
        (2, 'Beta', 'A', 95, TIMESTAMP '2026-11-14 10:01:00')
    INTO pagination_lab VALUES
        (3, 'Gamma', 'A', 95, TIMESTAMP '2026-11-14 10:02:00')
    INTO pagination_lab VALUES
        (4, 'Delta', 'A', 90, TIMESTAMP '2026-11-14 10:03:00')
    INTO pagination_lab VALUES
        (5, 'Epsilon', 'B', 90, TIMESTAMP '2026-11-14 10:04:00')
    INTO pagination_lab VALUES
        (6, 'Zeta', 'B', 85, TIMESTAMP '2026-11-14 10:05:00')
    INTO pagination_lab VALUES
        (7, 'Eta', 'B', 85, TIMESTAMP '2026-11-14 10:06:00')
    INTO pagination_lab VALUES
        (8, 'Theta', 'B', 80, TIMESTAMP '2026-11-14 10:07:00')
SELECT 1 FROM dual;

COMMIT;
~~~

The dataset contains pairs of rows tied on `SCORE`: 95 and 85 (as well as 90); distinct items can share the same score.

### Step 3 — Fetch Top 3 Rows with ONLY

~~~sql
SELECT item_id, item_name, score
FROM pagination_lab
ORDER BY score DESC
FETCH FIRST 3 ROWS ONLY;
~~~

Returns at most 3 rows. The third row falls in the score-95 group; without a tie-breaker, the order between Beta and Gamma is not guaranteed.

### Step 4 — Fetch Top 3 Rows with WITH TIES

~~~sql
SELECT item_id, item_name, score
FROM pagination_lab
ORDER BY score DESC
FETCH FIRST 3 ROWS WITH TIES;
~~~

Returns 3 rows: Alpha, Beta, and Gamma. Try changing the count to 2:

~~~sql
SELECT item_id, item_name, score
FROM pagination_lab
ORDER BY score DESC
FETCH FIRST 2 ROWS WITH TIES;
~~~

Returns **3 rows** because both Beta and Gamma share score 95 at the boundary. Try `FETCH FIRST 4 ROWS WITH TIES`: the fourth row has score 90; because there is only one row with score 90 in the table, the result is 4 rows.

### Step 5 — Add a Tie-Breaker and Observe the Change

~~~sql
SELECT item_id, item_name, score
FROM pagination_lab
ORDER BY score DESC, item_id
FETCH FIRST 2 ROWS WITH TIES;
~~~

Because `ITEM_ID` is unique, the result has strictly 2 rows. This is the right behavior when you want a total order and strictly two rows; it **no longer retains the equal-score tie group**. To both select score ties and keep stable output ordering, use an inline view as in Section 4.3.

### Step 6 — Paginate Two Rows Per Page

~~~sql
-- Page 1:
SELECT item_id, item_name, score
FROM pagination_lab
ORDER BY item_id
OFFSET 0 ROWS FETCH NEXT 2 ROWS ONLY;

-- Page 2:
SELECT item_id, item_name, score
FROM pagination_lab
ORDER BY item_id
OFFSET 2 ROWS FETCH NEXT 2 ROWS ONLY;

-- Page 3:
SELECT item_id, item_name, score
FROM pagination_lab
ORDER BY item_id
OFFSET 4 ROWS FETCH NEXT 2 ROWS ONLY;
~~~

Because `ITEM_ID` is the primary key, page order stays stable on static data. Try changing `OFFSET 4` to `OFFSET 20` to observe an empty result set.

### Step 7 — Compute Total Row Count

~~~sql
SELECT
    item_id,
    item_name,
    COUNT(*) OVER () AS total_rows
FROM pagination_lab
ORDER BY item_id
OFFSET 2 ROWS FETCH NEXT 2 ROWS ONLY;
~~~

Each returned row carries `TOTAL_ROWS = 8`. If offset is changed to 20, no rows return to display the total.

### Step 8 — Try Keyset Pagination

Suppose page 1 ordered by ascending `ITEM_ID` fetched two rows and the last row had `ITEM_ID=2`. Next page:

~~~sql
SELECT item_id, item_name, score
FROM pagination_lab
WHERE item_id > 2
ORDER BY item_id
FETCH NEXT 2 ROWS ONLY;
~~~

The result is the next two rows by ID, without skipping earlier rows from the start.

### Step 9 — Clean Up the Lab Table When Finished

~~~sql
-- Only run if you are sure this is your lab table.
DROP TABLE pagination_lab PURGE;
~~~

`PURGE` bypasses the recycle bin; once dropped/purged, do not expect Flashback Drop to recover the table. You can keep the table if you want to continue practicing `ROW_NUMBER()` and execution plans.

## 15. Review Questions

1. Why does `FETCH FIRST 20 ROWS ONLY` fail to guarantee the same 20 rows without `ORDER BY`?
2. Which page does `OFFSET 20 ROWS FETCH NEXT 20 ROWS ONLY` correspond to when page size is 20 and pages start at 1?
3. What is the difference between `ONLY` and `WITH TIES`?
4. With `ORDER BY salary DESC`, if 5 employees tie at the 10th position's salary, how many rows can `FETCH FIRST 10 ROWS WITH TIES` return?
5. If a unique `employee_id` is added to `ORDER BY salary DESC, employee_id`, do equal-salary employees still tie across the full order?
6. How do you both keep ties by score and sort output deterministically by ID?
7. Can `WITH TIES` replace `RANK() OVER (PARTITION BY department_id ...)` to get the top 3 per department?
8. Why can a large OFFSET be slow even when page size is only 20?
9. What information must keyset pagination retain from the previous page?
10. Why must a multi-column seek condition mirror ASC/DESC directions and handle NULLs accurately?
11. Does `COUNT(*) OVER()` return total rows in the output if the page is empty?
12. Why can a separate count query and a separate page query report mismatched numbers when data changes?
13. In `ROWNUM` pagination, why must sorting happen in a subquery before assigning ROWNUM?
14. How does `ROW_NUMBER()` differ from `RANK()` in handling ties?
15. Does `OFFSET/FETCH` guarantee the database physically reads only the fetched row count?

**Suggested answers:**

1. Oracle does not guarantee row order if ORDER BY is omitted.
2. Page 2.
3. ONLY stops at the exact count; WITH TIES adds all rows tied with the last row according to ORDER BY.
4. Up to 14 rows if the 5-row tied group at the end consists of the 10th row plus 4 tied rows after it.
5. No if ID is unique, because the full sort tuples differ.
6. Select ties in a subquery ordered only by score; sort by ID as well in the outer query.
7. No; WITH TIES caps the whole result set, without partitioning by group.
8. The database may have to traverse and skip many rows prior to the requested offset.
9. The last row's sort keys (and any values needed to construct the seek predicate).
10. Because NULL does not compare like ordinary values and the seek predicate must match the exact sort order.
11. No, there are no rows to carry the analytic count.
12. The two statements can observe different committed states of the data.
13. Assigning ROWNUM before sorting can pick N arbitrary rows first and sort only those.
14. ROW_NUMBER always assigns unique numbers; RANK gives ties the same rank and skips subsequent numbers.
15. No; FETCH defines result semantics, while the execution plan determines the physical work performed.

## Oracle Reference Documentation

- [Oracle SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): `row_limiting_clause` syntax, OFFSET, FETCH FIRST/NEXT, ONLY, and WITH TIES.
- [Oracle Database SQL Language Reference — ROWNUM Pseudocolumn](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ROWNUM-Pseudocolumn.html): behavior and limitations of ROWNUM.
- [Oracle Database SQL Language Reference — ROW_NUMBER](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ROW_NUMBER.html): numbering rows by analytic order.
- [Oracle Database SQL Language Reference — RANK](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/RANK.html): ranking and handling tied rows.
- [Oracle Database SQL Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/): reading execution plans, indexes, and query optimization.
