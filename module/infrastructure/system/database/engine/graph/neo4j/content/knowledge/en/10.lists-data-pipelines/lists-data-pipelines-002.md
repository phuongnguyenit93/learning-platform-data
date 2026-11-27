# `UNWIND` in Cypher: Turning Lists into Data Rows

## Lesson Objectives

Neo4j stores data using the **property graph** model: nodes represent entities, relationships represent connections, and properties store attributes. When querying a graph with Cypher, data flows through clauses as a **stream of rows**. A row can contain nodes, relationships, numbers, strings, maps, or lists.

In the **Lists and Data Pipelines** chapter, `UNWIND` addresses a very common need: **a variable holds a list, and the next step needs to process each element as an individual row**. This technique appears in analytical queries, transforming results from `collect()`, bulk data ingestion via the Java Driver or Spring Data Neo4j, and creating nodes/relationships from application payloads.

After this lesson, you will be able to:

- Explain the `UNWIND <list-expression> AS <variable>` syntax and its effect on row count.
- Distinguish between empty lists, `null` elements, duplicate elements, and nested lists.
- Combine `UNWIND` with `WITH`, `WHERE`, `DISTINCT`, `collect()`, and `ORDER BY`.
- Parse and transform a list of maps into data rows and ingest data into a graph using `MERGE`.
- Recognize the risks of row multiplication, non-guaranteed ordering, and the cost of large lists.

## 1. The Nature of `UNWIND`

Syntax:

~~~cypher
UNWIND listExpression AS item
~~~

`listExpression` must evaluate to a list; `item` is the new variable name for **each element**. For **every input row**, `UNWIND` produces one output row for each element in that row's list. Any other variables already present in the input row are carried forward.

~~~text
Input row
customerId = 'C01'
skus       = ['P01', 'P02', 'P03']
        |
        | UNWIND skus AS sku
        v
Row 1: customerId = 'C01', sku = 'P01'
Row 2: customerId = 'C01', sku = 'P02'
Row 3: customerId = 'C01', sku = 'P03'
~~~

An example you can run directly in Neo4j without any existing graph data:

~~~cypher
WITH 'C01' AS customerId, ['P01', 'P02', 'P03'] AS skus
UNWIND skus AS sku
RETURN customerId, sku
ORDER BY sku;
~~~

Result:

| customerId | sku |
| --- | --- |
| C01 | P01 |
| C01 | P02 |
| C01 | P03 |

The variable `skus` holds the entire list; `sku` takes on each value inside it in turn. `UNWIND` **does not select columns by itself**, **does not deduplicate by itself**, and **does not guarantee the output order of rows**. `ORDER BY` in the example above is why the result table is sorted by `sku`.

A helpful perspective:

| Clause | Main Function | Typical Effect on Row Count |
| --- | --- | --- |
| `WITH` | Forward, alias, filter, or group intermediate data | Preserves, reduces, or groups rows depending on expressions |
| `collect(x)` | Gather multiple values into a list per group | Reduces row count during aggregation |
| `UNWIND xs AS x` | Expand a list into rows | Can increase, preserve, or reduce to 0 rows |
| `RETURN` | Output the final rows of the query | Returns the selected rows/columns |

`UNWIND` is not equivalent to traversing relationships in a graph with `MATCH`. It operates on a **list value**; the expanded elements can then be used to `MATCH` or `MERGE` nodes/relationships in a subsequent stage.

## 2. Unwinding Lists of Simple Values

### Each Element Becomes a Row

~~~cypher
UNWIND [5, 10, 15] AS quantity
RETURN quantity, quantity * 2 AS doubleQuantity
ORDER BY quantity;
~~~

The query produces three output rows with `quantity` equal to 5, 10, and 15 respectively; the `doubleQuantity` column holds 10, 20, and 30. The calculation is performed on **each row's value**, not on the entire list at once.

### `UNWIND` Preserves Duplicate Values

~~~cypher
UNWIND ['P01', 'P02', 'P01'] AS sku
RETURN sku
ORDER BY sku;
~~~

The result has **three rows**, where `P01` appears twice. If you need one row per unique SKU:

~~~cypher
UNWIND ['P01', 'P02', 'P01'] AS sku
WITH DISTINCT sku
RETURN sku
ORDER BY sku;
~~~

The result contains only `P01` and `P02`. `DISTINCT` is an explicit deduplication operation; `UNWIND` does not perform it by default.

### Empty Lists and `null`

The following cases directly affect the row stream:

| Unwound Expression | Rows Produced | Explanation |
| --- | ---: | --- |
| `[1, 2, 3]` | 3 | One row per element |
| `[]` | 0 | No elements, so no rows are emitted |
| `[null]` | 1 | One row with value `null` |
| `[1, null, 1]` | 3 | Keeps both the `null` element and both `1` values |

Example:

~~~cypher
UNWIND [1, null, 1, 2] AS n
RETURN
  count(*) AS numberOfRows,
  count(n) AS nonNullValues,
  count(DISTINCT n) AS distinctNonNullValues;
~~~

The result is `numberOfRows = 4`, `nonNullValues = 3`, `distinctNonNullValues = 2`. `count(*)` counts rows; `count(n)` ignores `null` values.

An empty list **stops the row stream on that query branch**:

~~~cypher
WITH 'C01' AS customerId, [] AS tags
UNWIND tags AS tag
RETURN customerId, tag;
~~~

The query returns **0 rows**, even though `customerId` existed before `UNWIND`. This is a common reason data "disappears" in a pipeline when a list field can be empty.

If the list expression might be `null` (for example, a property does not exist yet), use `coalesce(..., [])` to default to an empty list:

~~~cypher
WITH {id: 'C01', tags: null} AS record
UNWIND coalesce(record.tags, []) AS tag
RETURN record.id AS customerId, tag;
~~~

The result is 0 rows, intentionally, rather than trying to unwind a non-list value directly. When business logic requires keeping the original record even when there are no elements, you must design dedicated handling (such as handling empty cases in a separate branch); `UNWIND []` on its own does not retain the row.

## 3. Unwinding a List of Maps

Data from REST APIs, JSON, or Java applications is often represented as a list of objects. In Cypher, each object corresponds to a **map** with keys and values.

~~~cypher
UNWIND [
  {sku: 'P01', name: 'Neo4j Book', price: 120000},
  {sku: 'P02', name: 'Cypher Book', price: 90000},
  {sku: 'P03', name: 'Graph Book', price: 150000}
] AS product
RETURN
  product.sku AS sku,
  product.name AS productName,
  product.price AS price
ORDER BY sku;
~~~

Each `product` is a map; its keys can be accessed via `product.sku`, `product.name`, and `product.price`. The result has three rows:

| sku | productName | price |
| --- | --- | ---: |
| P01 | Neo4j Book | 120000 |
| P02 | Cypher Book | 90000 |
| P03 | Graph Book | 150000 |

Filtering rows right after unwinding the list:

~~~cypher
UNWIND [
  {sku: 'P01', price: 120000},
  {sku: 'P02', price: 90000},
  {sku: 'P03', price: 150000}
] AS product
WITH product
WHERE product.price >= 100000
RETURN product.sku AS sku, product.price AS price
ORDER BY price DESC;
~~~

Here `WITH product WHERE ...` filters rows with a price of at least 100,000; the result contains `P03` and `P01`. In Cypher, `WHERE` is attached to an appropriate clause such as `MATCH` or `WITH`; when filtering immediately after `UNWIND`, use `WITH ... WHERE ...` as shown in this example.

## 4. Nested Lists: One `UNWIND` Expands One Level

If list elements are themselves lists, a single `UNWIND` expands only the **outer level**:

~~~cypher
UNWIND [[1, 2], [], [3, 4]] AS numbers
RETURN numbers;
~~~

The three output rows have `numbers` values `[1, 2]`, `[]`, and `[3, 4]` (do not assume order without `ORDER BY`). To extract each individual number, unwind one more time:

~~~cypher
UNWIND [[1, 2], [], [3, 4]] AS numbers
UNWIND numbers AS n
RETURN n
ORDER BY n;
~~~

The result has four rows: `1`, `2`, `3`, `4`. The empty sublist produces no rows on the second `UNWIND`.

### Example with Order Line Items

Suppose an application sends a list of orders, where each order contains an `items` list:

~~~cypher
UNWIND [
  {
    orderId: 'O01',
    items: [
      {sku: 'P01', quantity: 2},
      {sku: 'P02', quantity: 1}
    ]
  },
  {
    orderId: 'O02',
    items: [{sku: 'P02', quantity: 3}]
  },
  {
    orderId: 'O03',
    items: []
  }
] AS orderData
UNWIND orderData.items AS item
RETURN
  orderData.orderId AS orderId,
  item.sku AS sku,
  item.quantity AS quantity
ORDER BY orderId, sku;
~~~

| orderId | sku | quantity |
| --- | --- | ---: |
| O01 | P01 | 2 |
| O01 | P02 | 1 |
| O02 | P02 | 3 |

`O03` produces no rows because `items` is empty. Two `UNWIND` clauses create a **one order → many line items** relationship in the data stream, without yet creating nodes or relationships in the graph.

**Beware of unintended row multiplication.** Consider two independent lists:

~~~cypher
WITH ['C01', 'C02'] AS customerIds, ['P01', 'P02'] AS skus
UNWIND customerIds AS customerId
UNWIND skus AS sku
RETURN customerId, sku
ORDER BY customerId, sku;
~~~

The result has **4 combinations** (2 × 2). This is the Cartesian product of the two lists per input row, **not** a positional pairing of `C01` with `P01` and `C02` with `P02`. If the business logic requires corresponding pairs, pass the data as a list of maps such as `[{customerId: 'C01', sku: 'P01'}, ...]` and `UNWIND` once.

## 5. Combining `WITH`, `collect`, and `UNWIND` in a Pipeline

`WITH` organizes intermediate steps; `collect()` gathers values into a list; `UNWIND` turns list elements back into rows.

~~~text
Multiple rows             One row per group                  Multiple rows
id | sku                  id  | skus                         id | sku
C01| P01    --collect-->  C01 | [P01, P02]  --UNWIND-->      C01| P01
C01| P02                                                     C01| P02
~~~

This can be demonstrated using inline data directly in the query:

~~~cypher
UNWIND [
  {customerId: 'C01', sku: 'P01'},
  {customerId: 'C01', sku: 'P02'},
  {customerId: 'C02', sku: 'P02'}
] AS row
WITH row.customerId AS customerId, collect(row.sku) AS skus
UNWIND skus AS sku
RETURN customerId, sku
ORDER BY customerId, sku;
~~~

`WITH` groups by `customerId`; `UNWIND` then processes each SKU. This example intentionally returns to the original row count to illustrate the transformation. In an application, only use `collect()` followed by `UNWIND` when you need to perform a list-level operation in between; otherwise, keeping the rows as-is is usually simpler and cheaper.

### Preserving or Removing Duplicates

Suppose an application sends a list that may contain duplicate codes:

~~~cypher
UNWIND ['P02', 'P01', 'P02', 'P03'] AS sku
WITH DISTINCT sku
RETURN collect(sku) AS uniqueSkus;
~~~

`DISTINCT` reduces the stream to three distinct SKUs, and `collect()` builds the list. **Do not rely on the element order in `uniqueSkus`** without `ORDER BY`.

To return the list in ascending code order:

~~~cypher
UNWIND ['P02', 'P01', 'P02', 'P03'] AS sku
WITH DISTINCT sku
ORDER BY sku
RETURN collect(sku) AS uniqueSkus;
~~~

The result is `['P01', 'P02', 'P03']`. `ORDER BY` in `WITH` sorts the row stream before the immediately following clause executes `collect()`.

### Ordering Rules

Neo4j **does not guarantee** that `UNWIND` preserves the input list's element order. Whenever order matters (rankings, pagination, report output), sort explicitly with `ORDER BY`. If you must preserve the **original position** of each element, pass an index in the input payload, such as `[{position: 0, value: 'P02'}, {position: 1, value: 'P01'}]`, and sort by `position`.

## 6. `UNWIND` in Property Graph Data Ingestion

A typical scenario in `DATABASE_ENGINE_GRAPH_NEO4J` is receiving a list of records from the Java Driver or Spring Data Neo4j and turning them into nodes/relationships. **Pass the entire list as a query parameter**, rather than concatenating Cypher strings from external values.

Suppose the `$products` parameter is passed by the application with data equivalent to:

~~~json
[
  {"sku": "P01", "name": "Neo4j Book", "price": 120000},
  {"sku": "P02", "name": "Cypher Book", "price": 90000}
]
~~~

Create or update products in a single query:

~~~cypher
UNWIND $products AS raw
WITH
  trim(raw.sku) AS sku,
  raw.name AS productName,
  raw.price AS price
WHERE sku IS NOT NULL AND sku <> ''
MERGE (p:Product {sku: sku})
SET p.name = productName,
    p.price = price
RETURN count(p) AS processedRows;
~~~

Explanation:

1. `UNWIND $products AS raw` generates one row per input map.
2. `WITH` extracts and normalizes the required fields; `WHERE` removes empty or missing SKUs.
3. `MERGE` finds or creates the `Product` node by `sku`.
4. `SET` updates the properties; `count(p)` counts the processed rows, **not necessarily the number of newly created nodes or unique nodes** if the input contains duplicate SKUs.

To enforce the uniqueness of `Product.sku`, create a database constraint beforehand:

~~~cypher
CREATE CONSTRAINT product_sku_unique IF NOT EXISTS
FOR (p:Product) REQUIRE p.sku IS UNIQUE;
~~~

Constraints let Neo4j enforce uniqueness, especially when multiple concurrent transactions are writing. `MERGE` does not create a constraint on its own. If the input contains multiple records with the same `sku` but different `name` or `price` values, the update outcome can depend on processing order; the application should define conflict resolution rules and deduplicate before writing.

### Creating Relationships from a Nested Order List

Suppose `$orders` is a list of maps where each element has `customerId`, `orderId`, and an `items` list:

~~~json
[
  {
    "customerId": "C01",
    "orderId": "O01",
    "items": [
      {"sku": "P01", "quantity": 2},
      {"sku": "P02", "quantity": 1}
    ]
  },
  {
    "customerId": "C02",
    "orderId": "O02",
    "items": [{"sku": "P02", "quantity": 3}]
  }
]
~~~

Target model:

~~~text
(:Customer {id})
       |
       +--[:PLACED]--> (:Order {id})
                              |
                              +--[:CONTAINS {quantity}]--> (:Product {sku})
~~~

Query:

~~~cypher
UNWIND $orders AS rawOrder
WITH
  trim(rawOrder.customerId) AS customerId,
  trim(rawOrder.orderId) AS orderId,
  rawOrder.items AS items
WHERE
  customerId IS NOT NULL AND customerId <> ''
  AND orderId IS NOT NULL AND orderId <> ''
MERGE (c:Customer {id: customerId})
MERGE (o:Order {id: orderId})
MERGE (c)-[:PLACED]->(o)
WITH o, items
UNWIND coalesce(items, []) AS rawItem
WITH
  o,
  trim(rawItem.sku) AS sku,
  rawItem.quantity AS quantity
WHERE
  sku IS NOT NULL AND sku <> ''
  AND quantity IS NOT NULL AND quantity > 0
MERGE (p:Product {sku: sku})
MERGE (o)-[line:CONTAINS]->(p)
SET line.quantity = quantity;
~~~

These steps create or match `Customer` and `Order` first, then unwind `items` to create or match `Product` and the `CONTAINS` relationship. If `items` is empty or `null`, no rows proceed past `UNWIND`; the customer/order creation happens before it. The query above assumes each **order–product** pair has only one `CONTAINS` relationship and that `quantity` has been validated by the application as positive. If an order can contain multiple lines with the same SKU, you should specify quantity accumulation rather than arbitrarily overwriting.

In a Java application, pass `$products` or `$orders` as **query parameters** via the Neo4j Java Driver, or as parameters to a custom query in Spring Data Neo4j. There is no need to construct a separate `CREATE` or `MERGE` statement for every single element. For large-scale imports, split data into reasonable batches and manage transactions according to your system's memory, latency, and consistency limits.

## 7. Common Errors and How to Check Them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| No results after `UNWIND` | The list in the input row is empty | Check `size(list)` before unwinding; handle empty cases explicitly |
| One input record appears multiple times | `UNWIND` emits one row per element, or two independent `UNWIND`s multiply rows | Verify what each row represents; use a list of maps to keep paired items together |
| Duplicate SKUs in results | Input contains duplicates; `UNWIND` keeps them | Use `WITH DISTINCT` when you want unique values |
| `null` elements missing from aggregated results | `count(x)` and `collect(x)` ignore `null` | Use `count(*)` to count rows; handle `null` before `collect()` if needed |
| Results not in input order | `UNWIND` does not guarantee order | Add `ORDER BY`; carry the original index if needed |
| `MERGE` fails on `null` property or wrong type | Record missing an ID or field has wrong type | Normalize, validate, and filter values before `MERGE` |
| Slow import, high memory usage | List too large, many `MERGE` operations, or row multiplication | Measure with `PROFILE` on test data, batch the input, add appropriate constraints/indexes |

Some principles for effective implementation:

- **Control row counts:** given `N` input rows where each row has `kᵢ` elements, `UNWIND` generates a total of `k₁ + k₂ + ... + kₙ` rows; empty lists contribute 0 rows.
- **Trim unnecessary data:** filter, normalize, and deduplicate at the right stage in the pipeline. However, deduplicate only when business rules allow it, especially for order data.
- **Validate input data:** create uniqueness constraints for business keys such as `Customer.id`, `Order.id`, `Product.sku`; define how duplicate or missing fields are handled before writing.
- **Inspect execution plans:** `EXPLAIN` shows the planned execution steps; `PROFILE` shows actual row counts flowing through operators on test data. Avoid running write queries with `PROFILE` unintentionally in critical environments, because `PROFILE` executes the query.

## 8. Practice Exercises

**Exercise 1 — Turn a list of scores into rows.** Given the list `[7, 9, 7, null, 10]`, return the **unique**, non-`null` scores sorted in ascending order.

Hint:

~~~cypher
UNWIND [7, 9, 7, null, 10] AS score
WITH DISTINCT score
WHERE score IS NOT NULL
RETURN score
ORDER BY score;
~~~

Expected result: three rows with `score = 7`, `9`, and `10`.

**Exercise 2 — Compute order total from a list of line items.** Each line item has `sku`, `quantity`, and `unitPrice`. Unwind the list into rows, compute `lineTotal` for each line, and then calculate the total order value.

~~~cypher
UNWIND [
  {sku: 'P01', quantity: 2, unitPrice: 120000},
  {sku: 'P02', quantity: 1, unitPrice: 90000}
] AS item
WITH
  item.sku AS sku,
  item.quantity * item.unitPrice AS lineTotal
RETURN
  collect({sku: sku, lineTotal: lineTotal}) AS lines,
  sum(lineTotal) AS orderTotal;
~~~

Expected result: `orderTotal = 330000`, and `lines` has two maps with `lineTotal` equal to `240000` and `90000` (do not assume element order if unsorted).

**Self-check:** If `items = []`, how many rows will `UNWIND items AS item` produce? What if `items = [null]`? Answer: `[]` produces **0 rows**; `[null]` produces **1 row** with `item = null`. These two cases have different effects on `count(*)` and subsequent steps.

## Key Takeaway

`UNWIND` is the clause that **expands lists into rows** in Cypher: each element produces one row, empty lists produce zero rows, duplicates are preserved, and order is guaranteed only when explicitly sorted. Combining `UNWIND` with `WITH`, `collect()`, and `MERGE` enables clean data transformation pipelines and node/relationship ingestion for Neo4j, especially when Java applications pass data as lists of maps.
