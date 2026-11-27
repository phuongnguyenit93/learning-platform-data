# Combining Multiple Aggregations Without Double-Counting Metrics

In Neo4j, a report often needs several metrics at once: **order count**, **total amount**, **support ticket count**, and **total product quantity purchased** for each customer. Functions like `count()`, `sum()`, `avg()`, `min()`, and `max()` can appear together in a single `RETURN` or `WITH` clause. However, if a query traverses multiple relationship branches, **one node can appear multiple times in intermediate rows**. When that happens, aggregated results can be wrong even though the Cypher syntax is valid.

This lesson belongs to the **Aggregation** chapter of the Neo4j module. The focus is on identifying the right **unit of calculation** (*grain*), controlling row counts produced by property graph patterns, and combining multiple aggregations without double-summing or double-counting. These techniques apply directly to reporting queries before returning results via the Java Driver, Spring Data Neo4j, or a service API.

## 1. Model and Practice Dataset

Consider a bookstore graph with customers, orders, support tickets, and products:

~~~text
(:Customer)-[:PLACED]->(:Order)-[:HAS_LINE {quantity}]->(:Product)
      |
      +------[:OPENED]----->(:Ticket)
~~~

- `Customer`: `id`, `name`; identifies a customer.
- `Order`: `id`, `amount` (order value, VND), `status`.
- `Ticket`: `id`, `status`; support request opened by a customer.
- `Product`: `sku`, `name`; product in one or more orders.
- `HAS_LINE.quantity`: quantity of a product in an order.

Create the data in an **empty practice database**. Run it only once so you do not create duplicate nodes and relationships:

~~~cypher
CREATE
  (an:Customer {id: 'C01', name: 'An'}),
  (binh:Customer {id: 'C02', name: 'Binh'}),
  (chi:Customer {id: 'C03', name: 'Chi'}),
  (dung:Customer {id: 'C04', name: 'Dung'}),
  (o101:Order {id: 'O101', amount: 100000, status: 'PAID'}),
  (o102:Order {id: 'O102', amount: 100000, status: 'PENDING'}),
  (o103:Order {id: 'O103', amount: 150000, status: 'PAID'}),
  (o104:Order {id: 'O104', amount: 80000, status: 'PAID'}),
  (t01:Ticket {id: 'T01', status: 'OPEN'}),
  (t02:Ticket {id: 'T02', status: 'CLOSED'}),
  (t03:Ticket {id: 'T03', status: 'OPEN'}),
  (t04:Ticket {id: 'T04', status: 'OPEN'}),
  (p01:Product {sku: 'P01', name: 'Neo4j'}),
  (p02:Product {sku: 'P02', name: 'Java'}),
  (an)-[:PLACED]->(o101),
  (an)-[:PLACED]->(o102),
  (binh)-[:PLACED]->(o103),
  (dung)-[:PLACED]->(o104),
  (an)-[:OPENED]->(t01),
  (an)-[:OPENED]->(t02),
  (binh)-[:OPENED]->(t03),
  (chi)-[:OPENED]->(t04),
  (o101)-[:HAS_LINE {quantity: 1}]->(p01),
  (o101)-[:HAS_LINE {quantity: 2}]->(p02),
  (o102)-[:HAS_LINE {quantity: 3}]->(p02),
  (o103)-[:HAS_LINE {quantity: 2}]->(p01),
  (o104)-[:HAS_LINE {quantity: 1}]->(p02);
~~~

The **business-correct** metrics for each customer are:

| Customer | Order Count | Total Order Value (VND) | Ticket Count | OPEN Tickets | Total Product Quantity |
|---|---:|---:|---:|---:|---:|
| C01 / An | 2 | 200000 | 2 | 1 | 6 |
| C02 / Binh | 1 | 150000 | 1 | 1 | 2 |
| C03 / Chi | 0 | 0 | 1 | 1 | 0 |
| C04 / Dung | 1 | 80000 | 0 | 0 | 1 |
| **Total** | **4** | **430000** | **4** | **3** | **9** |

Note: O101 and O102 are **two different orders that both have `amount = 100000`**. This data is intentionally designed to prove that `sum(DISTINCT o.amount)` cannot replace summing the amounts of distinct orders.

## 2. Why Does Aggregation Double-Count?

Suppose you want to return order count, total amount, and ticket count for each customer at the same time. The following query looks reasonable:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
RETURN
  c.id AS maKhach,
  count(o) AS soDon,
  sum(o.amount) AS tongTien,
  count(t) AS soTicket
ORDER BY maKhach;
~~~

However, for An, both `PLACED` and `OPENED` branches are **one-to-many** relationships. Every order combines with every ticket of the same customer:

| Row After Two OPTIONAL MATCHes | Order `o` | Ticket `t` | `o.amount` |
|---:|---|---|---:|
| 1 | O101 | T01 | 100000 |
| 2 | O101 | T02 | 100000 |
| 3 | O102 | T01 | 100000 |
| 4 | O102 | T02 | 100000 |

Therefore the query returns for C01:

- `count(o) = 4` instead of **2**.
- `sum(o.amount) = 400000` instead of **200000**.
- `count(t) = 4` instead of **2**.

This is **intermediate row multiplication** (*row multiplication/fan-out*). Cypher is aggregating over **order–ticket pairs**, not separately over the order set and the ticket set.

If a customer has `m` orders and `n` tickets, two independent relationship branches can produce `m × n` rows when both sets are non-empty. With `OPTIONAL MATCH`, an unmatched branch still retains a row with the corresponding variable set to `null`; thus you cannot simply take the product `m × n` for cases with empty sets.

### 2.1. Distinguishing count(*) and count(variable)

For Chi, the customer has no orders but has one ticket T04:

~~~cypher
MATCH (c:Customer {id: 'C03'})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
RETURN
  count(*) AS soDong,
  count(o) AS soDon,
  count(t) AS soTicket;
~~~

Result: `soDong = 1`, `soDon = 0`, `soTicket = 1`. `OPTIONAL MATCH` retains the customer even though order variable `o` is `null`. When counting related entities, `count(o)` and `count(t)` are clearer than `count(*)`.

### 2.2. The Bug Is in the Input Rows, Not in sum()

`sum(o.amount)` does exactly what is technically specified: it sums `o.amount` across **all existing rows**. The bug is that an order is repeated across multiple matched paths. Therefore, the effective fix is to determine **which grain each metric belongs to** before aggregating.

## 3. What Can COUNT(DISTINCT) Solve and What Can It Not?

When you only need to count distinct entities, `DISTINCT` can eliminate duplicate occurrences:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
RETURN
  c.id AS maKhach,
  count(DISTINCT o) AS soDon,
  count(DISTINCT t) AS soTicket
ORDER BY maKhach;
~~~

For An, the result is now correct: `soDon = 2`, `soTicket = 2`. `DISTINCT o` relies on **order node identity**, so the two occurrences of O101 are counted only once.

However, do not conclude that adding `DISTINCT` to every aggregation is always right:

~~~cypher
MATCH (c:Customer {id: 'C01'})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
RETURN
  sum(o.amount) AS tongSaiViLapDong,
  sum(DISTINCT o.amount) AS tongSaiViGopGiaTri,
  count(DISTINCT o) AS soDonDung;
~~~

| Calculation | Result | Issue |
|---|---:|---|
| `sum(o.amount)` | 400000 | Each order is counted twice due to two tickets |
| `sum(DISTINCT o.amount)` | 100000 | Two real orders share the same amount and get collapsed |
| `count(DISTINCT o)` | 2 | Correctly counts two distinct order nodes |

**`DISTINCT` operates on the expression's value**, and does not inherently understand business units. Total amount must be summed **once per order**, even when two orders have the same monetary value.

Similarly, `collect(DISTINCT o)` or `count(DISTINCT o)` may have to process many elements and consume memory. In complex reports, avoid generating a huge number of duplicated rows in the first place.

## 4. Solution 1: Sequential Aggregation with WITH

A clean approach is to compute **order metrics before expanding to tickets**:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH
  c,
  count(o) AS soDon,
  sum(o.amount) AS tongTien
OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
RETURN
  c.id AS maKhach,
  soDon,
  tongTien,
  count(t) AS soTicket
ORDER BY maKhach;
~~~

Result:

| maKhach | soDon | tongTien | soTicket |
|---|---:|---:|---:|
| C01 | 2 | 200000 | 2 |
| C02 | 1 | 150000 | 1 |
| C03 | 0 | 0 | 1 |
| C04 | 1 | 80000 | 0 |

In `WITH c, count(o), sum(o.amount)`, the implicit grouping key is node `c`. Each customer is reduced to **one row** with order count and total amount already computed. Afterward, `OPTIONAL MATCH` to `Ticket` may produce multiple ticket rows, but `soDon` and `tongTien` are **carried forward as already-computed values**. Only `count(t)` is computed over the ticket rows in the final step.

Important: in the final `RETURN`, `c.id`, `soDon`, and `tongTien` are non-aggregate expressions and become **grouping keys** for `count(t)`. With this dataset, customer IDs are unique, so the result remains one row per customer.

### 4.1. Adding Multiple Metrics on the Same Data Source

Aggregates `count`, `sum`, `avg`, `min`, and `max` can be used together **if they are computed over the same row set at the right grain**:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH
  c,
  count(o) AS soDon,
  sum(o.amount) AS tongTien,
  avg(o.amount) AS trungBinhDon,
  min(o.amount) AS donNhoNhat,
  max(o.amount) AS donLonNhat,
  count(CASE WHEN o.status = 'PAID' THEN o END) AS soDonPaid,
  sum(CASE WHEN o.status = 'PAID' THEN o.amount ELSE 0 END)
    AS tienPaid
RETURN
  c.id AS maKhach,
  soDon,
  tongTien,
  trungBinhDon,
  donNhoNhat,
  donLonNhat,
  soDonPaid,
  tienPaid
ORDER BY maKhach;
~~~

For C01, `soDon = 2`, `tongTien = 200000`, `trungBinhDon = 100000`, `donNhoNhat = 100000`, `donLonNhat = 100000`, `soDonPaid = 1`, `tienPaid = 100000`.

For C03 with no orders, `soDon = 0`, `tongTien = 0`, `trungBinhDon = null`, `min/max = null`. This distinction is meaningful: there are no observations to compute an average or extrema.

### 4.2. Filtering Groups Between Two Aggregations

To report tickets only for customers with **at least two orders**, filter on order count **after** `WITH`:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, count(o) AS soDon, sum(o.amount) AS tongTien
WHERE soDon >= 2
OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
RETURN
  c.id AS maKhach,
  soDon,
  tongTien,
  count(t) AS soTicket;
~~~

Only C01 remains. The `WHERE` condition after `WITH` applies to **aggregated customer groups**, avoiding traversing ticket relationships for excluded customers.

## 5. Solution 2: CALL Subqueries for Independent Branches

When you need multiple metrics from several independent relationships, you can use `CALL { ... }` to compute each branch separately and then join back to the customer node:

~~~cypher
MATCH (c:Customer)
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
  RETURN
    count(o) AS soDon,
    sum(o.amount) AS tongTien
}
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
  RETURN
    count(t) AS soTicket,
    count(CASE WHEN t.status = 'OPEN' THEN t END) AS soTicketMo
}
RETURN
  c.id AS maKhach,
  soDon,
  tongTien,
  soTicket,
  soTicketMo
ORDER BY maKhach;
~~~

Each `CALL` runs in the context of the current customer `c`. The first subquery traverses only orders, so total amount is unaffected by ticket count. The second subquery traverses only tickets, so ticket count is unaffected by order count.

| maKhach | soDon | tongTien | soTicket | soTicketMo |
|---|---:|---:|---:|---:|
| C01 | 2 | 200000 | 2 | 1 |
| C02 | 1 | 150000 | 1 | 1 |
| C03 | 0 | 0 | 1 | 1 |
| C04 | 1 | 80000 | 0 | 0 |

**Why are customers without orders or tickets still preserved?** Each subquery uses `OPTIONAL MATCH` and ungrouped aggregate functions, so it returns **one row of metrics per customer** even when the branch has no relationships. If you replaced it with a mandatory `MATCH` and the subquery returned zero rows, the outer customer row could be dropped.

The example above uses `WITH c` to import the variable into the subquery, which is compatible with many Neo4j 5 versions. Newer versions support explicit variable scoping such as `CALL (c) { ... }`; use the syntax matching your running Neo4j version.

### 5.1. When to Prefer WITH vs. CALL?

| Scenario | Suitable Approach |
|---|---|
| Two simple relationship sets that can be computed sequentially | Aggregate one branch with `WITH`, then expand the next branch |
| Multiple independent branches, each with multiple `MATCH/WHERE/WITH` steps | Independent `CALL` subqueries |
| Reusing multiple metrics over the same order set | Compute together in one `WITH` or one subquery |
| Only need distinct entity counts after rows multiply | `count(DISTINCT node)` can work; weigh the cost |
| Single branch and single calculation level | Direct `MATCH ... RETURN` aggregation |

Subqueries do not automatically guarantee faster queries. Their primary benefit is **isolating aggregation scopes and avoiding Cartesian products across branches**. Use `PROFILE` to confirm actual row counts and costs.

## 6. Mixing Order Totals and Product Quantities: Two Different Data Grains

The `HAS_LINE` relationship holds product quantities. If you join straight from orders to products and sum both order amounts and quantities, an order with multiple product lines will repeat:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
MATCH (o)-[line:HAS_LINE]->(p:Product)
RETURN
  c.id AS maKhach,
  count(o) AS soLanDonXuatHien,
  count(DISTINCT o) AS soDonThuc,
  sum(o.amount) AS tongTienSai,
  sum(line.quantity) AS tongSoLuong
ORDER BY maKhach;
~~~

For C01, O101 has two product lines (`P01`, `P02`) and O102 has one line. Therefore:

- `soLanDonXuatHien = 3`, while the true order count is **2**.
- `tongTienSai = 300000`, while the true total amount is **200000**.
- `tongSoLuong = 6` is **correct** because each `HAS_LINE` contributes one quantity to the sum.

The unit of `o.amount` is the **order**, while the unit of `line.quantity` is the **product line**. To combine them accurately, compute each metric at its corresponding grain.

### 6.1. Two-Stage Aggregation: From Product Lines to Orders, Then to Customers

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
OPTIONAL MATCH (o)-[line:HAS_LINE]->(:Product)
WITH
  c,
  o,
  sum(line.quantity) AS soLuongTheoDon
RETURN
  c.id AS maKhach,
  count(o) AS soDon,
  sum(o.amount) AS tongTien,
  sum(soLuongTheoDon) AS tongSoLuong
ORDER BY maKhach;
~~~

In `WITH c, o, sum(line.quantity)`, the grouping key is the pair **(customer, order)**. Each order is reduced to one row after summing its product lines. Consequently, `sum(o.amount)` in `RETURN` adds each order **only once**.

| maKhach | soDon | tongTien | tongSoLuong |
|---|---:|---:|---:|
| C01 | 2 | 200000 | 6 |
| C02 | 1 | 150000 | 2 |
| C03 | 0 | 0 | 0 |
| C04 | 1 | 80000 | 1 |

Note: this two-stage pattern assumes each order belongs to one customer in the model and each `HAS_LINE` is a valid detail line. If in real data an order could be matched multiple times before `WITH` due to other branches, eliminate that earlier row multiplication first.

### 6.2. Isolating All Three Metric Sets in Subqueries

When you need **orders + tickets + product quantities** at the same time, you can keep each aggregation isolated:

~~~cypher
MATCH (c:Customer)
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
  RETURN
    count(o) AS soDon,
    sum(o.amount) AS tongTien
}
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
  RETURN count(t) AS soTicket
}
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:PLACED]->(:Order)-[line:HAS_LINE]->(:Product)
  RETURN sum(line.quantity) AS tongSoLuong
}
RETURN
  c.id AS maKhach,
  soDon,
  tongTien,
  soTicket,
  tongSoLuong
ORDER BY maKhach;
~~~

This query matches the sample data table in section 1, including C03 with no orders and C04 with no tickets.

## 7. Adding a Third Branch Can Multiply Errors Rapidly

If you join three branches simultaneously in one pipeline:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
OPTIONAL MATCH (o)-[line:HAS_LINE]->(:Product)
OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
RETURN
  c.id AS maKhach,
  count(DISTINCT o) AS soDon,
  count(DISTINCT t) AS soTicket,
  sum(o.amount) AS tongTienSai,
  sum(line.quantity) AS tongSoLuongSai
ORDER BY maKhach;
~~~

For C01:

- O101 has two product lines, O102 has one → **3 product lines**.
- C01 has two tickets → **each product line combines with two tickets**, producing **6 rows**.
- `sum(o.amount) = 600000` because all three product lines carry amount 100000 and all are repeated across the tickets.
- `sum(line.quantity) = 12` instead of **6** because every quantity is counted twice.
- `count(DISTINCT o) = 2` and `count(DISTINCT t) = 2` may look right, making the errors in the two sums harder to spot.

Having a few correct columns does not mean the entire query is correct. When combining multiple metrics, check **which node/relationship level each calculation draws from** and how many times it appears in the intermediate row set.

## 8. Filtering Source Data and Conditional Aggregation

Many reports need total order count, PAID order count, and PAID revenue simultaneously. If you put `WHERE o.status = 'PAID'` before `count(o)`, unpaid orders are lost from total order count. Instead, compute metrics over **the same order row set** using `CASE`:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.id AS maKhach,
  count(o) AS tongSoDon,
  count(CASE WHEN o.status = 'PAID' THEN o END) AS soDonPaid,
  sum(CASE WHEN o.status = 'PAID' THEN o.amount ELSE 0 END)
    AS tienPaid
ORDER BY maKhach;
~~~

| maKhach | tongSoDon | soDonPaid | tienPaid |
|---|---:|---:|---:|
| C01 | 2 | 1 | 100000 |
| C02 | 1 | 1 | 150000 |
| C03 | 0 | 0 | 0 |
| C04 | 1 | 1 | 80000 |

`count(CASE WHEN ... THEN o END)` counts rows where `CASE` returns a non-`null` node. `sum(CASE ... ELSE 0 END)` sums amounts for qualifying orders and contributes 0 for non-qualifying rows.

If reporting only PAID orders, a `WHERE o.status = 'PAID'` before aggregation is more readable and reduces rows. If you need **multiple metrics with different conditions**, `CASE` aggregation is suitable, provided the row set is not multiplied by other branches.

To filter **customers with PAID total greater than 100000**, use `WITH` followed by `WHERE`:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH
  c,
  sum(CASE WHEN o.status = 'PAID' THEN o.amount ELSE 0 END)
    AS tienPaid
WHERE tienPaid > 100000
RETURN c.id AS maKhach, tienPaid
ORDER BY maKhach;
~~~

Only C02 meets `> 100000` with `tienPaid = 150000`. This `WHERE` condition applies to **post-aggregation groups**, unlike a `WHERE` that filters individual orders before calculation.

## 9. How to Self-Verify Before Trusting Metrics

A result table with 4 customers does not reveal how many rows the query processed. To find where row multiplication occurs, temporarily return the detailed variables:

~~~cypher
MATCH (c:Customer {id: 'C01'})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
RETURN
  c.id AS maKhach,
  o.id AS maDon,
  t.id AS maTicket,
  o.amount AS tienDon
ORDER BY maDon, maTicket;
~~~

This table has **4 rows** instead of 2 order rows or 2 ticket rows. That is a clear sign that aggregating directly over the current rows will multiply metrics.

You can measure row counts and distinct entity counts before finalizing the query structure:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
RETURN
  c.id AS maKhach,
  count(*) AS soDongTrungGian,
  count(DISTINCT o) AS soDonKhacNhau,
  count(DISTINCT t) AS soTicketKhacNhau
ORDER BY maKhach;
~~~

| maKhach | soDongTrungGian | soDonKhacNhau | soTicketKhacNhau |
|---|---:|---:|---:|
| C01 | 4 | 2 | 2 |
| C02 | 1 | 1 | 1 |
| C03 | 1 | 0 | 1 |
| C04 | 1 | 1 | 0 |

When `soDongTrungGian` exceeds the number of order or ticket entities, re-evaluate any `sum()` and `avg()` running on this row set.

### 9.1. Questions to Check Calculation Grain

1. **What does one report row represent?** A customer, an order, a product, or a combination?
2. **Which unit does each metric belong to?** Amount at order grain, quantity at `HAS_LINE` grain, tickets at `Ticket` node grain.
3. **How many matched paths exist for that unit?** Two one-to-many branches can multiply rows.
4. **Is deduplication valid?** `count(DISTINCT o)` works for counting distinct order nodes; `sum(DISTINCT amount)` does not preserve distinct orders that share the same value.
5. **Where should aggregation happen?** Use `WITH` at the appropriate level or `CALL` to isolate branches before combining results.

### 9.2. PROFILE Helps Spot Row Expansion

~~~cypher
PROFILE
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
RETURN c.id AS maKhach, sum(o.amount) AS tongTienSai;
~~~

In the execution plan, watch **actual row counts** across relationship expansion and aggregation operators. If row counts surge before calculation, check whether multiple branches are multiplying them. On large graphs, `EXPLAIN` shows the planned execution without running it, while `PROFILE` executes the query to display measured numbers.

Indexes and constraints can help locate starting points (for example looking up `Customer.id`), but **do not automatically fix wrong sums caused by row multiplication**. Before tuning indexes, make sure the aggregation structure is correct.

## 10. Returning Results to Java Driver and Spring Data Neo4j

A typical reporting result should have **one record per business key** with clear aliases:

~~~cypher
MATCH (c:Customer)
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
  RETURN count(o) AS orderCount, sum(o.amount) AS orderAmount
}
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
  RETURN count(t) AS ticketCount
}
RETURN
  c.id AS customerId,
  orderCount,
  orderAmount,
  ticketCount
ORDER BY customerId;
~~~

The Java Driver can map `customerId`, `orderCount`, `orderAmount`, and `ticketCount` columns into a statistics object/DTO. With Spring Data Neo4j, use an appropriate projection for report results instead of forcing them into a node entity.

**Column types and semantics must remain consistent:** `orderCount = 0` means no orders; `orderAmount = 0` means the sum over an empty set is 0. Values like `avg`, `min`, and `max` over empty sets can be `null`, so the Java side must handle nullability when mapping.

When building APIs, avoid re-counting records from a query returning many detail rows; accurate reports should be calculated at the proper grain directly in Cypher.

## 11. Practice Exercises and Solutions

### Exercise 1. Detecting Row Multiplication

Explain why An's `count(o)`, `count(t)`, and `sum(o.amount)` are all wrong in the following query:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
MATCH (c)-[:OPENED]->(t:Ticket)
RETURN c.id AS maKhach,
       count(o) AS soDon,
       count(t) AS soTicket,
       sum(o.amount) AS tongTien;
~~~

**Solution:** For An, two orders combine with two tickets to produce four rows. Hence `count(o) = 4`, `count(t) = 4`, `sum(o.amount) = 400000`; the correct values are `2`, `2`, `200000` respectively. For customers missing either branch, mandatory `MATCH` can even drop them completely from the result.

### Exercise 2. Fixing the Query with WITH

Write a query returning all four customers along with order count, total amount, and ticket count, without multiplying metrics.

**Solution:**

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, count(o) AS soDon, sum(o.amount) AS tongTien
OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
RETURN
  c.id AS maKhach,
  soDon,
  tongTien,
  count(t) AS soTicket
ORDER BY maKhach;
~~~

Result: C01 = `(2, 200000, 2)`, C02 = `(1, 150000, 1)`, C03 = `(0, 0, 1)`, C04 = `(1, 80000, 0)`.

### Exercise 3. Why Is sum(DISTINCT) Wrong?

An's two orders O101 and O102 both have value 100000. What does `sum(DISTINCT o.amount)` return, and why is it wrong?

**Solution:** `sum(DISTINCT o.amount) = 100000`, because there is only one **distinct amount value** in the set. However, An has **two distinct orders**, so the correct total is `100000 + 100000 = 200000`. Aggregation must happen at the **order grain**, not simply by deduplicating numeric values.

### Exercise 4. Combining Three Sources with Subqueries

Return one row per customer with `soDon`, `soTicket`, and `tongSoLuong` across three independent branches. Both Chi and Dung must be preserved.

**Solution:**

~~~cypher
MATCH (c:Customer)
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
  RETURN count(o) AS soDon
}
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
  RETURN count(t) AS soTicket
}
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:PLACED]->(:Order)-[line:HAS_LINE]->(:Product)
  RETURN sum(line.quantity) AS tongSoLuong
}
RETURN c.id AS maKhach, soDon, soTicket, tongSoLuong
ORDER BY maKhach;
~~~

C01 `(2, 2, 6)`, C02 `(1, 1, 2)`, C03 `(0, 1, 0)`, C04 `(1, 0, 1)`.

## 12. Key Takeaways

- Combining multiple `count()`, `sum()`, `avg()` calls in one `RETURN` is only valid when **the same row set fits all metrics**.
- Multiple one-to-many relationship branches can multiply rows. When two sets both have elements, combinations can reach `m × n`.
- `count(DISTINCT node)` can fix entity counts; **`sum(DISTINCT amount)` does not fix total amounts** when distinct entities share the same value.
- Aggregate each relationship set **before joining another branch** using `WITH`, or compute independently inside `CALL` subqueries.
- Order totals must be calculated at the **Order** grain; product quantities at the **HAS_LINE** grain; ticket counts at the **Ticket** grain.
- Use `OPTIONAL MATCH` and `count(variable)` to retain groups without relationships and distinguish them from `count(*)`.
- Check intermediate row counts, verify results against sample data, and run `PROFILE` on realistic graphs before trusting that a report is accurate and efficient.
