# Combining `WITH`, `ORDER BY`, and `LIMIT` Across Processing Stages

In Neo4j, a Cypher query typically passes through multiple steps: matching nodes and relationships, filtering data, selecting a subset of records, aggregating, and returning results. The three components `WITH`, `ORDER BY`, and `LIMIT` control **which rows advance to the next step**. Placing them at different stages can change the actual query result, not just its execution speed.

This lesson belongs to the **Lists and Data Pipelines** group, focusing on row-stream processing in Cypher on Neo4j's property graph. After studying it, you will be able to:

- Distinguish the roles of `WITH`, `ORDER BY`, and `LIMIT`, as well as variable scope after each `WITH`.
- Choose the right stage to apply `LIMIT` before or after aggregation.
- Write multi-stage pipelines for top-N, pagination, and per-group top-N queries.
- Recognize unstable-result bugs and what to inspect in the execution plan.

## 1. How Do the Three Components Affect the Data Stream?

| Component | Role | Key Point |
| --- | --- | --- |
| `WITH` | Passes intermediate results to the next stage; selects variables, evaluates expressions, `DISTINCT`, or aggregations. | Variables not passed through `WITH` go out of scope for subsequent clauses. |
| `ORDER BY` | Sorts rows by one or more keys, ascending (`ASC`) or descending (`DESC`). | When selecting a business-meaningful top-N, establish ordering **before** `LIMIT`. |
| `LIMIT` | Keeps at most N rows at the point where it appears. | `LIMIT` in `WITH` bounds the input to the next step; `LIMIT` in `RETURN` bounds the returned result. |

A common pattern:

~~~cypher
MATCH (o:Order)
WHERE o.status = 'PAID'
WITH o
ORDER BY o.createdAt DESC, o.id ASC
LIMIT 10
RETURN o.id AS maDon, o.createdAt AS ngayTao
ORDER BY ngayTao DESC, maDon ASC;
~~~

Reading top to bottom: find paid orders → sort by newest, using order ID to break ties → forward only the first 10 orders to `RETURN` → output results in deterministic order. The example assumes `o.id` is unique and `o.createdAt` uses a consistent temporal type. Both sort keys in `RETURN` are stated explicitly so display order does not depend on later query edits.

**Distinguish two limiting scopes:**

~~~cypher
// Limit before aggregation: computes only over the 10 most recent orders.
MATCH (o:Order)
WITH o ORDER BY o.createdAt DESC, o.id ASC LIMIT 10
RETURN count(*) AS soDon, sum(o.total) AS tongTien;
~~~

~~~cypher
// Aggregate all orders, then return at most 10 groups.
MATCH (o:Order)
WITH o.status AS trangThai, count(*) AS soDon, sum(o.total) AS tongTien
RETURN trangThai, soDon, tongTien
ORDER BY soDon DESC, trangThai ASC
LIMIT 10;
~~~

The first query aggregates **the 10 selected rows**; the second aggregates **all matching rows**, then returns at most 10 status groups. You cannot move `LIMIT` arbitrarily and keep the same meaning.

## 2. Standalone Example: Picking the Top Three Records

To test immediately in Neo4j Browser without creating data, use `UNWIND` to turn a mock list into rows:

~~~cypher
UNWIND [
  {ma: 'O01', khach: 'An',   soTien: 120},
  {ma: 'O02', khach: 'Binh', soTien: 300},
  {ma: 'O03', khach: 'An',   soTien: 300},
  {ma: 'O04', khach: 'Chi',  soTien: 90},
  {ma: 'O05', khach: 'Binh', soTien: 160},
  {ma: 'O06', khach: 'Chi',  soTien: 200}
] AS don
WITH don
ORDER BY don.soTien DESC, don.ma ASC
LIMIT 3
RETURN don.ma AS maDon, don.khach AS khach, don.soTien AS soTien
ORDER BY soTien DESC, maDon ASC;
~~~

Expected result:

| maDon | khach | soTien |
| --- | --- | ---: |
| O02 | Binh | 300 |
| O03 | An | 300 |
| O06 | Chi | 200 |

Orders O02 and O03 both have `soTien = 300`. The secondary key `don.ma ASC` makes the ordering between them deterministic. `UNWIND` itself does not guarantee output order; do not rely on the initial element order when applying `LIMIT`.

One way to visualize the processing flow:

~~~text
UNWIND (6 rows)
    |
    v
WITH don + ORDER BY soTien DESC, ma ASC (6 sorted rows)
    |
    v
LIMIT 3 (only O02, O03, O06 remain)
    |
    v
RETURN ... ORDER BY ... (3 displayed rows)
~~~

**Note:** `LIMIT 3` means "at most three rows", not "every row tied with the third row". If you must keep all tied records, define a threshold or apply a ranking method matching the business requirement.

## 3. `WITH` Creates Stage Boundaries and Variable Scope

Each `WITH` determines which values are carried forward. It is also the right place to alias columns and compute intermediate results from multiple graph rows.

Suppose the data model is `(:Customer {id})-[:PLACED]->(:Order {id, total, createdAt, status})`. The query below computes per-customer revenue from paid orders, ranks them, and takes the top five customers:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
WITH c.id AS maKhach, o.total AS giaTri
WITH maKhach, count(*) AS soDon, sum(giaTri) AS tongTien
ORDER BY tongTien DESC, maKhach ASC
LIMIT 5
RETURN maKhach, soDon, tongTien
ORDER BY tongTien DESC, maKhach ASC;
~~~

After the first `WITH`, only `maKhach` and `giaTri` remain available in subsequent steps. The second `WITH` groups by `maKhach` and calculates order count and total amount; `ORDER BY ... LIMIT 5` therefore selects the **five highest-revenue customers**, not the five most expensive orders. If any orders have `total = null`, `count(*)` still counts those rows whereas `sum(giaTri)` ignores null values; define data-cleaning rules when working with real metrics.

Incorrect variable scope example:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c.id AS maKhach
RETURN maKhach, o.total AS giaTri; // Error: o is out of scope.
~~~

The fix is to forward the needed variable (such as `WITH c.id AS maKhach, o.total AS giaTri`) or compute the required value right inside `WITH`. Avoid carrying unnecessary variables forward because it obscures what each stage is actually operating on.

## 4. Chaining Multiple Stages: Top 100 Orders, Then Top 5 Customers

Problem: **Among the 100 most recent paid orders system-wide, find the five customers with the largest total order value.** This is an example where limits at two different stages have distinct meanings.

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
WITH c, o
ORDER BY o.createdAt DESC, o.id ASC
LIMIT 100

WITH c.id AS maKhach, count(*) AS soDon, sum(o.total) AS tongTien
ORDER BY tongTien DESC, maKhach ASC
LIMIT 5

RETURN maKhach, soDon, tongTien
ORDER BY tongTien DESC, maKhach ASC;
~~~

| Stage | Forwarded Output | Meaning |
| --- | --- | --- |
| `MATCH` and `WHERE` | Paid customer–order pairs | Initial dataset matching the filter condition. |
| `WITH c, o ORDER BY ... LIMIT 100` | Up to 100 pairs, newest orders first | **System-wide** limit before grouping. |
| `WITH c.id, count, sum ...` | One row per customer | Computes counts and revenue solely from the 100 orders above. |
| `ORDER BY tongTien ... LIMIT 5` | Up to five customers | Ranking after aggregation. |
| `RETURN ... ORDER BY ...` | Final result | Displays rows with the same ranking criteria. |

If the requirement changes to "the five customers with the highest revenue **across all** paid orders", remove `LIMIT 100` in the first stage. If the requirement is "the 100 most recent orders **for each customer**", the current `LIMIT 100` also does not fit because it limits globally; see the per-group approach in Section 6.

## 5. Limiting Before vs. After Aggregation: One Change, Two Results

Consider an illustrative dataset of five score rows. These are two standalone queries you can run directly.

**Case A — Take the top two score rows first, then sum by group:**

~~~cypher
UNWIND [
  {ma: 'A1', nhom: 'A', diem: 100},
  {ma: 'A2', nhom: 'A', diem: 50},
  {ma: 'B1', nhom: 'B', diem: 90},
  {ma: 'B2', nhom: 'B', diem: 90},
  {ma: 'C1', nhom: 'C', diem: 85}
] AS x
WITH x
ORDER BY x.diem DESC, x.ma ASC
LIMIT 2
WITH x.nhom AS nhom, sum(x.diem) AS tongDiem
RETURN nhom, tongDiem
ORDER BY tongDiem DESC, nhom ASC;
~~~

Result: group A = 100 and group B = 90. Only A1 and B1 pass `LIMIT 2`, so the remaining rows do not contribute to the sum.

**Case B — Sum all scores by group first, then pick the two highest-scoring groups:**

~~~cypher
UNWIND [
  {ma: 'A1', nhom: 'A', diem: 100},
  {ma: 'A2', nhom: 'A', diem: 50},
  {ma: 'B1', nhom: 'B', diem: 90},
  {ma: 'B2', nhom: 'B', diem: 90},
  {ma: 'C1', nhom: 'C', diem: 85}
] AS x
WITH x.nhom AS nhom, sum(x.diem) AS tongDiem
ORDER BY tongDiem DESC, nhom ASC
LIMIT 2
RETURN nhom, tongDiem
ORDER BY tongDiem DESC, nhom ASC;
~~~

Result: group B = 180, group A = 150. Here `LIMIT 2` selects two **groups**, after summing across all five rows.

| Business Question | Where to Place the Limit |
| --- | --- |
| "What is the total value of the 20 most recent orders?" | `ORDER BY` timestamp and `LIMIT 20` **before** `sum()`. |
| "Who are the 20 customers with the highest total revenue?" | `sum()` per customer **first**, then `ORDER BY` revenue and `LIMIT 20`. |
| "What are the newest orders among the 20 highest-revenue customers?" | Rank and limit customers first; then fetch orders for those selected customers and sort/limit per the new requirement. |

## 6. Global Top-N vs. Per-Group Top-N

The clauses:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, o
ORDER BY o.createdAt DESC, o.id ASC
LIMIT 3
RETURN c.id AS maKhach, o.id AS maDon;
~~~

only fetch the **three newest orders across all customers**. They do not fetch three orders per customer.

To get up to three newest paid orders **for each customer**, you can sort before `collect()` and then slice the list per group:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
WITH c, o
ORDER BY c.id ASC, o.createdAt DESC, o.id ASC
WITH c, collect(o)[..3] AS baDonMoiNhat
UNWIND baDonMoiNhat AS o
RETURN c.id AS maKhach, o.id AS maDon, o.createdAt AS ngayTao
ORDER BY maKhach ASC, ngayTao DESC, maDon ASC;
~~~

`WITH ... ORDER BY` guarantees row order fed **directly** into the next `WITH` clause, so elements gathered by `collect(o)` for each customer follow the sorted order. The `[..3]` slice keeps at most the first three elements; customers with one or two orders yield one or two results accordingly. This approach collects every customer's orders into a list before slicing, so it can consume significant memory if a customer has very many orders.

When order counts are large, you can place `ORDER BY ... LIMIT` inside a **subquery executed per customer**. On Neo4j versions supporting the `CALL (c) { ... }` variable scope syntax:

~~~cypher
MATCH (c:Customer)
CALL (c) {
  MATCH (c)-[:PLACED]->(o:Order)
  WHERE o.status = 'PAID'
  RETURN o.id AS maDon, o.createdAt AS ngayTao
  ORDER BY ngayTao DESC, maDon ASC
  LIMIT 3
}
RETURN c.id AS maKhach, maDon, ngayTao
ORDER BY maKhach ASC, ngayTao DESC, maDon ASC;
~~~

In this example, the three-row limit applies **to each subquery execution for a single customer**, and customers with no matching orders do not appear in the output. The syntax above belongs to Neo4j 5 versions supporting the `CALL` variable scope clause (since Neo4j 5.23); on older versions, use the `CALL { WITH c ... }` form appropriate for that version. Actual performance also depends on indexes and the execution plan.

## 7. Pagination: Always Maintain Deterministic Ordering

Example paginating paid orders:

~~~cypher
MATCH (o:Order)
WHERE o.status = 'PAID'
RETURN o.id AS maDon, o.createdAt AS ngayTao, o.total AS giaTri
ORDER BY ngayTao DESC, maDon ASC
SKIP $offset
LIMIT $pageSize;
~~~

With `$offset = 0` and `$pageSize = 20`, the query fetches up to the first 20 rows; the next page uses `$offset = 20`. Pagination parameters must be non-negative integers; the order ID serves as a unique secondary sort key so records with identical timestamps still have a clear order.

Pagination with `SKIP` can become expensive when skipping many rows. When data changes between calls, pages can repeat or miss records even with deterministic ordering. For large, continuously updated lists, consider keyset/cursor pagination based on the `(createdAt, id)` pair of the last row from the previous page. If the sort criteria change, the cursor condition must change accordingly.

## 8. Common Errors and Self-Checks

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| `LIMIT 10` returns different rows across runs | Missing `ORDER BY` or too many tied values | Add explicit ordering; use a unique secondary key when determinism is needed. |
| Total revenue is unexpectedly small | Limiting order rows before `sum()` even though all orders should be included | Move `LIMIT` after the aggregation step. |
| Cypher reports an undefined variable | A previous `WITH` dropped the variable | Forward the needed variable/alias through `WITH` or compute it earlier. |
| Wanted three records per group but got three records total | `LIMIT` placed on the global stream | Use per-group collection slicing or a subquery with a per-group limit. |
| Display order is wrong after extra processing steps | Relying on ordering from an intermediate step | Place `ORDER BY` on the final `RETURN`. |
| Top-N is incorrect when data is missing or mistyped | Sort key has `null`, numbers stored as strings, or inconsistent temporal types | Normalize properties; define `null` handling, using `coalesce()` when appropriate. |
| Query is slow despite small `LIMIT` | Many rows must be read, grouped, or sorted before top-N is known | Inspect `PROFILE`, filter predicates, graph model, and appropriate indexes. |

Practical rules of thumb:

1. State the business requirement in plain words: "top-N of **which rows**, over **which set**, ranked by **which key**?" Only then decide where to place `WITH` and `LIMIT`.
2. Put the primary sort key first and add a tie-breaker key. For `null` values, decide sorting behavior upfront; `coalesce(o.total, 0)` is only appropriate if business rules truly treat missing values as 0.
3. After every `WITH`, check which variables remain in scope and what row count is expected. `DISTINCT`, `count()`, `sum()`, and `collect()` can all alter row counts.
4. When using `ORDER BY` on aggregated results, prefer sorting by the computed alias, e.g., `WITH c.id AS maKhach, sum(o.total) AS tongTien ORDER BY tongTien DESC`.
5. Pass `$topN`, `$offset`, and `$pageSize` as type- and range-validated parameters from the application rather than manually concatenating Cypher strings.

## 9. Performance: `LIMIT` Does Not Guarantee the Query Only Reads N Rows

`LIMIT` bounds **the output row count of a stage**, but preceding operators may already have scanned the graph, joined rows, aggregated, or sorted a large volume of data. When fetching top-N by a property, a plan may leverage an index structure or top-N operator, though you should not assume this optimization always applies.

To verify, run `EXPLAIN` (plan only) or `PROFILE` (executes and measures) on a read query:

~~~cypher
PROFILE
MATCH (o:Order)
WHERE o.status = 'PAID'
WITH o
ORDER BY o.createdAt DESC, o.id ASC
LIMIT $topN
RETURN o.id AS maDon, o.createdAt AS ngayTao
ORDER BY ngayTao DESC, maDon ASC;
~~~

Inspect `Rows`, `DB Hits`, and operators such as `Sort`, `Top`, `NodeIndexSeek`/`NodeIndexScan` (exact names and presentation vary by version/plan). Indexes aligned with the `status` filter and `createdAt` sort key can help, but confirm via the actual plan, especially when a tie-breaker key `id` is involved. Never push `LIMIT` earlier solely to reduce cost if doing so alters the dataset being aggregated.

## 10. Stage-by-Stage Self-Practice

On the `Customer`–`PLACED`–`Order` model introduced earlier, identify the **stage where the limit belongs** before writing code:

1. Find the **10 highest-value orders** among all paid orders. Sort by `o.total DESC`, break ties with `o.id ASC`, and limit right before returning results.
2. Find the **10 customers who placed the most orders**. Compute `count(*)` per customer first, then sort by order count and limit at the customer level.
3. Find the **two newest orders for each customer**. A global `LIMIT 2` is wrong; limit per group as shown in Section 6.

Suggested solution for Question 2:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
WITH c.id AS maKhach, count(*) AS soDon
ORDER BY soDon DESC, maKhach ASC
LIMIT 10
RETURN maKhach, soDon
ORDER BY soDon DESC, maKhach ASC;
~~~

The core principle is that every `WITH` establishes an **intermediate data boundary**. Choose the right sequence—"filter → sort → limit → aggregate" or "filter → aggregate → sort → limit"—based on the actual question, and only then optimize using Neo4j's execution plan.
