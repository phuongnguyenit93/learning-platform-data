# Map Projection in Cypher: Shaping Results for Application Needs

## Lesson Objectives

In Neo4j, connected data is organized as a **property graph**: nodes hold entity properties, and relationships hold connections and relationship properties. An application often does not want to receive entire nodes or relationships from Neo4j. For example, a customer profile page only needs `id`, `name`, and the three most recent orders; a reporting API may need the total amount, status, and product list, without all the internal properties of the graph.

In the **Lists and Data Pipelines** chapter of module `DATABASE_ENGINE_GRAPH_NEO4J`, **map projection** is Cypher's tool for constructing a **result map shaped to what the application needs**, based on an existing map, node, or relationship variable. The syntax can select properties, add computed fields, and nest other maps or lists. This lesson connects directly to how results are returned via the **Neo4j Java Driver** and custom queries in **Spring Data Neo4j**.

After this lesson, you will be able to:

- Distinguish a **map literal** `{key: value}` from a **map projection** `variable { .property, key: expression }`.
- Use the `.property` selector, `key: expression` computed fields, and the `.*` operator.
- Combine map projection with `MATCH`, `WITH`, `collect()`, and list comprehensions to build nested results.
- Understand how missing properties, `null` values, row counts, and list ordering are handled.
- Design Cypher payloads tailored for DTOs/APIs while avoiding unintended exposure of internal properties.

## 1. Why Use Map Projection?

Suppose the graph contains a customer node:

~~~text
(:Customer {
  id: 'C01',
  name: 'Lan',
  email: 'lan@example.test',
  loyaltyPoints: 180,
  internalNote: 'For internal operations only'
})
~~~

A public application only needs:

~~~json
{
  "id": "C01",
  "name": "Lan",
  "tier": "GOLD"
}
~~~

Instead of sending the entire `Customer` node and doing redundant filtering in application code, you can use Cypher to return just the three required fields:

~~~cypher
MATCH (c:Customer {id: $customerId})
RETURN c {
  .id,
  .name,
  tier: CASE WHEN c.loyaltyPoints >= 100 THEN 'GOLD'
             ELSE 'STANDARD' END
} AS customer;
~~~

The returned result is **one `customer` column containing a map**, with keys `id`, `name`, and `tier`. The `internalNote` property does not appear because it was not selected. In this query, `c` remains an unchanged node in the graph; map projection only **constructs a return value** without modifying nodes or writing new data.

If `MATCH` finds no node with the given ID, the query returns **0 rows**. Handling the case where you want a row containing `null` is explained later.

## 2. Map Projection Syntax

General form:

~~~cypher
mapVariable {
  .propertyA,
  .propertyB,
  customKey: expression
}
~~~

Here, `mapVariable` is a **variable already bound** to a map, node, or relationship. The items inside the curly braces describe the keys to include in the resulting map.

Three common entry forms:

| Form | Example | Result |
| --- | --- | --- |
| **Property selector** | `c { .id, .name }` | Creates keys `id`, `name` from the corresponding properties |
| **Key–value entry** | `c { displayName: toUpper(c.name) }` | Creates key `displayName` with a value computed from the expression |
| **All-properties selector** | `c { .* }` | Copies all existing properties from the source object |

There is also a **variable selector** to include an in-scope variable under the same key name, such as `c { .id, orderCount }` when `orderCount` is already defined in query scope. For real-world APIs, the `key: expression` form is often clearest because it explicitly states the output key name.

### Self-Contained Example Without Graph Data

Map projection also works on a variable holding a **map literal**:

~~~cypher
WITH {
  id: 'C01',
  name: 'Lan',
  email: 'lan@example.test',
  loyaltyPoints: 180
} AS c
RETURN c {
  .id,
  .name,
  tier: CASE WHEN c.loyaltyPoints >= 100 THEN 'GOLD'
             ELSE 'STANDARD' END
} AS profile;
~~~

Result:

~~~text
profile = {
  id: 'C01',
  name: 'Lan',
  tier: 'GOLD'
}
~~~

This is a pure Cypher example: `c` is an in-query map, not yet a Neo4j node. When replaced with `MATCH (c:Customer)`, the projection syntax works the same way.

### How Do Map Projection and Map Literal Differ?

Both expressions below produce a map with keys `id` and `name`:

~~~cypher
WITH {id: 'C01', name: 'Lan'} AS c
RETURN
  {id: c.id, name: c.name} AS literalMap,
  c {.id, .name} AS projectedMap;
~~~

- **Map literal** `{id: c.id, name: c.name}` builds a map directly from expressions. No source map variable is required.
- **Map projection** `c {.id, .name}` attaches to variable `c` and concisely pulls properties with matching names. It is especially convenient when retaining many properties of a node.

Map literals fit when fields come from multiple sources without a single clear base object; map projections fit when you are shaping a "view" of an existing node, relationship, or map. Both produce **map values**, not nodes.

## 3. Selecting Fields and Naming to Match API Contracts

### Picking Only Needed Properties

~~~cypher
WITH {
  id: 'P01',
  sku: 'BOOK-001',
  title: 'Learning Neo4j',
  costPrice: 60000,
  salePrice: 100000,
  internalSupplierCode: 'SUP-09'
} AS p
RETURN p {.sku, .title, .salePrice} AS publicProduct;
~~~

The result contains `sku`, `title`, and `salePrice`. Fields like `costPrice` and `internalSupplierCode` are excluded from the new map.

### Renaming Fields

Property selectors keep the **original property names**. To rename fields in the output, use a `key: expression` entry:

~~~cypher
WITH {id: 'C01', name: 'Lan', loyaltyPoints: 180} AS c
RETURN c {
  customerId: c.id,
  displayName: c.name,
  points: c.loyaltyPoints
} AS customerView;
~~~

Output map:

~~~text
{
  customerId: 'C01',
  displayName: 'Lan',
  points: 180
}
~~~

For Java applications, explicit key naming keeps conversion into DTOs or JSON consistent. If a stored property is renamed, you only need `customerId: c.id`; you do not have to alter the schema of stored nodes.

### Mixing Properties and Computed Fields

~~~cypher
WITH {sku: 'P01', price: 100000, quantity: 3} AS line
RETURN line {
  .sku,
  .quantity,
  unitPrice: line.price,
  lineTotal: line.price * line.quantity
} AS orderLine;
~~~

The result is:

~~~text
{
  sku: 'P01',
  quantity: 3,
  unitPrice: 100000,
  lineTotal: 300000
}
~~~

The value `lineTotal` is computed only at query runtime; map projection does not write `lineTotal` onto nodes or relationships.

### Selecting All Properties with `.*`

~~~cypher
WITH {id: 'C01', name: 'Lan', email: 'lan@example.test'} AS c
RETURN c {.*} AS copiedProperties;
~~~

`.*` copies all existing properties/entries of the source variable into the result map. For a **node**, it extracts **node properties**, without automatically adding labels, internal IDs, or relationships. Other metadata, if needed, must be placed in computed fields:

~~~cypher
MATCH (c:Customer {id: $customerId})
RETURN c {
  .id,
  .name,
  labels: labels(c),
  graphElementId: elementId(c)
} AS debugView;
~~~

Here `labels(c)` and `elementId(c)` are computed into new keys. `elementId(c)` is useful for certain Neo4j-internal entity operations, but should not replace an application's **stable business ID** like `c.id` by default.

> For public APIs, prefer **explicitly listing the properties allowed in the response**. `c {.*}` can accidentally expose sensitive or operational fields as the schema evolves.

## 4. Variables, Scope, and Row Counts in a Pipeline

Map projection creates only a **value within the current row**. It does not aggregate multiple rows or alter row counts the way `UNWIND` or aggregation functions do.

~~~cypher
UNWIND [
  {id: 'C01', name: 'Lan'},
  {id: 'C02', name: 'Minh'}
] AS c
RETURN c {.id, .name} AS customer
ORDER BY customer.id;
~~~

The result has **two rows**, each containing a map in the `customer` column. If the application wants **one row containing a list of maps**, collect them:

~~~cypher
UNWIND [
  {id: 'C01', name: 'Lan'},
  {id: 'C02', name: 'Minh'}
] AS c
WITH c
ORDER BY c.id
RETURN collect(c {.id, .name}) AS customers;
~~~

The result has one row, with the `customers` column equal to:

~~~text
[
  {id: 'C01', name: 'Lan'},
  {id: 'C02', name: 'Minh'}
]
~~~

`ORDER BY` inside `WITH` defines the row order fed into `collect()` right afterward. Map projection defines the **columns and shape of each element**, while `collect()` changes the **grouping level** from multiple rows into a list.

### Aliasing a Variable Before Projecting

~~~cypher
MATCH (c:Customer)
WITH c AS customer
RETURN customer {.id, .name} AS profile;
~~~

After `WITH c AS customer`, the variable used in the projection is `customer`. If an intermediate `WITH` kept only `customer.id AS customerId`, the node variable `customer` would no longer be in scope for `customer { ... }`. Therefore, keep the base variable when you still need to select its properties in a later step.

### Expressions After the Colon Can Reference Other Variables

~~~cypher
WITH {id: 'O01', status: 'PAID'} AS o, 250000 AS calculatedTotal
RETURN o {
  .id,
  .status,
  total: calculatedTotal
} AS orderSummary;
~~~

The map projection pulls `id` and `status` from `o`, while the `total` field comes from `calculatedTotal`. This is how node data is combined with intermediate values calculated in a `WITH` step.

## 5. Building Nested Results for Customers and Orders

A property graph may have the following model:

~~~text
(:Customer {id, name})
       |
       +--[:PLACED]--> (:Order {id, status, createdAt, total})
                              |
                              +--[:CONTAINS {quantity}]--> (:Product {sku, name, price})
~~~

An API might want a customer object containing a **list of orders**:

~~~json
{
  "id": "C01",
  "name": "Lan",
  "orders": [
    {"id": "O01", "status": "PAID", "total": 250000},
    {"id": "O02", "status": "PENDING", "total": 100000}
  ]
}
~~~

### Step 1 — Project Each Order

~~~cypher
MATCH (c:Customer {id: $customerId})-[:PLACED]->(o:Order)
RETURN
  c.id AS customerId,
  o {.id, .status, .total} AS orderView
ORDER BY orderView.id;
~~~

Each order is a row; the `orderView` column is a map with exactly three keys. For a customer with two orders, the result has two rows, **not yet** the nested JSON object above.

### Step 2 — Collect the Projections into a List

~~~cypher
MATCH (c:Customer {id: $customerId})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, o
ORDER BY o.createdAt DESC, o.id ASC
WITH c, collect(o {.id, .status, .total}) AS orders
RETURN c {
  .id,
  .name,
  orders: orders
} AS customer;
~~~

Breakdown:

1. `MATCH` finds the customer by business ID.
2. `OPTIONAL MATCH` finds orders while keeping the customer in the pipeline if they have no orders yet.
3. `ORDER BY` sorts orders by creation timestamp descending and ID ascending for deterministic order.
4. `collect(o {.id, .status, .total})` gathers the order maps. When `o` is `null` because there are no orders, the map projection yields `null` and `collect()` skips `null`, resulting in `[]`.
5. `c {.id, .name, orders: orders}` creates the root map containing both customer info and the collected order list.

With the sample data, the output matches the JSON block above (assuming matching order and `createdAt` values). If the customer node exists without orders, `orders` is an empty list. If the customer **does not exist**, the initial `MATCH` returns 0 rows.

### Step 3 — Including Only a Subset of the List

~~~cypher
MATCH (c:Customer {id: $customerId})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, o
ORDER BY o.createdAt DESC, o.id ASC
WITH c, collect(o {.id, .status, .total}) AS allOrders
RETURN c {
  .id,
  .name,
  totalOrders: size(allOrders),
  recentOrders: allOrders[..3]
} AS customer;
~~~

`allOrders[..3]` returns at most the first three elements, while `size(allOrders)` still reflects the total number of orders. However, the query must **collect all orders before slicing**. For customers with very many orders, consider a subquery with `ORDER BY`/`LIMIT` to bound the orders fetched before `collect()`, and compute the total count separately if business logic needs both.

## 6. Combining Map Projection with List Comprehensions

Map projection can also be used inside a list comprehension, transforming **multiple input maps into a list of output maps** in a single expression.

### Input Data as a List of Maps

~~~cypher
WITH {
  id: 'O01',
  items: [
    {sku: 'P01', quantity: 2, unitPrice: 100000},
    {sku: 'P02', quantity: 1, unitPrice: 50000}
  ]
} AS orderData
RETURN orderData {
  .id,
  items: [
    item IN orderData.items
    | item {
        .sku,
        .quantity,
        lineTotal: item.quantity * item.unitPrice
      }
  ],
  total: reduce(
    sum = 0,
    item IN orderData.items |
    sum + item.quantity * item.unitPrice
  )
} AS orderView;
~~~

Expected result:

~~~text
{
  id: 'O01',
  items: [
    {sku: 'P01', quantity: 2, lineTotal: 200000},
    {sku: 'P02', quantity: 1, lineTotal: 50000}
  ],
  total: 250000
}
~~~

Here:

- The outer projection uses the `orderData` variable.
- The list comprehension iterates over `orderData.items` and creates a map for **each** `item`.
- The inner projection selects `sku`, `quantity`, and adds `lineTotal`.
- `reduce()` sums over the line items, returning `250000`.

This example does not require an `Order` node to exist in the graph. If `items` is an optional field that can be `null`, use `coalesce(orderData.items, [])` in both the comprehension and the summation after agreeing on the business rule for missing fields.

### Projecting Only Elements That Match a Condition

~~~cypher
WITH [
  {sku: 'P01', price: 120000, enabled: true},
  {sku: 'P02', price: 80000, enabled: false},
  {sku: 'P03', price: 150000, enabled: true}
] AS products
RETURN [
  p IN products
  WHERE p.enabled = true
  | p {
      .sku,
      .price,
      displayPrice: toString(p.price) + ' VND'
    }
] AS availableProducts;
~~~

The `availableProducts` list contains exactly two maps, for `P01` and `P03`. `WHERE` **inside the comprehension** filters list elements; it does not drop the outer query row. Thus, the API can still return `availableProducts: []` when no products match.

## 7. Nodes, Relationships, and Non-Property Data

### Projecting a Node

~~~cypher
MATCH (p:Product {sku: $sku})
RETURN p {
  .sku,
  .name,
  .price,
  isAvailable: coalesce(p.stock, 0) > 0
} AS product;
~~~

The `isAvailable` field is derived from the `stock` property. If the property is missing or `null`, `coalesce(p.stock, 0)` defaults it to 0 as defined by the example.

### Projecting a Relationship

A relationship can store properties such as `quantity` or `createdAt`. You can project from a relationship variable just like from a node:

~~~cypher
MATCH (o:Order {id: $orderId})-[line:CONTAINS]->(p:Product)
RETURN line {
  .quantity,
  productSku: p.sku,
  productName: p.name,
  lineTotal: line.quantity * p.price,
  relationshipType: type(line)
} AS orderLine
ORDER BY orderLine.productSku;
~~~

`line` is the relationship; `.quantity` takes the relationship property; `productSku` and `productName` read properties from node `p`; `type(line)` returns the relationship type name. This statement produces a map for each order line item without returning the full `p` node or `line` relationship directly.

### Projecting a Path into a List of Names

~~~cypher
MATCH path = (start:Person {id: $personId})-[:KNOWS*1..3]->(target:Person)
WITH nodes(path) AS pathNodes
RETURN [
  n IN pathNodes
  | n {.id, .name}
] AS peopleOnPath;
~~~

`nodes(path)` produces a list of nodes in path order; the comprehension creates a list of `{id, name}` maps. If multiple paths are found, the query returns **one row per path** rather than automatically merging paths into a single list.

## 8. `null`, Missing Properties, and Data Shape

Map projection follows Cypher's value rules; distinguish between a **null source map**, a **missing property**, and an **expression returning null**.

### Property Missing on a Node or Map

~~~cypher
WITH {id: 'C01', name: 'Lan'} AS c
RETURN c {
  .id,
  .name,
  .phone,
  phoneOrDefault: coalesce(c.phone, 'Not updated')
} AS customer;
~~~

The resulting map contains key `phone` with value `null` and key `phoneOrDefault` with value `'Not updated'`. Selecting a nonexistent property does not automatically turn it into an empty string.

### Source Map Is `null`

~~~cypher
OPTIONAL MATCH (c:Customer {id: $customerId})
RETURN c {.id, .name} AS customer;
~~~

Because `OPTIONAL MATCH` preserves a row when no node is found, `c` is `null` in that case; **the map projection of `c` is also `null`**. Compare this with:

~~~cypher
MATCH (c:Customer {id: $customerId})
RETURN c {.id, .name} AS customer;
~~~

A regular `MATCH` that finds no customer returns **0 rows**, so the application must distinguish between these two API contracts.

### A Projection Containing `null` Fields Is Still a Map

~~~cypher
WITH {id: 'C01', email: null} AS c
RETURN c {.id, .email, emailVerified: false} AS profile;
~~~

The result is a map containing `id`, `email: null`, and `emailVerified: false`. Completely omitting `null` keys from JSON is a choice for the serialization/conversion layer or another map-construction pattern; basic map projection has no "strip all null keys" option.

### Do Not Confuse a Map with JSON

What Cypher returns to the driver is a **map value**. The Java Driver receives typed values; when the application serializes to JSON, how dates, times, numbers, nodes, or `null` values are represented also depends on the serialization library and API contract. Having map projection produce the right keys addresses only the **logical shape** of the returned data.

## 9. Java Driver and Spring Data Neo4j

A major benefit of map projection is reducing unnecessary data read or processed by the application. With the Neo4j Java Driver, you can run a parameterized query and map the returned map column.

Java Driver example:

~~~java
String cypher = """
    MATCH (c:Customer {id: $customerId})
    RETURN c {
      .id,
      .name,
      tier: CASE WHEN c.loyaltyPoints >= 100
                 THEN 'GOLD' ELSE 'STANDARD' END
    } AS profile
    """;

try (Session session = driver.session()) {
    List<Map<String, Object>> profiles = session.executeRead(tx ->
        tx.run(cypher, Values.parameters("customerId", "C01"))
          .list(record -> record.get("profile").asMap())
    );

    // Convert profiles to DTO/JSON according to the API contract.
}
~~~

This snippet assumes `driver` is an already-initialized and lifecycle-managed `org.neo4j.driver.Driver` instance. Common types used include `org.neo4j.driver.Session`, `org.neo4j.driver.Values`, `java.util.List`, and `java.util.Map`. The application decides whether to return a single result, a list of results, or handle the not-found case.

If you want to access fields directly from a returned map column in Java:

~~~java
Map<String, Object> profile = record.get("profile").asMap();
Object customerId = profile.get("id");
Object customerName = profile.get("name");
~~~

Nested fields may require further mapping and type checks. Keeping the key names returned by Cypher consistent helps minimize unnecessary transformation code.

With **Spring Data Neo4j**, you can use custom queries to return fields backing a DTO or repository projection. However, **Cypher map projection does not automatically guarantee mapping to an arbitrary Java entity or DTO**. Mapping behavior depends on the return type, library version, and converter/repository configuration. For complex API contracts, verify the mapping carefully, or use the Java Driver to directly control Cypher map columns.

Two reminders:

- **Parameterization**: use `$customerId`, `$sku`, and other query parameters instead of concatenating user-supplied values into Cypher strings.
- **Output control**: explicitly select only needed properties, define optional fields clearly, and avoid relying on `.*` in APIs when internal data exists.

## 10. Accuracy and Performance When Building Responses

Map projection keeps results clean, but it does not replace query design and optimization.

| Risk | Symptom | Mitigation |
| --- | --- | --- |
| Returning too much data | `node {.*}` outputs every property, including unnecessary ones | Explicitly list allowed fields |
| Duplicate orders in list | `MATCH` traverses multiple relationships and produces multiple rows for the same `Order` | Check what each row represents; group by order or use `DISTINCT` appropriately before `collect()` |
| Unstable list order | `collect()` receives unsorted rows | Place `ORDER BY` right before the `collect()` step |
| Only need 10 items but collected thousands | `collect()` everything first, then slice `[..10]` | Limit input early with `ORDER BY`/`LIMIT` or a subquery when appropriate |
| Wrong API shape when node is missing | `MATCH` returns 0 rows; `OPTIONAL MATCH` may return a row with `null` | Define the response contract, distinguishing "not found" from "no relationships" |
| Confusing map projection with persistence | Looks like a new object, but the graph is unchanged | Use `CREATE`/`MERGE`/`SET` when business logic needs to write |
| Mistaking internal ID for business ID | Using `elementId(node)` as a long-term application identifier | Maintain a business key property with an appropriate constraint |
| Java mapping behaves unexpectedly | Query returns map/nested list while repository expects an entity | Check return types, converters, and mapping; use Driver when direct control is needed |

When optimizing queries, inspect the plan with `EXPLAIN` and actual row counts with `PROFILE` on test data. Cost can arise from relationship expansions, collecting large lists, or node lookups lacking appropriate indexes/constraints; the `c {.id, .name}` syntax itself does not automatically eliminate upstream data-access cost.

### Check Multiplicity and Grouping Before Projecting

For example, if an order has multiple line items, the following query can produce multiple rows for the same order:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
RETURN c {.id, .name} AS customer, o {.id, .status} AS order;
~~~

A customer with order `O01` containing two products will yield two rows with the same `order` map. If the API needs **each order once**, design the query to deduplicate orders before projecting or before collecting into a list:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
WITH DISTINCT c, o
WITH c, collect(o {.id, .status}) AS orders
RETURN c {.id, .name, orders: orders} AS customer;
~~~

`WITH DISTINCT c, o` removes duplicate customer–order pairs. `collect()` then builds the list once per pair. This example query considers only orders that have at least one product because it uses `MATCH` across `CONTAINS`; if empty orders must also be included, adjust the graph pattern to match business requirements.

## 11. Practice Exercises

### Exercise 1 — Project Exactly Three Fields

Given the map:

~~~cypher
WITH {
  id: 'C07',
  name: 'Hà',
  email: 'ha@example.test',
  points: 75,
  privateMemo: 'Internal'
} AS customer
RETURN customer {
  .id,
  .name,
  memberTier: CASE WHEN customer.points >= 100
                   THEN 'GOLD' ELSE 'STANDARD' END
} AS publicProfile;
~~~

Predict which fields appear. The result contains only `id = 'C07'`, `name = 'Hà'`, and `memberTier = 'STANDARD'`. `email` and `privateMemo` are absent from the output.

### Exercise 2 — List of Eligible Products

Create a list of product maps containing only `sku` and `price`, filtering for active products priced at least 100,000:

~~~cypher
WITH [
  {sku: 'P01', price: 120000, enabled: true},
  {sku: 'P02', price: 90000, enabled: true},
  {sku: 'P03', price: 200000, enabled: false},
  {sku: 'P04', price: 150000, enabled: true}
] AS products
RETURN [
  p IN products
  WHERE p.enabled = true AND p.price >= 100000
  | p {.sku, .price}
] AS result;
~~~

Expected result:

~~~text
[
  {sku: 'P01', price: 120000},
  {sku: 'P04', price: 150000}
]
~~~

### Exercise 3 — Customer with an Order List

Task: on the `Customer-[:PLACED]->Order` graph, return a `customer` map containing `id`, `name`, and an `orders` list. For each order, return only `id`, `status`, and total amount. Customers without orders must still appear with `orders: []`.

~~~cypher
MATCH (c:Customer {id: $customerId})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, o
ORDER BY o.id
WITH c, collect(o {.id, .status, .total}) AS orders
RETURN c {.id, .name, orders: orders} AS customer;
~~~

To clarify the output, suppose customer `C01` has paid order `O01` with total `250000` and pending order `O02` with total `100000`. The returned map looks like:

~~~text
{
  id: 'C01',
  name: 'Lan',
  orders: [
    {id: 'O01', status: 'PAID', total: 250000},
    {id: 'O02', status: 'PENDING', total: 100000}
  ]
}
~~~

When the Neo4j data differs from the example, the output changes according to the nodes and relationships actually present in the graph.

### Self-Check Questions

1. Does `c {.id, .name}` create a new `c` node or a map? **Creates a map**; the graph does not change.
2. Does `c {.*}` automatically include labels and relationships in the response? **No**; it selects properties of the source object.
3. If `OPTIONAL MATCH` does not find `c`, what does `c {.id}` evaluate to? **`null`**, because the source variable is `null`.
4. Does projecting within a row automatically group orders into a list? **No**; you need `collect()` or an appropriate list expression.
5. When an API needs to return `orders: []` for an existing customer who has no orders yet, which pattern should you use? **`MATCH` the customer, `OPTIONAL MATCH` the orders, `collect()` the projections**, and include the `orders` field in the customer projection.

## Key Takeaway

**Map projection** lets you design the **shape of returned data** directly in Cypher:

~~~cypher
variable { .property, renamedKey: expression, nested: anotherList }
~~~

It builds maps from existing nodes, relationships, or maps without writing new data to Neo4j. Combine it with `WITH`, `collect()`, `UNWIND`, and list comprehensions to control variable scope, row counts, and nested lists. In Java applications, explicitly selecting fields, defining `null` semantics clearly, and verifying mapping behavior helps build reliable and maintainable APIs.
