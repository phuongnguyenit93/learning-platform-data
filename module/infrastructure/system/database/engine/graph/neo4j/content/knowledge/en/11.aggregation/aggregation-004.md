# Using collect to Aggregate Data and Manage List Size

In Neo4j, Cypher queries often traverse from one node across many relationships to find related entities. For instance, a customer has many orders, an order contains many products, or a person has many friends. When an application wants to return **one row per primary entity** accompanied by a list of its related entities, the `collect()` aggregate function is an essential tool.

However, `collect()` can build very large lists when the graph has many relationship branches. To use it effectively, you need to understand input row counts, grouping keys, deduplication, result ordering, and when to apply `LIMIT`. This lesson belongs to the **Aggregation** chapter of the Neo4j module, focusing on aggregating data in the *property graph* model and controlling result sizes in Cypher.

## 1. What Problem Does collect() Solve?

Suppose a customer has three orders. A standard `MATCH` query returns three rows:

~~~cypher
MATCH (c:Customer {id: 'C01'})-[:PLACED]->(o:Order)
RETURN c.id AS maKhach, o.id AS maDon;
~~~

The application might want a structure closer to JSON:

~~~json
{
  "maKhach": "C01",
  "maDon": ["O101", "O102", "O104"]
}
~~~

This is where `collect(o.id)` comes in: **gathering values from multiple rows into a list** within each aggregation group.

~~~cypher
MATCH (c:Customer {id: 'C01'})-[:PLACED]->(o:Order)
RETURN c.id AS maKhach, collect(o.id) AS maDon;
~~~

`collect()` is an **aggregation function**. It differs from a list literal `['a', 'b']` because a list literal is declared directly, whereas `collect()` builds a list from the data rows produced by the query.

## 2. Sample Dataset Used Throughout

Consider a bookstore property graph:

~~~text
(:Customer)-[:PLACED]->(:Order)-[:CONTAINS {quantity}]->(:Product)
~~~

- `Customer`: customer, with `id` and `name`.
- `Order`: order, with `id`, `createdAt` (type `date`), `amount`, and `status`.
- `Product`: product, with `sku` and `name`.
- `CONTAINS.quantity`: quantity of a product in the order.

Create the data in an **empty practice database** and run this `CREATE` statement only once:

~~~cypher
CREATE
  (an:Customer {id: 'C01', name: 'An'}),
  (binh:Customer {id: 'C02', name: 'Binh'}),
  (chi:Customer {id: 'C03', name: 'Chi'}),
  (o101:Order {id: 'O101', createdAt: date('2026-11-01'),
                amount: 120000, status: 'PAID'}),
  (o102:Order {id: 'O102', createdAt: date('2026-11-03'),
                amount: 80000, status: 'PAID'}),
  (o103:Order {id: 'O103', createdAt: date('2026-11-04'),
                amount: 200000, status: 'PENDING'}),
  (o104:Order {id: 'O104', createdAt: date('2026-11-05'),
                amount: 60000, status: 'PAID'}),
  (o105:Order {id: 'O105', createdAt: date('2026-11-06'),
                amount: 50000, status: 'PAID'}),
  (p01:Product {sku: 'P01', name: 'Java'}),
  (p02:Product {sku: 'P02', name: 'Neo4j'}),
  (p03:Product {sku: 'P03', name: 'Cypher'}),
  (an)-[:PLACED]->(o101),
  (an)-[:PLACED]->(o102),
  (an)-[:PLACED]->(o104),
  (binh)-[:PLACED]->(o103),
  (binh)-[:PLACED]->(o105),
  (o101)-[:CONTAINS {quantity: 1}]->(p01),
  (o101)-[:CONTAINS {quantity: 2}]->(p02),
  (o102)-[:CONTAINS {quantity: 1}]->(p02),
  (o103)-[:CONTAINS {quantity: 2}]->(p01),
  (o103)-[:CONTAINS {quantity: 1}]->(p03),
  (o104)-[:CONTAINS {quantity: 1}]->(p02),
  (o105)-[:CONTAINS {quantity: 3}]->(p03);
~~~

The dataset has three customers, five orders, three products, and seven `CONTAINS` relationships.

| Customer | Orders | Order Count |
|---|---|---:|
| C01 / An | O101, O102, O104 | 3 |
| C02 / Binh | O103, O105 | 2 |
| C03 / Chi | No orders yet | 0 |

The case where Chi has no orders will help verify how `collect()` handles `null`.

## 3. collect() Syntax and Return Type

Basic forms:

~~~cypher
collect(expression)
collect(DISTINCT expression)
~~~

For each result group, `collect()` takes each expression value from the rows in that group and creates a **list** containing the **non-`null`** values. It can collect IDs, strings, numbers, nodes, relationships, or maps.

Example collecting all order IDs:

~~~cypher
MATCH (o:Order)
RETURN collect(o.id) AS danhSachMaDon;
~~~

The result is **one row** containing a list of five order IDs; element ordering is not guaranteed unless sorting is specified.

If you add a non-aggregate grouping key, Cypher collects a list per group:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN
  c.id AS maKhach,
  collect(o.id) AS danhSachMaDon
ORDER BY maKhach;
~~~

There are two result rows, one for C01 and one for C02. C03 does not appear because a regular `MATCH` requires a `PLACED` relationship.

### 3.1. Collecting Nodes, Properties, or Maps?

The three expressions below create lists with **different element types**:

~~~cypher
MATCH (c:Customer {id: 'C01'})-[:PLACED]->(o:Order)
RETURN
  collect(o) AS dsNodeDon,
  collect(o.id) AS dsMaDon,
  collect(o {.id, .amount, .status}) AS dsTomTatDon;
~~~

| Expression | Element Type | Suitable When |
|---|---|---|
| `collect(o)` | `Order` node | You need to continue working with the entity in Cypher |
| `collect(o.id)` | String | The API only needs order IDs |
| `collect(o {.id, .amount, .status})` | Map | The API needs a clear data structure with few fields |

Map projection `o {.id, .amount, .status}` fetches only the listed properties. When returning results via the Java Driver or an API, collecting small maps is usually easier for controlling payload size than returning entire nodes with many properties.

Note: reducing the number of properties **reduces element size**, but does not limit the **number of elements** in the list. A customer with hundreds of thousands of orders can still produce a very large list.

### 3.2. collect() and count() Do Not Replace Each Other

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN
  c.id AS maKhach,
  count(o) AS soDon,
  collect(o.id) AS maDon
ORDER BY maKhach;
~~~

`count(o)` returns **a number**, whereas `collect(o.id)` returns **a list**. When you only need a count, use `count()` because there is no need to build and hold a list of IDs.

## 4. Keeping Groups with Zero Elements: OPTIONAL MATCH and null

When a report must include customers without orders, start from all customer nodes and use `OPTIONAL MATCH`:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.id AS maKhach,
  count(o) AS soDon,
  collect(o.id) AS maDon
ORDER BY maKhach;
~~~

| maKhach | soDon | maDon |
|---|---:|---|
| C01 | 3 | List containing O101, O102, O104 |
| C02 | 2 | List containing O103, O105 |
| C03 | 0 | `[]` |

For Chi, `OPTIONAL MATCH` produces one row with `o = null`. The expression `o.id` is also `null`, and `collect(o.id)` **ignores null elements**. Therefore Chi's list is `[]`, not `[null]`.

You can test this rule yourself with a query independent of the sample data:

~~~cypher
UNWIND ['A', null, 'B'] AS x
RETURN
  count(*) AS soDong,
  count(x) AS soGiaTri,
  collect(x) AS danhSach;
~~~

Result: `soDong = 3`, `soGiaTri = 2`, and `danhSach` contains `'A'`, `'B'` in an order you should not rely on unless sorted.

If all values are `null`, `collect()` returns an empty list `[]`. If there are no grouping keys and the input is completely empty, an aggregate query like the following still returns one row containing `[]`:

~~~cypher
MATCH (o:Order)
WHERE o.status = 'CANCELLED'
RETURN collect(o.id) AS maDon;
~~~

Conversely, if the same query also projects `o.status` as a grouping key, an empty input set produces **zero result rows**.

## 5. collect(DISTINCT ...): Avoiding Duplicate Elements

In a graph, the same node can be matched multiple times via different paths. Specifically, An's `Neo4j` product appears in **three orders**. Consider the query:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
RETURN
  c.id AS maKhach,
  count(p) AS soDongSanPham,
  collect(p.name) AS cacLanSanPhamXuatHien,
  collect(DISTINCT p.name) AS cacLoaiSanPham
ORDER BY maKhach;
~~~

| maKhach | soDongSanPham | cacLanSanPhamXuatHien | cacLoaiSanPham |
|---|---:|---|---|
| C01 | 4 | Java, Neo4j, Neo4j, Neo4j | Java, Neo4j |
| C02 | 3 | Java, Cypher, Cypher | Java, Cypher |

The list columns in the table are shown in an illustrative order; since the query does not specify an order, Neo4j may return a different order.

- `collect(p.name)` **keeps repeated occurrences** of the same product name.
- `collect(DISTINCT p.name)` **keeps one element per distinct name** within each customer group.
- `collect(DISTINCT p)` deduplicates by **node identity**, which is useful if multiple nodes can share the same name.
- `DISTINCT` does not guarantee list ordering.

### 5.1. Choosing the Right Unit When Deduplicating

An order can contain multiple products, so traversing from `Order` to `Product` multiplies the order rows:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
RETURN
  c.id AS maKhach,
  collect(o.id) AS maDonCoLap,
  collect(DISTINCT o.id) AS maDonKhacNhau
ORDER BY maKhach;
~~~

For C01, the non-deduplicated list contains `O101` **twice** because that order has two product line items. The `DISTINCT` list has only the three distinct order IDs: O101, O102, O104.

However, do not use `DISTINCT` mechanically. If the business requirement is to count **each time a product appears in an order**, deduplicating loses occurrence frequency. If you need **item quantities**, use `sum(line.quantity)` on the relationship, because `collect(DISTINCT p.name)` only returns product category names.

## 6. Element Order: Sort Before Collecting

A common mistake is assuming the returned list is ordered by order creation date or ID. In Cypher, row order is not guaranteed without `ORDER BY`; consequently, a list from `collect()` must also **not be assumed to be sorted**.

To collect a list of orders from newest to oldest for each customer:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, o
ORDER BY c.id, o.createdAt DESC, o.id ASC
RETURN
  c.id AS maKhach,
  collect(o.id) AS maDonMoiDenCu
ORDER BY maKhach;
~~~

Expected result:

| maKhach | maDonMoiDenCu |
|---|---|
| C01 | `['O104', 'O102', 'O101']` |
| C02 | `['O105', 'O103']` |
| C03 | `[]` |

`ORDER BY` in `WITH` guarantees the order of rows fed into **the immediately following `RETURN` clause**. Thus `collect(o.id)` receives the orders in the chosen order. Adding `o.id ASC` as a tie-breaker makes the result deterministic if two orders share the same creation date.

This distinction is very important:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN c.id AS maKhach, collect(o.id) AS maDon
ORDER BY maKhach;
~~~

In the second query, `ORDER BY maKhach` only **sorts the customer rows**, not the elements inside `maDon`.

If you need a list sorted by a node property, sort **the node rows** with `WITH ... ORDER BY ...` before calling `collect()`. Do not rely on node creation order or index scan order.

## 7. Managing List Size: LIMIT Must Be Placed Correctly

`collect()` can put a very large number of values into **one list per group**. Having few customers does not mean small results: just one customer with one million orders is enough to make a list of IDs, nodes, or maps huge.

### 7.1. Slicing a List After collect: Concise, Yet Still Builds the Full List

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, o
ORDER BY c.id, o.createdAt DESC, o.id ASC
WITH c, collect(o.id) AS tatCaMaDon
RETURN
  c.id AS maKhach,
  size(tatCaMaDon) AS tongSoDon,
  tatCaMaDon[0..2] AS haiMaDonMoiNhat
ORDER BY maKhach;
~~~

In Cypher, the slice `[0..2]` takes elements at indices `0` and `1`, **excluding position `2`**. Result: C01 has `['O104', 'O102']`, C02 has `['O105', 'O103']`, and C03 has `[]`.

This approach is convenient for small sets, but **does not reduce the number of elements `collect()` must build before slicing**. When a group is very large, calling `collect()` and then slicing still risks consuming excessive memory and time.

### 7.2. Global LIMIT Does Not Mean LIMIT Per Group

The query below **keeps only two order rows across the entire result**, and only then groups them:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, o
ORDER BY o.createdAt DESC, o.id ASC
LIMIT 2
RETURN c.id AS maKhach, collect(o.id) AS maDon;
~~~

With the sample data, the two newest orders **system-wide** are O105 for C02 and O104 for C01. Both customers end up with one order ID in the result; this is **not** the two newest orders *per customer*.

Rule: if `LIMIT` is placed before `collect()` on a shared row set, it limits **all rows globally**, rather than splitting the limit per grouping key.

### 7.3. Limiting Each Group with a Subquery

To retrieve at most **the two most recent orders for each customer**, sorting and limiting must happen **within the scope of each customer**. You can use a `CALL` subquery with syntax compatible across many Neo4j 5.x releases:

~~~cypher
MATCH (c:Customer)
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
  WITH o
  ORDER BY o.createdAt DESC, o.id ASC
  LIMIT 2
  RETURN collect(o.id) AS maDonGanNhat
}
RETURN
  c.id AS maKhach,
  maDonGanNhat
ORDER BY maKhach;
~~~

| maKhach | maDonGanNhat |
|---|---|
| C01 | `['O104', 'O102']` |
| C02 | `['O105', 'O103']` |
| C03 | `[]` |

The subquery executes once for each row `c` from the outer query. On each execution, `LIMIT 2` caps the order rows **before** `collect()` constructs the list. Customers without orders are still preserved via `OPTIONAL MATCH`, and `collect(null)` produces `[]`.

This technique **bounds the number of elements in the list**. It does not mean the engine always traverses only two relationships; to see the actual filtering and sorting cost, inspect `PROFILE`.

Version note: the example uses variable-import syntax with `WITH c` inside `CALL { ... }`, which is common in Neo4j 5. Newer Neo4j versions support scoped variable syntax `CALL (c) { ... }`. When implementing in a project, choose the syntax matching your actual Cypher version.

### 7.4. Parameterizing the Limit

When list size depends on an API request, you can use a `$maxItems` parameter instead of hardcoding 2:

~~~cypher
MATCH (c:Customer {id: $customerId})
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
  WITH o
  ORDER BY o.createdAt DESC, o.id ASC
  LIMIT $maxItems
  RETURN collect(o {.id, .amount, .createdAt}) AS donGanNhat
}
RETURN c.id AS maKhach, donGanNhat;
~~~

The application should validate that `maxItems` is a non-negative integer and enforce a **reasonable upper bound** before sending the query—for example, capping the API at returning at most 20 or 50 orders per customer. Using parameters avoids concatenating Cypher strings from user input.

## 8. When Not to Use collect: Pagination Instead of Returning One Huge List

There are cases where an API genuinely needs to display thousands of orders and the user views only one page at a time. If you collect all orders into one large list and return it to the Java Driver, the application must receive and hold the entire result even though the UI only displays 20 rows.

Instead, return **one record per order** and paginate:

~~~cypher
MATCH (c:Customer {id: $customerId})-[:PLACED]->(o:Order)
RETURN
  o.id AS maDon,
  o.createdAt AS ngayTao,
  o.amount AS giaTri
ORDER BY ngayTao DESC, maDon ASC
SKIP $offset
LIMIT $pageSize;
~~~

Example parameters:

~~~json
{
  "customerId": "C01",
  "offset": 0,
  "pageSize": 20
}
~~~

This limits the number of rows that must be **returned to the application**. Deep `SKIP` can still be expensive because the engine must traverse/skip earlier rows; on very large datasets with heavy pagination, consider keyset/cursor pagination on a deterministic ordering pair such as `(createdAt, id)`.

Choose the return strategy according to the need:

| Need | Suitable Approach |
|---|---|
| Only want to know how many orders | `count(o)` |
| Need a small bounded list | `collect()` after per-group `LIMIT` |
| Want to summarize a few attributes per order | `collect(o {.id, .amount})` |
| Want to browse a very long list of orders | `RETURN` individual records, paginated |
| Need a unique set of products | `collect(DISTINCT p)` or `collect(DISTINCT p.sku)` |

## 9. Analyzing Some Common Pitfalls

### 9.1. Confusing Count with List Length

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN
  c.id AS maKhach,
  count(o) AS soDon,
  size(collect(o.id)) AS kichThuocList
ORDER BY maKhach;
~~~

In the sample data, `soDon` and `kichThuocList` are equal. However, this holds only when using the same expression, the same row set, and no differing `DISTINCT`. When you only need a count, `count(o)` expresses intent more clearly and usually uses less memory than `size(collect(o.id))`.

### 9.2. Duplication from Multiple Relationships

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
RETURN c.id AS maKhach, collect(o.id) AS maDon
ORDER BY maKhach;
~~~

For C01, O101 appears twice because the order contains two types of products. If you want **each order once**, it is best to collect orders before expanding to products, or use `collect(DISTINCT o.id)` when deduplication aligns with the business goal.

### 9.3. Slicing a List Before Counting Loses the Total

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, o
ORDER BY c.id, o.createdAt DESC
WITH c, collect(o.id)[0..2] AS topHai
RETURN c.id AS maKhach, size(topHai) AS soDon;
~~~

The alias `soDon` in this query is misleading: `size(topHai)` only counts elements **after slicing**, at most 2. It is no longer the customer's total order count. If you need both total orders and the top two orders, compute `count(o)` separately at the appropriate grain or use the full list for small sets.

### 9.4. DISTINCT Does Not Preserve Purchase Frequency or Quantity

When a product appears in multiple orders, `collect(DISTINCT p.name)` returns each name only once. It does not indicate how many times the customer bought the product, and does not represent total quantity purchased (`line.quantity`). Choose the aggregation based on the goal: **list of product types**, **count of order line items**, or **total quantity** are three different quantities.

### 9.5. Without ORDER BY, Taking the First Element Is Arbitrary

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, collect(o.id) AS dsDon
RETURN c.id AS maKhach, head(dsDon) AS maDonDau;
~~~

`head(dsDon)` means the first element of the list, **not the newest order**. To get the newest order, sort by `o.createdAt DESC` before the `collect` step, or query per customer with `ORDER BY ... LIMIT 1`.

## 10. Verifying Performance and Results

When encountering a slow or memory-heavy `collect()` query, investigate two variables: **the number of rows generated before aggregation** and **the list size within each group**.

Example of checking the execution plan for collecting order IDs:

~~~cypher
PROFILE
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN c.id AS maKhach, collect(o.id) AS maDon;
~~~

In the execution plan, observe the row counts across relationship expansions and the aggregation operator. Do not look only at the number of returned records: a query may return three customer rows while having processed millions of order rows.

Several operational guidelines:

1. **Filter early**: apply customer keys, time ranges, order statuses, or relevant business filters before building the list.
2. **Limit elements before collect**: use a per-entity subquery so `ORDER BY` and `LIMIT` apply at the right scope; slicing after `collect` does not protect the collection step from oversized data.
3. **Fetch only needed fields**: collect IDs or small map projections if the application does not need full nodes.
4. **Avoid collecting data just to count**: prefer `count()`, `sum()`, or the appropriate numeric aggregate.
5. **Test skewed large groups**: list sizes can be heavily skewed across customers. Test customers with zero orders, one order, and many orders.
6. **Tune queries from real data and plans**: appropriate indexes/constraints help locate starting nodes, but do not automatically eliminate the cost of collecting hundreds of thousands of elements.

In a Java Driver or Spring Data Neo4j application, avoid building DTOs with unbounded lists if the user only needs one page of results. Even if Cypher completes, the application still has to decode the records and hold the lists in Java memory.

## 11. Practice Exercises

### Exercise 1. List of Order IDs per Customer, Including Customers Without Orders

**Requirement:** return `maKhach`, `soDon`, `dsMaDon`; one row per customer; list ordered newest date first.

<details>
<summary>Reference Solution</summary>

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, o
ORDER BY c.id, o.createdAt DESC, o.id
RETURN
  c.id AS maKhach,
  count(o) AS soDon,
  collect(o.id) AS dsMaDon
ORDER BY maKhach;
~~~

C03 has `soDon = 0` and `dsMaDon = []`. C01 has `['O104', 'O102', 'O101']`.

</details>

### Exercise 2. List of Purchased Product Types

**Requirement:** for each customer with orders, return each purchased product type only once, regardless of how many times the product appeared across orders.

<details>
<summary>Reference Solution</summary>

~~~cypher
MATCH (c:Customer)-[:PLACED]->(:Order)-[:CONTAINS]->(p:Product)
RETURN
  c.id AS maKhach,
  collect(DISTINCT p.name) AS loaiSanPham
ORDER BY maKhach;
~~~

C01 has two types `Java` and `Neo4j`; C02 has `Java` and `Cypher`. Ordering inside the list is not guaranteed.

</details>

### Exercise 3. Taking Only the One Newest Order per Customer

**Requirement:** include C03 as well, with each customer having at most one newest order ID. Do not build a list of all orders before slicing.

<details>
<summary>Reference Solution</summary>

~~~cypher
MATCH (c:Customer)
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
  WITH o
  ORDER BY o.createdAt DESC, o.id ASC
  LIMIT 1
  RETURN collect(o.id) AS dsMaDon
}
RETURN c.id AS maKhach, dsMaDon
ORDER BY maKhach;
~~~

Result: C01 has `['O104']`, C02 has `['O105']`, C03 has `[]`.

</details>

### Exercise 4. Finding a Bug in Collection

Given the query:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
RETURN
  c.id AS maKhach,
  size(collect(o.id)) AS soDon;
~~~

**Question:** why is C01 counted as 4 instead of 3? Should you use `size(collect(DISTINCT o.id))`?

**Solution:** O101 has two `CONTAINS` relationships, so `o.id` appears twice. `size(collect(DISTINCT o.id))` returns 3 on the sample data, but if you only need to **count**, `count(DISTINCT o)` expresses intent more clearly and avoids constructing a list of IDs. If the query does not need product information yet, matching only up to `Order` is even simpler.

## 12. Key Takeaways

- `collect(x)` turns multiple **non-null** values into one **list per group**; `collect(DISTINCT x)` removes duplicates based on the value of expression `x`.
- Non-aggregate expressions in `RETURN` or `WITH` determine the **grouping keys**. To keep customers without orders, use `OPTIONAL MATCH`; the list for that customer is `[]`.
- For deterministic list order, use `WITH ... ORDER BY ...` immediately before `collect()`. `ORDER BY` after collection only sorts result rows.
- `collect(x)[0..N]` limits the **final result**, yet still builds the full list before slicing. To limit per customer, use a subquery with `ORDER BY ... LIMIT` **before `collect()`**.
- `LIMIT` on a shared row set is a **global** limit, not a limit of `N` per group.
- If you only need a count, use `count()`; if you need to browse large datasets, return paginated records instead of an unbounded list.
