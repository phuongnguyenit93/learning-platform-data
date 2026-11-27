# Accessing Elements, Slicing Lists, and Generating Sequences in Cypher

## Lesson Objectives

In Neo4j, data is modeled as a **property graph** consisting of nodes, relationships, and properties. Beyond traversing relationships, Cypher frequently processes **lists** containing values, nodes, relationships, or maps. Lists appear when applications pass parameters to queries, when `collect()` aggregates multiple rows, when `nodes(path)` extracts nodes along a path, or when you need to generate a sequence of numbers with `range()`.

In the **Lists and Data Pipelines** chapter of module `DATABASE_ENGINE_GRAPH_NEO4J`, this lesson focuses on three operations:

1. **Accessing an element by position** with `list[index]`.
2. **Slicing a list into a sublist** with `list[start..end]`.
3. **Generating an integer sequence** with `range(start, end[, step])`, then using the sequence in expressions or combining it with `UNWIND`.

After this lesson, you will be able to accurately determine zero-based indexes, negative indexes, and exclusive slice end boundaries; handle empty or `null` lists; and apply these operations to fetch the first few results, number rows, and analyze paths in a Neo4j graph.

## 1. Lists and Element Positions

Cypher lists are written with square brackets. Example:

~~~cypher
WITH ['Neo4j', 'Cypher', 'Java Driver', 'Spring Data Neo4j'] AS topics
RETURN topics, size(topics) AS topicCount;
~~~

`size(topics)` returns `4` because the list has four elements. Each element has a position (index) starting at **0**:

~~~text
topics = ['Neo4j', 'Cypher', 'Java Driver', 'Spring Data Neo4j']
index:       0        1           2                 3
neg idx:    -4       -3          -2                -1
~~~

A list of `n` elements has valid non-negative indexes from `0` to `n - 1`. Negative indexes count backward from the end: `-1` is the last element, and `-2` is the second-to-last element.

Not every list is a property stored in the database. **List values created inside a query** can contain maps, nodes, or relationships. Meanwhile, **node/relationship properties** can only store data types allowed by the Neo4j property model, such as arrays of primitive values; you cannot arbitrarily store lists of nodes or maps as properties.

## 2. Accessing a Single Element with `list[index]`

Syntax:

~~~cypher
listExpression[indexExpression]
~~~

The result is **a single element**, not a sublist. Both the list expression and the index expression can come from variables created in the query.

~~~cypher
WITH ['Neo4j', 'Cypher', 'Java Driver', 'Spring Data Neo4j'] AS topics
RETURN
  topics[0]  AS firstTopic,
  topics[2]  AS thirdTopic,
  topics[-1] AS lastTopic,
  topics[-2] AS nextToLastTopic;
~~~

| Returned Column | Value |
| --- | --- |
| `firstTopic` | `Neo4j` |
| `thirdTopic` | `Java Driver` |
| `lastTopic` | `Spring Data Neo4j` |
| `nextToLastTopic` | `Java Driver` |

### Out-of-Bounds Indexes

Accessing a non-existent position returns `null`:

~~~cypher
WITH ['A', 'B', 'C'] AS letters
RETURN
  letters[2]  AS validIndex,
  letters[3]  AS beyondEnd,
  letters[-4] AS beforeStart;
~~~

Result: `validIndex = 'C'`; both `beyondEnd` and `beforeStart` are `null`. Thus, reading an element by index in Cypher does not automatically fail the query simply because the index is out of bounds.

However, a `null` result does not immediately tell you whether the cause is an **empty list**, an **out-of-bounds index**, an **actual null element**, or a **null input list**. When those cases carry different business meanings, inspect the data first.

~~~cypher
WITH [] AS items
RETURN
  size(items) AS itemCount,
  items[0] AS firstItem,
  coalesce(items[0], 'NONE') AS firstOrFallback;
~~~

The result is `itemCount = 0`, `firstItem = null`, and `firstOrFallback = 'NONE'`. `coalesce(x, fallback)` takes the fallback value when `x` is `null`; for an actual `null` element, it also selects the fallback.

### Safe Element Access for Optional Input

Suppose a map from an application might not contain a `tags` field:

~~~cypher
WITH {id: 'C01', tags: null} AS customerInput
WITH
  customerInput.id AS customerId,
  coalesce(customerInput.tags, []) AS tags
RETURN
  customerId,
  size(tags) AS tagCount,
  CASE
    WHEN size(tags) > 0 THEN tags[0]
    ELSE 'NO_TAG'
  END AS firstTag;
~~~

`coalesce(..., [])` normalizes a missing list value into an empty list. `CASE` explicitly expresses the business decision when there are no tags, instead of relying on `null` and guessing the cause.

### Comparing with `head()` and `last()`

Cypher also provides functions to get the first/last element:

~~~cypher
WITH [10, 20, 30] AS amounts
RETURN
  amounts[0] AS firstByIndex,
  head(amounts) AS firstByFunction,
  amounts[-1] AS lastByIndex,
  last(amounts) AS lastByFunction;
~~~

Both ways of getting the first element and both ways of getting the last element return `10` and `30`, respectively. Use index syntax when you need an **arbitrary position**; use `head()`/`last()` when the "first/last" intent should stand out.

## 3. Slicing a List with `list[start..end]`

While `list[index]` retrieves **one element**, the following syntax produces **a sublist**:

~~~cypher
listExpression[startIndex..endIndex]
~~~

Key rules:

- `startIndex` **is included** in the slice (inclusive).
- `endIndex` **is excluded** from the slice (exclusive).
- You can omit `startIndex` to start from the beginning, or omit `endIndex` to slice until the end.
- Negative indexes counting from the end of the list are allowed.
- If the start and end positions coincide, the slice is an empty list `[]`.

Consider a five-element list:

~~~cypher
WITH ['A', 'B', 'C', 'D', 'E'] AS letters
RETURN
  letters[1..4]   AS middle,
  letters[..3]    AS firstThree,
  letters[2..]    AS fromThird,
  letters[-2..]   AS lastTwo,
  letters[..-1]   AS exceptLast,
  letters[2..2]   AS emptySlice;
~~~

| Expression | Result | Explanation |
| --- | --- | --- |
| `letters[1..4]` | `['B', 'C', 'D']` | Positions 1, 2, 3; excludes position 4 |
| `letters[..3]` | `['A', 'B', 'C']` | Start omitted, begins at 0 |
| `letters[2..]` | `['C', 'D', 'E']` | From position 2 to the end |
| `letters[-2..]` | `['D', 'E']` | Last two elements |
| `letters[..-1]` | `['A', 'B', 'C', 'D']` | Excludes the last element |
| `letters[2..2]` | `[]` | Start equals end |

For `letters[-3..-1]`, the start is `C` and the end is the position of `E`, **excluding E**, so the result is `['C', 'D']`.

### Be Careful with "Up to the Nth Element"

To get the **first three elements**, use `letters[..3]`, not `letters[..2]`. The slice ends at index `3` without including the element at that index.

~~~text
Index:          0    1    2    3    4
List:           A    B    C    D    E
letters[1..4]:      [B   C    D]   (excludes E)
letters[..3]:  [A    B    C]       (excludes D, E)
~~~

Slicing **does not mutate the original list**; it returns a new list value to pass to the next step.

### Using Variables to Compute Boundaries

In applications, the number of elements to take is often parameterized:

~~~cypher
WITH
  ['O01', 'O02', 'O03', 'O04', 'O05'] AS orderIds,
  1 AS startIndex,
  2 AS pageSize
RETURN
  orderIds[startIndex..startIndex + pageSize] AS selectedOrders;
~~~

Result: `selectedOrders = ['O02', 'O03']`. Here `startIndex = 1` and `pageSize = 2`; the end boundary is `3`, so positions 1 and 2 are selected.

Slicing an in-memory list is **not the same** as limiting rows in the underlying query. If `collect()` previously gathered many nodes into a large list, `list[..10]` only selects the subset **after the full list has been built**. When you only need 10 rows, you can reduce data early by placing `ORDER BY` and `LIMIT` at the right spot before `collect()`.

## 4. Generating Integer Sequences with `range()`

`range()` is a Cypher function that creates a **list of consecutive integers by step**:

~~~cypher
range(start, end)
range(start, end, step)
~~~

In `range()`, **the end value is included in the result if it is reachable by the step**. This differs from `endIndex` in `list[start..end]` slicing.

~~~cypher
RETURN
  range(0, 4) AS zeroToFour,
  range(1, 9, 2) AS oddNumbers,
  range(10, 4, -3) AS descending;
~~~

| Expression | Result |
| --- | --- |
| `range(0, 4)` | `[0, 1, 2, 3, 4]` |
| `range(1, 9, 2)` | `[1, 3, 5, 7, 9]` |
| `range(10, 4, -3)` | `[10, 7, 4]` |
| `range(0, 5, 2)` | `[0, 2, 4]` |

If `step` is omitted, the default step is `1`. When counting backward, pass a negative step such as `-1` or `-3`. A step of `0` is invalid. To avoid an empty sequence caused by going in the wrong direction, use a positive step when incrementing and a negative step when decrementing.

`range()` returns **a single list**; it does not emit multiple rows on its own. This is clear in the following example:

~~~cypher
WITH range(1, 5) AS sequence
RETURN sequence, size(sequence) AS numberOfValues;
~~~

The result is **one row** containing `sequence = [1, 2, 3, 4, 5]` and `numberOfValues = 5`.

### Turning a Sequence into Rows with `UNWIND`

To perform a calculation for each number, combine `range()` with `UNWIND`:

~~~cypher
UNWIND range(1, 5) AS n
RETURN n, n * n AS square
ORDER BY n;
~~~

| n | square |
| ---: | ---: |
| 1 | 1 |
| 2 | 4 |
| 3 | 9 |
| 4 | 16 |
| 5 | 25 |

Now each element in the sequence produces one row. `ORDER BY` ensures the result is presented in the right order; do not rely on a default row order after `UNWIND`.

### Creating a Sequence for List Comprehension

A list comprehension is a way to transform values **directly within a list**:

~~~cypher
WITH range(1, 6) AS numbers
RETURN
  [n IN numbers | n * n] AS squares,
  [n IN numbers WHERE n % 2 = 0 | n] AS evenNumbers;
~~~

Result:

- `squares = [1, 4, 9, 16, 25, 36]`;
- `evenNumbers = [2, 4, 6]`.

Comparison: `UNWIND` expands a list into **multiple rows**; a list comprehension returns **a single filtered or transformed list**. Choose based on the shape of data the next clause needs.

## 5. Combining Indexes and `range()` to Number Elements

Suppose a list of SKUs is already ordered as the application wants to display them:

~~~cypher
WITH ['P01', 'P02', 'P03'] AS skus
WITH
  skus,
  CASE
    WHEN size(skus) = 0 THEN []
    ELSE range(0, size(skus) - 1)
  END AS indexes
UNWIND indexes AS i
RETURN
  i AS zeroBasedIndex,
  i + 1 AS displayPosition,
  skus[i] AS sku
ORDER BY zeroBasedIndex;
~~~

| zeroBasedIndex | displayPosition | sku |
| ---: | ---: | --- |
| 0 | 1 | P01 |
| 1 | 2 | P02 |
| 2 | 3 | P03 |

This pattern has three steps: generate valid indexes, unwind the index list with `UNWIND`, and access `skus[i]`. `CASE` handles an empty list by producing `[]` instead of computing an invalid index range.

> Note: if you only need each SKU without knowing its position, `UNWIND skus AS sku` is enough. Generating `range()` and indexing back into the list is only useful when the **index** itself is also needed in the output or for calculations.

### Numbering from Map Input

When application data has an important order, the clearest approach is usually to pass a `position` field along with each item:

~~~cypher
UNWIND [
  {position: 2, sku: 'P03'},
  {position: 0, sku: 'P01'},
  {position: 1, sku: 'P02'}
] AS row
RETURN row.position AS position, row.sku AS sku
ORDER BY position;
~~~

The result `P01`, `P02`, `P03` is determined by `ORDER BY position`. This avoids relying on any order that `UNWIND` might not guarantee when expanding a list.

## 6. Applying to Nodes, Relationships, and Neo4j Paths

Lists in Cypher do not only contain strings or numbers. When matching a path, the `nodes(p)` and `relationships(p)` functions return lists of nodes and relationships along that path.

Suppose the graph has the structure:

~~~text
(:Person {id: 'U01'})-[:KNOWS]->(:Person)-[:KNOWS]->(:Person)
~~~

The following query illustrates how to get the start, end, and intermediate nodes of a path:

~~~cypher
MATCH p = (a:Person {id: $personId})-[:KNOWS*1..3]->(b:Person)
WITH p, nodes(p) AS pathNodes, relationships(p) AS pathRels
RETURN
  pathNodes[0] AS startPerson,
  pathNodes[-1] AS endPerson,
  pathNodes[1..-1] AS intermediatePeople,
  size(pathNodes) AS nodeCount,
  size(pathRels) AS relationshipCount;
~~~

If a path has three nodes `A → B → C`, then `pathNodes = [A, B, C]`, `pathNodes[0] = A`, `pathNodes[-1] = C`, and `pathNodes[1..-1] = [B]`. The number of relationships is two.

This is an example of **querying an existing graph**: matching `Person` nodes, `KNOWS` relationships, and the `$personId` parameter must exist for rows to be returned. You do not need to change the graph structure to understand indexing or slicing; they operate on the list returned by `nodes(p)`.

### Taking the First Few Elements from a `collect()` Result

Another case is a list of orders collected per customer:

~~~cypher
MATCH (c:Customer {id: $customerId})-[:PLACED]->(o:Order)
WITH o
ORDER BY o.createdAt DESC, o.id ASC
WITH collect(o.id) AS orderedOrderIds
RETURN
  orderedOrderIds[0] AS newestOrderId,
  orderedOrderIds[..3] AS threeNewestOrderIds,
  size(orderedOrderIds) AS totalOrders;
~~~

`ORDER BY o.createdAt DESC, o.id ASC` defines the input order for `collect()` in the next clause: the newest order comes first, with `o.id` as a tie-breaker when timestamps match. `orderedOrderIds[..3]` takes up to the first three IDs.

**Distinguish between two goals**:

- Need both the **total order count** and the **first three IDs** in the same row: `collect()` followed by list slicing expresses the intent directly.
- Only need the **three newest order nodes**: consider `ORDER BY ... LIMIT 3` before collecting the list to reduce the amount of data retained. When limiting before `collect()`, `totalOrders` no longer reflects the original total if you only count the truncated rows.

## 7. Slicing Lists for Pagination: Right Order, Right Cost

For a result list whose order has already been standardized by the application, you can slice by page:

~~~cypher
WITH
  ['O01', 'O02', 'O03', 'O04', 'O05', 'O06', 'O07'] AS orderedIds,
  1 AS page,
  3 AS pageSize
WITH orderedIds, page * pageSize AS offset, pageSize
RETURN orderedIds[offset..offset + pageSize] AS pageIds;
~~~

Assuming `page` starts at 0, `page = 1` is the second page. In the example, `offset = 3` and `pageIds = ['O04', 'O05', 'O06']`.

The application must validate `page >= 0`, `pageSize > 0`, and bound the page size before passing them to the query. If `orderedIds` is produced by `collect()` from multiple graph matches, make sure the input stream is explicitly sorted before collecting.

For large datasets, paginating directly on **Cypher result rows** is usually more efficient than calling `collect()` on everything:

~~~cypher
MATCH (o:Order)
WITH o
ORDER BY o.createdAt DESC, o.id ASC
SKIP $offset
LIMIT $pageSize
RETURN o.id AS orderId, o.createdAt AS createdAt
ORDER BY createdAt DESC, orderId ASC;
~~~

`SKIP`/`LIMIT` limits the **rows** passed onward; `[start..end]` slicing only slices an **already-existing list value**. Both require deterministic ordering when used for pagination. In systems with large or rapidly changing datasets, consider keyset pagination instead of deep `SKIP` offsets.

## 8. Common Mistakes

| Situation | Cause | How to Fix |
| --- | --- | --- |
| Getting the wrong first/last element | Confusing lists as 1-based | Remember the first index is `0` and the last is `-1` |
| Slicing three elements but getting only two | Mistaking the end boundary of `[start..end]` as inclusive | `items[..3]` takes positions `0, 1, 2` |
| `range(0, 3)` has four numbers | `range()` includes the end value if reachable | Distinguish `range(0, 3)` from `items[0..3]` |
| Out-of-bounds access returns `null` | List is too short or index is wrong | Check `size(list)`, and use `CASE`/`coalesce()` intentionally |
| Sublist is not in business order | Source list from `collect()` lacked deterministic order | Put `ORDER BY` on the stream before `collect()` |
| `UNWIND range(...)` blows up the query | Range generates too many elements, each creating a row | Bound input parameters; check row count and memory before generating ranges |
| Slice-based pagination is slow on large data | Building the entire list before slicing | Use `ORDER BY` + `SKIP`/`LIMIT` on rows, or keyset pagination |
| Generating positions with `range(0, size(xs) - 1)` on an empty list | No valid indexes exist in an empty list | Handle `size(xs) = 0` with `CASE` before generating the range |

When evaluating performance, use `EXPLAIN` to inspect the estimated plan and `PROFILE` to observe actual row counts flowing through each operator on test data. Do not assume that writing a concise slice expression reduces the number of nodes read in earlier steps.

## 9. Practice Exercises

### Exercise 1 — Accessing Elements and Slicing a List

Given the list `['A', 'B', 'C', 'D', 'E', 'F']`, return:

1. The first element and the last element.
2. Three elements starting at position 1, i.e., `['B', 'C', 'D']`.
3. The list without its last two elements.

Reference solution:

~~~cypher
WITH ['A', 'B', 'C', 'D', 'E', 'F'] AS letters
RETURN
  letters[0] AS firstValue,
  letters[-1] AS lastValue,
  letters[1..4] AS threeFromSecond,
  letters[..-2] AS withoutLastTwo;
~~~

The results are `'A'`, `'F'`, `['B', 'C', 'D']`, and `['A', 'B', 'C', 'D']`, respectively.

### Exercise 2 — Generating a Sequence and Numbering Records

Given `products = ['P10', 'P20', 'P30', 'P40']`, return four rows with `position` starting at 1 and the corresponding `sku`.

~~~cypher
WITH ['P10', 'P20', 'P30', 'P40'] AS products
UNWIND range(0, size(products) - 1) AS i
RETURN i + 1 AS position, products[i] AS sku
ORDER BY position;
~~~

Expected result: `(1, 'P10')`, `(2, 'P20')`, `(3, 'P30')`, and `(4, 'P40')`. In this example, the list is known to have four elements; if accepting an arbitrary list from an application, apply the empty-list handling pattern from Section 5.

### Exercise 3 — Boundary Self-Check

Given `items = [10, 20, 30, 40]`, predict the result of:

~~~cypher
WITH [10, 20, 30, 40] AS items
RETURN
  items[-1] AS a,
  items[1..3] AS b,
  items[..-1] AS c,
  range(1, 4, 2) AS d;
~~~

Answer: `a = 40`; `b = [20, 30]`; `c = [10, 20, 30]`; `d = [1, 3]`. The value `4` does not appear in `d` because stepping by 2 from 1 visits 1, 3, and then goes past the end value 4.

## Key Takeaway

Cypher provides three ways to work with positions in a list:

- `list[index]` retrieves **a single element**; indexes start at 0, negative indexes count from the end, and out-of-bounds returns `null`.
- `list[start..end]` creates a **sublist**; it includes the start position and **excludes the end position**.
- `range(start, end[, step])` generates an **integer sequence**; the end value is included if the step lands on it.

When combined with `WITH`, `collect()`, `UNWIND`, and path list functions like `nodes(p)`, these operations keep Neo4j property graph queries concise and easier to control. Always verify input order, list size, and the meaning of positions before indexing or slicing inside a data pipeline.
