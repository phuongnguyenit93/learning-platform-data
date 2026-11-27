# Pre-Aggregation Filtering and Post-Aggregation Filtering with WITH

In Neo4j, a Cypher query often has to answer two very different questions:

- **Which orders should be included in the calculation?** For example: include only paid orders.
- **Which groups should be kept after the calculation?** For example: show only customers with at least two paid orders.

The first question requires **filtering rows before aggregation**, while the second requires **filtering groups after aggregation**. In the **Aggregation** chapter, `WHERE` and `WITH` help place conditions at the right stage while keeping the query's *aggregation grain* clear.

This is an essential skill when summarizing connected data in Neo4j: each `MATCH` produces rows from matching node–relationship patterns; `WITH` can collapse those rows into groups; and placing `WHERE` before versus after `WITH` can produce completely different results even with the same business condition.

## 1. Sample Data

Consider the property graph of an order management system:

~~~text
(:Customer {id, name})-[:PLACED]->(:Order {id, amount, status})
~~~

`Customer` represents customers, `Order` represents orders; `PLACED` indicates that a customer placed an order. The `amount` property is the order value in VND, and `status` indicates the order status.

Create the following data in an **empty practice database**. Run the `CREATE` statement only once to avoid duplicate records:

~~~cypher
CREATE
  (an:Customer {id: 'C01', name: 'An'}),
  (binh:Customer {id: 'C02', name: 'Binh'}),
  (chi:Customer {id: 'C03', name: 'Chi'}),
  (dung:Customer {id: 'C04', name: 'Dung'}),
  (o101:Order {id: 'O101', amount: 100000, status: 'PAID'}),
  (o102:Order {id: 'O102', amount: 150000, status: 'PAID'}),
  (o103:Order {id: 'O103', amount: 90000, status: 'PENDING'}),
  (o104:Order {id: 'O104', amount: 200000, status: 'PAID'}),
  (o105:Order {id: 'O105', amount: 70000, status: 'CANCELLED'}),
  (o106:Order {id: 'O106', amount: 50000, status: 'PAID'}),
  (an)-[:PLACED]->(o101),
  (an)-[:PLACED]->(o102),
  (an)-[:PLACED]->(o103),
  (binh)-[:PLACED]->(o104),
  (binh)-[:PLACED]->(o105),
  (dung)-[:PLACED]->(o106);
~~~

Business reference table:

| Customer | Orders | All Orders | PAID Orders | Total PAID Amount |
|---|---|---:|---:|---:|
| C01 / An | O101, O102, O103 | 3 | 2 | 250000 |
| C02 / Binh | O104, O105 | 2 | 1 | 200000 |
| C03 / Chi | None | 0 | 0 | 0 |
| C04 / Dung | O106 | 1 | 1 | 50000 |

There are **6 orders** in total, of which **4 are PAID** with a combined value of **500000 VND**. These values will be used to verify the queries.

## 2. Two Different Filtering Stages

Picture a query as a data flow:

~~~text
MATCH                  → produces rows from the graph pattern
WHERE before WITH      → removes rows not meeting the condition
WITH ... count/sum     → groups and computes metrics per group
WHERE after WITH       → removes groups not meeting metric thresholds
RETURN                 → presents the results
~~~

For example, the requirement: **"List customers with at least two paid orders, along with their paid order count and paid total."**

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
WITH
  c,
  count(o) AS soDonDaThanhToan,
  sum(o.amount) AS tongDaThanhToan
WHERE soDonDaThanhToan >= 2
RETURN
  c.id AS maKhach,
  c.name AS ten,
  soDonDaThanhToan,
  tongDaThanhToan
ORDER BY maKhach;
~~~

Result:

| maKhach | ten | soDonDaThanhToan | tongDaThanhToan |
|---|---|---:|---:|
| C01 | An | 2 | 250000 |

Stage-by-stage explanation:

1. `MATCH` finds six order rows.
2. `WHERE o.status = 'PAID'` keeps four paid order rows.
3. `WITH c, count(o), sum(o.amount)` forms three customer groups: C01, C02, C04; the implicit grouping key is node `c`.
4. `WHERE soDonDaThanhToan >= 2` keeps only group C01.
5. `RETURN` outputs one result row for An.

Key point: **pre-filtering determines which data enters the calculation; post-filtering determines which aggregated results are displayed**.

## 3. Pre-Aggregation Filtering: WHERE on Source Rows

A `WHERE` placed after `MATCH` typically checks properties, labels, values, or conditions on **each individual matched row**:

~~~cypher
MATCH (o:Order)
WHERE o.status = 'PAID'
RETURN
  count(o) AS soDon,
  sum(o.amount) AS tongTien,
  avg(o.amount) AS giaTriTrungBinh;
~~~

Result: `soDon = 4`, `tongTien = 500000`, `giaTriTrungBinh = 125000.0`.

In this query, `PENDING` and `CANCELLED` orders are filtered out before `RETURN`, so they do not contribute to the sum or average. If `WHERE` is removed, the total value of all six orders would be `660000`, which is no longer the total paid amount.

### 3.1. Filtering with Multiple Conditions

For example, counting only paid orders with a value of at least 100000 VND:

~~~cypher
MATCH (o:Order)
WHERE o.status = 'PAID' AND o.amount >= 100000
RETURN count(o) AS soDon, sum(o.amount) AS tongTien;
~~~

Result: `soDon = 3`, `tongTien = 450000` (O101, O102, O104). Even though O106 is paid, it is excluded because its value is only 50000.

### 3.2. Filtering the Root Entity Before Traversing Relationships

If a report is only for one customer, you can locate the customer first and then traverse orders:

~~~cypher
MATCH (c:Customer)
WHERE c.id = 'C01'
MATCH (c)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN c.name AS ten, count(o) AS soDon, sum(o.amount) AS tongTien;
~~~

Result: An, 2 PAID orders, total 250000 VND.

Placing selective conditions early usually reduces the volume of data that must be traversed. In production environments, evaluate indexes on `Customer.id` or frequently filtered properties; actual index usage still depends on Neo4j's execution plan.

## 4. Post-Aggregation Filtering: WITH ... WHERE

Cypher does not use an SQL-style `HAVING` clause to filter group results. Instead, a common pattern is to **aggregate inside `WITH`**, assign aliases to metrics, and then **filter with `WHERE` after `WITH`**.

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, count(o) AS soDon
WHERE soDon >= 2
RETURN c.id AS maKhach, c.name AS ten, soDon
ORDER BY maKhach;
~~~

Result:

| maKhach | ten | soDon |
|---|---|---:|
| C01 | An | 3 |
| C02 | Binh | 2 |

`WHERE soDon >= 2` filters **customers by the computed metric**, not individual orders. It is only meaningful once `soDon` already exists after aggregation.

### 4.1. Why Cannot count() Be Placed Directly in MATCH's WHERE?

The example below violates Cypher's aggregation syntax/semantics:

~~~cypher
// WRONG: do not use count() directly inside WHERE after MATCH
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE count(o) >= 2
RETURN c.id;
~~~

At the point where `WHERE` is attached to `MATCH`, Cypher is processing individual matched rows—there are no groups yet to compute `count(o)`. Create the groups with `WITH` first and then filter on the alias:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, count(o) AS soDon
WHERE soDon >= 2
RETURN c.id AS maKhach, soDon;
~~~

Make a clear distinction: `WHERE` after `MATCH` filters **source rows**; `WHERE` immediately after an aggregating `WITH` filters **grouped result rows**.

### 4.2. Filtering by Total Amount, Average, or Multiple Metrics

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
WITH
  c,
  count(o) AS soDonPaid,
  sum(o.amount) AS tongTienPaid,
  avg(o.amount) AS trungBinhPaid
WHERE soDonPaid >= 1 AND tongTienPaid >= 100000
RETURN
  c.id AS maKhach,
  soDonPaid,
  tongTienPaid,
  trungBinhPaid
ORDER BY maKhach;
~~~

The result contains C01 (2 orders, 250000, average 125000) and C02 (1 order, 200000, average 200000). C04 is excluded because their paid total is 50000.

You can use logical operators `AND`, `OR` to place multiple conditions on **aggregated metrics** just as shown above.

## 5. Comparing the Same Threshold with Different WHERE Placements

Consider two questions:

**Question A:** "Which customers have at least two **PAID orders**?"

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
WITH c, count(o) AS soDon
WHERE soDon >= 2
RETURN c.id AS maKhach, soDon;
~~~

Only C01 has `soDon = 2`.

**Question B:** "Which customers have at least two **orders of any status**?"

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, count(o) AS soDon
WHERE soDon >= 2
RETURN c.id AS maKhach, soDon
ORDER BY maKhach;
~~~

C01 has 3 orders; C02 has 2 orders. Query B places no restriction on order status.

If the requirement is "customers with at least two orders of any status, but display only their count of PAID orders", the two steps must be separated:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, count(o) AS tongSoDon
WHERE tongSoDon >= 2
OPTIONAL MATCH (c)-[:PLACED]->(paid:Order)
WHERE paid.status = 'PAID'
RETURN
  c.id AS maKhach,
  tongSoDon,
  count(paid) AS soDonPaid
ORDER BY maKhach;
~~~

| maKhach | tongSoDon | soDonPaid |
|---|---:|---:|
| C01 | 3 | 2 |
| C02 | 2 | 1 |

The first `WITH` identifies qualifying customers by **total order count**. The subsequent `OPTIONAL MATCH` then counts PAID orders for those customers. Do not move `WHERE o.status = 'PAID'` before `WITH` if customer eligibility must be based on **all orders**.

## 6. Identifying Implicit Grouping Keys in WITH

In an aggregating `WITH` projection, the non-aggregate expressions determine the grouping keys. The choice of grouping key directly affects subsequent filtering.

### 6.1. Grouping by Customer

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, count(o) AS soDon
WHERE soDon >= 2
RETURN c.id AS maKhach, soDon;
~~~

`c` is the grouping key, so `soDon` is the order count **for each customer node**.

### 6.2. Grouping by Status

~~~cypher
MATCH (o:Order)
WITH o.status AS trangThai, count(o) AS soDon
WHERE soDon >= 2
RETURN trangThai, soDon;
~~~

Only the `PAID` group remains with `soDon = 4`. `PENDING` and `CANCELLED` each have only one order.

### 6.3. Grouping by Customer and Status Pair

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c.id AS maKhach, o.status AS trangThai, count(o) AS soDon
WHERE soDon >= 2
RETURN maKhach, trangThai, soDon;
~~~

Only the pair `(C01, PAID)` has `soDon = 2`.

Ask before writing `WITH`: **does one row after this step represent a customer, a status, or a customer–status pair?** Any condition after `WITH` filters at that exact grain.

## 7. OPTIONAL MATCH: Preserving Customers Without Orders While Filtering

A report often must include customers who have not placed any orders yet. With a regular `MATCH`, customer C03 is dropped because they have no `PLACED` relationship. Use `OPTIONAL MATCH` to retain this customer.

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.id AS maKhach,
  count(o) AS tongSoDon
ORDER BY maKhach;
~~~

Result: C01 = 3, C02 = 2, C03 = 0, C04 = 1.

### 7.1. Filtering Inside OPTIONAL MATCH to Keep Customer Rows

To count **PAID orders** for *every customer*, including customers with no PAID orders, place `WHERE` immediately after `OPTIONAL MATCH`:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN
  c.id AS maKhach,
  count(o) AS soDonPaid,
  sum(o.amount) AS tongTienPaid
ORDER BY maKhach;
~~~

| maKhach | soDonPaid | tongTienPaid |
|---|---:|---:|
| C01 | 2 | 250000 |
| C02 | 1 | 200000 |
| C03 | 0 | 0 |
| C04 | 1 | 50000 |

In this case, `WHERE` is a condition on the **optional pattern match**. If no PAID order is found for a customer, `OPTIONAL MATCH` still keeps one row for that customer with `o = null`.

### 7.2. Moving the Condition After WITH Can Drop Customers

Compare:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, o
WHERE o.status = 'PAID'
RETURN c.id AS maKhach, count(o) AS soDonPaid
ORDER BY maKhach;
~~~

This query **no longer keeps C03**. Because the condition is placed in `WHERE` after `WITH c, o`, it acts as a filter on the already-produced rows. C03's row has `o = null`, so `o.status = 'PAID'` does not evaluate to `true` and is dropped.

Both `WHERE` placements can be valid depending on the requirement; placement decides whether unmatched groups are preserved.

### 7.3. Use count(o), Avoid count(*) When Counting Orders

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.id AS maKhach,
  count(*) AS soDong,
  count(o) AS soDon
ORDER BY maKhach;
~~~

For C03, `soDong = 1` while `soDon = 0`. `OPTIONAL MATCH` creates one row to preserve the customer, yet variable `o` is `null`. Therefore, if you want to count orders that actually exist, use `count(o)`.

## 8. Conditional Filtering Inside Aggregations

Sometimes you need total orders, paid orders, and paid total amount on **the same customer row**. If you filter with `WHERE o.status = 'PAID'` before grouping, orders with other statuses disappear from `tongSoDon`. In this situation, you can use `CASE` inside the aggregate functions:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH
  c,
  count(o) AS tongSoDon,
  count(CASE WHEN o.status = 'PAID' THEN o END) AS soDonPaid,
  sum(CASE WHEN o.status = 'PAID' THEN o.amount ELSE 0 END)
    AS tongTienPaid
WHERE tongSoDon >= 1
RETURN
  c.id AS maKhach,
  tongSoDon,
  soDonPaid,
  tongTienPaid
ORDER BY maKhach;
~~~

| maKhach | tongSoDon | soDonPaid | tongTienPaid |
|---|---:|---:|---:|
| C01 | 3 | 2 | 250000 |
| C02 | 2 | 1 | 200000 |
| C04 | 1 | 1 | 50000 |

`count(CASE WHEN ... THEN o END)` counts rows where `CASE` returns a non-`null` node `o`. `sum(CASE WHEN ... THEN o.amount ELSE 0 END)` sums only PAID order amounts; other rows contribute 0.

`WHERE tongSoDon >= 1` sits after `WITH`, so C03 is excluded from the final report even though C03 was retained in the pre-aggregation input set. To include C03 in the report as well, simply remove the filter after `WITH`.

Note: `CASE` is well suited when you need **multiple metrics with different conditions over the same row set**. If the entire report considers only PAID orders, `WHERE` before aggregation is usually simpler and easier to read.

## 9. WITH Also Manages Variable Scope

After `WITH`, only the variables and aliases passed through the projection are available in the next step. This both reduces carried data and gives rise to a few common errors.

For example:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, count(o) AS soDon
WHERE soDon >= 2
RETURN c.id AS maKhach, soDon;
~~~

In `RETURN`, we can still use `c` and `soDon`, but variable `o` is **no longer in scope**. This query will be invalid:

~~~cypher
// WRONG: o is not passed through WITH
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, count(o) AS soDon
WHERE soDon >= 2
RETURN c.id AS maKhach, o.id AS maDon;
~~~

If you add `o` into the aggregating `WITH` itself to "fix the error", the grouping key becomes `(c, o)`. Then `count(o)` may become 1 for each order, breaking the goal of counting orders **per customer**.

If you want both to filter groups by total order count and to retrieve details of each order, group first and then re-match the relationship:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, count(o) AS soDon
WHERE soDon >= 2
MATCH (c)-[:PLACED]->(chiTiet:Order)
RETURN
  c.id AS maKhach,
  soDon,
  chiTiet.id AS maDon
ORDER BY maKhach, maDon;
~~~

Result: three order rows for C01 and two order rows for C02; each detail row still carries its customer's `soDon`. **This query returns detail rows after filtering groups**, so the final result is no longer one row per customer.

## 10. Avoiding Double-Counting When Expanding Relationships

Aggregation grain can break if an order expands into multiple rows when traversing to products. Suppose the graph extends with:

~~~text
(:Order)-[:CONTAINS {quantity}]->(:Product)
~~~

If an order has three product line items, adding `MATCH (o)-[:CONTAINS]->(p)` causes that order to appear three times. Then `count(o)` counts **row occurrences**, and `sum(o.amount)` can add the order's amount multiple times.

Example simulating this scenario without adding sample data:

~~~cypher
UNWIND [
  {orderId: 'O1', amount: 100000, sku: 'P01'},
  {orderId: 'O1', amount: 100000, sku: 'P02'},
  {orderId: 'O2', amount: 50000, sku: 'P03'}
] AS dong
RETURN
  count(dong) AS soDongChiTiet,
  count(DISTINCT dong.orderId) AS soDonKhacNhau,
  sum(dong.amount) AS tongBiLap;
~~~

Result: `soDongChiTiet = 3`, `soDonKhacNhau = 2`, but `tongBiLap = 250000` instead of 150000.

The safe approach is to compute order metrics **before** expanding to detail relationships, and only then filter groups:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
WITH c, count(o) AS soDonPaid, sum(o.amount) AS tongTienPaid
WHERE tongTienPaid >= 200000
RETURN
  c.id AS maKhach,
  soDonPaid,
  tongTienPaid
ORDER BY maKhach;
~~~

The result keeps C01 and C02. Because aggregation is performed on each PAID order right after `PLACED`, no many-to-many expansion has multiplied the rows yet. If you need product details for those qualifying customers, run the next `MATCH` **after `WITH ... WHERE`**.

## 11. Performance: Filter as Early as Possible, While Preserving Semantics

A pre-aggregation filter typically reduces the amount of data the aggregation operator must process. A post-aggregation filter reduces **the number of groups passed to later steps**, but it does not eliminate the aggregation cost that has already occurred.

Example:

~~~cypher
PROFILE
MATCH (o:Order)
WHERE o.status = 'PAID'
WITH o.status AS trangThai, count(o) AS soDon
WHERE soDon >= 2
RETURN trangThai, soDon;
~~~

With the sample data:

| Step | Meaningful Row Count |
|---|---:|
| `MATCH (o:Order)` before status filter | 6 orders |
| `WHERE o.status = 'PAID'` | 4 orders |
| `WITH ... count(o)` grouped by `o.status` | 1 group |
| `WHERE soDon >= 2` | 1 group |

`PROFILE` shows the actual number of rows flowing through each operator in the plan chosen by Neo4j; the table above is a logical trace of the sample dataset, not a fixed prediction of the operator structure or order in every execution plan.

Guidelines when tuning queries:

- **Place conditions on source data in the right spot**: filter on `status`, `amount`, or customer ID before aggregation when those conditions are part of the metric definition.
- **Place conditions on metrics after `WITH`**: `soDon >= 2`, `tongTien > 100000` only make sense after grouping.
- **Choose the right grouping key**: adding a non-aggregate property to `WITH` can create many more groups and change the metrics.
- **Avoid expanding relationships too early**: a node with many relationships can repeat across rows before `sum` or `count`.
- **Inspect `EXPLAIN` / `PROFILE`**: evaluate input row counts, relationship traversals, and aggregation operators on realistic data. Indexes help locate starting points when appropriate, but do not guarantee removing aggregation cost.

If a Java Driver or Spring Data Neo4j application needs a grouped report, it is better to let Cypher aggregate and filter the necessary results before returning records to the application, rather than loading all orders into Java to sum manually.

## 12. Practice Exercises

### Exercise 1. Only Customers with at Least Two PAID Orders

Return customer ID, name, PAID order count, and PAID total amount. With the sample data, the result must contain only C01.

<details>
<summary>Solution</summary>

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
WITH c, count(o) AS soDonPaid, sum(o.amount) AS tongTienPaid
WHERE soDonPaid >= 2
RETURN c.id AS maKhach, c.name AS ten, soDonPaid, tongTienPaid;
~~~

Result: C01 / An / 2 / 250000.

</details>

### Exercise 2. Orders Over 100000 VND, Then Filter Groups by Total Amount

Requirement: first consider only orders with `amount >= 100000` (regardless of status), then keep only customers whose total value from those orders is **at least 200000**.

<details>
<summary>Solution</summary>

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE o.amount >= 100000
WITH c, count(o) AS soDonDatNguong, sum(o.amount) AS tongTienDatNguong
WHERE tongTienDatNguong >= 200000
RETURN c.id AS maKhach, soDonDatNguong, tongTienDatNguong
ORDER BY maKhach;
~~~

C01 has 2 qualifying orders totaling 250000; C02 has 1 qualifying order totaling 200000. C04 is excluded because they only have one 50000 order.

</details>

### Exercise 3. Keeping Customers Without Orders

Requirement: return all customers along with their PAID order count; use `OPTIONAL MATCH` so C03 still appears with `soDonPaid = 0`.

<details>
<summary>Solution</summary>

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN c.id AS maKhach, count(o) AS soDonPaid
ORDER BY maKhach;
~~~

C01 = 2, C02 = 1, C03 = 0, C04 = 1.

</details>

### Exercise 4. Identifying Wrong Filter Placement

Consider the query:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
WITH c, count(o) AS soDon
WHERE soDon >= 2
RETURN c.id AS maKhach, soDon;
~~~

A new requirement asks for "customers with at least two **orders of any status**, then summarize the count of PAID orders". Explain why this query does not meet the requirement and rewrite it.

<details>
<summary>Solution</summary>

`WHERE o.status = 'PAID'` sits before `count(o)`, so the count reflects only PAID orders. C02 has two orders overall but only one PAID order, so they are wrongly excluded. You must aggregate all orders first, filter qualifying customers, and then count PAID orders in a separate step:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, count(o) AS tongSoDon
WHERE tongSoDon >= 2
OPTIONAL MATCH (c)-[:PLACED]->(paid:Order)
WHERE paid.status = 'PAID'
RETURN c.id AS maKhach, tongSoDon, count(paid) AS soDonPaid
ORDER BY maKhach;
~~~

The result contains C01 / 3 / 2 and C02 / 2 / 1.

</details>

## 13. Key Takeaways

- **Pre-aggregation filtering** using `WHERE` in the `MATCH` step decides **which rows participate** in `count`, `sum`, `avg`, etc.
- **Post-aggregation filtering** using `WITH ... AS alias WHERE alias ...` decides **which groups are kept**.
- To filter on `count` or `sum`, create an alias in `WITH` and then use `WHERE`. Do not write aggregate functions directly inside `MATCH`'s `WHERE`.
- Non-aggregate expressions in `WITH` determine the **implicit grouping keys**; adding a key can completely change the level of calculation.
- `OPTIONAL MATCH ... WHERE` preserves the root entity when the optional pattern does not match; moving the condition down to `WITH ... WHERE` can drop `null` rows.
- `WITH` controls **variable scope**. If you want to filter customers by order count and then retrieve individual orders, aggregate and filter first, then re-match the relationship.
- Optimize by reducing source rows before aggregation and reducing groups before subsequent expansions, while ensuring filter placement **matches the business question**.
