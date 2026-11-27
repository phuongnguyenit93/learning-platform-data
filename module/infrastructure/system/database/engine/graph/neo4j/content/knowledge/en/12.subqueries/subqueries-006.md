# Isolating Aggregation Steps to Avoid Unintended Row Multiplication

In Neo4j, data is modeled with **nodes**, **relationships**, and their properties (property graph). Cypher queries linked patterns very naturally; however, a `MATCH` clause can generate **multiple intermediate result rows for the same node**. If you expand two independent relationship branches before calling `count()`, `sum()`, or `avg()`, the row count can multiply and distort the metrics.

This lesson belongs to the **Subqueries** section and focuses on **aggregating each branch separately using `CALL` subqueries**. Examples use Neo4j/Cypher to calculate customer order count, revenue, and review count; the same principles apply to users–posts–comments, products–orders–tags, or any node with multiple one-to-many relationships.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why combining multiple `MATCH` branches produces `m × n` rows even when the query does not write `CROSS JOIN`.
2. Recognize incorrect aggregation results caused by row growth, especially with `count()`, `sum()`, and weighted calculations.
3. Use `CALL (var) { ... }` to isolate aggregations, returning exactly one metric row per input node.
4. Distinguish when to use `DISTINCT`, `WITH`, `OPTIONAL MATCH`, and subqueries, and choose the right approach.
5. Inspect intermediate row counts and execution plans with `EXPLAIN`/`PROFILE`.

## 2. Understanding Row Counts in Cypher

Consider the following graph:

~~~text
                     ┌─[:PLACED]─> (O01:Order {amount: 120})
(C01:Customer {name: Mai})
                     ├─[:PLACED]─> (O02:Order {amount: 180})
                     ├─[:WROTE]──> (R01:Review)
                     ├─[:WROTE]──> (R02:Review)
                     └─[:WROTE]──> (R03:Review)
~~~

Customer `C01` has **2 orders** and **3 reviews**. The `PLACED` and `WROTE` branches are independent: reviews do not correspond one-to-one with orders.

You can create the sample data in a database **dedicated to practice**:

~~~cypher
// Run once on a test database; CREATE will add duplicate data if re-run.
CREATE (c:Customer {customerId: 'C01', name: 'Mai'})
CREATE (o1:Order {orderId: 'O01', amount: 120}),
       (o2:Order {orderId: 'O02', amount: 180}),
       (r1:Review {reviewId: 'R01'}),
       (r2:Review {reviewId: 'R02'}),
       (r3:Review {reviewId: 'R03'})
CREATE (c)-[:PLACED]->(o1),
       (c)-[:PLACED]->(o2),
       (c)-[:WROTE]->(r1),
       (c)-[:WROTE]->(r2),
       (c)-[:WROTE]->(r3)
RETURN c.customerId AS createdCustomer;
~~~

The following query expands **both branches** before returning results:

~~~cypher
MATCH (c:Customer {customerId: 'C01'})
MATCH (c)-[:PLACED]->(o:Order)
MATCH (c)-[:WROTE]->(r:Review)
RETURN o.orderId AS orderId, r.reviewId AS reviewId
ORDER BY orderId, reviewId;
~~~

| Order | Review |
|---|---|
| O01 | R01 |
| O01 | R02 |
| O01 | R03 |
| O02 | R01 |
| O02 | R02 |
| O02 | R03 |

The order branch produces 2 rows for `C01`. For **each** of those rows, the next `MATCH` finds 3 reviews; the result is `2 × 3 = 6` rows. This is cardinality multiplication between two independent branches, not Neo4j creating extra orders or reviews.

| Stage | Rows for C01 |
|---|---:|
| `MATCH` customer | 1 |
| Expand `PLACED` branch | 2 |
| Also expand `WROTE` branch | 6 |
| Aggregate in `RETURN` | 1 row, **but values can be wrong** |

Key takeaway: **Cypher aggregates the rows present at the point of aggregation**; it does not automatically reconstruct the original node/relationship counts.

## 3. Common Mistake: Aggregating After Expanding Multiple Branches

~~~cypher
MATCH (c:Customer {customerId: 'C01'})
MATCH (c)-[:PLACED]->(o:Order)
MATCH (c)-[:WROTE]->(r:Review)
RETURN c.customerId AS customerId,
       count(o) AS orderCount,
       count(r) AS reviewCount,
       sum(o.amount) AS totalAmount;
~~~

**Results on the sample data:**

| Metric | Wrong result | Correct result |
|---|---:|---:|
| `orderCount` | 6 | 2 |
| `reviewCount` | 6 | 3 |
| `totalAmount` | 900 | 300 |

`count(o)` counts 6 occurrences of variable `o` across 6 rows; each order is counted 3 times. `count(r)` also counts 6; each review appears twice. `sum(o.amount)` adds `120` three times and `180` three times to get `900`, instead of `120 + 180 = 300`.

When a customer has `m` orders and `n` reviews (both greater than 0), the two branches produce `m × n` rows. Order revenue gets multiplied `n` times. Adding a third independent branch with `k` matches can blow the row count up to `m × n × k`.

**Note on `OPTIONAL MATCH`:** replacing `MATCH` with two consecutive `OPTIONAL MATCH` clauses preserves the customer when a branch is missing, but **does not solve row multiplication** when both branches have multiple records.

~~~cypher
MATCH (c:Customer {customerId: 'C01'})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
OPTIONAL MATCH (c)-[:WROTE]->(r:Review)
RETURN c.customerId AS customerId,
       count(o) AS orderCount,
       count(r) AS reviewCount;
// Still returns 6 and 6 for C01.
~~~

## 4. Primary Solution: Isolating Each Aggregation with `CALL`

On **Neo4j 5.23 and later**, use the subquery syntax with an imported variable list `CALL (c) { ... }`:

~~~cypher
MATCH (c:Customer {customerId: 'C01'})
CALL (c) {
    MATCH (c)-[:PLACED]->(o:Order)
    RETURN count(o) AS orderCount,
           coalesce(sum(o.amount), 0) AS totalAmount
}
CALL (c) {
    MATCH (c)-[:WROTE]->(r:Review)
    RETURN count(r) AS reviewCount
}
RETURN c.customerId AS customerId,
       orderCount,
       reviewCount,
       totalAmount;
~~~

Expected result: `C01 | 2 | 3 | 300`.

How the query executes:

1. The outermost `MATCH` selects customer `c`.
2. The first subquery traverses only `PLACED` and computes `orderCount` and `totalAmount`. Because `RETURN` contains only aggregations, the subquery returns **one row** per `c`.
3. The second subquery traverses only `WROTE` and computes `reviewCount`, also returning **one row** per `c`.
4. The outer query combines the **already aggregated results**, without pairing every order with every review.

~~~text
                          ┌─ CALL (c): PLACED ──> {orderCount: 2, totalAmount: 300} ─┐
(Customer C01) ───────────┤                                                      ├─> 1 result row
                          └─ CALL (c): WROTE  ──> {reviewCount: 3} ───────────────┘
~~~

The subqueries here are **correlated subqueries** because they access node `c` from the outer query. `CALL (c)` explicitly declares the variable passed into each subquery. The aliases `orderCount`, `reviewCount`, and `totalAmount` are returned to the outer query and must not collide with variable names already defined in the same scope.

If you are using a Neo4j version that supports `CALL { ... }` but **does not yet support `CALL (c)`**, use the legacy variable-importing syntax:

~~~cypher
MATCH (c:Customer {customerId: 'C01'})
CALL {
    WITH c
    MATCH (c)-[:PLACED]->(o:Order)
    RETURN count(o) AS orderCount,
           coalesce(sum(o.amount), 0) AS totalAmount
}
CALL {
    WITH c
    MATCH (c)-[:WROTE]->(r:Review)
    RETURN count(r) AS reviewCount
}
RETURN c.customerId AS customerId,
       orderCount, reviewCount, totalAmount;
~~~

`WITH c` at the start of the subquery is the legacy variable-importing syntax; on Neo4j 5.23+, prefer the `CALL (c)` import list. Verify your running Cypher/Neo4j version before copying syntax into an application.

### Why Do Aggregating Subqueries Still Keep Customers Without Data?

When the inner `MATCH` finds no orders, an ungrouped `count(o)` aggregation **without grouping keys** still emits one row with value `0`. `coalesce(sum(o.amount), 0)` explicitly treats missing-order revenue as `0`. Thus, customers with no orders or no reviews still appear in the outer output.

Conversely, a subquery that simply returns matching relationship rows, **without an aggregation guaranteeing a single row**, can return 0 or multiple rows and drop or multiply rows of `c`:

~~~cypher
MATCH (c:Customer)
CALL (c) {
    MATCH (c)-[:PLACED]->(o:Order)
    RETURN o
}
RETURN c.customerId, o.orderId;
// Each order creates one row; customers with no orders are dropped.
~~~

To preserve one output row per customer, you must control the subquery's **cardinality**, not merely wrap any statement in `CALL`.

## 5. Sequential Aggregation with `WITH`: Another Option

For two simple branches, you can aggregate the first branch **before** expanding the second branch:

~~~cypher
MATCH (c:Customer {customerId: 'C01'})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c,
     count(o) AS orderCount,
     coalesce(sum(o.amount), 0) AS totalAmount
OPTIONAL MATCH (c)-[:WROTE]->(r:Review)
RETURN c.customerId AS customerId,
       orderCount,
       totalAmount,
       count(r) AS reviewCount;
~~~

`WITH c, count(o), sum(o.amount)` collapses order data down to **one row per `c`** before the query expands reviews. The result is still `C01 | 2 | 300 | 3` in the query's column order.

| Criterion | Early `WITH` aggregation | Independent `CALL` subqueries |
|---|---|---|
| Branch separation | Sequential clauses inside one pipeline | Each branch lives in its own block |
| Order dependency | Yes: must aggregate one branch before opening the next | Less: each branch aggregates independently |
| Adding more branches | Must manage intermediate `WITH`s and grouping keys | Can append another `CALL` block |
| Code scalability | Concise with few branches | Easier to read with many distinct calculations |
| Key requirement | Preserve grouping keys, such as `c` | Each subquery returns the exact expected row count |

Both approaches are valid. `CALL` is particularly useful when each branch has its own filters, formulas, or grouping levels—for example, summing only paid orders while counting all reviews.

## 6. Why Isn't `DISTINCT` a Universal Cure?

You could fix **just the two node counts** in our example with:

~~~cypher
MATCH (c:Customer {customerId: 'C01'})
MATCH (c)-[:PLACED]->(o:Order)
MATCH (c)-[:WROTE]->(r:Review)
RETURN count(DISTINCT o) AS orderCount,
       count(DISTINCT r) AS reviewCount,
       sum(o.amount) AS totalAmount;
// orderCount = 2, reviewCount = 3, but totalAmount = 900 (still wrong).
~~~

`count(DISTINCT o)` only counts each **distinct `o` node** once. It does not eliminate duplicate rows before `sum(o.amount)` executes. Another patch is `sum(DISTINCT o.amount)`, which also breaks easily:

- Suppose two different orders both have `amount = 120`.
- The true sum is `120 + 120 = 240`.
- `sum(DISTINCT o.amount)` adds **only one `120`**, returning `120`.

`DISTINCT` applies to **the specified value or expression**; it does not understand the business rule "count each order once". If data can contain multiple relationships pointing to the same order, deduplicate by **order identity** *inside the isolated branch* before aggregating:

~~~cypher
MATCH (c:Customer {customerId: 'C01'})
CALL (c) {
    MATCH (c)-[:PLACED]->(o:Order)
    WITH DISTINCT o
    RETURN count(o) AS orderCount,
           coalesce(sum(o.amount), 0) AS totalAmount
}
RETURN c.customerId AS customerId, orderCount, totalAmount;
~~~

The `WITH DISTINCT o` technique makes sense when an order can appear via multiple matching paths yet business rules require counting it **once per Order node**. If the goal is to count actual **relationships** or event occurrences, do not blindly deduplicate them.

## 7. Real-World Cases and Row-Count Traps

### 7.1. Filtering Separately Inside Each Subquery

Example: count all orders, sum revenue of paid orders, and count only public reviews. Assume nodes also carry `status` and `isPublic` properties:

~~~cypher
MATCH (c:Customer)
CALL (c) {
    MATCH (c)-[:PLACED]->(o:Order)
    RETURN count(o) AS allOrders
}
CALL (c) {
    MATCH (c)-[:PLACED]->(o:Order)
    WHERE o.status = 'PAID'
    RETURN coalesce(sum(o.amount), 0) AS paidRevenue
}
CALL (c) {
    MATCH (c)-[:WROTE]->(r:Review)
    WHERE r.isPublic = true
    RETURN count(r) AS publicReviews
}
RETURN c.customerId AS customerId,
       allOrders, paidRevenue, publicReviews
ORDER BY customerId;
~~~

Each filter governs only its own branch. This is a major advantage when relationships have differing business conditions.

### 7.2. Input Already Multiplied Before Calling `CALL`

`CALL` executes over the outer query's input rows. If `c` already appears multiple times from a preceding `MATCH`, the subquery will be evaluated repeatedly for the same customer and the final output will still have multiple rows:

~~~cypher
// Can produce multiple rows per customer if they have multiple accounts.
MATCH (c:Customer)-[:OWNS]->(a:Account)
WITH DISTINCT c
CALL (c) {
    MATCH (c)-[:PLACED]->(o:Order)
    RETURN count(o) AS orderCount
}
RETURN c.customerId AS customerId, orderCount;
~~~

`WITH DISTINCT c` proactively establishes **one row per customer** before the independent aggregations. Use this only when business rules truly require statistics **per customer**; if statistics must be **per customer and account**, the grouping key must include both `c` and `a`, and inner subquery conditions must reflect that relationship.

### 7.3. Multi-Level Relationship Aggregation

If revenue lives on `OrderLine` rather than `Order`, you can aggregate all line items **within a single subquery**, then return one number outside:

~~~cypher
MATCH (c:Customer)
CALL (c) {
    MATCH (c)-[:PLACED]->(:Order)-[:HAS_LINE]->(line:OrderLine)
    RETURN coalesce(
        sum(line.quantity * line.unitPrice),
        0
    ) AS grossAmount
}
CALL (c) {
    MATCH (c)-[:WROTE]->(r:Review)
    RETURN count(r) AS reviewCount
}
RETURN c.customerId AS customerId, grossAmount, reviewCount;
~~~

Here the summation scope is **order lines**. If the same `OrderLine` can be reached by multiple paths and must be counted once per line, deduplicate **order lines** before summing. There is no single default deduplication rule that fits every data model.

### 7.4. `COUNT { ... }` When You Only Need to Count

In Neo4j 5 versions that support **count subqueries**, `COUNT { ... }` is convenient when you only need to count pattern matches:

~~~cypher
MATCH (c:Customer)
RETURN c.customerId AS customerId,
       COUNT { (c)-[:PLACED]->(:Order) } AS orderCount,
       COUNT { (c)-[:WROTE]->(:Review) } AS reviewCount;
~~~

Both count expressions are evaluated independently for each `c`, so they do not produce an `Orders × Reviews` product. However, `COUNT { ... }` counts **matching relationship patterns**; with parallel relationships, match count may differ from unique target node count. For calculations like `sum(amount)` or multiple metrics in the same branch, an aggregating `CALL` is usually more flexible.

## 8. Verifying and Tuning Queries

**Verify correctness first, then optimize speed.** A query returning a single row very quickly can still contain multiplied numbers.

1. **Write an unaggregated detail query:** return keys such as `o.orderId`, `r.reviewId` to observe the combinations and locate where row multiplication begins.
2. **Identify the unit to count/sum:** Order node, PLACED relationship, OrderLine, or a customer–order pair? This determines whether `DISTINCT` is needed.
3. **Test edge cases:** customers with `0`/`1`/many orders and `0`/`1`/many reviews; two orders with identical amounts; data with duplicate paths; input streams already containing repeated customers.
4. **Verify against known data:** the example above must yield `orderCount = 2`, `reviewCount = 3`, and `totalAmount = 300`.
5. **Measure the execution plan:** use `EXPLAIN` to view the planned execution and `PROFILE` to inspect actual `Rows`, `DB Hits`, and expansion/aggregation operators.

Example analyzing a query prone to row multiplication:

~~~cypher
PROFILE
MATCH (c:Customer {customerId: 'C01'})
MATCH (c)-[:PLACED]->(o:Order)
MATCH (c)-[:WROTE]->(r:Review)
RETURN count(o) AS orders, sum(o.amount) AS amount;
~~~

In the Neo4j Browser plan view, watch the row counts flowing through the expansion operators: from 2 order rows up to 6 combinations after expanding reviews. **An operator named `CartesianProduct` does not have to appear** for row multiplication to occur; multiple branches sharing variable `c` also multiply combinations.

Now compare with the `CALL` version:

~~~cypher
PROFILE
MATCH (c:Customer {customerId: 'C01'})
CALL (c) {
    MATCH (c)-[:PLACED]->(o:Order)
    RETURN count(o) AS orderCount,
           coalesce(sum(o.amount), 0) AS totalAmount
}
CALL (c) {
    MATCH (c)-[:WROTE]->(r:Review)
    RETURN count(r) AS reviewCount
}
RETURN orderCount, totalAmount, reviewCount;
~~~

Subqueries avoid creating the **cross product of two intermediate result sets**, though that does not automatically guarantee every query will run faster. Total runtime also depends on input customer count, branching factor, indexes on lookup properties, relationship modeling, and optimizer plan choices. When querying a large customer base, benchmark on representative-scale data and return only necessary columns.

## 9. Quick Solution Selection Table

| Situation | Appropriate approach |
|---|---|
| Two independent one-to-many branches needing multiple metrics per branch | Aggregate each branch separately with `CALL (c) { ... }` |
| Few branches, simple metrics, wanting a short single pipeline | Aggregate one branch with `WITH` before `MATCH`ing the next |
| Only need to count matches of a pattern | `COUNT { ... }` (if supported by the version) |
| Need to count distinct destination nodes | `count(DISTINCT node)`, or `WITH DISTINCT node` before aggregating |
| Need total amount per order despite duplicate rows | Deduplicate **by order** inside the branch then `sum()`; avoid `sum(DISTINCT amount)` |
| Need to keep customers even without linked data | Subquery with only ungrouped aggregation, or `OPTIONAL MATCH` paired with `WITH` appropriately |
| Input stream may repeat the same customer | Normalize row keys with `WITH DISTINCT c` before subqueries if aggregating per customer |

## 10. Practice Exercises

**Exercise 1 — Predict the numbers:** An author has 4 posts and 5 followers. A query expands both branches and runs `RETURN count(post), count(follower)`. What is the result? When might `count(DISTINCT post)` be helpful?

<details>
<summary>Answer hint</summary>

If each post and each follower yields one match, there are `4 × 5 = 20` rows, so both `count(...)` expressions return `20`. `count(DISTINCT post)` brings the post count back to `4`; to avoid row multiplication from the start, aggregate the two branches independently.

</details>

**Exercise 2 — Fix the query:** Rewrite a query computing total order amount and login count per user, given the patterns `(u:User)-[:BOUGHT]->(o:Order)` and `(u)-[:LOGGED_IN]->(s:Session)`. Requirement: always emit one row per `u`, even if the user has never placed an order or logged in.

<details>
<summary>Reference solution</summary>

~~~cypher
MATCH (u:User)
CALL (u) {
    MATCH (u)-[:BOUGHT]->(o:Order)
    RETURN count(o) AS orderCount,
           coalesce(sum(o.amount), 0) AS spent
}
CALL (u) {
    MATCH (u)-[:LOGGED_IN]->(s:Session)
    RETURN count(s) AS sessionCount
}
RETURN u, orderCount, spent, sessionCount;
~~~

Each `CALL` returns a single ungrouped aggregation row, preserving `u` nodes that lack matching relationships. Adjust the counting rule if multiple relationships can point to the same target node.

</details>

**Exercise 3 — Analyze the mistake:** Two orders both have `amount = 200`. Why can `sum(DISTINCT o.amount)` return `200` instead of `400`? Describe how to use `WITH DISTINCT o` inside a subquery to sum by order identity.

## 11. Takeaways

- **Row multiplication happens before aggregation.** Two independent one-to-many branches attached to the same node can create `m × n` combinations.
- **Identify the exact unit of aggregation.** Counting nodes, relationships, and line items are three distinct goals.
- **Isolating aggregations with `CALL` subqueries** ensures each branch returns compacted metrics and prevents one branch from multiplying another branch's rows.
- **`DISTINCT` is no substitute for a proper aggregation model**, especially when summing equal values.
- **Inspect `Rows` using `PROFILE`** to catch row-count bugs and evaluate query cost on realistic data.
