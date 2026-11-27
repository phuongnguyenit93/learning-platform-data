# count, sum, avg, min, and max in Graph Queries

In Neo4j, data is stored as **nodes**, **relationships**, and **properties**. When querying with Cypher, you often want not only to retrieve related nodes, but also to answer questions such as: how many orders has a customer placed, what is the total order value, what is the average, or who placed the largest order. The five aggregate functions `count()`, `sum()`, `avg()`, `min()`, and `max()` address these needs.

A distinctive characteristic of graph queries is that **each matched path can produce an intermediate result row**. Therefore, before aggregating, you need to understand how many rows Cypher currently has and whether a node appears repeatedly across multiple paths.

## 1. Sample Data and Goal

Consider a bookstore model:

~~~text
(:Customer)-[:PLACED]->(:Order)-[:HAS_ITEM {quantity}]->(:Product)
~~~

- `Customer`: customer; has `id` and `name`.
- `Order`: order; has `id`, `amount` (order value, in VND), and `status`.
- `Product`: product; has `sku` and `name`.
- `HAS_ITEM.quantity`: quantity of a product ordered in an order line item.

Create a small dataset so you can run all the examples below yourself on an empty practice database:

~~~cypher
CREATE
  (an:Customer {id: 'C01', name: 'An'}),
  (binh:Customer {id: 'C02', name: 'Binh'}),
  (chi:Customer {id: 'C03', name: 'Chi'}),
  (o101:Order {id: 'O101', amount: 120000, status: 'PAID'}),
  (o102:Order {id: 'O102', amount: 80000,  status: 'PAID'}),
  (o103:Order {id: 'O103', amount: 200000, status: 'PENDING'}),
  (neo4j:Product {sku: 'P01', name: 'Neo4j'}),
  (java:Product {sku: 'P02', name: 'Java'}),
  (an)-[:PLACED]->(o101),
  (an)-[:PLACED]->(o102),
  (binh)-[:PLACED]->(o103),
  (o101)-[:HAS_ITEM {quantity: 1}]->(neo4j),
  (o101)-[:HAS_ITEM {quantity: 2}]->(java),
  (o102)-[:HAS_ITEM {quantity: 1}]->(java),
  (o103)-[:HAS_ITEM {quantity: 3}]->(neo4j);
~~~

Run the `CREATE` statement **once** on an empty practice database to avoid creating duplicate data. In this dataset, An has two orders, Binh has one order, and Chi has no orders yet. Order O101 contains two types of products; this detail helps observe row multiplication when traversing additional relationships.

## 2. How Do the Five Aggregate Functions Work?

| Function | Meaning | Common Result |
|---|---|---|
| `count(*)` | Counts all rows entering the aggregation, including rows with `null` in a variable | Number of rows/matched paths |
| `count(x)` | Counts rows where the expression `x` is non-`null` | Number of present nodes, relationships, or values |
| `sum(x)` | Sums non-`null` numeric values | Total revenue, total quantity |
| `avg(x)` | Arithmetic mean of non-`null` numeric values | Average order value |
| `min(x)`, `max(x)` | Returns the minimum/maximum among comparable values, ignoring `null` | Lower/upper bound of a set |

Aggregate functions collapse multiple rows into one row per **group**. If a `RETURN` or `WITH` clause contains only aggregate expressions, Cypher creates a single overall group. If there are also non-aggregate expressions, such as `c.name` or `o.status`, those expressions become **grouping keys**.

For example, summarizing all orders:

~~~cypher
MATCH (o:Order)
RETURN
  count(o) AS soDon,
  sum(o.amount) AS tongGiaTri,
  avg(o.amount) AS trungBinh,
  min(o.amount) AS thapNhat,
  max(o.amount) AS caoNhat;
~~~

Expected result: `soDon = 3`, `tongGiaTri = 400000`, `trungBinh ≈ 133333.33`, `thapNhat = 80000`, `caoNhat = 200000`. The average value may be displayed with more decimal places.

## 3. count(): Counting the Right Target

### 3.1. Distinguishing count(*) and count(expression)

With `MATCH (o:Order)`, each order produces one row, so both `count(*)` and `count(o)` are 3. However, when using `OPTIONAL MATCH`, a customer without orders is still preserved, with the variable `o` holding `null`:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.name AS khachHang,
  count(*) AS soDong,
  count(o) AS soDon
ORDER BY khachHang;
~~~

| khachHang | soDong | soDon |
|---|---:|---:|
| An | 2 | 2 |
| Binh | 1 | 1 |
| Chi | 1 | 0 |

Chi still produces **one row due to `OPTIONAL MATCH`**, but this row has no `o` node. Therefore:

- Use `count(*)` when you truly want to know the number of intermediate rows.
- Use `count(o)` when you want to count existing orders, especially after `OPTIONAL MATCH`.
- Use `count(o.amount)` if the goal is to count non-`null` `amount` values, because an existing node can still be missing a property.

### 3.2. count(DISTINCT ...): Eliminating Repeated Occurrences

When expanding from orders to products, O101 appears twice because it has two `HAS_ITEM` relationships:

~~~cypher
MATCH (o:Order)-[:HAS_ITEM]->(p:Product)
RETURN
  count(*) AS soDongChiTiet,
  count(o) AS soLanXuatHienCuaDon,
  count(DISTINCT o) AS soDonKhacNhau;
~~~

Result: `soDongChiTiet = 4`, `soLanXuatHienCuaDon = 4`, but `soDonKhacNhau = 3`.

`DISTINCT` operates on the value of the expression being counted. `count(DISTINCT o)` counts the number of distinct order nodes, while `count(DISTINCT o.status)` counts the number of distinct status values (2 in the sample data). You need to choose the exact unit to count: row, order, relationship, or status.

## 4. sum() and avg(): Sum and Average

### 4.1. Aggregating on Node Properties

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN
  c.name AS khachHang,
  count(o) AS soDon,
  sum(o.amount) AS tongGiaTri,
  avg(o.amount) AS giaTriTrungBinh
ORDER BY khachHang;
~~~

| khachHang | soDon | tongGiaTri | giaTriTrungBinh |
|---|---:|---:|---:|
| An | 2 | 200000 | 100000.0 |
| Binh | 1 | 200000 | 200000.0 |

Chi does not appear because a regular `MATCH` filters out customers that do not match the relationship. If the report must include customers who have not made a purchase yet, use `OPTIONAL MATCH`:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.name AS khachHang,
  count(o) AS soDon,
  coalesce(sum(o.amount), 0) AS tongGiaTri,
  avg(o.amount) AS giaTriTrungBinh
ORDER BY khachHang;
~~~

Chi has `soDon = 0`, `tongGiaTri = 0`, and `giaTriTrungBinh = null`. `avg()` cannot compute an average when there are no valid values. You should not replace `null` with 0 by default for an average if 0 would mislead readers into thinking there was an observation with value 0.

### 4.2. Aggregating Relationship Properties

A metric in a graph often resides on a **relationship**, such as the quantity of each product in an order:

~~~cypher
MATCH (o:Order)-[item:HAS_ITEM]->(p:Product)
RETURN
  p.name AS sanPham,
  count(item) AS soDongDonHang,
  sum(item.quantity) AS tongSoLuong
ORDER BY sanPham;
~~~

| sanPham | soDongDonHang | tongSoLuong |
|---|---:|---:|
| Java | 2 | 3 |
| Neo4j | 2 | 4 |

Here `sum(item.quantity)` sums the quantity across each `HAS_ITEM` relationship. `count(item)`, on the other hand, counts the number of relationship rows, not the number of books. The two metrics have different business meanings.

### 4.3. Aggregating Only a Subset

The value of pending orders is not collected revenue. Filter before aggregating:

~~~cypher
MATCH (o:Order)
WHERE o.status = 'PAID'
RETURN
  count(o) AS soDonDaThanhToan,
  sum(o.amount) AS doanhThuDaThanhToan,
  avg(o.amount) AS trungBinhDonDaThanhToan;
~~~

The results are `2`, `200000`, and `100000.0` respectively. The `WHERE` condition determines **which rows enter the aggregate function**.

In real systems, to avoid rounding errors when calculating money, monetary values can be stored as integers in the appropriate smallest currency unit (for example, integer VND), rather than using binary floating-point numbers for additions requiring exact precision.

## 5. min() and max(): Finding Extrema

~~~cypher
MATCH (o:Order)
RETURN
  min(o.amount) AS donNhoNhat,
  max(o.amount) AS donLonNhat;
~~~

The results are `80000` and `200000`. These two functions return the **extreme value**, not automatically the corresponding order node. To know which order has the highest value, sort the orders and take the first row:

~~~cypher
MATCH (o:Order)
RETURN o.id AS maDon, o.amount AS giaTri
ORDER BY giaTri DESC, maDon ASC
LIMIT 1;
~~~

The result is order `O103`, with value `200000`. The secondary sort `maDon ASC` makes the result deterministic when multiple orders share the same value; `LIMIT 1` returns only one order in case of a tie.

`min()` and `max()` are also useful for comparable ordered values, such as start/end timestamps stored as `date` or `datetime`. For a meaningful report, values passed into the same aggregation should share a consistent data type and business meaning.

## 6. Grouping Data with RETURN and WITH

In Cypher, you do not need to declare a separate `GROUP BY`. The **non-aggregate** expressions in the same projection determine the groups.

~~~cypher
MATCH (o:Order)
RETURN
  o.status AS trangThai,
  count(*) AS soDon,
  sum(o.amount) AS tongGiaTri,
  avg(o.amount) AS trungBinh
ORDER BY trangThai;
~~~

| trangThai | soDon | tongGiaTri | trungBinh |
|---|---:|---:|---:|
| PAID | 2 | 200000 | 100000.0 |
| PENDING | 1 | 200000 | 200000.0 |

The `WITH` clause can also perform aggregation and pass results to the next step. For example, finding customers with at least two orders:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, count(o) AS soDon, sum(o.amount) AS tongGiaTri
WHERE soDon >= 2
RETURN c.name AS khachHang, soDon, tongGiaTri
ORDER BY soDon DESC;
~~~

Only An satisfies the condition. Here `WHERE soDon >= 2` runs **after** the aggregation step in `WITH`, so it can filter on the counted result.

Important rule: before every `RETURN` or `WITH` step containing an aggregate function, clearly identify the grouping keys. Adding a non-aggregate variable to `RETURN` can split one large group into many smaller groups and change the entire result.

## 7. null, Empty Results, and OPTIONAL MATCH

Most aggregate functions ignore `null` values in the input expression. Observe this standalone example:

~~~cypher
UNWIND [10, null, 20] AS x
RETURN
  count(*) AS soDong,
  count(x) AS soGiaTri,
  sum(x) AS tong,
  avg(x) AS trungBinh,
  min(x) AS nhoNhat,
  max(x) AS lonNhat;
~~~

Result: `soDong = 3`, `soGiaTri = 2`, `tong = 30`, `trungBinh = 15.0`, `nhoNhat = 10`, `lonNhat = 20`.

When there are no valid numeric values, `avg()` returns `null`; `min()` and `max()` also return `null` if there are no values to compare. `count()` returns 0 when there are no values to count; `sum()` returns 0 when there are no values to add. You need to distinguish "no observations" from "observation with value 0", especially when displaying reports.

With `OPTIONAL MATCH`, place `WHERE` immediately after the optional relationship pattern to still retain customers without matching orders:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN
  c.name AS khachHang,
  count(o) AS soDonDaThanhToan,
  sum(o.amount) AS tongDaThanhToan
ORDER BY khachHang;
~~~

Results in order An/Binh/Chi: paid order count is `2/0/0`; paid total amount is `200000/0/0`. This `WHERE` condition is attached to `OPTIONAL MATCH`, so Binh and Chi are still retained.

If you need **multiple conditional metrics in a single traversal**, you can combine `CASE` with aggregation:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.name AS khachHang,
  count(o) AS tongSoDon,
  count(CASE WHEN o.status = 'PAID' THEN o END) AS donDaThanhToan,
  sum(CASE WHEN o.status = 'PAID' THEN o.amount ELSE 0 END)
    AS tienDaThanhToan
ORDER BY khachHang;
~~~

This approach counts all orders with `count(o)`, but only sums values for orders with status `PAID`. Check the `ELSE` branch in `CASE` carefully: returning `0` means that row contributes 0 to the sum, whereas omitting `ELSE` usually produces `null` and is ignored by the aggregate function.

## 8. Common Pitfall: A Node Counted Multiple Times After Expanding Relationships

Consider the following query:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
MATCH (o)-[:HAS_ITEM]->(p:Product)
RETURN c.name AS khachHang, sum(o.amount) AS tongGiaTri
ORDER BY khachHang;
~~~

For An, order O101 appears **twice** because it connects to two products. As a result, the query returns `320000` for An (`120000 + 120000 + 80000`) instead of `200000`. The query is syntactically valid, but **it is summing over product line-item rows** rather than over individual orders.

The fix is to aggregate by order **before** expanding to the detail relationship, and only then calculate product quantities:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH
  c,
  count(o) AS soDon,
  sum(o.amount) AS tongGiaTriDon
OPTIONAL MATCH (c)-[:PLACED]->(:Order)-[item:HAS_ITEM]->(:Product)
RETURN
  c.name AS khachHang,
  soDon,
  tongGiaTriDon,
  sum(item.quantity) AS tongSoLuong
ORDER BY khachHang;
~~~

Expected result:

| khachHang | soDon | tongGiaTriDon | tongSoLuong |
|---|---:|---:|---:|
| An | 2 | 200000 | 4 |
| Binh | 1 | 200000 | 3 |
| Chi | 0 | 0 | 0 |

Do not fix the pitfall above with `sum(DISTINCT o.amount)`. If two different orders happen to have `amount = 120000`, `DISTINCT` on the **monetary value** will mistakenly collapse them into one. Only use `DISTINCT` when you genuinely want to remove duplicate values according to the exact definition of the metric.

A safe principle when writing graph queries is: **choose the aggregation unit (customer, order, product, or relationship) first, then check the row count after each `MATCH`**. Multiple relationship branches or multiple independent `MATCH` patterns can cause the row count to grow rapidly and double-count summed values.

## 9. Performance and Result Verification

On large graphs, query cost depends not only on addition or counting operations, but also on the number of traversed nodes/relationships and the number of rows passing through the aggregation step.

- **Filter early:** if you only need paid orders, place `WHERE o.status = 'PAID'` before the aggregation to reduce the number of rows processed.
- **Aggregate at the right time:** use `WITH` to group results before expanding additional relationships that are unnecessary for the metric being computed.
- **Be mindful of DISTINCT:** deduplicate only on the exact entity to be counted; deduplicating over a large result set also consumes memory and time.
- **Inspect the execution plan:** `EXPLAIN` shows the planned execution, while `PROFILE` executes the query and displays the actual row counts flowing through operators. Compare row counts before and after traversing relationships to detect unintended multiplication.
- **Check index filtering:** for properties frequently used in filter conditions, an appropriate index can help find input nodes faster; inspect the actual plan rather than assuming every aggregate query uses an index.

Example of inspecting the query that summarizes paid orders:

~~~cypher
PROFILE
MATCH (o:Order)
WHERE o.status = 'PAID'
RETURN count(o) AS soDonDaThanhToan;
~~~

When testing, check at least three scenarios: nodes with multiple relationships, nodes with no relationships, and missing/`null` properties. Errors in aggregation results are most likely to surface under these conditions.

## 10. Practice Exercises

**Exercise 1.** Write a query to summarize the total quantity ordered for each product, including products that have not been ordered yet. With the sample data, Java has 3 units and Neo4j has 4 units.

<details>
<summary>Suggested Answer</summary>

~~~cypher
MATCH (p:Product)
OPTIONAL MATCH (:Order)-[item:HAS_ITEM]->(p)
RETURN
  p.name AS sanPham,
  count(item) AS soDongDonHang,
  sum(item.quantity) AS tongSoLuong
ORDER BY sanPham;
~~~

</details>

**Exercise 2.** List every customer along with their order count and maximum order value. Customers who have never placed an order must appear with an order count of 0 and a maximum value of `null`.

<details>
<summary>Suggested Answer</summary>

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.name AS khachHang,
  count(o) AS soDon,
  max(o.amount) AS giaTriLonNhat
ORDER BY khachHang;
~~~

</details>

**Exercise 3.** A query starts at `Order`, traverses to `Product`, and then uses `sum(o.amount)` to calculate the total amount. Explain why the result may be larger than the actual total, and rewrite the query so each order is added only once. You can use the `WITH` pattern in section 8 for reference.

## Key Takeaways

- `count(*)` counts **rows**; `count(x)` counts **non-null** values; `count(DISTINCT x)` counts distinct values.
- `sum()` and `avg()` operate on numbers; `min()` and `max()` find extrema; most aggregations ignore `null`.
- Non-aggregate expressions in `RETURN` or `WITH` determine the **grouping keys**.
- `OPTIONAL MATCH` retains nodes without matching relationships, making it especially useful for reports that must also show groups with a value of 0.
- Before summing or counting in a graph, you must understand **how many times an entity appears in the intermediate row set**. This is what determines the correctness of a Cypher aggregate query.
