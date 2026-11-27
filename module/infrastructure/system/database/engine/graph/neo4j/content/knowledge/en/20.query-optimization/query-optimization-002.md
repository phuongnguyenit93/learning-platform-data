# Pushing Filter Predicates to Semantically Correct Positions and Reducing Row Counts

## 1. Why Does Filter Placement Determine Both Speed and Results?

When querying a **property graph** with **Cypher**, a single result row can be multiplied at each relationship expansion. For example, a customer has 200 orders, and each order has an average of 8 product line items. If a query expands all orders and products before selecting the needed ones, intermediate results can grow to around **1,600 rows**. If the business logic only needs 10 paid orders, filtering in the right place can substantially reduce the number of rows flowing through subsequent steps.

However, "moving **WHERE** earlier" is not a mechanical rule. Filter placement also determines which question the query is answering:

- Filtering orders **before LIMIT**: retrieve the 10 most recent paid orders.
- Taking the 10 most recent orders **before filtering**: out of the 10 newest orders, keep only the paid ones; the result may have fewer than 10 rows.
- Filtering inside **OPTIONAL MATCH**: keep the customer even if they have no matching orders.
- Filtering rows with **null** values after OPTIONAL MATCH: can eliminate the customer from the result.

The goal of this lesson is to write **semantically correct** queries first, and then structure filtering, graph expansion, aggregation, and pagination to **limit the number of rows processed**. Neo4j has a query optimizer (*query planner*) that can automatically push certain predicates down to appropriate execution positions; therefore, you must verify using **EXPLAIN** and **PROFILE** rather than drawing conclusions solely from the order of Cypher clauses.

## 2. Running Example: Customer, Order, and Product

Suppose the application has the following graph:

~~~text
(c:Customer {customerId, name})
    |
    +--[:PLACED]-->(o:Order {orderId, status, createdAt, totalInCents})
                        |
                        +--[line:HAS_ITEM {quantity}]-->(p:Product {productId, category, active})
~~~

A customer can place many orders; an order can have many **HAS_ITEM** relationships to products. Common read requirements include:

1. List the **20 most recent PAID orders** for a customer.
2. Display a customer along with their **PAID order count**, even if the customer has no matching orders.
3. Retrieve only orders that **contain at least one product** in a target category.
4. Paginate **by order** while also returning each order's list of product line items.

Illustrative data assumptions: **Customer.customerId** and **Order.orderId** are unique business keys; **Order.createdAt** has a consistent temporal type; each order has a single PLACED relationship from its customer. If real-world data contains duplicate PLACED relationships between the same pair, address the modeling issue or consider DISTINCT in the right position.

In parameterized examples, the application must pass **$customerId**, **$pageSize**, **$category**, etc., with appropriate types; **$pageSize** should be bounds-checked before being sent to Neo4j.

## 3. Understanding "Row Count" After Each MATCH Step

Examine the query:

~~~cypher
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
MATCH (o)-[line:HAS_ITEM]->(p:Product)
RETURN c.customerId AS customerId,
       o.orderId AS orderId,
       p.productId AS productId,
       line.quantity AS quantity;
~~~

If the customer has 200 orders and each order has 8 line items:

| Logical Step | Illustrative Row Count |
|---|---:|
| Find one Customer by customerId | 1 |
| Expand PLACED to 200 Orders | 200 |
| Expand HAS_ITEM from each Order | 1,600 |
| RETURN four columns | 1,600 |

The numbers above are illustrative only; real graphs have different degrees and conditions. Each result row of a MATCH represents a **combination of variables matching the pattern**. One Order is repeated across multiple rows if it has multiple HAS_ITEM relationships.

If the API only displays order IDs and statuses, expanding to Product is completely unnecessary. Write the query according to the data contract:

~~~cypher
MATCH (:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN o.orderId AS orderId,
       o.status AS status
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $pageSize;
~~~

The query avoids expanding HAS_ITEM, preventing row multiplication by the number of product lines. The key is to define clearly **what entity each row represents**, and then produce only the necessary combinations.

## 4. Placing WHERE with the MATCH Pattern It Constrains

### 4.1. Filtering Customer and Order Directly

~~~cypher
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
  AND o.createdAt >= $fromDate
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt,
       o.totalInCents AS totalInCents;
~~~

The query expresses three conditions:

- Find the exact Customer by **customerId** key.
- Traverse only **PLACED** relationships to fetch that customer's Orders.
- Keep Orders with **status = PAID** and **createdAt** on or after the target date.

Placing predicates close to the MATCH pattern helps readers see that the condition applies to the **matched orders**, while also giving the optimizer opportunities to leverage predicates where beneficial.

You could write an equivalent form in terms of the result set when there is no aggregation, pagination, or optional match boundary:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, o
WHERE c.customerId = $customerId
  AND o.status = 'PAID'
  AND o.createdAt >= $fromDate
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt,
       o.totalInCents AS totalInCents;
~~~

**Do not assert** that the second form always starts by expanding the entire graph. Neo4j can often safely move predicates around in the execution plan. The first form makes the starting point and scope easier to read; to know which form is faster on real data, inspect the plan and measure.

### 4.2. Filtering Relationship Properties

If you need to find line items with a quantity of at least 3 and a product in a given category:

~~~cypher
MATCH (o:Order {orderId: $orderId})
      -[line:HAS_ITEM]->
      (p:Product)
WHERE line.quantity >= $minQuantity
  AND p.category = $category
RETURN p.productId AS productId,
       line.quantity AS quantity;
~~~

**line.quantity** is a property of the **HAS_ITEM** relationship; **p.category** is a property of the Product node. Both are predicates on the matched pattern. A filter placed on the wrong variable can make the query return incorrect data even though it executes without error.

### 4.3. Choosing a Selective Starting Point

The following two forms express a predicate on Customer:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
RETURN c.name AS name;
~~~

~~~cypher
MATCH (c:Customer)
WHERE c.customerId = $customerId
RETURN c.name AS name;
~~~

With the same equality predicate and label, these two approaches are generally semantically equivalent; the planner can pick a nearly identical lookup strategy. When **Customer.customerId** is a unique key, an appropriate constraint/index lets Neo4j find the target node without scanning every Customer.

Example of a constraint deployed by schema migration, **not** executed on every read request:

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;
~~~

Placing WHERE in an intuitive spot alone is not enough for optimization. Speed also depends on labels, indexes, statistics, selectivity, graph traversal direction, and the row count produced after each Expand.

## 5. OPTIONAL MATCH: Where WHERE Placement Changes the Result Set

This is the most important case when discussing **semantic correctness**.

Suppose you need to display a Customer **even if they have no PAID orders**, along with their PAID order count if any exist.

### 5.1. Correct: Filtering Directly Inside OPTIONAL MATCH

~~~cypher
MATCH (c:Customer {customerId: $customerId})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN c.customerId AS customerId,
       count(o) AS paidOrders;
~~~

**WHERE** is attached to **OPTIONAL MATCH**. Neo4j treats only PAID orders as matching records in the optional part. If there are no PAID orders, the Customer row is still preserved, and variable **o** receives **null**.

In that case, **count(o)** equals 0 because it does not count null values. This is the right behavior for a reporting view that must include customers who have no PAID orders yet.

### 5.2. Different Meaning: Filtering After Passing Optional Results Through WITH

~~~cypher
MATCH (c:Customer {customerId: $customerId})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, o
WHERE o.status = 'PAID'
RETURN c.customerId AS customerId,
       count(o) AS paidOrders;
~~~

In this query, WHERE filters **the rows after OPTIONAL MATCH**. If the customer has no orders, or only has orders with a status other than PAID, the expression **o.status = 'PAID'** does not evaluate to true for any row. The result has **no Customer rows left** to return.

Comparison table:

| Customer Data | WHERE inside OPTIONAL MATCH | WHERE after WITH |
|---|---|---|
| Has 3 PAID orders | Customer, paidOrders = 3 | Customer, paidOrders = 3 |
| Has 2 NEW orders, no PAID | Customer, paidOrders = 0 | No rows |
| Has no orders | Customer, paidOrders = 0 | No rows |

Therefore, "pushing WHERE earlier" cannot mean freely moving predicates across an **OPTIONAL MATCH** boundary. You must explicitly decide whether the business rule is **filtering the optional linked entities** or **filtering the parent row itself**.

### 5.3. Distinguishing count(o) and count(*)

~~~cypher
MATCH (c:Customer {customerId: $customerId})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN count(o) AS paidOrders,
       count(*) AS rowsAfterOptional;
~~~

If the Customer exists but has no PAID orders, **count(o) = 0**, whereas **count(*) = 1** because there is still one row containing the Customer and a null variable o. To count actual matching optional entities, typically use **count(o)** or **count(DISTINCT o)** depending on the data model.

### 5.4. When Should Customers Without PAID Orders Be Excluded?

If the requirement is "only return Customers who **have at least one** PAID order," a mandatory MATCH or an EXISTS predicate may be more appropriate:

~~~cypher
MATCH (c:Customer)
WHERE EXISTS {
    MATCH (c)-[:PLACED]->(o:Order)
    WHERE o.status = 'PAID'
}
RETURN c.customerId AS customerId,
       c.name AS name;
~~~

EXISTS checks **existence** and does not force creating a result row for every matching Order. This is useful when you only need to know whether a matching relationship exists, rather than returning all Orders.

## 6. Should WHERE Come Before or After LIMIT?

### 6.1. "20 Most Recent PAID Orders" — Filter Before Pagination

~~~cypher
MATCH (:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt
ORDER BY createdAt DESC, orderId DESC
LIMIT $pageSize;
~~~

First, the candidate set is restricted to **PAID orders**; then it is sorted and up to **pageSize** rows are selected. If the customer has enough PAID orders, the result can contain the exact requested number of rows.

### 6.2. "Among the 20 Most Recent Orders, Get the PAID Ones" — Filter After Pagination

~~~cypher
MATCH (:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WITH o
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $pageSize
WITH o
WHERE o.status = 'PAID'
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt
ORDER BY createdAt DESC, o.orderId DESC;
~~~

This query fetches up to **pageSize** most recent orders **regardless of status**, then discards non-PAID orders. If only 6 of the 20 most recent orders are PAID, the result has 6 rows, even if older PAID orders exist.

Both queries can be valid, but they answer **two different questions**. Choose based on the product requirement; never move WHERE across LIMIT just because "filtering earlier is faster."

### 6.3. Stable Pagination Requires ORDER BY

Cypher does not guarantee row ordering without ORDER BY. If multiple orders share the same **createdAt**, include a tie-breaker key like **orderId** for deterministic ordering:

~~~cypher
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $pageSize
~~~

**LIMIT** caps the number of returned rows, yet the engine may still need to scan and sort many rows to determine the top N. It does not guarantee processing cost proportional to only N records. Appropriate indexes and query starting points remain important.

## 7. Filtering and LIMIT Before Expanding High-Fan-Out Relationships

An API requires the **20 most recent PAID orders**, each with its list of products. The following query uses the wrong pagination unit:

~~~cypher
MATCH (:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
MATCH (o)-[line:HAS_ITEM]->(p:Product)
WHERE o.status = 'PAID'
RETURN o.orderId AS orderId,
       p.productId AS productId,
       line.quantity AS quantity
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $pageSize;
~~~

Because one Order has multiple product lines, LIMIT caps the **number of order–item rows**. For instance, if the newest order has 15 line items, it consumes 15 out of 20 rows; orders without items are excluded entirely by the mandatory MATCH. This query fails to fulfill "20 orders, each with all its items."

### 7.1. Writing It to Preserve the Correct Page Unit

~~~cypher
MATCH (:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
WITH DISTINCT o
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $pageSize

OPTIONAL MATCH (o)-[line:HAS_ITEM]->(p:Product)
WITH o,
     collect(
         CASE
             WHEN p IS NULL THEN null
             ELSE {
                 productId: p.productId,
                 category: p.category,
                 quantity: line.quantity
             }
         END
     ) AS items
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt,
       o.status AS status,
       items
ORDER BY createdAt DESC, orderId DESC;
~~~

How it is structured:

1. MATCH Customer and Order, keeping only PAID status.
2. **WITH DISTINCT o** picks one row per Order before paginating. DISTINCT matters if the model or path pattern could put the same Order into multiple rows; with a single PLACED relationship per Order, it may be unnecessary.
3. **ORDER BY + LIMIT** selects the page by **Order**.
4. **OPTIONAL MATCH** expands the item list after the page has been chosen.
5. **collect(...)** aggregates multiple item rows into one list per Order. **collect(null)** adds no null elements, so an Order with no items receives an empty list.
6. The final ORDER BY restores output order; ordering from an earlier WITH should not be implicitly assumed to hold across all final rows after subsequent expansions and aggregations.

This pattern still has to inspect the Orders needed to determine the top N; its biggest value is avoiding expanding items on **every** Order before deciding which page to take.

### 7.2. Do Not Place Product Predicates in the Wrong Spot

If the requirement is "the 20 most recent PAID orders **that contain** a Product in category X," you must not take 20 orders first and filter products afterward if you expect up to 20 orders **matching the condition**. Check for the existence of a matching Product before paginating:

~~~cypher
MATCH (:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
  AND EXISTS {
      MATCH (o)-[:HAS_ITEM]->(p:Product)
      WHERE p.category = $category
  }
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt
ORDER BY createdAt DESC, orderId DESC
LIMIT $pageSize;
~~~

EXISTS fits well because the API only needs to know whether the order contains **at least one** product in the category. Using a regular MATCH to expand Product could generate multiple rows for the same order and skew pagination unless grouped/deduplicated beforehand.

## 8. WHERE After WITH and Aggregations: Different from Filtering Base Rows

Consider the requirement: "Find Customers with **at least 5 PAID orders**."

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
WITH c, count(DISTINCT o) AS paidOrders
WHERE paidOrders >= $minPaidOrders
RETURN c.customerId AS customerId,
       paidOrders
ORDER BY paidOrders DESC;
~~~

There are two WHERE clauses with distinct roles:

- **WHERE o.status = 'PAID'** before WITH: removes Order rows that do not meet the condition **before counting**.
- **WHERE paidOrders >= $minPaidOrders** after WITH: removes **Customer groups** whose aggregated result fails the threshold.

You cannot simply push **paidOrders >= ...** before the **paidOrders** variable is computed. Neo4j does not use SQL's HAVING clause; a WHERE on aggregation results is normally written after WITH.

### 8.1. Filtering Items Before SUM Changes the Summed Value

Suppose you need to calculate the **total quantity across all line items** for each Order, but only return Orders whose total is at least 10:

~~~cypher
MATCH (o:Order {orderId: $orderId})-[line:HAS_ITEM]->(:Product)
WITH o, sum(line.quantity) AS totalQuantity
WHERE totalQuantity >= 10
RETURN o.orderId AS orderId,
       totalQuantity;
~~~

If you move **line.quantity >= 10** into the MATCH before SUM, you are summing **only line items with quantity >= 10** and dropping smaller lines. The result is no longer equivalent: an order with 6 + 4 items has a total of 10, yet neither line reaches the threshold of 10.

This is the difference between a **predicate on individual rows** and a **predicate on aggregated results**.

### 8.2. Does DISTINCT Reduce Rows Sensibly?

~~~cypher
MATCH (o:Order)-[:HAS_ITEM]->(p:Product)
RETURN DISTINCT o.orderId AS orderId,
                p.category AS category;
~~~

DISTINCT here deduplicates **(orderId, category) pairs**; it does not turn the whole result into **one row per Order**. If the API needs the number of product categories per Order, aggregate intentionally:

~~~cypher
MATCH (o:Order)-[:HAS_ITEM]->(p:Product)
WITH o, count(DISTINCT p.category) AS categoryCount
RETURN o.orderId AS orderId,
       categoryCount;
~~~

Do not overuse DISTINCT as a cure-all for row count issues. First determine the grouping key and which fields actually need to be retained.

## 9. Filtering via EXISTS to Avoid Unnecessary Row Multiplication

When merely checking **whether or not** a relationship exists, expanding it often creates extra rows that the application never uses.

### 9.1. An Approach That Can Multiply Rows

~~~cypher
MATCH (o:Order)-[:HAS_ITEM]->(p:Product)
WHERE p.category = $category
RETURN o.orderId AS orderId;
~~~

An Order containing three Products in the same category will appear three times. To remove duplicates, you must add DISTINCT or another aggregation.

### 9.2. Expressing Existence Directly

~~~cypher
MATCH (o:Order)
WHERE EXISTS {
    MATCH (o)-[:HAS_ITEM]->(p:Product)
    WHERE p.category = $category
}
RETURN o.orderId AS orderId;
~~~

This asks **"Does the Order have at least one Product in this category?"**. EXISTS does not need to emit multiple rows for multiple matching Products. The planner can choose an execution plan tailored for an existence check.

Do not assume EXISTS is always faster than DISTINCT. The selectivity of Order and Product, relationship counts, and indexes can change the optimal plan. Choose EXISTS first for **clarity of intent**, then verify performance.

## 10. NULL and Three-Valued Logic in WHERE

In Cypher, comparison expressions involving **null** generally evaluate to null; WHERE only keeps rows where the expression evaluates to **true**.

~~~cypher
MATCH (o:Order)
WHERE o.status <> 'CANCELLED'
RETURN o.orderId AS orderId;
~~~

This query **does not** return Orders missing the status property, because **null <> 'CANCELLED'** is not true. If the business logic wants to keep orders without a status as well:

~~~cypher
MATCH (o:Order)
WHERE o.status IS NULL
   OR o.status <> 'CANCELLED'
RETURN o.orderId AS orderId;
~~~

Similarly, when OPTIONAL MATCH produces null variables, predicates on those variables can eliminate rows in later filtering steps. Before moving a WHERE clause, always check edge cases where **a variable is unbound, a property is absent, or no matching relationship exists**.

**Do not confuse correctness with forcing coalesce.** Turning null into a default status can mask data bugs; null-handling rules must come from the business contract.

## 11. Avoid Dropping Needed Variables When WITH Cuts Scope

WITH acts as a projection selecting variables, while also enabling filtering, pagination, aggregation, or splitting a query pipeline. Variables not carried forward through WITH are no longer in scope afterward.

Valid example:

~~~cypher
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
WITH c.customerId AS customerId, o
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $pageSize
RETURN customerId,
       o.orderId AS orderId,
       o.createdAt AS createdAt;
~~~

If WITH only keeps **o**, subsequent clauses can no longer reference the previously declared variable **c**. When moving a condition after WITH, ensure any variables used in that condition are still passed forward. This is a matter of **Cypher scoping**, independent of performance.

Also distinguish between:

- **WITH o WHERE o.status = ...**: filters each individual row `o`.
- **WITH c, count(o) AS n WHERE n >= 5**: filters groups after aggregation.
- **WITH o ORDER BY ... LIMIT 20**: establishes an ordered subset before the next step.

These boundaries can alter **semantics** if predicates are moved across them.

## 12. Avoid Cartesian Products When Filtering by Relationships

The query below does not accurately express "orders of a Customer":

~~~cypher
MATCH (c:Customer), (o:Order)
WHERE c.customerId = $customerId
  AND o.status = 'PAID'
RETURN c.customerId AS customerId,
       o.orderId AS orderId;
~~~

The two patterns **(c:Customer)** and **(o:Order)** are not connected by a relationship; they can pair the matching Customer with every PAID Order in the database. Even with WHERE clauses, the result can include orders **not belonging to** that Customer.

When the business rule requires an ownership relationship:

~~~cypher
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN c.customerId AS customerId,
       o.orderId AS orderId;
~~~

Cypher must express the true **data relationship**, not just filter to shrink row counts. An intentional Cartesian product is occasionally valid, but it must stem from a requirement to generate all combinations, not from accidentally omitting a relationship pattern.

## 13. The Planner Can Push Predicates: Read the Plan Instead of Guessing

Neo4j uses a query planner to decide node access order, index usage, and Filter/Expand/Sort/Aggregation operators. **Textual order** is not necessarily the physical operator order.

### 13.1. EXPLAIN Inspects the Plan Without Running the Query

~~~cypher
EXPLAIN
MATCH (:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt
ORDER BY createdAt DESC, orderId DESC
LIMIT $pageSize;
~~~

In the plan, observe:

- **NodeIndexSeek / NodeUniqueIndexSeek** if the query leverages the corresponding index/constraint.
- **NodeByLabelScan** when a set of nodes must be scanned by label.
- Where **Filter** sits relative to **Expand**; predicates may be fused into another operator.
- **Estimated Rows**, **Sort/Top** steps, **Aggregation**, and expected row volumes.
- The order in which the plan accesses the starting point and expands relationships.

Specific operator names vary across Neo4j versions and runtimes; do not rely on a single fixed operator name to draw conclusions.

### 13.2. PROFILE Measures During Execution

~~~cypher
PROFILE
MATCH (:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt
ORDER BY createdAt DESC, orderId DESC
LIMIT $pageSize;
~~~

PROFILE **executes** the query and returns actual metrics, which can include **Rows**, **DB Hits**, memory statistics, and executed operators. The query above is read-only; if you PROFILE a **CREATE/SET/DELETE** query, the writes are also executed, so do not treat PROFILE as a safe dry run on important data.

To compare two query formulations:

1. Use the **same database, dataset, parameters, and page limit**.
2. Confirm both queries return **equivalent results per the business requirement** before comparing performance.
3. Compare **Rows** after each Expand/Filter operator, DB Hits, and Sort/Aggregation cost.
4. Also measure returned payload size, read latency through the Java Driver, and DTO/JSON construction time if the API handles substantial data.
5. Repeat measurements appropriately on representative data; warm/cold caches and concurrent load can shift timings.

Returning fewer columns does not necessarily make the server faster if the query still scans many nodes and sorts many rows. Conversely, selecting the exact page before expanding child relationships can significantly cut intermediate row counts.

### 13.3. Indexes and Constraints Supporting Selectivity

These are schema examples you might consider for the query above, depending on your model:

~~~cypher
CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;
~~~

~~~cypher
CREATE INDEX order_status_created_at IF NOT EXISTS
FOR (o:Order)
ON (o.status, o.createdAt);
~~~

Do not create an index for every property appearing in WHERE. Indexes incur storage, write, and maintenance costs; their usefulness depends on property selectivity and whether the query starts from Customer and expands to Order. An index on Order may provide little benefit to a plan that already finds very few Orders via the relationship from Customer.

Reading the query plan is the practical way to see which indexes are actually used. Create schema changes through an appropriate migration workflow and validate existing data before adding uniqueness constraints.

## 14. Integrating Narrow Queries with the Java Driver

The API only needs a list of **OrderSummary**, so Cypher returns columns matching the DTO; avoid returning full Order nodes and relationships only to filter them in Java.

~~~java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class OrderReadService {
    public record OrderSummary(
        String orderId,
        String status,
        String createdAt
    ) {}

    private final Driver driver;

    public OrderReadService(Driver driver) {
        this.driver = driver;
    }

    public List<OrderSummary> recentPaidOrders(
            String customerId, int requestedPageSize) {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("customerId is required");
        }
        int pageSize = Math.max(1, Math.min(requestedPageSize, 100));

        String cypher = """
            MATCH (:Customer {customerId: $customerId})
                  -[:PLACED]->(o:Order)
            WHERE o.status = 'PAID'
            RETURN o.orderId AS orderId,
                   o.status AS status,
                   toString(o.createdAt) AS createdAt
            ORDER BY o.createdAt DESC, o.orderId DESC
            LIMIT $pageSize
            """;

        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            return session.executeRead(tx ->
                tx.run(cypher, Map.of(
                    "customerId", customerId,
                    "pageSize", pageSize
                )).list(row -> new OrderSummary(
                    row.get("orderId").asString(),
                    row.get("status").asString(),
                    row.get("createdAt").asString()
                ))
            );
        }
    }
}
~~~

This example assumes **Order.createdAt** has a valid value and **Order.orderId, Order.status** are non-null. If the data allows missing properties, define the DTO and mapping rules accordingly. **Driver** is reused across the application; each **Session** is short-lived. **executeRead** uses a managed transaction for read operations and provides retry handling for transient errors recognized by the driver.

With **Spring Data Neo4j**, the same idea applies: define a DTO/projection for the endpoint, use Cypher returning only required fields, and inspect the mapping. Do not assume you must load an entire aggregate entity and its relationships just to return a summary list.

Optimizing WHERE placement and row counts in Neo4j reduces work for the Driver, though you should still measure query duration, materialized record counts, and JSON payload size on the application side.

## 15. Practice: Identifying Correct Semantics and Row Counts

### Exercise 1 — Filtering Status Before LIMIT

Requirement: "Fetch up to the 10 most recent PAID orders for Customer X." Choose between the two approaches:

~~~cypher
// Approach A
MATCH (:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN o.orderId AS orderId
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT 10;
~~~

~~~cypher
// Approach B
MATCH (:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WITH o ORDER BY o.createdAt DESC, o.orderId DESC LIMIT 10
WITH o WHERE o.status = 'PAID'
RETURN o.orderId AS orderId;
~~~

**Answer:** Approach A meets the requirement because it filters for PAID before taking the top 10. Approach B returns only the PAID orders that happen to fall within the 10 newest orders regardless of status; the result may have fewer than 10 rows.

### Exercise 2 — Preserving Customers Without Orders

Requirement: "Return the Customer and their count of CANCELLED orders, even when 0." Query:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, o
WHERE o.status = 'CANCELLED'
RETURN c.customerId AS customerId, count(o) AS cancelledOrders;
~~~

**Issue:** WHERE after WITH filters out the Customer row when there are no CANCELLED orders.

**Fix:**

~~~cypher
MATCH (c:Customer {customerId: $customerId})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WHERE o.status = 'CANCELLED'
RETURN c.customerId AS customerId, count(o) AS cancelledOrders;
~~~

### Exercise 3 — Paginating by Order or by Order–Product?

An Order has 12 items. Can a query that does MATCH Order, MATCH HAS_ITEM, and then LIMIT 10 at the end guarantee returning 10 Orders?

**Answer:** No. It limits to 10 **Order–Item rows**, which might represent only part of a single Order. You must paginate on Order before expanding HAS_ITEM and aggregating items if the contract requires one row per Order.

### Exercise 4 — WHERE with Aggregation Results

Requirement: "Retrieve only Orders whose total quantity across product lines is at least 20." Is filtering **line.quantity >= 20** before SUM correct?

**Answer:** No. That drops smaller lines that contribute to the total. You must compute **sum(line.quantity)** per Order, then apply **WHERE** on the computed total variable in WITH.

### Exercise 5 — Querying for Existence

Requirement: "Retrieve only Order IDs that have at least one Product with category = 'BOOK'." If you MATCH HAS_ITEM directly, how many times does an Order with 5 books appear?

**Answer:** Potentially 5 times, one row per matching Product. You can use **WHERE EXISTS { MATCH ... }** to express existence and avoid generating 5 rows just to return the same Order.

## 16. Mental Checklist When Writing Queries

Before deciding to push a WHERE or add a WITH, ask yourself:

1. **What does one output row represent?** A Customer, an Order, an Order–Product pair, or a post-aggregation group?
2. **Which entity is being filtered?** Root node, relationship, neighbor node, or the entire result row?
3. **Is there an OPTIONAL MATCH?** If so, should the parent row be kept when no matching child row exists, or should the parent row be excluded?
4. **Is there a pagination limit?** Should the predicate apply **before** or **after** picking N records, per the business requirement?
5. **Is there an aggregation?** Does the condition apply to **base rows** or **aggregated metrics**?
6. **Is there a risk of row multiplication?** Could a node with many relationships distort totals, counts, or page ordering?
7. **Is there an actual path between labels?** Avoid Cartesian products caused by omitting relationships.
8. **What is the planner doing?** Use EXPLAIN/PROFILE to verify indexes, rows, expands, filters, and sorts before drawing performance conclusions.

## 17. Takeaways

**Pushing filter predicates to semantically correct positions** means narrowing data as early as possible **while preserving the exact business question**. Filtering early before relationship expansion can cut row counts; filtering before LIMIT helps collect the right number of qualifying records; filtering inside OPTIONAL MATCH retains parent rows when links are absent; filtering after WITH lets you operate on aggregated results. These positions are **not freely interchangeable**.

When tuning Cypher in Neo4j, start from the **right graph pattern, right row granularity, and right null/pagination rules**, then measure with **EXPLAIN**, **PROFILE**, and Java Driver or Spring Data Neo4j metrics. A well-written query returns the exact data the application needs while minimizing intermediate rows and graph expansion overhead.
