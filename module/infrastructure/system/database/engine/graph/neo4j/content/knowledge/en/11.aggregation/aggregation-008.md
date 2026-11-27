# Verifying Aggregation Results with Small Ground-Truth Datasets

## 1. Why Verify Aggregations?

In Neo4j, Cypher queries aggregate data using functions such as `count()`, `sum()`, `avg()`, `min()`, `max()`, and `collect()`. The output depends directly on **the number of rows produced after graph pattern matching**. Even a single one-to-many relationship can increase the row count; `MATCH` can drop entities without relationships, whereas `OPTIONAL MATCH` can produce rows containing `null`. Thus, a result that looks plausible can still be wrong.

A reliable verification technique is to build a **fixed dataset small enough to compute the answers by hand**, then cross-check every group and totals with Cypher. This technique works well when building reports over a *property graph*, testing queries, validating imported data, and verifying results returned via the Neo4j Java Driver or Spring Data Neo4j.

After this lesson, you will be able to:

- Build an independent test graph and calculate expected aggregations before running queries.
- Distinguish `count(*)`, `count(variable)`, and `count(DISTINCT variable)` across one-to-many relationship patterns.
- Verify aggregations by order, customer, product, and across the entire dataset.
- Detect bugs caused by dropped empty groups, row multiplication, misused `DISTINCT`, or relying on unguaranteed result ordering.
- Write queries that self-compare **actual results** against **fixed ground-truth answers** without needing APOC.

> **Scope and units:** Monetary values in this lesson are expressed in **thousands of VND**. For example, `260` corresponds to 260,000 VND. This is synthetic data for verification practice, not a real production database.

## 2. Building a Re-Runnable Test Graph

The model uses four node labels:

- `Customer` — customer.
- `Order` — order.
- `Line` — order line item, storing `qty` (quantity) and `unitPrice` (unit price).
- `Product` — product.

Three directed relationship types:

~~~text
(Customer)-[:PLACED]->(Order)-[:HAS_LINE]->(Line)-[:OF_PRODUCT]->(Product)
~~~

All nodes in this lesson carry an additional `QA008` label so queries do not mix with other data. Only run test-data deletion commands in a **practice database**.

**Step 1 — Delete the previous QA008 dataset (if any):**

~~~cypher
MATCH (n:QA008)
DETACH DELETE n;
~~~

**Step 2 — Create the baseline dataset:**

~~~cypher
CREATE
  (c1:QA008:Customer {id: 'C01', name: 'An'}),
  (c2:QA008:Customer {id: 'C02', name: 'Bình'}),
  (c3:QA008:Customer {id: 'C03', name: 'Chi'}),
  (c4:QA008:Customer {id: 'C04', name: 'Dũng'}),

  (o1:QA008:Order {id: 'O01'}),
  (o2:QA008:Order {id: 'O02'}),
  (o3:QA008:Order {id: 'O03'}),
  (o4:QA008:Order {id: 'O04'}),

  (l1:QA008:Line {id: 'L01', qty: 2, unitPrice: 100}),
  (l2:QA008:Line {id: 'L02', qty: 3, unitPrice: 20}),
  (l3:QA008:Line {id: 'L03', qty: 1, unitPrice: 100}),
  (l4:QA008:Line {id: 'L04', qty: 5, unitPrice: 20}),
  (l5:QA008:Line {id: 'L05', qty: 2, unitPrice: 50}),

  (p1:QA008:Product {id: 'P01', name: 'Book'}),
  (p2:QA008:Product {id: 'P02', name: 'Pen'}),
  (p3:QA008:Product {id: 'P03', name: 'Notebook'})

WITH c1, c2, c3, o1, o2, o3, o4,
     l1, l2, l3, l4, l5, p1, p2, p3
CREATE
  (c1)-[:PLACED]->(o1),
  (c1)-[:PLACED]->(o2),
  (c2)-[:PLACED]->(o3),
  (c3)-[:PLACED]->(o4),

  (o1)-[:HAS_LINE]->(l1),
  (o1)-[:HAS_LINE]->(l2),
  (o2)-[:HAS_LINE]->(l3),
  (o3)-[:HAS_LINE]->(l4),
  (o3)-[:HAS_LINE]->(l5),

  (l1)-[:OF_PRODUCT]->(p1),
  (l2)-[:OF_PRODUCT]->(p2),
  (l3)-[:OF_PRODUCT]->(p1),
  (l4)-[:OF_PRODUCT]->(p2),
  (l5)-[:OF_PRODUCT]->(p3);
~~~

Note that **order O04 has no line items** and **customer C04 has no orders**. These two cases are intentional to test how empty groups are handled.

**Step 3 — Verify baseline data:**

~~~cypher
MATCH (n:QA008)
RETURN count(n) AS soNode;
~~~

The result must be **16 nodes**: 4 customers + 4 orders + 5 line items + 3 products.

~~~cypher
MATCH (a:QA008)-[r]->(b:QA008)
RETURN count(r) AS soQuanHe;
~~~

The result must be **14 relationships**: 4 `PLACED` + 5 `HAS_LINE` + 5 `OF_PRODUCT`. If either number is wrong, fix the sample data before evaluating the aggregate queries.

## 3. Building an Answer Table Independently of Cypher

Before writing `sum()`, compute each line item's value using the formula:

\[
\text{Line amount}=\text{qty}\times\text{unitPrice}
\]

| Line Item | Order | Product | Qty | Unit Price | Line Amount |
|---|---|---|---:|---:|---:|
| L01 | O01 | P01 — Book | 2 | 100 | 200 |
| L02 | O01 | P02 — Pen | 3 | 20 | 60 |
| L03 | O02 | P01 — Book | 1 | 100 | 100 |
| L04 | O03 | P02 — Pen | 5 | 20 | 100 |
| L05 | O03 | P03 — Notebook | 2 | 50 | 100 |
| **Total** | | | **13** | | **560** |

From the table above, we establish the ground-truth answers to check against:

**By order:**

| Order | Line Count | Total Amount |
|---|---:|---:|
| O01 | 2 | 260 |
| O02 | 1 | 100 |
| O03 | 2 | 200 |
| O04 | 0 | 0 |

**By customer:**

| Customer ID | Customer | Orders | Line Items | Total Amount |
|---|---|---:|---:|---:|
| C01 | An | 2 | 3 | 360 |
| C02 | Bình | 1 | 2 | 200 |
| C03 | Chi | 1 | 0 | 0 |
| C04 | Dũng | 0 | 0 | 0 |

**By product:**

| Product ID | Product | Line Items | Total Qty | Total Amount |
|---|---|---:|---:|---:|
| P01 | Book | 2 | 3 | 300 |
| P02 | Pen | 2 | 8 | 160 |
| P03 | Notebook | 1 | 2 | 100 |

Important cross-check invariants:

- Total amount from line items: **560**.
- Total amount by orders: `260 + 100 + 200 + 0 = 560`.
- Total amount by customers: `360 + 200 + 0 + 0 = 560`.
- Total amount by products: `300 + 160 + 100 = 560`.
- Total product units sold: **13**.
- Total line items: **5**; orders with at least one line item: **3**; total orders: **4**.

When independent calculations disagree, re-check relationship directions, filter conditions, and row counts formed before aggregation.

## 4. Verifying Whole-Graph Aggregations

For aggregations at the **line-item** level, there is no need to traverse through orders or customers if all required information already lives on `Line`. Shorter paths reduce the risk of generating unnecessary row duplicates.

~~~cypher
MATCH (l:QA008:Line)
RETURN
  count(l) AS soDong,
  sum(l.qty) AS tongSoLuong,
  sum(l.qty * l.unitPrice) AS tongTien,
  min(l.qty * l.unitPrice) AS dongNhoNhat,
  max(l.qty * l.unitPrice) AS dongLonNhat,
  avg(l.qty * l.unitPrice) AS trungBinhMoiDong;
~~~

| soDong | tongSoLuong | tongTien | dongNhoNhat | dongLonNhat | trungBinhMoiDong |
|---:|---:|---:|---:|---:|---:|
| 5 | 13 | 560 | 60 | 200 | 112.0 |

Explanation: the five line amounts are `[200, 60, 100, 100, 100]`. Therefore the average **per line item** is `560 / 5 = 112.0`, not the average price per unit of product. If you need the average selling price per **unit**, compute `sum(l.qty * l.unitPrice) / sum(l.qty)` and state its meaning clearly; in this dataset that is `560 / 13`, approximately **43.08 thousand VND/unit**.

Check distinct unit price tiers:

~~~cypher
MATCH (l:QA008:Line)
WITH DISTINCT l.unitPrice AS donGia
ORDER BY donGia
RETURN collect(donGia) AS cacDonGia;
~~~

The exact answer is **`[20, 50, 100]`**. Here `DISTINCT` applies to *unit price*, and then `ORDER BY` guarantees the ordering before feeding into `collect()`.

## 5. Verifying Grouping by Order, Including Empty Orders

~~~cypher
MATCH (o:QA008:Order)
OPTIONAL MATCH (o)-[:HAS_LINE]->(l:QA008:Line)
RETURN
  o.id AS donHang,
  count(l) AS soDong,
  coalesce(sum(l.qty * l.unitPrice), 0) AS tongTien
ORDER BY donHang;
~~~

| donHang | soDong | tongTien |
|---|---:|---:|
| O01 | 2 | 260 |
| O02 | 1 | 100 |
| O03 | 2 | 200 |
| O04 | 0 | 0 |

`OPTIONAL MATCH` preserves O04 even though it has no `HAS_LINE` relationship. For that group, variable `l` is `null`: `count(l)` returns 0, and `coalesce(..., 0)` expresses the business rule that an empty order's total amount is 0. This is a readable and resilient pattern when adding other aggregates that could return `null`.

If changed to `MATCH (o)-[:HAS_LINE]->(l)`, **O04 disappears from the result**. When a report must output every order, that is a missing-group bug, even though the totals for the remaining three orders are still right.

## 6. Verifying Grouping by Customer and Row Multiplicity

From customer to line item there can be two one-to-many hops: one customer places multiple orders, and each order has multiple lines. Counting rows of the matched pattern is **not equivalent** to counting distinct orders.

~~~cypher
MATCH (c:QA008:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:QA008:Order)
OPTIONAL MATCH (o)-[:HAS_LINE]->(l:QA008:Line)
RETURN
  c.id AS khachHang,
  c.name AS ten,
  count(*) AS soDongKhongGianKetQua,
  count(o) AS soLanXuatHienDon,
  count(DISTINCT o) AS soDonThucTe,
  count(l) AS soDongHang,
  coalesce(sum(l.qty * l.unitPrice), 0) AS tongTien
ORDER BY khachHang;
~~~

| khachHang | ten | soDongKhongGianKetQua | soLanXuatHienDon | soDonThucTe | soDongHang | tongTien |
|---|---|---:|---:|---:|---:|---:|
| C01 | An | 3 | 3 | 2 | 3 | 360 |
| C02 | Bình | 2 | 2 | 1 | 2 | 200 |
| C03 | Chi | 1 | 1 | 1 | 0 | 0 |
| C04 | Dũng | 1 | 0 | 0 | 0 | 0 |

Key points to remember:

1. `count(*)` counts **result rows**, including rows preserved by `OPTIONAL MATCH` when relationship variables are `null`. Hence C03 and C04 still have value 1.
2. `count(o)` counts non-`null` values of `o`. Order O01 appears twice because it has two line items, inflating C01's order occurrence count to 3.
3. `count(DISTINCT o)` counts **distinct orders**, matching the requirement "actual order count": C01 has 2 orders, C02 has 1, C03 has 1, C04 has 0.
4. `count(l)` counts line items; empty orders and customers without orders both receive 0.
5. In the sample model, each line item belongs to exactly one order, so `sum(l.qty * l.unitPrice)` over the linked lines produces the answers 360, 200, 0, 0.

**Two common mistakes:**

~~~cypher
// WRONG when counting orders: counts each order occurrence after joining with lines.
MATCH (c:QA008:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:QA008:Order)
OPTIONAL MATCH (o)-[:HAS_LINE]->(l:QA008:Line)
RETURN c.id AS khachHang, count(o) AS soDonSai
ORDER BY khachHang;
~~~

The query above returns `3, 2, 1, 0` for C01–C04 instead of `2, 1, 1, 0`.

~~~cypher
// WRONG when keeping empty orders: OPTIONAL MATCH combines two hops into one pattern.
MATCH (c:QA008:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:QA008:Order)-[:HAS_LINE]->(l:QA008:Line)
RETURN c.id AS khachHang, count(DISTINCT o) AS soDonSai
ORDER BY khachHang;
~~~

The combined pattern requires **both hops to exist together**. O04 has no line items so it fails the entire pattern; C03 gets counted as 0 orders. Therefore, use **two separate `OPTIONAL MATCH` clauses** when you need to preserve both customers without orders and orders without line items.

## 7. Verifying Grouping by Product

~~~cypher
MATCH (l:QA008:Line)-[:OF_PRODUCT]->(p:QA008:Product)
RETURN
  p.id AS sanPham,
  p.name AS ten,
  count(l) AS soDongHang,
  sum(l.qty) AS soLuong,
  sum(l.qty * l.unitPrice) AS tongTien
ORDER BY sanPham;
~~~

| sanPham | ten | soDongHang | soLuong | tongTien |
|---|---|---:|---:|---:|
| P01 | Book | 2 | 3 | 300 |
| P02 | Pen | 2 | 8 | 160 |
| P03 | Notebook | 1 | 2 | 100 |

The query uses `p.id` and `p.name` as grouping keys in `RETURN`; when non-aggregate expressions are placed alongside aggregate functions in `RETURN`, Cypher groups by those expressions. Using a stable identifier key avoids accidentally merging two products with the same name.

If you want to list **products that have never been sold as well**, start from `Product` and `OPTIONAL MATCH` to `Line`, with explicit handling for a total of 0. The current dataset has no unsold products in stock, so the `MATCH` query above is sufficient to verify all three products in the sample.

## 8. Why Should DISTINCT Not Be Used Blindly in SUM?

`DISTINCT` is useful when counting orders duplicated after relationship expansion, but it can discard valid figures if applied directly to **monetary values**.

~~~cypher
MATCH (l:QA008:Line)
RETURN
  sum(l.qty * l.unitPrice) AS tongDung,
  sum(DISTINCT l.qty * l.unitPrice) AS tongSai;
~~~

| tongDung | tongSai |
|---:|---:|
| 560 | 360 |

Because the line amounts on L03, L04, and L05 are all 100, `sum(DISTINCT ...)` keeps only **one** value of 100. The wrong calculation becomes `200 + 60 + 100 = 360`. All three line items are valid transactions, even though they happen to have the same line amount.

Rule of thumb: identify **the entity or business line to count/sum** first; when handling an order appearing multiple times, use `count(DISTINCT o)` for order counts. Do not replace every `sum()` with `sum(DISTINCT ...)` to mask row-duplication bugs from an overly broad pattern match.

If a query has joined additional relationships causing a line item to appear multiple times, collapse back to **one record per line item** using `WITH DISTINCT l` or grouping by `l.id` before summing, while verifying that input values are genuinely unique under that identifier.

## 9. Writing Automated Verification Tests Against Ground-Truth Answers

Instead of reading tables by eye, you can put the fixed expected answers in a list of maps, then use `UNWIND` to generate each test case. The following query compares all four customers and returns a `passed` column:

~~~cypher
WITH [
  {id: 'C01', orders: 2, lines: 3, revenue: 360},
  {id: 'C02', orders: 1, lines: 2, revenue: 200},
  {id: 'C03', orders: 1, lines: 0, revenue: 0},
  {id: 'C04', orders: 0, lines: 0, revenue: 0}
] AS expected
UNWIND expected AS e
OPTIONAL MATCH (c:QA008:Customer {id: e.id})
OPTIONAL MATCH (c)-[:PLACED]->(o:QA008:Order)
OPTIONAL MATCH (o)-[:HAS_LINE]->(l:QA008:Line)
WITH e,
     count(DISTINCT c) AS customers,
     count(DISTINCT o) AS orders,
     count(l) AS lines,
     coalesce(sum(l.qty * l.unitPrice), 0) AS revenue
RETURN
  e.id AS customerId,
  customers,
  orders,
  lines,
  revenue,
  customers = 1
    AND orders = e.orders
    AND lines = e.lines
    AND revenue = e.revenue AS passed
ORDER BY customerId;
~~~

Expected result: **4 rows, with all 4 `passed` values equal to `true`**.

Why use `OPTIONAL MATCH` even on the first lookup for the customer? Because if you used `MATCH` and an expected customer was deleted from the data, that test row would **disappear**, giving the illusion that all remaining rows passed. With `OPTIONAL MATCH`, the expected row is preserved; `customers = 0` causes the test to fail. Counting `DISTINCT c` also catches cases where multiple nodes share the same customer ID.

To cross-check total revenue via two independent calculation paths, also run:

~~~cypher
MATCH (o:QA008:Order)
OPTIONAL MATCH (o)-[:HAS_LINE]->(l:QA008:Line)
WITH o, coalesce(sum(l.qty * l.unitPrice), 0) AS orderTotal
WITH sum(orderTotal) AS totalByOrders
OPTIONAL MATCH (line:QA008:Line)
WITH totalByOrders,
     coalesce(sum(line.qty * line.unitPrice), 0) AS totalByLines
RETURN
  totalByOrders,
  totalByLines,
  totalByOrders = totalByLines
    AND totalByLines = 560 AS passed;
~~~

The result must be `totalByOrders = 560`, `totalByLines = 560`, `passed = true`. Cross-checking catches bugs that drop or duplicate rows when joining from orders; however, two totals matching is **not enough** to guarantee every group is right, so per-group checks for C01–C04, O01–O04, and P01–P03 are still needed.

You can use the same testing style in the Java Driver or Spring Data Neo4j: the query returns a list of records, and the application compares by **identifier** and confirms the full group count, numeric values, and `passed` column. When writing integration tests, recreate the fixture in a dedicated test database and never rely on row ordering if the query lacks `ORDER BY`.

## 10. Troubleshooting Checklist When Results Do Not Match

| Symptom | Cause to Check | How to Verify/Fix |
|---|---|---|
| Missing C04 or O04 | `MATCH` drops entities without relationships | Start from the entity to report, add `OPTIONAL MATCH` for branches that may be empty |
| C01's order count is 3 | An order appears multiple times per line item | Inspect row counts before aggregation; use `count(DISTINCT o)` |
| C03 is counted as 0 orders | Two hops combined into one `OPTIONAL MATCH` | Split customer–order and order–line hops |
| Total amount is 360 instead of 560 | Used `sum(DISTINCT lineAmount)` | Keep every valid line item; distinguish duplicate entities from duplicate values |
| Group has 0 lines yet `count(*) = 1` | Row with `null` variable retained by `OPTIONAL MATCH` | Use `count(l)` when counting actual line items |
| A group disappears after filtering | `WHERE` excludes rows or is placed at the wrong stage | Review filter placement before/after `OPTIONAL MATCH` |
| `collect()` array changes order | No guarantee on input order | Use `WITH ... ORDER BY` before `collect()` |
| All remaining checks pass when a group is missing | Test uses `MATCH` which drops the expected row | Use `UNWIND` expected answers + `OPTIONAL MATCH` and assert full group count |

If results are still wrong, debug the query step by step: inspect row counts after each `MATCH` or `OPTIONAL MATCH` with a temporary `RETURN`, verify node/relationship pairs have the right identities, and only then bring `sum()` or `count()` back in. `PROFILE` can show actual row counts through each operator; on this 16-node dataset, the goal is **understanding cardinality and correctness**, not benchmarking large-scale performance.

## 11. Self-Verification Exercises

**Exercise 1.** Write a query computing `count(DISTINCT o)` for orders **that have at least one line item**. Answer: **3** (O01, O02, O03). Compare against the total order count of **4**.

**Exercise 2.** Write a query returning `collect(l.id)` in ascending order of line-item ID. Answer: `['L01', 'L02', 'L03', 'L04', 'L05']`.

Hint for Exercise 2:

~~~cypher
MATCH (l:QA008:Line)
WITH l ORDER BY l.id
RETURN collect(l.id) AS ids;
~~~

**Exercise 3.** Suppose a second relationship from L01 to the same product P01 is added in corrupted data. Joining `Line` → `Product` will make L01 appear twice; P01's group sum inflates from **300** to **500** if `sum(l.qty * l.unitPrice)` is used directly. Re-check the `OF_PRODUCT` relationship count, detect duplicated rows by `l.id`, and enforce the rule **each line item belongs to exactly one product** with an appropriate data validation step.

Exercise 3 is only a hypothetical scenario; do not modify the baseline fixture to complete the first two exercises. If you intentionally add a relationship to test the bug, delete and rebuild the fixture from section 2 before running the main verification suite.

## 12. Cleaning Up Test Data

After practicing, you can delete all 16 fixture nodes along with their attached relationships:

~~~cypher
MATCH (n:QA008)
DETACH DELETE n;
~~~

Use this command only in a practice database. When building repeatable tests, recreate the fixture before each run, compare results by identifier, and keep an **answer table independent** of the query under test. This small, hand-verified ground-truth set is the foundation for trusting aggregations on larger graphs.
