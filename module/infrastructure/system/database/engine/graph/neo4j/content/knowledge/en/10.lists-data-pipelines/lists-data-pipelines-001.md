# `WITH` in Cypher: Forwarding, Aliasing, and Limiting Variable Scope

## Lesson Objectives

In Neo4j, data is modeled as **nodes**, **relationships**, and properties. When querying a property graph, Cypher does not merely find matching nodes or relationships; it processes a **stream of result rows** across multiple clauses. `WITH` is a key clause for organizing this stream.

After this lesson, you will be able to:

- Use `WITH` to forward the necessary variables from one query stage to the next.
- Alias variables, compute intermediate expressions, and understand why unforwarded variables go out of scope.
- Combine `WITH` with `WHERE`, `DISTINCT`, aggregation functions, `ORDER BY`, `SKIP`, `LIMIT`, and `UNWIND`.
- Read variable-scope errors, avoid overcounting caused by row multiplication when traversing relationships, and choose the right processing position in a pipeline.

## 1. What Does `WITH` Do in a Query?

Imagine a Cypher query as a sequence of data transformation steps:

~~~text
MATCH ...          Find graph patterns and produce result rows
    |
WITH ...           Select, alias, compute, group, or filter rows
    |
MATCH ...          Expand the search using variables still in scope
    |
WITH ...           Process intermediate results
    |
RETURN ...         Return results to the application
~~~

`WITH` has two closely connected roles:

1. **Passing data across stages**: each row after `WITH` contains the variables or expressions listed in that clause.
2. **Defining variable scope**: variables that are not retained generally cannot be referenced in subsequent clauses. A variable aliased with `AS` must be referenced by its new name.

General structure example:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, o
MATCH (o)-[:CONTAINS]->(p:Product)
RETURN c.name AS customer, o.id AS orderId, p.sku AS productSku;
~~~

In the second step, `WITH c, o` keeps both `c` and `o`. Therefore, the next `MATCH` step can use `o` to find products, and `RETURN` can still read `c.name`.

`WITH` is similar to `RETURN` in its ability to select columns and evaluate expressions, except `WITH` **continues the query** whereas `RETURN` **outputs the result**. `WITH` does not create a new transaction on its own or guarantee that intermediate data is materialized into a physical table; Neo4j can still optimize the execution plan of the entire query.

## 2. Sample Data: Customers, Orders, and Products

The following examples use this model:

~~~text
(:Customer)-[:PLACED]->(:Order)-[:CONTAINS {quantity}]->(:Product)
~~~

Each `Customer` places multiple `Order` nodes; each `Order` contains `Product` nodes with the quantity stored on the `CONTAINS` relationship. You can create this small dataset in an **empty test database** with the following query. Running `CREATE` again will create duplicate data.

~~~cypher
CREATE
  (lan:Customer {id: 'C01', name: 'Lan'}),
  (minh:Customer {id: 'C02', name: 'Minh'}),
  (o1:Order {id: 'O01', status: 'PAID'}),
  (o2:Order {id: 'O02', status: 'PENDING'}),
  (o3:Order {id: 'O03', status: 'PAID'}),
  (p1:Product {sku: 'P01', price: 100000}),
  (p2:Product {sku: 'P02', price: 50000}),
  (lan)-[:PLACED]->(o1),
  (lan)-[:PLACED]->(o2),
  (minh)-[:PLACED]->(o3),
  (o1)-[:CONTAINS {quantity: 2}]->(p1),
  (o1)-[:CONTAINS {quantity: 1}]->(p2),
  (o2)-[:CONTAINS {quantity: 1}]->(p1),
  (o3)-[:CONTAINS {quantity: 3}]->(p2);
~~~

From this dataset, Lan has two orders (`O01` and `O02`); Minh has one order (`O03`). The total line-item value of paid orders is 250,000 for Lan and 150,000 for Minh.

## 3. Forwarding and Aliasing Variables

### Keeping Variables Needed in Later Steps

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, o
MATCH (o)-[line:CONTAINS]->(p:Product)
RETURN
  c.name AS customer,
  o.id AS orderId,
  p.sku AS productSku,
  line.quantity AS quantity
ORDER BY orderId, productSku;
~~~

After `WITH c, o`, both variables remain available. After the second `MATCH`, each row corresponds to one product line item in an order. Order `O01` has two `CONTAINS` relationships and thus produces **two rows**, an important detail when counting or summing later.

### Aliasing with `AS`

~~~cypher
MATCH (customer:Customer)
WITH customer AS buyer
RETURN buyer.id AS customerId, buyer.name AS customerName
ORDER BY customerId;
~~~

After `WITH customer AS buyer`, the name to use in the following clause is `buyer`. The old name `customer` is no longer forwarded. Similarly, you can derive new values from properties:

~~~cypher
MATCH (c:Customer)
WITH c.id AS customerId, toUpper(c.name) AS displayName
RETURN customerId, displayName
ORDER BY customerId;
~~~

`customerId` and `displayName` are now computed values; the node variable `c` is no longer in scope for `RETURN`.

### Dropping Variables Is Part of Scope Design

**Incorrect** example:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c.name AS customerName
RETURN o.id AS orderId;
~~~

The query fails because `o` was not forwarded through `WITH`. If you still need `o.id`, keep `o` or project the property into a new variable:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c.name AS customerName, o.id AS orderId
RETURN customerName, orderId
ORDER BY customerName, orderId;
~~~

If you need to keep the original node to continue traversing the graph, use `WITH c, c.name AS customerName`. The `WITH *` syntax forwards all variables currently in scope, but in large queries, explicitly listing the required variables helps control scope and improves maintainability.

> Advanced note: variables imported into a `CALL` subquery have their own scoping rules. The variable-dropping rule above applies directly to standard clause chains in the examples of this lesson.

## 4. Filtering Data Before and After `WITH`

`WHERE` immediately after `MATCH` typically filters the matched patterns. `WHERE` attached to `WITH` can filter the row stream at an intermediate stage, which is especially useful after an aggregation.

For example, consider only paid orders, then find customers with a total amount of at least 200,000:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)-[line:CONTAINS]->(p:Product)
WHERE o.status = 'PAID'
WITH c, sum(line.quantity * p.price) AS totalPaid
WHERE totalPaid >= 200000
RETURN c.id AS customerId, c.name AS customerName, totalPaid
ORDER BY totalPaid DESC;
~~~

This pipeline has three steps:

1. `MATCH ... WHERE o.status = 'PAID'` keeps only line items belonging to paid orders.
2. `WITH c, sum(...) AS totalPaid` groups the rows by customer node `c` and computes the total amount.
3. `WHERE totalPaid >= 200000` filters **after the total has been computed**, so the result contains only customer Lan with `totalPaid = 250000`.

If you mistakenly filter on the total amount before `sum(...)` is calculated, the condition will not have the required total variable. Conversely, filtering order status as early as possible reduces the number of rows that need to be summed.

You can chain consecutive `WITH` clauses to separate calculations:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, count(o) AS orderCount
WITH c.id AS customerId, c.name AS customerName, orderCount
WHERE orderCount >= 2
RETURN customerId, customerName, orderCount;
~~~

The result from the test dataset is customer `C01`, Lan, with `2` orders. Each `WITH` redefines the variable names carried into the next stage.

## 5. Aggregation, Grouping, and Avoiding Overcounting

`WITH` supports aggregation functions such as `count()`, `sum()`, `avg()`, `min()`, `max()`, and `collect()`. When an aggregation function is present, the non-aggregated expressions selected alongside it serve as the **grouping keys**.

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, count(o) AS orderCount
RETURN c.id AS customerId, orderCount
ORDER BY customerId;
~~~

Because `c` is retained, `count(o)` is computed **per customer**: `C01 = 2`, `C02 = 1`. If you only write `WITH count(o) AS orderCount`, all input rows are combined into a single group, yielding the total number of orders across the entire query.

### When One Order Produces Multiple Rows

Consider a query traversing from orders to products:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
WITH
  c,
  count(o) AS lineCount,
  count(DISTINCT o) AS orderCount
RETURN c.id AS customerId, lineCount, orderCount
ORDER BY customerId;
~~~

| Customer | `lineCount` | `orderCount` |
| --- | ---: | ---: |
| `C01` | 3 | 2 |
| `C02` | 1 | 1 |

`count(o)` counts the number of **rows** carrying variable `o`; when an order has multiple products, the same order appears multiple times. `count(DISTINCT o)` counts only distinct order nodes. Choose the counting method based on the metric's semantics, rather than assuming one row after `MATCH` always corresponds to one order.

`WITH DISTINCT` can also deduplicate the entire combination of forwarded values:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(:Order)-[:CONTAINS]->(p:Product)
WITH DISTINCT c, p
RETURN c.id AS customerId, p.sku AS productSku
ORDER BY customerId, productSku;
~~~

Each customer–product pair appears only once, even if the customer bought the same product across multiple orders.

## 6. Sorting, Pagination, and Limiting Intermediate Rows

`WITH` can be combined with `ORDER BY`, `SKIP`, and `LIMIT` to select which rows are passed to the next step. For example, retrieve up to five customers with the most orders, then get the list of orders for that selected group:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, count(o) AS orderCount
ORDER BY orderCount DESC, c.id ASC
LIMIT 5
MATCH (c)-[:PLACED]->(selectedOrder:Order)
RETURN
  c.id AS customerId,
  orderCount,
  collect(selectedOrder.id) AS orderIds
ORDER BY orderCount DESC, customerId ASC;
~~~

`LIMIT 5` is applied **after counting orders per customer**, thereby limiting the number of **customers** before the second `MATCH`. Placing the limit right after individual order rows and before `count()` would mean the count only considers the truncated subset and could return different results.

For stable pagination, use `ORDER BY` with a deterministic tie-breaker key, such as `c.id`, before `SKIP` and `LIMIT`:

~~~cypher
MATCH (c:Customer)
WITH c
ORDER BY c.id
SKIP 0
LIMIT 10
RETURN c.id AS customerId, c.name AS customerName
ORDER BY customerId;
~~~

`SKIP 0` means no rows are skipped yet; to fetch the next page, you can replace it with `SKIP 10`. For large or frequently changing datasets, keyset pagination can be more stable and efficient than continually increasing `SKIP`.

**Ordering of aggregated lists** requires special attention. `ORDER BY` in `WITH` guarantees that the immediately following clause receives rows in sorted order; if you want `collect()` to receive orders sorted by `id`:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, o
ORDER BY o.id
WITH c, collect(o.id) AS orderedOrderIds
RETURN c.id AS customerId, orderedOrderIds
ORDER BY customerId;
~~~

Putting `ORDER BY` only in the final `RETURN` sorts the **result rows**, not the elements already inside a `collect()` list.

## 7. From Rows to Lists and Back with `UNWIND`

A pipeline often needs to collect results in one step and then expand the list to process each element in a later step:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c.id AS customerId, collect(o.id) AS orderIds
UNWIND orderIds AS orderId
RETURN customerId, orderId
ORDER BY customerId, orderId;
~~~

Here, `collect(o.id)` creates an `orderIds` list for each customer; `UNWIND` turns each element of the list into a row. The purpose here is to illustrate the **rows → list → rows** flow. In a real query where aggregation is unnecessary, omitting the `collect()/UNWIND` round-trip is usually simpler.

`WITH` is also useful for **normalizing input data** before `MERGE`. Suppose the application passes a `$orders` parameter as a list of objects with `customerId` and `orderId`:

~~~cypher
UNWIND $orders AS raw
WITH
  trim(raw.customerId) AS customerId,
  trim(raw.orderId) AS orderId
WHERE
  customerId IS NOT NULL AND customerId <> ''
  AND orderId IS NOT NULL AND orderId <> ''
MERGE (c:Customer {id: customerId})
MERGE (o:Order {id: orderId})
MERGE (c)-[:PLACED]->(o);
~~~

For example, `$orders` might be `[{customerId: 'C01', orderId: 'O04'}]` passed as a parameter from the Java Driver or the data access layer in Spring Data Neo4j. `WITH` names the two `trim()`-processed values; `WHERE` filters out rows missing IDs; the subsequent `MERGE` clauses operate only on normalized data. In a production system, you should have uniqueness constraints on the IDs and handle conflicting input data to ensure uniqueness.

## 8. Common Errors and Pitfalls

| Situation | Why It Happens | How to Fix |
| --- | --- | --- |
| `Variable ... not defined` in `RETURN` or `MATCH` after `WITH` | A prior variable was not forwarded or was aliased | List the variable again in `WITH`, or use the new alias |
| Order count is higher than actual | `MATCH` through `CONTAINS` produces multiple rows per order | Use `count(DISTINCT o)` when counting unique orders |
| Incorrect sum after `LIMIT` | Rows were truncated before grouping | Clarify whether you need to limit input rows or limit groups after aggregation |
| `collect()` list has an unexpected order | Only sorted rows at the final `RETURN` | Sort before the clause that performs `collect()` |
| Using `WITH *` at every step | Hard to see which variables are needed vs. accidentally retained | Forward only the variables and expressions you need |
| Assuming `WITH` automatically speeds up queries | Performance depends on row count, graph expansions, and query plan | Use `EXPLAIN`/`PROFILE` to measure; filter early when semantics remain unchanged |

Some optimization principles:

- **Maintain the right unit of data**: a row can represent a customer, an order, or a product line item depending on where `MATCH` is. Before using `count()`, verify what a single row represents.
- **Filter at the right stage**: predicates on simple properties such as `o.status` are usually placed early; predicates on aggregated values such as `totalPaid` go after the `WITH` that computes the sum.
- **Reduce intermediate data intentionally**: project columns, use `DISTINCT`, or apply `LIMIT` when appropriate for the target result. Very large `collect()` lists can consume significant memory.
- **Read the execution plan**: use `EXPLAIN` to inspect the estimated plan and `PROFILE` to observe actual row counts across operators. Do not assume each `WITH` corresponds to a physical materialization of data.

## 9. Practice Exercise

**Task:** From the sample graph, return the ID, name, and order count of customers who have at least two orders. Sort by order count descending, and by ID ascending in case of ties. Use `WITH` to compute and filter the order count.

**Suggested solution:**

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, count(o) AS orderCount
WHERE orderCount >= 2
RETURN
  c.id AS customerId,
  c.name AS customerName,
  orderCount
ORDER BY orderCount DESC, customerId ASC;
~~~

With the dataset in Section 2, the expected result is one row: `customerId = 'C01'`, `customerName = 'Lan'`, `orderCount = 2`.

**Self-check:** If you replace `WITH c, count(o) AS orderCount` with `WITH count(o) AS orderCount`, can you still return the customer name? Why? Answer: **No**, because `c` is neither kept as a grouping key nor forwarded; the count is now computed across all input rows as a whole.

## Key Takeaway

`WITH` is the tool for shaping **data flow and variable scope** in Cypher. Think sequentially: what rows does the current step produce, which variables must the next step keep, and do you need to alias, group, or filter rows before continuing to traverse the graph. Controlling these points well makes Neo4j queries easier to understand, ensures accurate results, and simplifies optimization with `EXPLAIN`/`PROFILE`.
