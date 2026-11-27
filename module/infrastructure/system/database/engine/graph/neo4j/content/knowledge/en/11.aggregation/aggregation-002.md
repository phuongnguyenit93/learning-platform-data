# Implicit Grouping Keys and Identifying Aggregation Grain

In Neo4j, many Cypher queries must turn sets of nodes, relationships, and matched paths into a report: order count per customer, revenue by status, or number of products in each order. Functions such as `count()`, `sum()`, `avg()`, `min()`, and `max()` aggregate data, but there is a decision even more important than choosing the function: **what entity or group does each result row represent?**

Unlike SQL, which typically uses a `GROUP BY` clause, Cypher infers **implicit grouping keys** from the expressions projected in `WITH` or `RETURN`. Therefore, simply adding a property to `RETURN` can change the aggregation grain. In a *property graph* system, the number of matched paths before the aggregation step can also increase when a query traverses multiple relationships.

This lesson focuses on identifying and controlling the **aggregation grain**: whether one row represents the entire graph, a status, a customer, a customer–status pair, or a product line item.

## 1. Sample Data: Observing a Row Set That Can Multiply

Consider a bookstore model:

~~~text
(:Customer)-[:PLACED]->(:Order)-[:CONTAINS {quantity}]->(:Product)
~~~

`Customer` has `id`, `name`; `Order` has `id`, `amount` (VND), `status`; `Product` has `sku`, `name`; the `CONTAINS` relationship has `quantity`.

Create the dataset in an **empty practice database** (run `CREATE` only once):

~~~cypher
CREATE
  (c01:Customer {id: 'C01', name: 'An'}),
  (c02:Customer {id: 'C02', name: 'Binh'}),
  (c03:Customer {id: 'C03', name: 'An'}),
  (c04:Customer {id: 'C04', name: 'Chi'}),
  (o101:Order {id: 'O101', amount: 100000, status: 'PAID'}),
  (o102:Order {id: 'O102', amount: 200000, status: 'PAID'}),
  (o103:Order {id: 'O103', amount: 150000, status: 'PENDING'}),
  (o104:Order {id: 'O104', amount: 50000, status: 'PAID'}),
  (p01:Product {sku: 'P01', name: 'Graph'}),
  (p02:Product {sku: 'P02', name: 'Java'}),
  (c01)-[:PLACED]->(o101),
  (c01)-[:PLACED]->(o102),
  (c02)-[:PLACED]->(o103),
  (c03)-[:PLACED]->(o104),
  (o101)-[:CONTAINS {quantity: 1}]->(p01),
  (o101)-[:CONTAINS {quantity: 2}]->(p02),
  (o102)-[:CONTAINS {quantity: 1}]->(p01),
  (o103)-[:CONTAINS {quantity: 3}]->(p02),
  (o104)-[:CONTAINS {quantity: 1}]->(p01);
~~~

The dataset has **4 customers, 4 orders, 5 `CONTAINS` relationships**:

| Customer ID | Name | Orders | Total Order Value |
|---|---|---|---:|
| C01 | An | O101, O102 | 300000 |
| C02 | Binh | O103 | 150000 |
| C03 | An | O104 | 50000 |
| C04 | Chi | None | 0 |

Two different customers (C01 and C03) share the name `An`. O101 contains two products, so it produces **two rows** if queried from orders down to product line items. These two cases help test two specific risks: **merging unrelated groups** and **double-counting during row multiplication**.

## 2. What Is an Implicit Grouping Key?

In a projection containing aggregate functions (`WITH` or `RETURN`), you can think of expressions as falling into two categories:

1. **Aggregate expressions:** `count(o)`, `sum(o.amount)`, `avg(o.amount)`, etc., which compute a value from multiple rows.
2. **Non-aggregate expressions:** `c`, `c.id`, `c.name`, `o.status`, etc., which define the **implicit grouping keys**.

For each **distinct combination of grouping key values**, Cypher returns one aggregated row. If there are no grouping keys, the entire input row set is aggregated into a single overall group.

For example:

~~~cypher
MATCH (o:Order)
RETURN count(o) AS soDon, sum(o.amount) AS tongTien;
~~~

Result:

| soDon | tongTien |
|---:|---:|
| 4 | 500000 |

There are no expressions outside aggregate functions in `RETURN`, so there is **one group** and **one result row**.

Add `o.status`:

~~~cypher
MATCH (o:Order)
RETURN
  o.status AS trangThai,
  count(o) AS soDon,
  sum(o.amount) AS tongTien
ORDER BY trangThai;
~~~

| trangThai | soDon | tongTien |
|---|---:|---:|
| PAID | 3 | 350000 |
| PENDING | 1 | 150000 |

Here `o.status` is the implicit grouping key. Orders are split into two groups, `PAID` and `PENDING`, even though `GROUP BY` is **never written** in the query.

You can read the query flow as:

~~~text
MATCH produces input rows
    ↓
Select grouping keys from non-aggregate expressions
    ↓
Group rows with the same tuple of key values
    ↓
Compute count/sum/avg... on each group
    ↓
RETURN one row per group
~~~

The clause `AS trangThai` only names the output column; it does not remove the grouping-key role of `o.status`.

## 3. Identifying Aggregation Grain by Grouping Key Count and Identity

**Aggregation grain** is the answer to the question: "What does one row after `WITH` or `RETURN` represent?". Look at both the **non-aggregate expressions** and the **input row count**.

| Implicit Grouping Key | One Row Represents | Example Output |
|---|---|---|
| No key | The entire input set | 4 orders |
| `o.status` | One order status | PAID, PENDING |
| `c` | One specific customer node | C01, C02, C03, C04 |
| `c.id` | One customer ID | C01, C02, C03, C04 |
| `c.name` | One **name value**, which may include multiple customers | An, Binh, Chi |
| `c.id` and `o.status` | One customer–status pair | (C01, PAID), (C02, PENDING)... |

### 3.1. One Group per Customer

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.id AS maKhach,
  c.name AS ten,
  count(o) AS soDon,
  sum(o.amount) AS tongTien
ORDER BY maKhach;
~~~

| maKhach | ten | soDon | tongTien |
|---|---|---:|---:|
| C01 | An | 2 | 300000 |
| C02 | Binh | 1 | 150000 |
| C03 | An | 1 | 50000 |
| C04 | Chi | 0 | 0 |

Both `c.id` and `c.name` act together as grouping keys. Because `id` in the sample data is unique, each customer appears in only one group. `OPTIONAL MATCH` retains C04 even though that customer has no orders.

You can also group directly by node:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, count(o) AS soDon
RETURN c.id AS maKhach, c.name AS ten, soDon
ORDER BY maKhach;
~~~

In the `WITH c, count(o)` step, **the node `c` itself** is the grouping key. Two nodes with the property `name = 'An'` are still two distinct nodes, so they are not merged.

### 3.2. Mistake When Using a Display Attribute as a Key

If you replace customer ID with name:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.name AS ten,
  count(o) AS soDon,
  sum(o.amount) AS tongTien
ORDER BY ten;
~~~

| ten | soDon | tongTien |
|---|---:|---:|
| An | 3 | 350000 |
| Binh | 1 | 150000 |
| Chi | 0 | 0 |

This query is **correct if you want to group by name**, but **wrong if the report requires individual customers**: C01 and C03 are both named An, so they are merged into one group.

**Rule:** if you want one row to represent one entity, use that node or a genuinely unique business identifier key (for example `c.id`). Display attributes such as name, label, or city may not be unique.

### 3.3. Adding a Key Makes the Aggregation Grain Finer

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN
  c.id AS maKhach,
  o.status AS trangThai,
  count(o) AS soDon
ORDER BY maKhach, trangThai;
~~~

The key pair `(c.id, o.status)` identifies **one customer in one status**, rather than all orders of that customer. With the sample data, the groups are:

| maKhach | trangThai | soDon |
|---|---|---:|
| C01 | PAID | 2 |
| C02 | PENDING | 1 |
| C03 | PAID | 1 |

If you only need total orders by status, omit `c.id` from the projection:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN o.status AS trangThai, count(o) AS soDon
ORDER BY trangThai;
~~~

The result returns to two groups: `PAID = 3`, `PENDING = 1`. Adding or removing **a grouping key** changes the question the query is answering.

## 4. WITH Can Change the Aggregation Grain at Each Stage

`WITH` does not merely pass data between parts of a query. When it contains aggregate functions, it **locks in the result at a new aggregation grain** and passes the grouped rows to the next stage.

### 4.1. Aggregate by Customer First, Then Process Further

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH
  c,
  count(o) AS soDon,
  sum(o.amount) AS tongTien
WHERE soDon >= 2
RETURN
  c.id AS maKhach,
  c.name AS ten,
  soDon,
  tongTien;
~~~

`WITH` groups by node `c` and computes `soDon` and `tongTien`. The `WHERE` after `WITH` filters **the already-computed groups**, so only C01 remains with `soDon = 2`, `tongTien = 300000`.

Note: after `WITH c, count(o) AS soDon, ...`, the variable `o` is no longer carried forward. If you need `o` later, you must redesign the projection or query accordingly; including `o` in the same aggregating `WITH` would also change the grouping key.

### 4.2. From Customer Grain Back to Name Grain

You can intentionally perform **two levels of aggregation**:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, count(o) AS soDonTheoKhach, sum(o.amount) AS tienTheoKhach
RETURN
  c.name AS ten,
  sum(soDonTheoKhach) AS tongSoDon,
  sum(tienTheoKhach) AS tongTien
ORDER BY ten;
~~~

First stage: one row **per customer node**. Second stage: one row **per name value**.

| ten | tongSoDon | tongTien |
|---|---:|---:|
| An | 3 | 350000 |
| Binh | 1 | 150000 |
| Chi | 0 | 0 |

Using two stages is reasonable when you need a summary report from metrics already calculated per entity. However, only merge by name when that is the business intent.

### 4.3. Grouping by a Computed Classification

A grouping key does not have to be an existing property. You can compute a classification before aggregating:

~~~cypher
MATCH (o:Order)
WITH
  o,
  CASE
    WHEN o.amount >= 150000 THEN '150k and above'
    ELSE 'Under 150k'
  END AS nhomGiaTri
RETURN
  nhomGiaTri,
  count(o) AS soDon,
  sum(o.amount) AS tongTien
ORDER BY nhomGiaTri;
~~~

| nhomGiaTri | soDon | tongTien |
|---|---:|---:|
| 150k and above | 2 | 350000 |
| Under 150k | 2 | 150000 |

In the `WITH` step there is no aggregation yet, so each order remains one row. In `RETURN`, only `nhomGiaTri` is the grouping key; `o` is passed into `count(o)` and `sum(o.amount)`.

You should separate complex computed expressions via `WITH` as shown above. Mixing aggregate functions directly into expressions with non-aggregate expressions makes grouping keys harder to identify and can run into the **implicit grouping expressions** rules of your Cypher version.

## 5. Row Count Before Aggregation Determines the Result

**Having the right grouping key is still not enough** if the input rows have already multiplied due to traversing relationships.

Consider a query from customer through order to product:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
MATCH (o)-[line:CONTAINS]->(p:Product)
RETURN
  c.id AS maKhach,
  count(o) AS soLanDonXuatHien,
  count(DISTINCT o) AS soDonThuc,
  sum(o.amount) AS tongTienTinhTheoDong,
  sum(line.quantity) AS soLuongSanPham
ORDER BY maKhach;
~~~

| maKhach | soLanDonXuatHien | soDonThuc | tongTienTinhTheoDong | soLuongSanPham |
|---|---:|---:|---:|---:|
| C01 | 3 | 2 | 400000 | 4 |
| C02 | 1 | 1 | 150000 | 3 |
| C03 | 1 | 1 | 50000 | 1 |

C01's order O101 has two `CONTAINS` relationships, so the value `100000` appears **twice**. `sum(o.amount) = 400000` is aggregating at the **product line-item** grain, whereas C01's actual revenue is only `300000`.

`count(DISTINCT o)` fixes the **distinct order count**, but does not automatically fix `sum(o.amount)`. In particular, `sum(DISTINCT o.amount)` is also not a general way to calculate revenue: if two orders legitimately have the same amount, that function will mistakenly collapse those two monetary values.

### 5.1. Place the Aggregation at the Right Level Before Expanding

Compute the order count and amount **before** traversing down to product line items:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH
  c,
  count(o) AS soDon,
  sum(o.amount) AS tongTien
OPTIONAL MATCH (c)-[:PLACED]->(:Order)-[line:CONTAINS]->(:Product)
RETURN
  c.id AS maKhach,
  c.name AS ten,
  soDon,
  tongTien,
  sum(line.quantity) AS soLuongSanPham
ORDER BY maKhach;
~~~

| maKhach | ten | soDon | tongTien | soLuongSanPham |
|---|---|---:|---:|---:|
| C01 | An | 2 | 300000 | 4 |
| C02 | Binh | 1 | 150000 | 3 |
| C03 | An | 1 | 50000 | 1 |
| C04 | Chi | 0 | 0 | 0 |

The first `WITH` groups orders by `c`, so `tongTien` is computed accurately and has only one value per customer. The subsequent `OPTIONAL MATCH` can multiply rows by product, but only `line.quantity` needs to be summed at that detail grain. The columns `maKhach`, `ten`, `soDon`, and `tongTien` become grouping keys in the final `RETURN`.

An effective way to think about this is to distinguish the **grain of the source data** (order, product line item) from the **grain of the metric** (order count, revenue, units sold). Each metric should be aggregated over the exact row set of its corresponding grain.

## 6. OPTIONAL MATCH, null, and Empty Groups

With a regular `MATCH`, customers without orders are excluded from the row set. `OPTIONAL MATCH` keeps those customers and assigns `null` to unmatched variables.

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.id AS maKhach,
  count(*) AS soDong,
  count(o) AS soDon
ORDER BY maKhach;
~~~

| maKhach | soDong | soDon |
|---|---:|---:|
| C01 | 2 | 2 |
| C02 | 1 | 1 |
| C03 | 1 | 1 |
| C04 | 1 | 0 |

In group C04, `count(*) = 1` because there is still one result row from `OPTIONAL MATCH`; `count(o) = 0` because there is no order node. When reporting the number of related entities, you usually want `count(o)` instead of `count(*)`.

### 6.1. When a Grouping Key Is null

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  o.status AS trangThai,
  count(c) AS soDongKhach,
  count(o) AS soDon
ORDER BY trangThai;
~~~

Besides `PAID` and `PENDING`, the query also produces a group `trangThai = null` representing rows of customers without orders. This group has `soDongKhach = 1` and `soDon = 0`.

This does not mean there is an order status named `null`: it is a **missing value** produced when an optional match fails to match. When designing a report, consider whether to keep this group or replace it with a label like `'No orders yet'` after clarifying its exact meaning.

### 6.2. No Input Rows vs. No Groups

The following two queries use the same filter that matches no orders, yet produce different result shapes:

~~~cypher
MATCH (o:Order)
WHERE o.status = 'CANCELLED'
RETURN count(o) AS soDon;
~~~

Returns **one row** with `soDon = 0`, because the aggregation has no grouping key.

~~~cypher
MATCH (o:Order)
WHERE o.status = 'CANCELLED'
RETURN o.status AS trangThai, count(o) AS soDon;
~~~

Returns **zero rows**, because there is a grouping key `o.status` but no input rows to form any group. This is an important detail when a Java application or API expects one row containing zero.

## 7. How Do WHERE, ORDER BY, and DISTINCT Affect Grouping Keys?

These three elements are easily confused with the grouping mechanism:

| Element | Role | Note |
|---|---|---|
| `WHERE` before aggregation | Filters input rows | Can change the group's count and total amount |
| `WHERE` after aggregating `WITH` | Filters computed group results | Can use aggregate aliases such as `soDon` |
| `ORDER BY` | Sorts result rows | Does not create new grouping keys |
| `LIMIT` after aggregation | Keeps a subset of output groups | Does not change how the kept groups are computed |
| `DISTINCT` | Removes duplicates for the selected expressions | Does not replace identifying the aggregation grain |

Example considering only paid orders:

~~~cypher
MATCH (o:Order)
WHERE o.status = 'PAID'
RETURN count(o) AS soDon, sum(o.amount) AS tongTien;
~~~

Result is one group: `soDon = 3`, `tongTien = 350000`. The `WHERE` condition reduces the row set before `RETURN`.

Conversely, finding statuses with at least two orders:

~~~cypher
MATCH (o:Order)
WITH o.status AS trangThai, count(o) AS soDon
WHERE soDon >= 2
RETURN trangThai, soDon
ORDER BY soDon DESC;
~~~

First groups by status, then keeps only the `PAID` group with `soDon = 3`. `ORDER BY` only sorts the final groups.

Compare:

~~~cypher
MATCH (o:Order)
RETURN DISTINCT o.status AS trangThai;
~~~

The `DISTINCT` query above returns two distinct status values, but **does not count orders**. To summarize order counts by status, use `RETURN o.status, count(o)` with the appropriate grouping key.

## 8. A Method for Checking Aggregation Grain Before Running Queries

Before trusting a Cypher aggregation, answer five questions in order:

1. **What should one report row represent?** For example: one customer, one status, or one customer–product pair.
2. **Which key identifies that grain?** Choose `c` or `c.id` if you need to distinguish individual customers; avoid using names unless you intend to merge matching names.
3. **How many rows is each `MATCH` producing?** Traversing one-to-many relationships can repeat nodes and their properties.
4. **On what unit does the aggregate function operate?** `count(o)` counts occurrences, `count(DISTINCT o)` counts distinct nodes, `sum(o.amount)` sums amounts across every row received.
5. **After each `WITH`, does the data grain change?** Non-aggregate expressions carried through `WITH` may act as grouping keys at that stage.

You can inspect intermediate rows before writing the final aggregation:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
MATCH (o)-[line:CONTAINS]->(p:Product)
RETURN
  c.id AS maKhach,
  o.id AS maDon,
  p.sku AS maSanPham,
  o.amount AS giaTriDon,
  line.quantity AS soLuong
ORDER BY maKhach, maDon, maSanPham;
~~~

Here C01 appears in **three rows**, not two, because O101 has two products. On large datasets, use `EXPLAIN` to view the planned execution and `PROFILE` to observe actual row counts flowing through each operator. Only conclude a query is efficient after checking the plan against realistic data.

To keep queries maintainable, use descriptive aliases such as `soDonTheoKhach`, `tongTienTheoDon`, and `soDongSanPham`, rather than naming every metric `total`. Clear aliases expose the **unit of measurement** and help catch wrong-grain aggregations during code review.

## 9. Practice Exercises and Reference Solutions

### Exercise 1. Identifying Aggregation Grain

Given the query:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN
  c.name AS ten,
  o.status AS trangThai,
  count(o) AS soDon;
~~~

Question: What does one result row represent? With the sample data, how many rows are returned? What happens to the two customers named `An`?

**Solution:** The grouping key is `(c.name, o.status)`, meaning a **name–status** pair, not a specific customer. There are two rows: `(An, PAID, 3)` and `(Binh, PENDING, 1)`. To report per individual customer, replace `c.name` with `c.id` or group by node `c` before projecting the name.

### Exercise 2. Rewriting a Query at the Right Unit

Requirement: return one row per customer, including customer ID, name, order count, and largest order; Chi must appear with `soDon = 0`, `donLonNhat = null`.

**Solution:**

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, count(o) AS soDon, max(o.amount) AS donLonNhat
RETURN
  c.id AS maKhach,
  c.name AS ten,
  soDon,
  donLonNhat
ORDER BY maKhach;
~~~

The `donLonNhat` results for C01/C02/C03/C04 are `200000/150000/50000/null` respectively.

### Exercise 3. Diagnosing Row Multiplication Errors

Why does the query below return `400000` as C01's total amount?

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
RETURN c.id AS maKhach, sum(o.amount) AS tongTien;
~~~

**Solution:** In the input data, O101 has two product line items, so the value `100000` is added twice. The total per customer must be calculated after matching to `Order`, **before expanding** to `Product`:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, sum(o.amount) AS tongTien
RETURN c.id AS maKhach, tongTien
ORDER BY maKhach;
~~~

The result is C01 `300000`, C02 `150000`, C03 `50000`, C04 `0`.

### Exercise 4. Distinguishing No Groups from a Group with Value 0

Predict the number of rows returned by each query with `status = 'CANCELLED'` in the sample data:

~~~cypher
MATCH (o:Order)
WHERE o.status = 'CANCELLED'
RETURN count(o) AS soDon;
~~~

~~~cypher
MATCH (o:Order)
WHERE o.status = 'CANCELLED'
RETURN o.status AS trangThai, count(o) AS soDon;
~~~

**Solution:** The first query returns one row `soDon = 0`; the second query returns zero rows because the key `trangThai` is needed to form a group.

## 10. Key Takeaways

- **Grouping keys of an aggregating `RETURN` or `WITH` are inferred from non-aggregate expressions** in the same projection.
- **One result row = one combination of grouping keys**; with no grouping keys, the entire input forms a single group.
- **Display names do not replace identifier keys**: `c.name` can merge multiple distinct customers; `c` or `c.id` distinguishes each customer.
- **Each `WITH` is an opportunity to change data grain**. Grouping by customer, by status, and by product line item are distinct calculations.
- **Input row count determines counts and sums**. Traversing one-to-many relationships can repeat nodes; `count(DISTINCT o)` only fixes node counting, not summing amounts.
- **`OPTIONAL MATCH` preserves groups without matching relationships**, and `count(*)` vs. `count(o)` can produce different results when `o = null`.
- Before writing `sum()` or `avg()`, be able to state in one sentence: **"What unit do the rows being aggregated represent?"**.
