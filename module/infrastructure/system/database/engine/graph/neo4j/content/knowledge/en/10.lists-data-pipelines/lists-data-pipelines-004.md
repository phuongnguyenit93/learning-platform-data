# List Comprehensions and Element Filtering in Cypher

## Lesson Objectives

In Neo4j, data is represented as a **property graph** consisting of nodes, relationships, and properties. Beyond finding relationships or paths in the graph, Cypher queries frequently need to process **lists**: product SKUs received from a Java application, orders gathered with `collect()`, or nodes along a path returned by `nodes(path)`.

In the **Lists and Data Pipelines** chapter of module `DATABASE_ENGINE_GRAPH_NEO4J`, this lesson focuses on **list creation expressions** and **element filtering**. The primary tool is the *list comprehension*: creating a new list by iterating over, filtering, and transforming the elements of an input list directly inside a Cypher expression.

After this lesson, you will be able to:

- Write list literals and build lists using `range()`, `collect()`, or list comprehensions.
- Use the `[x IN xs WHERE condition | expression]` syntax to filter and transform elements.
- Distinguish between **filtering elements inside a list** and **filtering rows in a pipeline** using `WITH ... WHERE`.
- Handle empty lists, `null` values, duplicate elements, and element ordering.
- Apply these expressions to lists of maps, nodes, Neo4j paths, and parameters passed from the Java Driver or Spring Data Neo4j.

## 1. What Is a List in Cypher?

A list is an ordered value containing zero, one, or more elements. The following query creates three types of lists without requiring any existing graph data:

~~~cypher
RETURN
  ['Neo4j', 'Cypher', 'Java'] AS technologies,
  [100, 200, 300] AS prices,
  [{sku: 'P01', price: 100000}, {sku: 'P02', price: 50000}] AS products;
~~~

Elements can be simple values such as numbers and strings, or composite values such as maps. A list created during a query can also hold nodes or relationships. However, **not every list can be stored directly as a property** on a node or relationship: Neo4j properties only support storable types and cannot arbitrarily store lists of maps or nodes.

Common sources of lists:

| Source | Example | Meaning |
| --- | --- | --- |
| **List literal** | `['P01', 'P02']` | Explicitly declare elements |
| **Number sequence** | `range(1, 5)` | Generates `[1, 2, 3, 4, 5]` |
| **Aggregation function** | `collect(o.id)` | Gathers values from multiple rows into a list |
| **Path functions** | `nodes(p)`, `relationships(p)` | Extracts the list of nodes or relationships on a path |
| **Application parameters** | `$products`, `$customerIds` | Receives lists via query parameters |
| **List comprehension** | `[x IN xs | x * 2]` | Builds a new list from an existing list |

For instance, `size(xs)` returns the length of a list:

~~~cypher
WITH ['P01', 'P02', 'P03'] AS skus
RETURN size(skus) AS numberOfSkus, skus[0] AS firstSku;
~~~

The result is `numberOfSkus = 3` and `firstSku = 'P01'`. Element access via `xs[index]` uses zero-based indexing; the main focus of this lesson is **creating new lists from elements**, rather than picking a single position.

## 2. List Comprehension Syntax: Iterating, Filtering, and Transforming

A list comprehension has the general form:

~~~cypher
[item IN sourceList WHERE condition | expression]
~~~

Where:

- `item` is the variable representing **each element** of `sourceList`.
- `WHERE condition` is **optional**, keeping an element only when the predicate evaluates to `true`.
- `| expression` is also **optional**, determining the corresponding element value in the resulting list.
- If `| expression` is omitted, matching elements are kept **with their original values**.

Three forms to remember:

~~~cypher
WITH [1, 2, 3, 4, 5] AS numbers
RETURN
  [n IN numbers | n * 10] AS multiplied,
  [n IN numbers WHERE n % 2 = 0] AS evenNumbers,
  [n IN numbers WHERE n % 2 = 0 | n * n] AS evenSquares;
~~~

| Expression | Result | Effect |
| --- | --- | --- |
| `[n IN numbers \| n * 10]` | `[10, 20, 30, 40, 50]` | Transforms all elements |
| `[n IN numbers WHERE n % 2 = 0]` | `[2, 4]` | Filters only, keeping original values |
| `[n IN numbers WHERE n % 2 = 0 \| n * n]` | `[4, 16]` | Filters first, then transforms |

When filtering, each element is evaluated individually against the condition. Elements that do not match are excluded from the new list; **the original list is not modified**.

### Why Is the Result Still a Single List?

~~~cypher
WITH [2, 5, 8, 11] AS numbers
RETURN [n IN numbers WHERE n > 5 | n + 1] AS transformed;
~~~

This query returns **one row** with column `transformed = [9, 12]`. Two elements in a list do not mean two Cypher rows.

Distinguish between them:

~~~text
Input list:              [2, 5, 8, 11]
                               |
                WHERE n > 5, then n + 1
                               |
List comprehension:         [9, 12]        (one list value)
                               |
                        UNWIND ... AS n
                               |
Result rows:                   9
                              12           (two rows)
~~~

`UNWIND` expands a list into rows when the next stage needs to process each element as an individual record.

## 3. Ways to Create New Lists

### Creating a List from a Number Sequence with `range()`

`range(start, end[, step])` creates a list of integers. The end value is included in the sequence if the step reaches it:

~~~cypher
WITH range(1, 6) AS numbers
RETURN
  numbers AS original,
  [n IN numbers | n * n] AS squares,
  [n IN numbers WHERE n % 3 = 0 | n * 10] AS multiplesOfThreeTimesTen;
~~~

Result:

- `original = [1, 2, 3, 4, 5, 6]`;
- `squares = [1, 4, 9, 16, 25, 36]`;
- `multiplesOfThreeTimesTen = [30, 60]`.

When `range()` generates a large list, it can create many intermediate elements, so bound the range and step according to actual requirements.

### Transforming Strings and Normalizing Values

For product codes entered in inconsistent formats:

~~~cypher
WITH [' p01 ', 'P02', ' p03'] AS rawSkus
RETURN [sku IN rawSkus | toUpper(trim(sku))] AS normalizedSkus;
~~~

Result: `['P01', 'P02', 'P03']`. Each element is processed with `trim()` to remove leading/trailing whitespace, then `toUpper()` to uppercase it. If the data may contain `null` elements, define handling rules before normalizing.

### Creating a New List of Maps

A transformation can output **maps** instead of numbers or strings:

~~~cypher
WITH [
  {sku: 'P01', price: 100000},
  {sku: 'P02', price: 50000}
] AS products
RETURN [
  p IN products
  | {productCode: p.sku, priceWithTax: p.price * 1.1}
] AS priceSummary;
~~~

The result is a list containing two maps:

~~~text
[
  {productCode: 'P01', priceWithTax: 110000.0},
  {productCode: 'P02', priceWithTax: 55000.0}
]
~~~

These are **maps created in the query result**; the example does not create nodes or update properties in the graph. `priceWithTax` is only an illustrative calculation, not a tax formula applicable to every business domain.

## 4. Filtering Elements by Condition

### Filtering Numbers, Strings, and Maps

With a list of numbers:

~~~cypher
WITH [12, 3, 25, 8, 17] AS quantities
RETURN [q IN quantities WHERE q >= 10] AS largeQuantities;
~~~

Result: `[12, 25, 17]`. Element order is preserved from the input list.

With a list of maps representing orders:

~~~cypher
WITH [
  {id: 'O01', status: 'PAID', amount: 250000},
  {id: 'O02', status: 'PENDING', amount: 600000},
  {id: 'O03', status: 'PAID', amount: 750000}
] AS orders
RETURN
  [o IN orders WHERE o.status = 'PAID' | o.id] AS paidOrderIds,
  [o IN orders WHERE o.status = 'PAID' AND o.amount >= 500000
    | {id: o.id, amount: o.amount}] AS largePaidOrders;
~~~

Result:

| Column | Value |
| --- | --- |
| `paidOrderIds` | `['O01', 'O03']` |
| `largePaidOrders` | `[{id: 'O03', amount: 750000}]` |

`WHERE` inside a comprehension is evaluated on **each map** `o`. Only maps satisfying the condition are transformed into the output. You can combine `AND`, `OR`, comparison operators, and Cypher functions in this condition.

### Checking Whether a Value Belongs to an Allowed Set

The `IN` operator checks whether a value appears in a list:

~~~cypher
WITH
  ['PAID', 'SHIPPED'] AS acceptedStatuses,
  [
    {id: 'O01', status: 'PAID'},
    {id: 'O02', status: 'CANCELLED'},
    {id: 'O03', status: 'SHIPPED'}
  ] AS orders
RETURN [
  o IN orders
  WHERE o.status IN acceptedStatuses
  | o.id
] AS acceptedOrderIds;
~~~

The result is `['O01', 'O03']`. Do not confuse the two uses of the `IN` keyword:

- `o IN orders`: loop variable `o` takes each element in the comprehension.
- `o.status IN acceptedStatuses`: predicate checking whether the status belongs to the allowed list.

### Combining Filtering and Counting

A filtered list can be passed directly to `size()`:

~~~cypher
WITH [4, 10, 2, 15, 11] AS values
RETURN size([x IN values WHERE x >= 10]) AS numberOfMatchingValues;
~~~

The result is `3`. This is the number of elements matching the condition inside **one list**, not the number of output rows. When counting rows of a graph query, use `count(*)` or `count(expression)` according to the metric you intend to measure.

## 5. Empty Lists, `null`, and Duplicate Elements

Edge cases must be handled explicitly because they affect query results or ingestion logic.

### An Empty List Produces an Empty List

~~~cypher
WITH [] AS numbers
RETURN
  [n IN numbers WHERE n > 0 | n * 2] AS positiveDoubles,
  size(numbers) AS inputSize;
~~~

Result: `positiveDoubles = []`, `inputSize = 0`. An empty list generates no elements after comprehension.

### `null` Values Inside a List

~~~cypher
WITH [1, null, 3] AS values
RETURN
  [x IN values | x * 2] AS mapped,
  [x IN values WHERE x > 1] AS greaterThanOne,
  [x IN values WHERE x IS NOT NULL | x * 2] AS nonNullDoubles;
~~~

| Column | Result |
| --- | --- |
| `mapped` | `[2, null, 6]` |
| `greaterThanOne` | `[3]` |
| `nonNullDoubles` | `[2, 6]` |

The transformation expression `null * 2` evaluates to `null`. In the condition `x > 1`, when `x = null`, the predicate does not evaluate to `true`, so that element **is not retained**. `IS NOT NULL` makes the requirement to exclude missing elements explicit.

If the **entire input list** is `null`, the comprehension also returns `null`, unlike an empty list which returns `[]`:

~~~cypher
WITH null AS incomingTags
RETURN
  [tag IN incomingTags | tag] AS directResult,
  [tag IN coalesce(incomingTags, []) | tag] AS emptyByDefault;
~~~

Result: `directResult = null` and `emptyByDefault = []`. For optional inputs coming from an application, `coalesce(list, [])` is a common way to define a default rule.

### List Comprehensions Do Not Deduplicate

~~~cypher
WITH ['P01', 'P02', 'P01'] AS skus
RETURN [sku IN skus WHERE sku STARTS WITH 'P'] AS result;
~~~

The result is still `['P01', 'P02', 'P01']`. If business logic requires unique SKUs, deduplicate using `DISTINCT` at the **row** level and then `collect()`:

~~~cypher
WITH ['P01', 'P02', 'P01'] AS skus
UNWIND skus AS sku
WITH DISTINCT sku
ORDER BY sku
RETURN collect(sku) AS uniqueSkus;
~~~

Result: `['P01', 'P02']`. `ORDER BY` before `collect()` makes the output list order predictable. Also consider handling duplicates at the ingestion layer if elements carry extra fields such as quantities or update timestamps.

## 6. Distinguishing List Element Filtering from Cypher Row Filtering

In a Cypher pipeline, `WITH` forwards variables across stages; `WITH ... WHERE` filters **rows**. Inside a list comprehension, `WHERE` filters **elements of a list within a single row**. Both approaches can yield equivalent values, yet have different shapes.

### Approach A: Keep One Row, Return a List of IDs

~~~cypher
WITH [
  {id: 'O01', status: 'PAID'},
  {id: 'O02', status: 'PENDING'},
  {id: 'O03', status: 'PAID'}
] AS orders
RETURN
  [o IN orders WHERE o.status = 'PAID' | o.id] AS paidOrderIds,
  size(orders) AS originalOrderCount;
~~~

Returns **one row**:

~~~text
paidOrderIds   = ['O01', 'O03']
originalOrderCount = 3
~~~

### Approach B: Unwind the List, Filter, and Return Individual Rows

~~~cypher
WITH [
  {id: 'O01', status: 'PAID'},
  {id: 'O02', status: 'PENDING'},
  {id: 'O03', status: 'PAID'}
] AS orders
UNWIND orders AS o
WITH o
WHERE o.status = 'PAID'
RETURN o.id AS paidOrderId
ORDER BY paidOrderId;
~~~

Returns **two rows**, one for `O01` and one for `O03`.

| Criterion | List Comprehension | `UNWIND` + `WITH ... WHERE` |
| --- | --- | --- |
| Data after filtering | One **list value** per input row | **Result rows** corresponding to remaining elements |
| Row count at current step | Unchanged by the comprehension itself | Can increase, decrease, or drop to 0 |
| Continuing to match nodes/relationships per ID | Needs `UNWIND` to process each ID as a row | Can `MATCH`/`MERGE` directly using each row's variable |
| Returning a JSON-like list to the application | Well-suited | Requires `collect()` if re-grouping is needed |

Choose a list comprehension when you want to **keep the result as a list** to return to the client or use in subsequent calculations. Choose `UNWIND` when you want **each element to be a row** for `MATCH`, `MERGE`, aggregation, or per-row processing.

## 7. Checking Conditions Across an Entire List

In addition to creating a new list, Cypher supports *list predicate functions* to ask questions about elements. They return a **boolean value** rather than a list.

~~~cypher
WITH [2, 4, 6] AS numbers
RETURN
  all(n IN numbers WHERE n % 2 = 0) AS allEven,
  any(n IN numbers WHERE n > 5) AS anyGreaterThanFive,
  none(n IN numbers WHERE n < 0) AS noneNegative,
  single(n IN numbers WHERE n > 4) AS exactlyOneGreaterThanFour;
~~~

All four columns return `true`:

- `all()`: does every element satisfy the condition?
- `any()`: does at least one element satisfy the condition?
- `none()`: do no elements satisfy the condition?
- `single()`: does exactly one element satisfy the condition?

| Function | Empty List `[]`, Any Condition |
| --- | --- |
| `all()` | `true` |
| `any()` | `false` |
| `none()` | `true` |
| `single()` | `false` |

With `null` elements, the result of predicate functions can be `null` when true/false cannot be conclusively determined. Therefore, decide how missing elements should be handled before using predicates for critical business decisions.

If you need to **keep the matching elements**, use a comprehension. If you only need to **confirm whether a condition holds**, `all()`, `any()`, `none()`, and `single()` usually express the intent more clearly than checking `size()` on an intermediate list.

## 8. Working with Nodes, Relationships, and Paths

List comprehensions are not limited to list literals. They can process lists of nodes or relationships produced by property graph queries.

Suppose the graph has these nodes and relationships:

~~~text
(:Customer {id})-[:PLACED]->(:Order {id, status, amount})
(:Person {id, name, active})-[:KNOWS]->(:Person)
~~~

### Filtering Orders After Collecting Them into a List

~~~cypher
MATCH (c:Customer {id: $customerId})-[:PLACED]->(o:Order)
WITH c, o
ORDER BY o.createdAt DESC, o.id ASC
WITH c, collect(o) AS orders
RETURN
  c.id AS customerId,
  [o IN orders | o.id] AS allOrderIds,
  [o IN orders WHERE o.status = 'PAID' | o.id] AS paidOrderIds,
  [o IN orders WHERE o.amount >= 500000
     | {id: o.id, amount: o.amount}] AS largeOrders;
~~~

Here:

1. `MATCH` finds `Order` nodes connected via `PLACED` from the selected customer.
2. `ORDER BY` sorts the rows by creation time and ID before collecting.
3. `collect(o)` gathers the `Order` nodes into a list for that customer.
4. The comprehensions extract different views of the same order list: all IDs, paid IDs, and high-value orders.

This example assumes the graph has appropriate `createdAt`, `status`, and `amount` properties; the query only returns data if the customer and orders exist. `collect()` requires memory consideration when a customer has very many orders; if you only need a few orders, limit or process rows before collecting.

### Building Lists from Nodes on a Path

The `nodes(path)` function returns the list of nodes along a matched path:

~~~cypher
MATCH p = (a:Person {id: $personId})-[:KNOWS*1..3]->(b:Person)
WITH nodes(p) AS people
RETURN
  [person IN people | person.name] AS namesOnPath,
  [person IN people
    WHERE person.active = true
    | person.name] AS activeNamesOnPath;
~~~

If a path consists of three nodes named `An`, `Bình`, and `Chi`, where `An` and `Chi` have `active = true`, the result is two lists:

~~~text
namesOnPath       = ['An', 'Bình', 'Chi']
activeNamesOnPath = ['An', 'Chi']
~~~

The list comprehension preserves the order of nodes along the path itself. However, if `MATCH` finds **multiple paths**, the query produces one row per path; if you need to sort the paths relative to one another, add an appropriate `ORDER BY` at the query level.

### Pattern Comprehension: Creating a List Directly from a Relationship Pattern

Cypher also supports *pattern comprehensions*: writing a relationship pattern inside square brackets and projecting it into a list:

~~~cypher
MATCH (c:Customer {id: $customerId})
RETURN [
  (c)-[:PLACED]->(o:Order)
  WHERE o.status = 'PAID'
  | o.id
] AS paidOrderIds;
~~~

For the matched customer, the expression builds a list of IDs for orders matching the relationship pattern and condition. Unlike regular list comprehensions (which iterate over an existing list), a pattern comprehension pulls values from a **graph pattern**. If there are no matching relationships, the corresponding list is empty; if no node `c` matches in the initial `MATCH`, the entire query returns no rows. Do not assume result ordering without explicit sorting.

Pattern comprehensions are convenient for concise expressions. For complex queries requiring multi-step filtering, aggregation, and row-count control, using `MATCH`/`WITH`/`collect()` or an appropriate subquery can express the pipeline more clearly.

## 9. Combining with Java Driver and Spring Data Neo4j Parameters

A Java application commonly passes a list of maps to Cypher via **query parameters**. For example, the value of `$products`:

~~~json
[
  {"sku": " P01 ", "price": 120000, "name": "Neo4j Book"},
  {"sku": "P02", "price": 80000, "name": "Cypher Book"},
  {"sku": "", "price": 500000, "name": "Missing SKU"},
  {"sku": "P03", "price": 200000, "name": "Java Book"}
]
~~~

The `$minPrice` parameter might be `100000`. The query builds a list of eligible products to return to the application:

~~~cypher
WITH coalesce($products, []) AS products
RETURN [
  product IN products
  WHERE
    product.sku IS NOT NULL
    AND trim(product.sku) <> ''
    AND product.price IS NOT NULL
    AND product.price >= $minPrice
  | {
      sku: toUpper(trim(product.sku)),
      name: product.name,
      price: product.price
    }
] AS eligibleProducts;
~~~

The result contains two maps: product `P01` with price `120000` and `P03` with price `200000`. Products priced below the threshold or missing a valid SKU are excluded. The application should pre-validate that `sku` is a string, `price` is numeric, and the threshold parameter has the expected type to avoid runtime errors when calling `trim()` or comparing values.

If the next step needs to **write data to the graph**, unwind the normalized list into rows:

~~~cypher
WITH [
  sku IN coalesce($skus, [])
  WHERE sku IS NOT NULL AND trim(sku) <> ''
  | toUpper(trim(sku))
] AS cleanedSkus
UNWIND cleanedSkus AS sku
WITH DISTINCT sku
MERGE (p:Product {sku: sku})
RETURN count(p) AS distinctProductsTouched;
~~~

Processing steps:

1. The list comprehension filters out empty SKUs and normalizes values.
2. `UNWIND` turns the list into rows.
3. `WITH DISTINCT` keeps only one row per SKU.
4. `MERGE` finds or creates the `Product` node by SKU.

`distinctProductsTouched` counts the number of distinct SKU rows processed, **not the number of newly created nodes**. For concurrent write workloads, create an appropriate uniqueness constraint on `:Product(sku)` to guarantee uniqueness in the database. Queries taking similar parameters can be executed via the Neo4j Java Driver or custom repositories/queries in Spring Data Neo4j; avoid concatenating user-supplied data directly into Cypher strings.

## 10. Common Errors and Misconceptions

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| Expected multiple rows, got one row containing a list | List comprehension returns a **list value**, not separate rows | Use `UNWIND` if each element needs to be a row |
| `null` elements disappear after filtering | Predicate on `null` does not evaluate to `true` | Write explicit `IS NULL`/`IS NOT NULL` conditions as needed |
| Result is `null` instead of `[]` | The entire input list is `null` | Use `coalesce(sourceList, [])` where appropriate |
| Same code appears multiple times | Comprehension preserves duplicates | Use `UNWIND` + `DISTINCT` + `collect()` when uniqueness is required |
| Wrong order in a list built from the graph | Input rows to `collect()` were unsorted | Put `ORDER BY` before the `collect()` step |
| `any()` check returns `null` | Predicate on a `null` element yields unknown | Handle `null` beforehand, or define three-valued logic interpretation |
| Memory spike when returning a very long list | `collect()` or comprehension builds an oversized list | Limit the data going into the list; inspect the plan and row counts |
| `WHERE` outside comprehension drops the entire record | `WITH ... WHERE` filters **rows**, not list elements | Put the condition inside `[x IN list WHERE ...]` to keep the original row |

### Practical Guidelines

- **Choose the right output shape:** a single list, a boolean value, or multiple rows? List comprehensions, list predicates, and `UNWIND` serve different purposes.
- **Define the semantics of `null`:** distinguish between an empty list, an unprovided list, and an element with missing data.
- **Deduplicate only when allowed:** in order data, two lines with the same SKU may have distinct meanings (such as different batches or pricing tiers).
- **Control list sizes:** building and holding large lists in a query incurs cost; push filter predicates down into graph-reading steps when doing so does not alter semantics.
- **Inspect execution plans:** use `EXPLAIN` to view the plan and `PROFILE` on test data to check row counts at each step, especially before and after `collect()`/`UNWIND`.

## 11. Practice Exercises

### Exercise 1 — Filter Then Transform Numbers

Given the sequence from 1 to 10, return a list containing the **squares of numbers divisible by 3**.

~~~cypher
WITH range(1, 10) AS numbers
RETURN [n IN numbers WHERE n % 3 = 0 | n * n] AS result;
~~~

Expected result: `[9, 36, 81]`.

### Exercise 2 — Filter Maps and Keep Required Fields

Given three orders with ID, status, and total amount below, return a list containing only the ID and amount of `PAID` orders.

~~~cypher
WITH [
  {id: 'O01', status: 'PAID', total: 300000},
  {id: 'O02', status: 'PENDING', total: 450000},
  {id: 'O03', status: 'PAID', total: 250000}
] AS orders
RETURN [
  o IN orders
  WHERE o.status = 'PAID'
  | {orderId: o.id, amount: o.total}
] AS paidOrders;
~~~

Result:

~~~text
[
  {orderId: 'O01', amount: 300000},
  {orderId: 'O03', amount: 250000}
]
~~~

### Exercise 3 — Predict the Output with `null`

~~~cypher
WITH [2, null, 5, 2] AS numbers
RETURN
  [n IN numbers WHERE n >= 2] AS filtered,
  [n IN numbers WHERE n IS NOT NULL | n * 3] AS multiplied,
  size([n IN numbers WHERE n = 2]) AS countTwos;
~~~

Answer:

- `filtered = [2, 5, 2]`: `null` does not satisfy `n >= 2`.
- `multiplied = [6, 15, 6]`: removes `null`, then multiplies by 3.
- `countTwos = 2`: both occurrences of `2` are counted individually because comprehensions do not automatically deduplicate.

### Self-Check Question

**If you need to find a `Product` node for each valid SKU, can you just use `[sku IN skus WHERE ...]` and then `MATCH` directly?** You cannot treat the newly created list as separate rows. Before running `MATCH`/`MERGE` per SKU, you normally need `UNWIND cleanedSkus AS sku` to turn the list into rows with an independent `sku` variable.

## Key Takeaway

A list comprehension is a concise tool for **creating a new list from an existing list** in Cypher:

~~~cypher
[x IN source WHERE predicate | projection]
~~~

`WHERE` inside the expression selects elements, `| projection` transforms them, and the result remains **a single list value**. To split elements into rows, use `UNWIND`; to test a condition across the whole list, consider `all()`, `any()`, `none()`, or `single()`. When used with `collect()`, `nodes(path)`, and parameters from the Java Driver or Spring Data Neo4j, handle empty lists, `null` values, duplicates, and ordering explicitly so Neo4j queries stay reliable and easy to maintain.
