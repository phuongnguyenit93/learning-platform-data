# `reduce()` in Cypher: Accumulating Values from a List

## Lesson Objectives

In Neo4j, data is organized according to the **property graph** model, consisting of nodes, relationships, and properties. Cypher queries often return multiple rows or produce **lists** from connected data: a list of products in an order, nodes along a path, relationships in a route, or records passed in by a Java application.

In the **Lists and Data Pipelines** chapter of module `DATABASE_ENGINE_GRAPH_NEO4J`, the `reduce()` function lets you **iterate sequentially over elements of a list and update an accumulated value**. That value can be a number, string, list, or map. This is a useful technique for computing order totals, total route distances, aggregated states, or building a composite result from connected elements.

After this lesson, you will be able to:

- Read and write `reduce(acc = initial, item IN items | expression)` expressions.
- Explain the roles of the **initial value**, **accumulator variable**, and **element variable** at each step.
- Use `reduce()` to add, multiply, concatenate strings, and build accumulated maps.
- Handle empty lists, `null` lists, `null` elements, and inputs with missing properties.
- Combine `reduce()` with `collect()`, `WITH`, list comprehensions, `nodes(path)`, and `relationships(path)`.
- Distinguish accumulating **elements of a single list** from aggregation functions **across multiple Cypher rows** such as `sum()` and `count()`.

## 1. What Is `reduce()`?

Imagine a shopping cart with three pre-calculated line amounts: `[200000, 50000, 150000]`. To compute the total, an application can start at 0 and add each number one by one:

~~~text
Initial value:                      0
Element 200000:            0 + 200000 = 200000
Element  50000:       200000 +  50000 = 250000
Element 150000:       250000 + 150000 = 400000
Final result:                  400000
~~~

The corresponding Cypher expression:

~~~cypher
RETURN reduce(total = 0, amount IN [200000, 50000, 150000] |
              total + amount) AS orderTotal;
~~~

Result: **one row**, with column `orderTotal = 400000`.

The key point is that `reduce()` operates on **an existing list** and returns **a single result value**. It does not expand elements into rows like `UNWIND`, nor does it automatically update nodes or relationships in the database.

## 2. Syntax and Accumulation Model

Syntax:

~~~cypher
reduce(accumulator = initialValue,
       element IN listExpression |
       updateExpression)
~~~

| Component | Role |
| --- | --- |
| `accumulator` | Variable holding the accumulated result of processed elements |
| `initialValue` | Starting value, used before reading the first element |
| `element` | Variable representing the element currently being evaluated |
| `listExpression` | Expression that evaluates to a list |
| `updateExpression` | Formula computing the new accumulated value from the old value and current element |

Simplest example:

~~~cypher
WITH [2, 4, 6] AS numbers
RETURN reduce(acc = 0, n IN numbers | acc + n) AS total;
~~~

Step-by-step progression:

| Step | `n` | `acc` before step | `acc` after step |
| --- | ---: | ---: | ---: |
| Initialization | — | — | 0 |
| 1 | 2 | 0 | 2 |
| 2 | 4 | 2 | 6 |
| 3 | 6 | 6 | 12 |

The final result is `12`. At each step, the expression to the right of `|` is evaluated to produce a **new** accumulated value. The variables `acc` and `n` are scoped only within the `reduce()` expression; you can choose clearer domain-specific names.

### Not a Data-Writing Loop

`reduce()` is an **expression**, similar to `size()` or `coalesce()`. It can appear in `WITH`, `RETURN`, or nested inside larger expressions:

~~~cypher
WITH [100, 200, 300] AS values
WITH values, reduce(sum = 0, x IN values | sum + x) AS total
RETURN total, size(values) AS numberOfValues;
~~~

The `WITH` clause forwards `total` to the next step. The query returns `total = 600` and `numberOfValues = 3`; no `SET`, `CREATE`, or `MERGE` operation is performed.

## 3. The Initial Value Defines the Accumulation Semantics

### Summing: Initialize with 0

~~~cypher
WITH [5, 8, 12] AS quantities
RETURN reduce(total = 0, q IN quantities | total + q) AS quantityTotal;
~~~

The result is `25`.

### Multiplying: Initialize with 1

~~~cypher
WITH [2, 3, 4] AS factors
RETURN reduce(product = 1, x IN factors | product * x) AS result;
~~~

The result is `24`. If you initialized the product with 0, every subsequent multiplication step would stay 0; therefore, the initial value must match the operation.

### String Concatenation: Initialize with an Empty String

~~~cypher
WITH ['Neo', '4', 'j'] AS parts
RETURN reduce(textValue = '', part IN parts |
              textValue + part) AS productName;
~~~

The result is `'Neo4j'`. String concatenation **depends on element order**: reordering the strings can produce a different name.

### The Result Does Not Have to Be a Number

~~~cypher
WITH [2, 4, 6] AS numbers
RETURN reduce(
  state = {count: 0, total: 0},
  n IN numbers |
  {
    count: state.count + 1,
    total: state.total + n
  }
) AS summary;
~~~

Output map:

~~~text
summary = {
  count: 3,
  total: 12
}
~~~

Each step produces a **new map** from the previous accumulator map. This is a way to compute multiple metrics in a single pass over a list; the expression does not mutate the original map or write changes to the graph.

## 4. Empty Lists, `null`, and Missing Data

These cases are critical when lists are produced from `OPTIONAL MATCH` or passed by the Java Driver via query parameters.

### An Empty List Returns the Initial Value

~~~cypher
WITH [] AS amounts
RETURN
  reduce(total = 0, x IN amounts | total + x) AS sumOfEmpty,
  reduce(product = 1, x IN amounts | product * x) AS productOfEmpty;
~~~

The result is `sumOfEmpty = 0` and `productOfEmpty = 1`. With no elements to iterate over, `reduce()` keeps `initialValue`.

### A `null` Input List

If the **entire list** is `null`, the result of `reduce()` is `null`:

~~~cypher
WITH null AS amounts
RETURN
  reduce(total = 0, x IN amounts | total + x) AS directResult,
  reduce(total = 0, x IN coalesce(amounts, []) | total + x)
    AS defaultToEmpty;
~~~

`directResult = null`, whereas `defaultToEmpty = 0`. Use `coalesce(amounts, [])` when business rules treat "no list provided" as equivalent to "a list with zero elements"; the two cases can carry different meanings in an API.

### A Single `null` Element Can Break Accumulation

~~~cypher
WITH [10, null, 20] AS amounts
RETURN reduce(total = 0, x IN amounts | total + x) AS result;
~~~

At the step encountering `null`, `total + null` evaluates to `null`. Subsequent addition steps continue returning `null`, so the final result is no longer `30`.

If the business rule is to **skip missing elements**, you can use `CASE`:

~~~cypher
WITH [10, null, 20] AS amounts
RETURN reduce(
  total = 0,
  x IN amounts |
  CASE
    WHEN x IS NULL THEN total
    ELSE total + x
  END
) AS totalIgnoringNull;
~~~

Result: `totalIgnoringNull = 30`. Another approach is filtering the list beforehand:

~~~cypher
WITH [10, null, 20] AS amounts
WITH [x IN amounts WHERE x IS NOT NULL] AS validAmounts
RETURN reduce(total = 0, x IN validAmounts | total + x) AS total;
~~~

This example also returns `30`. However, **do not arbitrarily treat missing data as 0** in domains like shipping fees, inventory, or payments. When a missing unit price is a data error, the application should validate and reject the record instead of silently ignoring it.

### Comparing Empty Lists and `null` Elements

| Input List | Direct Addition with `initialValue = 0` | Notes |
| --- | --- | --- |
| `[]` | `0` | Zero iterations |
| `[5, 10]` | `15` | Two additions |
| `[5, null, 10]` | `null` | Accumulator becomes `null` |
| `null` | `null` | Input list has no value |
| `coalesce(null, [])` | `0` | Explicitly substitutes an empty list |

## 5. Practical Example: Order Total Value

An order has multiple line items. Each line stores `sku`, `quantity`, and `unitPrice` as a map. Test data:

~~~cypher
WITH {
  id: 'O01',
  items: [
    {sku: 'P01', quantity: 2, unitPrice: 120000},
    {sku: 'P02', quantity: 1, unitPrice: 90000},
    {sku: 'P03', quantity: 3, unitPrice: 30000}
  ]
} AS orderData
RETURN
  orderData.id AS orderId,
  reduce(
    total = 0,
    item IN orderData.items |
    total + item.quantity * item.unitPrice
  ) AS orderTotal;
~~~

Result: `orderId = 'O01'` and `orderTotal = 420000`:

~~~text
P01: 2 * 120000 = 240000
P02: 1 *  90000 =  90000
P03: 3 *  30000 =  90000
Total:              420000
~~~

This example runs standalone, without needing to create `Order` or `Product` nodes. That makes it easy to verify summation logic before placing the expression inside a graph query.

### Computing Multiple Metrics at Once

If besides the monetary total you also need total quantity and line count:

~~~cypher
WITH [
  {sku: 'P01', quantity: 2, unitPrice: 120000},
  {sku: 'P02', quantity: 1, unitPrice: 90000},
  {sku: 'P03', quantity: 3, unitPrice: 30000}
] AS items
RETURN reduce(
  s = {lineCount: 0, quantity: 0, amount: 0},
  item IN items |
  {
    lineCount: s.lineCount + 1,
    quantity: s.quantity + item.quantity,
    amount: s.amount + item.quantity * item.unitPrice
  }
) AS orderSummary;
~~~

Result:

~~~text
{
  lineCount: 3,
  quantity: 6,
  amount: 420000
}
~~~

`lineCount` counts the number of elements in the list, **not the number of distinct SKUs**. If one SKU appears on two lines, it still contributes twice. This can be valid for data involving multiple batches or pricing tiers.

### Normalizing an Optional List

When the application might omit `items`, you can write:

~~~cypher
WITH {id: 'O02', items: null} AS orderData
WITH orderData.id AS orderId,
     coalesce(orderData.items, []) AS items
RETURN orderId,
       reduce(total = 0, item IN items |
              total + item.quantity * item.unitPrice) AS orderTotal;
~~~

Result: `O02` has `orderTotal = 0` under the example's convention. In a real system, distinguish a **valid order with no line items** from an **order missing data due to a sync error** before defaulting the total to 0.

## 6. Combining `reduce()` with `WITH`, `collect()`, and Query Rows

Cypher processes a stream of rows through clauses such as `MATCH`, `WITH`, and `RETURN`. `collect()` is a function that **aggregates rows into a list**, whereas `reduce()` processes **elements already inside that list**.

~~~text
Cypher rows:       O01, 240000       O01, 90000       O01, 90000
                         |                |                |
                         +----- collect(amount) ------------+
                                           |
                         O01, [240000, 90000, 90000]
                                           |
                         reduce(total = 0, amount IN list ...)
                                           |
                                O01, 420000
~~~

Example grouping by order from a list of line records:

~~~cypher
UNWIND [
  {orderId: 'O01', quantity: 2, unitPrice: 120000},
  {orderId: 'O01', quantity: 1, unitPrice: 90000},
  {orderId: 'O02', quantity: 3, unitPrice: 30000}
] AS line
WITH line.orderId AS orderId,
     collect(line) AS lines
RETURN
  orderId,
  reduce(total = 0, item IN lines |
         total + item.quantity * item.unitPrice) AS amount
ORDER BY orderId;
~~~

| orderId | amount |
| --- | ---: |
| O01 | 330000 |
| O02 | 90000 |

`WITH line.orderId AS orderId, collect(line) AS lines` groups rows by `orderId`. Then `reduce()` computes the sum separately for each group's list. This pattern makes sense when the application genuinely needs to retain and process the `lines` list in an intermediate step.

### When Should You Use `sum()` Instead of `reduce()`?

If the sole goal is to sum directly over line-item rows, `sum()` is cleaner and usually more efficient because it avoids building an intermediate list:

~~~cypher
UNWIND [
  {orderId: 'O01', quantity: 2, unitPrice: 120000},
  {orderId: 'O01', quantity: 1, unitPrice: 90000},
  {orderId: 'O02', quantity: 3, unitPrice: 30000}
] AS line
RETURN
  line.orderId AS orderId,
  sum(line.quantity * line.unitPrice) AS amount
ORDER BY orderId;
~~~

The result is also `O01 = 330000` and `O02 = 90000`.

| Criterion | `reduce()` | `sum()` |
| --- | --- | --- |
| Natural input | A single **list** value | Multiple **Cypher rows** |
| Output | Value produced by an arbitrary update formula | Numeric sum, ignoring `null` values |
| Accumulation state | User-defined; can be number, string, map, or list | Managed by the aggregation function |
| Element order | Can affect output, e.g., string concatenation | Irrelevant for addition |
| Best fit | Custom accumulations, updating multiple fields, path/list operations | Directly summing numeric values across rows |

**Choose `sum()` when you only need to add rows together.** Choose `reduce()` when the input **is already a list** or when the accumulation requires state and logic more flexible than standard aggregation.

## 7. `reduce()` Over the Relationships of a Path

In a Neo4j graph, `relationships(path)` returns a list of relationships in the order they appear along the path. You can use `reduce()` to sum the weights of each edge.

Suppose the model is:

~~~text
(:Location {id: 'A'})
   -[:ROAD {distanceKm: 8.5}]->
(:Location {id: 'B'})
   -[:ROAD {distanceKm: 3.0}]->
(:Location {id: 'C'})
~~~

The total distance of path `A → B → C` is `11.5 km`.

Query on an existing graph:

~~~cypher
MATCH p = (origin:Location {id: $originId})
          -[:ROAD*1..4]->
          (destination:Location {id: $destinationId})
WITH p, [r IN relationships(p) | r.distanceKm] AS segments
WHERE all(km IN segments WHERE km IS NOT NULL)
WITH
  p,
  reduce(totalKm = 0.0, km IN segments |
         totalKm + km) AS distanceKm
RETURN
  [n IN nodes(p) | n.id] AS locationIds,
  size(relationships(p)) AS hopCount,
  distanceKm
ORDER BY distanceKm ASC, hopCount ASC
LIMIT 3;
~~~

Explanation:

1. `MATCH p = ...` finds paths of one to four `ROAD` relationships in the specified direction.
2. `relationships(p)` produces the list of relationships on each path; the comprehension extracts the segment lengths into `segments`.
3. `all(km IN segments WHERE km IS NOT NULL)` excludes paths missing distance data, preventing unweighted edges from being treated as 0 km.
4. `reduce(totalKm = 0.0, km IN segments | totalKm + km)` sums each segment's distance sequentially.
5. `ORDER BY ... LIMIT 3` selects up to three paths with the smallest total distance **among the paths matched by the query**.

This query only demonstrates summing weights **after finding paths bounded to four hops**. It does not guarantee finding the global shortest path in the graph if the optimal route has more than four hops; enumerating all paths can be resource-intensive. For weighted pathfinding on large graphs, consider appropriate pathfinding algorithms and tools such as Neo4j Graph Data Science once requirements are defined.

### `reduce()` Inside a Path Projection

You can also return the summed weight inside a projection:

~~~cypher
MATCH p = (a:Location {id: $originId})-[:ROAD*1..4]->
          (b:Location {id: $destinationId})
WITH p, relationships(p) AS roads
WHERE all(r IN roads WHERE r.distanceKm IS NOT NULL)
RETURN {
  route: [n IN nodes(p) | n.id],
  distanceKm: reduce(
    total = 0.0,
    road IN roads |
    total + road.distanceKm
  )
} AS routeSummary;
~~~

The result map has two fields: `route` and `distanceKm`. This combination is useful when a Java API simply needs one map of summary metrics per path.

## 8. Order-Dependent Accumulation: Strings and State

Most numeric additions are order-independent, but **string concatenation** or stateful updates can depend on order.

~~~cypher
WITH ['A', 'B', 'C'] AS stops
RETURN reduce(label = '', stop IN stops |
              CASE
                WHEN label = '' THEN stop
                ELSE label + ' -> ' + stop
              END) AS routeLabel;
~~~

Result: `'A -> B -> C'`. If the input list were `['C', 'A', 'B']`, the label would change accordingly.

### Difference Between List Order and Row Order

A list literal like `['A','B','C']` has a fixed element order. However, when a list is built with `collect()` from multiple graph rows, you must **sort the rows before the `collect` clause** if order matters:

~~~cypher
MATCH (o:Order {id: $orderId})-[:HAS_EVENT]->(e:OrderEvent)
WITH e
ORDER BY e.occurredAt ASC, e.id ASC
WITH collect(e.type) AS eventTypes
RETURN reduce(
  summary = '',
  eventType IN eventTypes |
  CASE
    WHEN summary = '' THEN eventType
    ELSE summary + ' -> ' + eventType
  END
) AS eventHistory;
~~~

This example assumes the graph contains `OrderEvent` nodes with `occurredAt`, `id`, and `type`. Using two sort keys establishes a deterministic event order before joining them into a string; if timestamps tie without a tie-breaker key, the order can be unstable.

### Accumulating a State Map

Example computing the running balance after amount changes and tracking the lowest balance seen:

~~~cypher
WITH [-100, 200, -50] AS changes
RETURN reduce(
  s = {balance: 0, minimumBalance: 0},
  delta IN changes |
  {
    balance: s.balance + delta,
    minimumBalance: CASE
      WHEN s.balance + delta < s.minimumBalance
        THEN s.balance + delta
      ELSE s.minimumBalance
    END
  }
) AS balanceSummary;
~~~

Progression: balance `0 → -100 → 100 → 50`. Result:

~~~text
{
  balance: 50,
  minimumBalance: -100
}
~~~

Notably, each step can depend on the **accumulated state from the previous step**. That makes this expression more suitable than computing `sum(changes)` alone when you also need to track the minimum balance across the transaction sequence.

## 9. `reduce()` with Lists, List Comprehensions, and Other Functions

### Building a Result List Using an Accumulator

You can use a list as the accumulator value:

~~~cypher
WITH [1, 2, 3] AS numbers
RETURN reduce(
  squares = [],
  n IN numbers |
  squares + [n * n]
) AS squaredValues;
~~~

Result: `[1, 4, 9]`. However, when merely transforming each element independently, a **list comprehension** expresses the intent more simply:

~~~cypher
WITH [1, 2, 3] AS numbers
RETURN [n IN numbers | n * n] AS squaredValues;
~~~

Both produce the same result. Using `reduce()` with `squares + [n * n]` can create many intermediate lists when the input is large; avoid using it just to copy or map elements when a comprehension suffices.

### Combining Filtering and Accumulation

Given a list of orders, sum only the amounts of paid orders:

~~~cypher
WITH [
  {id: 'O01', status: 'PAID', amount: 200000},
  {id: 'O02', status: 'PENDING', amount: 50000},
  {id: 'O03', status: 'PAID', amount: 80000}
] AS orders
WITH [o IN orders WHERE o.status = 'PAID'] AS paidOrders
RETURN reduce(
  total = 0,
  o IN paidOrders |
  total + o.amount
) AS paidTotal;
~~~

Result: `paidTotal = 280000`.

You can also fold the condition directly into `reduce()`:

~~~cypher
WITH [
  {status: 'PAID', amount: 200000},
  {status: 'PENDING', amount: 50000},
  {status: 'PAID', amount: 80000}
] AS orders
RETURN reduce(
  total = 0,
  o IN orders |
  CASE
    WHEN o.status = 'PAID' THEN total + o.amount
    ELSE total
  END
) AS paidTotal;
~~~

The second approach avoids allocating an intermediate filtered list, though the accumulation expression becomes longer. Choose whichever is clearer for the business logic, and verify `null` handling and the data type of `amount` before computing.

## 10. Passing Data from the Java Driver and Spring Data Neo4j

In a Java application, you can pass a list of maps as the `$items` parameter and compute the total in Cypher. This fits well when you want to return unified results alongside graph queries in the same data access layer.

Parameterized query:

~~~cypher
WITH coalesce($items, []) AS items
RETURN reduce(
  total = 0,
  item IN items |
  total + item.quantity * item.unitPrice
) AS amount;
~~~

Java Driver example (assuming `driver` is already initialized and lifecycle-managed):

~~~java
List<Map<String, Object>> items = List.of(
    Map.of("quantity", 2, "unitPrice", 120_000L),
    Map.of("quantity", 1, "unitPrice", 90_000L)
);

String query = """
    WITH coalesce($items, []) AS items
    RETURN reduce(
      total = 0,
      item IN items |
      total + item.quantity * item.unitPrice
    ) AS amount
    """;

try (Session session = driver.session()) {
    long amount = session.executeRead(tx ->
        tx.run(query, Values.parameters("items", items))
          .single()
          .get("amount")
          .asLong()
    );

    // amount = 330000
}
~~~

Common imports include `java.util.List`, `java.util.Map`, and `Session`/`Values` from `org.neo4j.driver`. This snippet only illustrates reading an integer result. The application must validate that list elements are properly structured maps, `quantity` is non-negative, `unitPrice` has an appropriate numeric type, and handle query/transaction errors as required.

With **Spring Data Neo4j**, you can place a similar expression inside a custom `@Query`; the return type and parameter binding depend on your repository and mapping configuration. `reduce()` does not turn into an entity-update mechanism on its own, nor does it replace application-layer validation.

### Should You Compute in Cypher or in Java?

It depends on the goal:

- If the data is **already in Neo4j**, computing the result inside Cypher can reduce the amount of data sent to the application.
- If the data is **only in Java** and requires no graph query, computing directly in Java can be simpler than sending payload to the database just to add numbers.
- For monetary values requiring exact precision and rounding rules, use an appropriate representation (such as integers in the smallest currency unit) and control numeric bounds; do not assume floating-point types fit every business domain.

## 11. Common Errors, Performance, and Limitations

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Wrong total on an empty list | Inappropriate initial value | Start addition at 0 and multiplication at 1 |
| Unexpected `null` result | List is `null` or a `null` element propagated through operations | Inspect data, use `coalesce()` or `CASE` per business rules |
| `reduce()` throws a type error | Element has a type incompatible with addition/multiplication | Validate maps and numeric types before running the query |
| Doubled order total | List has duplicate lines from `MATCH` expanding multiple relationships | Check what each row represents; group and deduplicate when business logic permits |
| Concatenated string has wrong order | List built by `collect()` lacked sorting | Add `ORDER BY` before `collect()` |
| Query consumes high memory | `collect()` builds a huge list only to `reduce()` it | Consider `sum()`/aggregation directly on rows |
| Slow list accumulation | Appending to a new list on every iteration | Use a list comprehension for simple filtering/mapping |
| Thinking `reduce()` writes to the graph | Expression only computes a value | Use separate `SET`/`MERGE`/`CREATE` clauses when graph mutations are required |
| Weighted path evaluated incorrectly | Missing weight properties or incomplete path enumeration | Validate weights and choose a suitable pathfinding solution |

Principles for reliable queries:

1. **Keep the accumulator minimal:** carry only the fields genuinely needed during computation.
2. **Verify numeric units:** quantities, currency amounts, distances, and durations cannot be added arbitrarily if units differ.
3. **Handle `null` upfront:** especially for lists coming from APIs or optional relationships.
4. **Avoid collecting lists unnecessarily:** `sum()`, `avg()`, or `count()` usually express basic multi-row aggregations better.
5. **Inspect the query plan:** use `EXPLAIN` to view the plan and `PROFILE` on test data to check row counts and cost, especially before `collect()` or path expansions.

`reduce()` iterates through all elements of the provided list; there is no `break` mechanism to stop early as in a Java loop. For existence checks, `any()`, `all()`, or other predicate expressions may be a better fit than a manual accumulator.

## 12. Practice Exercises

### Exercise 1 — Computing Factorial with `range()` and `reduce()`

Given `n = 5`, compute `5! = 1 × 2 × 3 × 4 × 5`:

~~~cypher
WITH 5 AS n
RETURN reduce(product = 1, x IN range(1, n) |
              product * x) AS factorial;
~~~

Result: `factorial = 120`.

**Self-check:** Why initialize `product = 1`? Because 1 is the multiplicative identity; initializing with 0 would keep the result 0 forever. For `n = 0`, handle the edge case explicitly according to the mathematical convention `0! = 1`, for example with `CASE WHEN n = 0 THEN 1 ELSE reduce(...) END`.

### Exercise 2 — Cart Total Value and Total Quantity

Given three line items, build a result map containing `itemCount`, `quantityTotal`, and `amountTotal`:

~~~cypher
WITH [
  {sku: 'P01', quantity: 2, unitPrice: 100000},
  {sku: 'P02', quantity: 1, unitPrice: 80000},
  {sku: 'P03', quantity: 4, unitPrice: 20000}
] AS items
RETURN reduce(
  s = {itemCount: 0, quantityTotal: 0, amountTotal: 0},
  item IN items |
  {
    itemCount: s.itemCount + 1,
    quantityTotal: s.quantityTotal + item.quantity,
    amountTotal: s.amountTotal + item.quantity * item.unitPrice
  }
) AS summary;
~~~

Expected result:

~~~text
{
  itemCount: 3,
  quantityTotal: 7,
  amountTotal: 360000
}
~~~

### Exercise 3 — Intentionally Handling `null` Values

The input list is `[5, null, 10, 15]`. Write a `reduce()` expression that skips `null` elements and returns the sum:

~~~cypher
WITH [5, null, 10, 15] AS numbers
RETURN reduce(
  total = 0,
  n IN numbers |
  CASE WHEN n IS NULL THEN total ELSE total + n END
) AS sumWithoutNull;
~~~

Result: `sumWithoutNull = 30`.

### Exercise 4 — Choosing the Right Tool

Given a graph query returning rows of `Order-[:CONTAINS]->Product`, if you only need the total amount of each order, which option is simpler and avoids intermediate lists?

~~~cypher
MATCH (o:Order)-[line:CONTAINS]->(p:Product)
RETURN
  o.id AS orderId,
  sum(line.quantity * p.price) AS totalAmount
ORDER BY orderId;
~~~

Answer: `sum()` fits because the data is already in multiple rows and only numeric addition is needed. Only reach for `reduce()` when you already have a list input or need complex accumulated state.

## Key Takeaway

`reduce()` in Cypher performs **left-to-right accumulation over the elements of a list**:

~~~cypher
reduce(acc = initialValue, item IN sourceList |
       expressionUsing(acc, item))
~~~

It returns **a single final value** that can be a number, string, list, or map; the initial value determines the result when the list is empty. Handle `null` carefully, choose the right data types, and control ordering when accumulation depends on position. When working with Neo4j, `reduce()` is especially useful for lists from `collect()` or `relationships(path)`; however, for direct summation across multiple rows, `sum()` is usually simpler and more economical.
