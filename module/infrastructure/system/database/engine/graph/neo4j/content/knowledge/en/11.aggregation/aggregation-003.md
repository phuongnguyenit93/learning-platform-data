# Distinguishing Row Count, Non-null Value Count, and Distinct Value Count

In Neo4j, a Cypher query can return multiple rows because one node matches multiple relationships or multiple paths. Therefore, the question "how many?" needs to be clarified: **how many result rows**, **how many values actually exist**, or **how many distinct values**?

The three core expressions are:

- `count(*)`: counts **all rows** entering the aggregation.
- `count(expression)`: counts rows where **the expression value is non-`null`**.
- `count(DISTINCT expression)`: counts **distinct, non-`null` values** of the expression.

This lesson belongs to the **Aggregation** chapter of the **DATABASE_ENGINE_GRAPH_NEO4J** module. In the *property graph* model (nodes, relationships, and properties), distinguishing these three counts helps you accurately report customers, orders, links, and missing data in Cypher queries; it is also the foundation for building reports with the Java Driver or Spring Data Neo4j.

## 1. How Do the Three Counts Differ?

Suppose a query produces rows where the expression `x` takes the values: `10`, `null`, `10`, `20`, `null`.

| Expression | What Is Counted | Result |
|---|---|---:|
| `count(*)` | Every row, regardless of the value of `x` | 5 |
| `count(x)` | Rows where `x` is non-`null` | 3 |
| `count(DISTINCT x)` | Distinct, non-`null` values of `x`: `10`, `20` | 2 |

You can verify this with a standalone Cypher query without creating any data:

~~~cypher
UNWIND [10, null, 10, 20, null] AS x
RETURN
  count(*) AS soDong,
  count(x) AS soGiaTriCoMat,
  count(DISTINCT x) AS soGiaTriKhacNhau;
~~~

Result:

| soDong | soGiaTriCoMat | soGiaTriKhacNhau |
|---:|---:|---:|
| 5 | 3 | 2 |

In this example, **a row with `x = null` is still a row**. Therefore `count(*)` keeps both `null` rows, while the two expression-based counts ignore them.

One way to double-check is to write out the row set before aggregation:

~~~text
Row    x        count(*)   count(x)   count(DISTINCT x)
1      10          +1         +1         +1 (10 is new)
2      null        +1          -          -
3      10          +1         +1          - (10 already seen)
4      20          +1         +1         +1 (20 is new)
5      null        +1          -          -
Total               5          3          2
~~~

Two points follow from this:

1. `DISTINCT` deduplicates **values of the chosen expression**; it does not automatically know whether the business unit is a customer or an order.
2. `count(x)` counts **non-`null` occurrences**; it does not automatically merge identical values.

## 2. Sample Data for Practicing on a Property Graph

Consider a bookstore model:

~~~text
(:Customer)-[:PLACED]->(:Order)-[:CONTAINS {quantity}]->(:Product)
~~~

Here `Customer` has `id`, `name`, `email`, `city`; `Order` has `id`, `amount`, `status`; `Product` has `sku`, `name`; the `CONTAINS` relationship has `quantity`.

Run **once** in an empty practice database:

~~~cypher
CREATE
  (c01:Customer {
    id: 'C01', name: 'An',
    email: 'an@example.test', city: 'Ha Noi'
  }),
  (c02:Customer {
    id: 'C02', name: 'Binh',
    email: 'binh@example.test', city: 'Ha Noi'
  }),
  (c03:Customer {
    id: 'C03', name: 'An',
    email: 'an@example.test', city: 'Da Nang'
  }),
  (c04:Customer {id: 'C04', name: 'Chi', city: 'Hue'}),
  (o101:Order {id: 'O101', amount: 120000, status: 'PAID'}),
  (o102:Order {id: 'O102', amount: 120000, status: 'PAID'}),
  (o103:Order {id: 'O103', amount: 200000, status: 'PENDING'}),
  (o104:Order {id: 'O104', amount: 90000, status: 'PAID'}),
  (p01:Product {sku: 'P01', name: 'Java'}),
  (p02:Product {sku: 'P02', name: 'Neo4j'}),
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

The dataset is intentionally designed to observe commonly confused cases:

| Scenario | Sample Data |
|---|---|
| Customer with no orders | C04 (Chi) |
| Missing property | C04 has no `email` |
| Duplicate property values | C01 and C03 share `name = 'An'`, `email = 'an@example.test'` |
| Two distinct nodes with same order amount | O101 and O102 both have `amount = 120000` |
| One order connected to multiple products | O101 has two `CONTAINS` relationships |

Using two customers with the same email is solely for practicing duplicate values, not a data rule recommendation for real systems. The sample dataset has **4 customers, 4 orders, 4 `PLACED` relationships, 5 `CONTAINS` relationships**; total order value is `530000` VND.

## 3. count(*): Counting Intermediate Rows

The simplest form:

~~~cypher
MATCH (c:Customer)
RETURN count(*) AS soDong;
~~~

The result is `4` because `MATCH (c:Customer)` produces one row for each customer node.

If you switch to traversing the order relationship:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN count(*) AS soDong;
~~~

The result is still `4`, but now each row is **one customer–order pattern match**. The two counts being equal is purely coincidental in the sample data; they can differ if a customer creates multiple orders or if an order is linked in a more complex model.

Continue expanding to products:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
RETURN count(*) AS soDong;
~~~

The result is `5`, because O101 matches two products.

**Conclusion:** `count(*)` is **not synonymous with "counting nodes"**. It counts the number of rows produced by the entire preceding query part. If one node appears across three relationship patterns, that node can contribute three rows.

### 3.1. Counting Relationships per Matched Row

~~~cypher
MATCH (o:Order)-[item:CONTAINS]->(p:Product)
RETURN
  count(*) AS soDong,
  count(item) AS soQuanHe;
~~~

Both values are `5` because in this pattern each row has a non-`null` relationship `item`. To know **how many distinct relationships** exist when a complex query may repeat relationships, use `count(DISTINCT item)` with the appropriate relationship variable.

## 4. count(expression): Counting Only Non-null Values

A node existing does not mean all of its properties exist.

~~~cypher
MATCH (c:Customer)
RETURN
  count(*) AS soDong,
  count(c) AS soNode,
  count(c.email) AS soEmailCoMat;
~~~

Result:

| soDong | soNode | soEmailCoMat |
|---:|---:|---:|
| 4 | 4 | 3 |

C04 is a valid customer node, so it is included in `count(*)` and `count(c)`. However, C04 has no `email` property, so `c.email` evaluates to `null` and does not contribute to `count(c.email)`.

In Neo4j, a property with no value is typically represented by **the absence of the property**; assigning `null` to a property is equivalent to removing the property. For counting, accessing a missing property evaluates to `null`.

### 4.1. count(node) Differs from count(property)

| Expression | Question Answered |
|---|---|
| `count(c)` | How many rows contain a non-`null` node `c`? |
| `count(c.email)` | How many rows have a non-`null` email value? |
| `count(c.name)` | How many rows have a non-`null` name? |
| `count(o)` | How many rows contain an order node `o`? |
| `count(o.amount)` | How many rows have a non-`null` order amount property? |

With the sample data, `count(c.name) = 4` and `count(c.email) = 3`. `count(c.email)` does not validate email format; it only checks whether the expression returns `null`. An empty string `''` is still a non-`null` value and will be counted.

### 4.2. Does Not Count Elements Inside a List

`count(x)` counts **one expression value per row**. If `x` is a list with multiple elements, the entire list is still **one value**, not multiple rows.

~~~cypher
WITH ['Java', 'Neo4j'] AS tags
RETURN
  count(tags) AS soGiaTriList,
  size(tags) AS soPhanTu;
~~~

Result: `soGiaTriList = 1`, `soPhanTu = 2`. If you want to count the elements after turning the list into multiple rows, use `UNWIND`:

~~~cypher
WITH ['Java', 'Neo4j'] AS tags
UNWIND tags AS tag
RETURN count(tag) AS soPhanTu;
~~~

Result: `2`. When writing reports, distinguish between **rows containing a list** and **elements inside the list**.

## 5. count(DISTINCT expression): Counting Unique Values

From the customer set:

~~~cypher
MATCH (c:Customer)
RETURN
  count(c) AS soKhach,
  count(DISTINCT c) AS soNodeKhacNhau,
  count(c.name) AS soTenCoMat,
  count(DISTINCT c.name) AS soTenKhacNhau,
  count(c.email) AS soEmailCoMat,
  count(DISTINCT c.email) AS soEmailKhacNhau;
~~~

Result:

| soKhach | soNodeKhacNhau | soTenCoMat | soTenKhacNhau | soEmailCoMat | soEmailKhacNhau |
|---:|---:|---:|---:|---:|---:|
| 4 | 4 | 4 | 3 | 3 | 2 |

Explanation:

- `count(DISTINCT c)` distinguishes **node identity**; C01 and C03 are two distinct nodes despite sharing the same name and email.
- `count(DISTINCT c.name)` distinguishes **name strings**: `An`, `Binh`, `Chi` → `3`.
- `count(DISTINCT c.email)` leaves only `an@example.test` and `binh@example.test` → `2`. C04's missing email is `null` and is not counted.

`DISTINCT` always applies to the value of **the expression written after it**. With `DISTINCT c`, Neo4j compares node entities; with `DISTINCT c.email`, Neo4j compares email property values.

### 5.1. Counting Entities Differs from Counting Property Values

For orders, O101 and O102 are **two distinct nodes** but share the same `amount = 120000`:

~~~cypher
MATCH (o:Order)
RETURN
  count(DISTINCT o) AS soDonKhacNhau,
  count(DISTINCT o.id) AS soMaDonKhacNhau,
  count(DISTINCT o.amount) AS soMucTienKhacNhau;
~~~

The results are `4`, `4`, `3` respectively.

Do not use `count(DISTINCT o.amount)` to answer the question "how many orders are there?": that expression counts **distinct monetary amount levels**, not orders. In this dataset there are three levels: `90000`, `120000`, `200000`.

A similar warning applies when using `sum(DISTINCT o.amount)`: because O101 and O102 have the same value, `sum(DISTINCT o.amount) = 410000`, whereas the true total of the **four orders** is `530000`. Deduplicating by monetary amount can drop valid orders.

## 6. OPTIONAL MATCH: Where the Three Counts Diverge Most Clearly

`OPTIONAL MATCH` preserves the left-hand row when no matching relationship pattern is found. Variables in the unmatched part receive `null`, while the row still exists.

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.id AS maKhach,
  count(*) AS soDong,
  count(o) AS soDon
ORDER BY maKhach;
~~~

Result:

| maKhach | soDong | soDon |
|---|---:|---:|
| C01 | 2 | 2 |
| C02 | 1 | 1 |
| C03 | 1 | 1 |
| C04 | 1 | 0 |

C04 has no orders, yet `OPTIONAL MATCH` creates one row containing `c = C04` and `o = null`. Therefore:

- `count(*) = 1` for C04 because one row was retained.
- `count(o) = 0` for C04 because there is no order node.
- `count(DISTINCT o) = 0` for C04 because there is no non-`null` order value to count.

### 6.1. Counting the Entire Dataset After OPTIONAL MATCH

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  count(*) AS soDong,
  count(c) AS soLanKhachXuatHien,
  count(DISTINCT c) AS soKhachKhacNhau,
  count(o) AS soDon,
  count(DISTINCT o) AS soDonKhacNhau;
~~~

| soDong | soLanKhachXuatHien | soKhachKhacNhau | soDon | soDonKhacNhau |
|---:|---:|---:|---:|---:|
| 5 | 5 | 4 | 4 | 4 |

C01 has two orders and therefore appears on two rows; the remaining three customers each take one row. Total rows are `2 + 1 + 1 + 1 = 5`. `count(c) = 5` does **not** mean the database has five customers: it is the number of times variable `c` has a value across the rows.

### 6.2. Placing WHERE Correctly for Conditional Counts

For example, counting paid orders **for every customer, including customers who have not paid yet**:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN c.id AS maKhach, count(o) AS soDonPaid
ORDER BY maKhach;
~~~

Result: C01 has `2`, C02 has `0`, C03 has `1`, C04 has `0`. Attaching `WHERE` to the `OPTIONAL MATCH` clause allows customers with no matching orders to still be retained.

Conversely, if you place the filter condition on `o` **after a `WITH`**:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, o
WHERE o.status = 'PAID'
RETURN c.id AS maKhach, count(o) AS soDonPaid
ORDER BY maKhach;
~~~

Rows where `o = null` or status is not `PAID` are filtered out in `WHERE` after `WITH`, so C02 and C04 **do not appear** in the report. If you need to keep groups with a count of 0, check the placement of the filter condition and how `OPTIONAL MATCH` is used.

## 7. Grouping Grain Changes the Meaning of a Count

In Cypher, non-aggregate expressions in the same `RETURN` or `WITH` define the **implicit grouping keys**. The result of `count()` is always computed **separately for each group**.

For example, counting by city:

~~~cypher
MATCH (c:Customer)
RETURN
  c.city AS thanhPho,
  count(*) AS soDong,
  count(c.email) AS soEmailCoMat,
  count(DISTINCT c.email) AS soEmailKhacNhau
ORDER BY thanhPho;
~~~

| thanhPho | soDong | soEmailCoMat | soEmailKhacNhau |
|---|---:|---:|---:|
| Da Nang | 1 | 1 | 1 |
| Ha Noi | 2 | 2 | 2 |
| Hue | 1 | 0 | 0 |

Each group only considers rows sharing the same `c.city`. Here `count(DISTINCT c.email)` counts distinct emails **within one city**, not across the entire graph.

### 7.1. Grouping by Name Can Merge Multiple Customers

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.name AS ten,
  count(c) AS soLanXuatHienKhach,
  count(DISTINCT c) AS soKhachThuc,
  count(o) AS soDon
ORDER BY ten;
~~~

Result:

| ten | soLanXuatHienKhach | soKhachThuc | soDon |
|---|---:|---:|---:|
| An | 3 | 2 | 3 |
| Binh | 1 | 1 | 1 |
| Chi | 1 | 1 | 0 |

The `An` group contains **C01 and C03**. Because C01 has two orders, `count(c) = 3`, yet there are only **two distinct customer nodes**, so `count(DISTINCT c) = 2`. If the goal is one row per customer, group by node `c` or a unique identifier key:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.id AS maKhach,
  c.name AS ten,
  count(o) AS soDon
ORDER BY maKhach;
~~~

Distinguish between two business questions:

- "How many distinct customers are named An?" → `count(DISTINCT c)` after filtering or grouping by name.
- "How many orders does customer C01 have?" → group by `c.id` (or `c`) and then `count(o)`.

## 8. When Relationships Multiply Rows, DISTINCT May Be Needed

From each order, we expand to products:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
MATCH (o)-[item:CONTAINS]->(p:Product)
RETURN
  count(*) AS soDongChiTiet,
  count(o) AS soLanDonXuatHien,
  count(DISTINCT o) AS soDonKhacNhau,
  count(item) AS soQuanHeChiTiet,
  count(DISTINCT p) AS soSanPhamKhacNhau;
~~~

| soDongChiTiet | soLanDonXuatHien | soDonKhacNhau | soQuanHeChiTiet | soSanPhamKhacNhau |
|---:|---:|---:|---:|---:|
| 5 | 5 | 4 | 5 | 2 |

O101 has two `CONTAINS` relationships and therefore appears **twice**; `count(o)` counts both, while `count(DISTINCT o)` counts O101 only once.

Here, each type of count answers a different question:

| Need | Suitable Expression |
|---|---|
| Total matched line-item rows | `count(*)` |
| Total times orders appear in line-item rows | `count(o)` |
| Total distinct orders that have products | `count(DISTINCT o)` |
| Number of line-item relationships | `count(item)` |
| Number of distinct products referenced | `count(DISTINCT p)` |

### 8.1. Do Not Blindly Apply DISTINCT to the Entire Result

`RETURN DISTINCT c.id, o.status` returns distinct `(customer id, status)` pairs. This is **not the same** as `RETURN c.id, count(DISTINCT o)`, which gives the number of distinct orders per customer.

When a report has multiple relationship branches, an entity can repeat across every combination of branches. Apply `DISTINCT` to **the exact variable** to be counted, or use `WITH` to redefine the aggregation grain before expanding further.

### 8.2. DISTINCT in Counting Does Not Fix All Aggregations

~~~cypher
MATCH (o:Order)-[:CONTAINS]->(p:Product)
RETURN
  count(o) AS soLanDon,
  count(DISTINCT o) AS soDonKhacNhau,
  sum(o.amount) AS tongTienTheoDong;
~~~

Result: `soLanDon = 5`, `soDonKhacNhau = 4`, but `tongTienTheoDong = 650000` because O101 is added twice. The correct total for the four orders is `530000`:

~~~cypher
MATCH (o:Order)
RETURN
  count(o) AS soDon,
  sum(o.amount) AS tongTien;
~~~

Neither `count(DISTINCT o)` nor `sum(DISTINCT o.amount)` **automatically fixes** other sums affected by row multiplication. Metrics must be computed at the proper source grain: order totals must be summed over individual **orders**, and product quantities must be summed over individual **line-item relationships**.

## 9. Counting When There Is No Input Data

If a query matches no nodes and has no grouping keys, aggregate functions still return one row with value 0:

~~~cypher
MATCH (o:Order)
WHERE o.status = 'CANCELLED'
RETURN
  count(*) AS soDong,
  count(o) AS soDon,
  count(DISTINCT o) AS soDonKhacNhau;
~~~

The result is **one row** with all three columns equal to `0`.

However, add the grouping key `o.status`:

~~~cypher
MATCH (o:Order)
WHERE o.status = 'CANCELLED'
RETURN
  o.status AS trangThai,
  count(*) AS soDong;
~~~

This query returns **zero rows**, because there are no input rows to form a status group. Distinguishing these two cases matters to a Java application: receiving one `Record` containing zero is different from receiving an empty result list.

Another case is when there are input rows, but all expression values are `null`:

~~~cypher
UNWIND [null, null] AS x
RETURN
  count(*) AS soDong,
  count(x) AS soGiaTri,
  count(DISTINCT x) AS soGiaTriDuyNhat;
~~~

The results are `2`, `0`, `0`. Do not infer that `count(x) = 0` means there are no rows; **rows can exist while values are missing**.

## 10. Should null Be Converted to a Value for Counting?

Suppose you want to know the number of email groups, where "missing email" is also treated as a group. `count(DISTINCT c.email)` returns `2`, ignoring `null`. You can intentionally replace `null` with a label:

~~~cypher
MATCH (c:Customer)
WITH coalesce(c.email, '(missing email)') AS nhomEmail
RETURN count(DISTINCT nhomEmail) AS soNhomEmail;
~~~

The result is `3`: An's email, Binh's email, and the missing-email group. However, this is a **new business definition**: moving from not counting `null` values to treating missing data as a separate group. Choose a replacement label that cannot collide with real values, or separate the missing group using an explicit expression.

Do not apply `coalesce(x, 0)` arbitrarily. If `0` is a valid value in the data, it can cause the missing-value group to be merged with rows that genuinely have value 0.

## 11. Verifying Correctness and Performance

When aggregating on a large graph, proceed step by step:

1. **Identify the unit:** do you want to count matched paths, customer nodes, order nodes, relationships, or property values?
2. **Identify possible nulls:** can `MATCH` or `OPTIONAL MATCH` produce a `null` variable? Can a property be missing?
3. **Identify possible duplicates:** can one node appear via multiple relationships/paths? Can multiple distinct nodes share the same property value?
4. **Choose grouping keys:** `RETURN c.id, count(o)` counts by customer; `RETURN o.status, count(o)` counts by status.
5. **Compare count variants on small data:** place `count(*)`, `count(o)`, and `count(DISTINCT o)` side by side to spot discrepancies.
6. **Inspect the execution plan:** use `EXPLAIN` and `PROFILE` to see whether the query multiplies rows before the aggregation step.

Example of checking actual row counts during a traversal:

~~~cypher
PROFILE
MATCH (c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
RETURN
  count(*) AS soDong,
  count(DISTINCT o) AS soDon;
~~~

This query returns `soDong = 5` and `soDon = 4`. On larger datasets, the number of input rows fed into `DISTINCT` is a key factor to watch because deduplication typically has to store/compare previously seen values. Some very simple count queries can leverage Neo4j's statistics store; do not assume every `count()` or `count(DISTINCT ...)` has the same performance. Rely on the execution plan rather than guessing.

When an application reads results with the Java Driver, use meaningful aliases (`soDong`, `soDon`, `soDonKhacNhau`) and check whether the query returns one row or multiple groups. When writing repository methods in Spring Data Neo4j, preserve the semantics of grouping keys and metric data types; changing an alias or replacing `count(DISTINCT o)` with `count(o)` can make a report wrong even though the query still runs.

## 12. Practice Exercises

### Exercise 1. Counting Rows with null

Given the query:

~~~cypher
UNWIND [1, 1, 2, null, null, 3] AS x
RETURN
  count(*) AS a,
  count(x) AS b,
  count(DISTINCT x) AS c;
~~~

Predict `a`, `b`, and `c` before running it.

**Answer:** `a = 6`; `b = 4` (two `null` values are ignored); `c = 3` (distinct values are 1, 2, 3).

### Exercise 2. Counting Customers with Email and Distinct Emails

Requirement: use the sample dataset to return one row containing total customers, customers with an email, and number of distinct emails.

**Answer:**

~~~cypher
MATCH (c:Customer)
RETURN
  count(DISTINCT c) AS tongKhach,
  count(c.email) AS khachCoEmail,
  count(DISTINCT c.email) AS soEmailKhacNhau;
~~~

Results: `4`, `3`, `2`. If a customer could appear on multiple rows due to expanding relationships, consider how to handle duplicates before treating `count(c.email)` as **the number of customers** with an email.

### Exercise 3. Counting Orders for Every Customer, Including Non-Buyers

Requirement: one row per customer ID and order count. C04 must return 0.

**Answer:**

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.id AS maKhach,
  count(o) AS soDon
ORDER BY maKhach;
~~~

Results in order C01, C02, C03, C04: `2`, `1`, `1`, `0`. If changed to `count(*)`, C04 would mistakenly be counted as `1`.

### Exercise 4. Counting Distinct Orders After Traversing Products

Requirement: count distinct orders that have a `CONTAINS` relationship and the number of product line-item relationship rows.

**Answer:**

~~~cypher
MATCH (o:Order)-[:CONTAINS]->(p:Product)
RETURN
  count(*) AS soDongChiTiet,
  count(DISTINCT o) AS soDonKhacNhau;
~~~

Results `5` and `4`. The difference comes from O101 having two product line items.

### Exercise 5. Finding the Bug in Counting by Name

Why can the following query not be used to determine the number of customers in the system?

~~~cypher
MATCH (c:Customer)
RETURN count(DISTINCT c.name) AS soKhach;
~~~

**Answer:** It counts **distinct names**, not customer nodes; C01 and C03 are both named An and will be counted once. With the sample data the result is `3`, whereas there are `4` customers. Use `count(DISTINCT c)`, or `count(DISTINCT c.id)` if `id` is guaranteed unique.

## Key Takeaways

- **`count(*)`**: counts every row present at the aggregation point; rows with `null` variables are still counted.
- **`count(x)`**: counts rows where `x` is non-`null`; duplicate values are counted multiple times.
- **`count(DISTINCT x)`**: counts distinct, non-`null` values of `x`.
- **Choose the right expression:** `count(DISTINCT o)` counts distinct order nodes; `count(DISTINCT o.amount)` only counts distinct monetary amount levels.
- **Watch `OPTIONAL MATCH`:** a customer without orders can still contribute a row to `count(*)`, but contributes no order to `count(o)`.
- **Watch row multiplication:** expanding one-to-many relationships can inflate `count(*)` and `count(o)`; correctly identify the counting unit, grouping keys, and scope of `DISTINCT`.
