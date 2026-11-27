# Projection: Field Inclusion, Exclusion, and Handling `_id`

In MongoDB, a document can hold many fields: identifiers, names, prices, stock levels, descriptions, images, change history, and nested objects. However, each UI screen or API endpoint usually needs only a subset of that data. **Projection** lets you choose which fields appear in query results, avoiding returning the entire document when the client needs only a few attributes.

Example product document:

```javascript
{
  _id: "P001",
  sku: "KB-001",
  name: "Mechanical Keyboard",
  category: "keyboard",
  price: NumberDecimal("1250000.00"),
  stock: 28,
  description: "Mechanical keyboard for office and programming use.",
  specifications: {
    switch: "brown",
    layout: "75%",
    wireless: true
  },
  tags: ["mechanical", "wireless", "compact"],
  supplier: { company: "ABC Supplies", phone: "0123456789" },
  createdAt: ISODate("2026-01-05T08:00:00Z")
}
```

A product listing API needs only the name and price:

```javascript
db.products.find(
  { category: "keyboard" },
  { name: 1, price: 1, _id: 0 }
);
```

The result contains only `name` and `price`. The **filter** `{ category: "keyboard" }` decides which documents are retrieved; the **projection** decides which fields are returned.

## 1. Projection Syntax in Queries

In `mongosh`:

```javascript
db.collection.find(query, projection);
db.collection.findOne(query, projection);
```

Where:

- `query`: filter selecting documents; for example `{ status: "ACTIVE" }`, or `{}` to select all.
- `projection`: object describing fields to include in or exclude from the result.
- Value `1` (or `true`) means **include**.
- Value `0` (or `false`) means **exclude**.
- The `_id` field is **included by default**, even when the projection specifies only a few other fields.

Examples:

```javascript
// No projection: all fields.
db.products.find({ category: "keyboard" });

// With projection: name, price, and _id by default.
db.products.find(
  { category: "keyboard" },
  { name: 1, price: 1 }
);

// Exclude _id, keeping only name and price.
db.products.find(
  { category: "keyboard" },
  { name: 1, price: 1, _id: 0 }
);
```

Projection can be combined with filter, sort, and limit:

```javascript
db.products.find(
  { category: "keyboard", stock: { $gt: 0 } },
  { _id: 0, sku: 1, name: 1, price: 1 }
).sort({ price: 1 }).limit(20);
```

Meaning: filter keyboards in stock, return only SKU/name/price, sort by price ascending, and limit to 20 documents. The `stock` field appears in the filter, yet **does not have to appear in the returned result**.

## 2. Inclusion Projection: Selecting Only the Fields You Need

When fields are specified with `1`, MongoDB returns only those fields, plus `_id` unless excluded:

```javascript
db.products.find(
  { category: "keyboard" },
  { name: 1, price: 1 }
);
```

One result:

```javascript
{
  _id: "P001",
  name: "Mechanical Keyboard",
  price: NumberDecimal("1250000.00")
}
```

Fields such as `description`, `specifications`, and `supplier` do not appear. MongoDB leaves the original document untouched in the collection.

### 2.1. Returning Only a Single Field

```javascript
db.products.find({}, { name: 1, _id: 0 });
```

Illustrative output:

```javascript
{ name: "Mechanical Keyboard" }
{ name: "Wireless Mouse" }
{ name: "Monitor" }
```

Projection still returns **one result document per document matching the filter**. If your goal is to retrieve **distinct** values of a field, use `distinct("category")` or aggregation instead of assuming projection deduplicates values.

### 2.2. Returning Only `_id`

```javascript
db.products.find(
  { stock: { $gt: 0 } },
  { _id: 1 }
);
```

The result contains only `_id`. Even though the filter uses `stock`, it does not need to be returned.

### 2.3. Non-Existent Fields

```javascript
db.projectionLab.insertMany([
  { _id: "A", name: "Product A", color: "black" },
  { _id: "B", name: "Product B" }
]);

db.projectionLab.find(
  {},
  { _id: 1, name: 1, color: 1 }
).sort({ _id: 1 });
```

Returned data:

```javascript
{ _id: "A", name: "Product A", color: "black" }
{ _id: "B", name: "Product B" }
```

MongoDB does not synthesize `color: null` for document B just because the projection requested that field. A **missing field** and a **field with value null** are two different data states. If an API requires a field to always be present, normalize the schema or supply a default value in the application or aggregation.

## 3. Exclusion Projection: Omitting Fields You Do Not Want Returned

When using `0`, MongoDB excludes the specified fields and returns everything else:

```javascript
db.products.find(
  { category: "keyboard" },
  { description: 0, supplier: 0 }
);
```

The result still includes `_id`, `sku`, `name`, `price`, `stock`, `tags`, and all remaining fields.

### 3.1. Excluding Only `_id`

```javascript
db.products.find({}, { _id: 0 });
```

This command returns **every field except `_id`**, unlike:

```javascript
db.products.find({}, { _id: 1 });
```

The latter returns only `_id`.

### 3.2. When to Be Cautious with Exclusion

Suppose:

```javascript
db.users.find(
  { status: "ACTIVE" },
  { passwordHash: 0, recoveryCodes: 0 }
);
```

If the schema later adds `apiSecret`, an exclusion projection listing only the two old fields can **accidentally expose** the new field. Public APIs should usually use inclusion (a field allowlist) and DTOs to declare permitted fields explicitly. Projection controls only **the shape of the current query result**; it does not replace database permissions, security rules, or application-layer validation.

## 4. Do Not Mix Inclusion and Exclusion, Except for `_id`

An important rule for standard projections in `find()`:

> Do not combine fields included with `1` and other fields excluded with `0`, **except for the special field `_id`**.

Invalid example:

```javascript
db.products.find(
  {},
  { name: 1, price: 1, description: 0 }
);
```

Valid examples:

```javascript
// Inclusion: _id is returned by default.
db.products.find({}, { name: 1, price: 1 });

// Inclusion with the _id exception.
db.products.find({}, { name: 1, price: 1, _id: 0 });

// Exclusion of unnecessary fields.
db.products.find({}, { description: 0, supplier: 0 });

// Exclusion including _id.
db.products.find({}, { description: 0, _id: 0 });

// Return only _id.
db.products.find({}, { _id: 1 });
```

| Projection | Meaning |
|---|---|
| `{}` | Return all fields as default |
| `{ name: 1 }` | Only `name` and `_id` |
| `{ name: 1, _id: 0 }` | Only `name` |
| `{ price: 0 }` | All fields except `price` |
| `{ price: 0, _id: 0 }` | All fields except `price` and `_id` |
| `{ _id: 0 }` | All fields except `_id` |
| `{ _id: 1 }` | Only `_id` |
| `{ name: 1, price: 0 }` | Error: mixing inclusion and exclusion |

Specialized projection operators and projection expressions in supported versions have their own rules. That **does not** allow arbitrarily mixing `1` and `0` on ordinary fields.

## 5. Projecting Nested Fields with Dot Notation

MongoDB allows selecting fields inside **embedded documents**:

```javascript
{
  _id: "P001",
  name: "Mechanical Keyboard",
  specifications: {
    layout: "75%",
    switch: "brown",
    wireless: true,
    connection: {
      bluetooth: true,
      usbC: true
    }
  }
}
```

Retrieve only name, layout, and Bluetooth status:

```javascript
db.products.find(
  { _id: "P001" },
  {
    _id: 0,
    name: 1,
    "specifications.layout": 1,
    "specifications.connection.bluetooth": 1
  }
);
```

Result shape:

```javascript
{
  name: "Mechanical Keyboard",
  specifications: {
    layout: "75%",
    connection: {
      bluetooth: true
    }
  }
}
```

Dotted names in a projection specify **paths**; they do not turn the output into flat keys containing literal dots. Objects are reconstructed in their nested structure.

### 5.1. Excluding a Child Field

```javascript
db.products.find(
  { _id: "P001" },
  { "specifications.connection.usbC": 0 }
);
```

The result keeps other fields while excluding the `usbC` path. When a field does not exist in a document, there is nothing to return or omit at that path.

### 5.2. Avoiding Path Collisions

Do not select both an entire parent object and one of its children with overlapping paths:

```javascript
// Prone to path collision.
db.products.find(
  {},
  { specifications: 1, "specifications.layout": 1 }
);
```

Choose `specifications: 1` if you want the entire object, or only `"specifications.layout": 1` if you want the subset. Changing key declaration order is not a valid way to resolve a path collision.

### 5.3. Projection Does Not Modify Source Data

```javascript
db.products.findOne(
  { _id: "P001" },
  { "specifications.layout": 1, _id: 0 }
);
```

This command selects fields only in the **read result**. The `switch` and `wireless` fields still exist in the collection. To actually delete a field, you must use an update operation such as `$unset`.

## 6. Projection and Arrays

Suppose an order document is:

```javascript
{
  _id: "ORD-1001",
  customerId: "C001",
  status: "PAID",
  items: [
    { sku: "BK-01", quantity: 2, price: 50000 },
    { sku: "PN-02", quantity: 1, price: 25000 },
    { sku: "KB-03", quantity: 1, price: 450000 }
  ],
  history: [
    { status: "CREATED", at: ISODate("2026-03-01T10:00:00Z") },
    { status: "PAID", at: ISODate("2026-03-01T10:05:00Z") },
    { status: "SHIPPED", at: ISODate("2026-03-02T08:00:00Z") }
  ]
}
```

Selecting `items: 1` returns **the entire array** without automatically limiting element count:

```javascript
db.orders.find(
  { _id: "ORD-1001" },
  { _id: 0, items: 1 }
);
```

### 6.1. Selecting Fields Inside Each Array Element

```javascript
db.orders.find(
  { _id: "ORD-1001" },
  { _id: 0, "items.sku": 1, "items.quantity": 1 }
);
```

Result:

```javascript
{
  items: [
    { sku: "BK-01", quantity: 2 },
    { sku: "PN-02", quantity: 1 },
    { sku: "KB-03", quantity: 1 }
  ]
}
```

Dot notation selects which fields to return for each element. It **does not filter out** array elements by price or SKU.

### 6.2. Slicing an Array with `$slice`

The `$slice` projection operator limits the number of array elements **returned**:

```javascript
// First two elements of history.
db.orders.find(
  { _id: "ORD-1001" },
  { history: { $slice: 2 }, _id: 0 }
);

// Last two elements.
db.orders.find(
  { _id: "ORD-1001" },
  { history: { $slice: -2 }, _id: 0 }
);

// Skip 1 element, take the next 2 elements.
db.orders.find(
  { _id: "ORD-1001" },
  { history: { $slice: [1, 2] }, _id: 0 }
);
```

`$slice` in a read projection differs from the `$slice` modifier combined with `$push` in write operations. A read command only trims the returned array in the output; **it does not truncate the array stored in the database**. If an array grows without bound, change the data model (such as moving items to a separate child collection) rather than merely adding `$slice` on read.

`$slice` also does not sort the array: "last two elements" depends on the existing order stored in the array.

### 6.3. `$elemMatch` Projection: Returning the First Matching Element

```javascript
db.orders.find(
  { _id: "ORD-1001" },
  {
    _id: 0,
    items: { $elemMatch: { sku: "PN-02" } }
  }
);
```

Result:

```javascript
{
  items: [
    { sku: "PN-02", quantity: 1, price: 25000 }
  ]
}
```

In the **projection** context, `$elemMatch` returns at most **the first matching element** in the array. Distinguish this from `$elemMatch` in a query filter:

```javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "PN-02",
      quantity: { $gte: 1 }
    }
  }
});
```

The filter selects documents having at least one item satisfying multiple conditions on the same element. The projection selects which element is returned. If you want **every item** matching a condition, use aggregation `$filter`.

### 6.4. Positional Projection `$`

When a query matches an array element, certain cases allow positional projection to return **the first matching element**:

```javascript
db.orders.find(
  { "items.sku": "PN-02" },
  { "items.$": 1, _id: 0 }
);
```

This operator has limitations regarding arrays in the query and projection; for complex queries or multiple arrays, check the rules for your MongoDB version. Do not confuse positional projection in read queries with the positional update operator used to modify data.

## 7. Projection in Aggregation: `$project` and Transformations

The `$project` stage in aggregation lets you select fields and **compute new fields**:

```javascript
db.products.aggregate([
  { $match: { category: "keyboard" } },
  {
    $project: {
      _id: 0,
      sku: 1,
      name: 1,
      price: 1,
      displayName: {
        $concat: ["$sku", " - ", "$name"]
      }
    }
  }
]);
```

Besides `sku`, `name`, and `price`, the output includes `displayName`, constructed from two fields. It is **not saved** back to the collection.

Example line-item total:

```javascript
db.orderLines.aggregate([
  {
    $project: {
      _id: 0,
      orderId: 1,
      sku: 1,
      quantity: 1,
      unitPrice: 1,
      lineTotal: {
        $multiply: ["$quantity", "$unitPrice"]
      }
    }
  }
]);
```

### 7.1. Filtering All Array Elements with `$filter`

```javascript
db.orders.aggregate([
  { $match: { _id: "ORD-1001" } },
  {
    $project: {
      _id: 0,
      customerId: 1,
      expensiveItems: {
        $filter: {
          input: "$items",
          as: "item",
          cond: { $gte: ["$$item.price", 50000] }
        }
      }
    }
  }
]);
```

`$filter` keeps **every element** satisfying the expression, unlike `$elemMatch` projection which returns at most one element. For missing or `null` arrays, check `$filter` handling rules and consider `$ifNull` if the application expects an empty array.

### 7.2. Values `0` and `1` Are Projection Flags, Not Literals

In `$project`, `0` means exclude and `1` means include. To **produce the numeric value 0**, use `$literal`:

```javascript
db.orderLines.aggregate([
  {
    $project: {
      _id: 0,
      sku: 1,
      initialDiscount: { $literal: 0 }
    }
  }
]);
```

If you write `initialDiscount: 0`, MongoDB treats it as excluding the field rather than setting the number `0`. A standard `$project` stage also prohibits arbitrarily mixing inclusion and exclusion apart from `_id`; computed fields are allowed alongside inclusion under specific rules.

### 7.3. Dropping Fields with `$unset` in Aggregation

```javascript
db.products.aggregate([
  { $unset: ["description", "supplier"] }
]);
```

This is a stage operating on **the pipeline output stream**, not an update command removing fields from stored documents. You can use an equivalent `$project` exclusion when appropriate:

```javascript
db.products.aggregate([
  {
    $project: {
      description: 0,
      supplier: 0,
      _id: 0
    }
  }
]);
```

Some MongoDB versions also support aggregation expressions inside `find()` projections. However, when multiple calculations, complex array filtering, and structural reshaping are required, aggregation usually expresses intent more clearly.

## 8. Projection and Performance: What Does It Save?

Projection generally provides the following benefits:

- **Fewer bytes transferred over the network** because returned documents have fewer fields.
- **Lower client-side processing overhead** by avoiding decoding/deserializing unused fields.
- **Potential covered queries** when both the filter and projected fields are served by an appropriate index.

However, projection **does not guarantee fewer documents read from the storage engine**. If the query plan includes a `FETCH` stage, MongoDB still must read the document to retrieve fields outside the index. A small response does not automatically imply low disk I/O.

### 8.1. Covered Query: Index Only

Create an index:

```javascript
db.products.createIndex({
  category: 1,
  name: 1
});
```

Query:

```javascript
db.products.find(
  { category: "keyboard" },
  { name: 1, _id: 0 }
);
```

This can be served purely from the index because:

1. `category` is the filter field.
2. `name` is the returned field.
3. `_id` is explicitly excluded, so fetching the ID from the document is unnecessary.
4. The index contains all values needed by the filter and projection.

If `_id` is not excluded:

```javascript
db.products.find(
  { category: "keyboard" },
  { name: 1 }
);
```

MongoDB includes `_id` by default. The secondary index `{ category: 1, name: 1 }` does not store the document's `_id` as an index key field available for direct return, so the query may have to `FETCH` unless another suitable plan or index exists.

This example shows how **handling `_id` affects both the response shape and index-covering capability**.

### 8.2. Inspecting with `explain`

```javascript
db.products.find(
  { category: "keyboard" },
  { name: 1, _id: 0 }
).explain("executionStats");
```

Key metrics:

| Component | Meaning |
|---|---|
| `winningPlan` | Execution plan chosen by the query planner |
| `IXSCAN` | Index scan |
| `FETCH` | Document lookup required outside the index |
| `COLLSCAN` | Full collection scan instead of relying solely on an index |
| `totalKeysExamined` | Number of index keys examined |
| `totalDocsExamined` | Number of documents examined |
| `nReturned` | Number of documents returned |
| `executionTimeMillis` | Execution time recorded in explain output |

With a valid covered query, `totalDocsExamined` is typically `0`. Seeing `IXSCAN` alone **is not enough**: the plan may contain both `IXSCAN` and `FETCH`. Stage names and output formatting may vary by query engine and MongoDB version.

### 8.3. Indexing Across Filter, Sort, and Projection

Example endpoint:

```javascript
db.products.find(
  { category: "keyboard", stock: { $gt: 0 } },
  { sku: 1, name: 1, price: 1, _id: 0 }
).sort({ price: 1 }).limit(20);
```

Indexes should be evaluated across the `category`/`stock` filter, the `price` sort, and returned fields. Adding very wide indexes with many fields may help certain queries, but it also increases storage size and insert/update overhead. Do not create indexes blindly from the list of displayed columns.

Multikey indexes have restrictions on covering array fields; incompatible collations or complex projection expressions can also force document fetches. Always measure against realistic data and workloads.

## 9. Projection vs. Filter, Sort, Limit, and Update

| Purpose | What MongoDB uses |
|---|---|
| Choose **which documents** | Filter in `find(query, ...)` |
| Choose **which fields** | Projection in `find(..., projection)` |
| Order documents | `sort()` |
| Cap number of documents | `limit()` |
| Skip documents | `skip()` or keyset pagination |
| Filter part of an array to return | `$elemMatch`, `$slice` projection, or aggregation `$filter` |
| Modify stored fields | Update, e.g. `$set`, `$unset` |
| Cap stored array size on write | `$push` + `$slice` modifier |

Example:

```javascript
db.orders.find(
  { status: "PAID" },
  { customerId: 1, status: 1, createdAt: 1, _id: 0 }
).sort({ createdAt: -1 }).limit(20);
```

Four independent tasks: filter paid orders; choose fields; sort by time; take at most 20 records. Projection **does not** sort results and does not guarantee `find()` returns documents in field order or insertion order.

When stable pagination is needed, sort by sufficiently unique keys (such as adding `_id` as a tie-breaker) and include the necessary sort keys in the cursor token or response.

## 10. Projection in Java and Spring Data MongoDB

When a Java application queries MongoDB, you can use the driver's projection API or Spring Data MongoDB.

### 10.1. MongoDB Java Sync Driver

Example:

```java
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Projections.fields;
import static com.mongodb.client.model.Projections.include;
import static com.mongodb.client.model.Projections.excludeId;

MongoCollection<Document> products =
    database.getCollection("products");

for (Document product : products
        .find(eq("category", "keyboard"))
        .projection(fields(include("name", "price"), excludeId()))) {
    System.out.println(product.toJson());
}
```

`include("name", "price")` selects the two fields, and `excludeId()` omits `_id`. Without calling `excludeId()`, MongoDB returns `_id` by default alongside included fields.

### 10.2. Spring Data MongoDB with MongoTemplate

```java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = new Query(
    Criteria.where("category").is("keyboard")
);

query.fields()
     .include("name")
     .include("price")
     .exclude("_id");

List<Product> products =
    mongoTemplate.find(query, Product.class);
```

When only a subset of fields is loaded, the Java entity may hold `null` or default values for unprojected fields depending on field types and mapping. Therefore, passing such a partial entity back to **replace or save the whole document** is dangerous if the code cannot distinguish unloaded fields from explicit `null` values.

For read-only APIs needing just a few attributes, use a DTO or dedicated repository projection:

```java
public record ProductCard(String name, java.math.BigDecimal price) {}
```

Spring Data MongoDB offers multiple repository projection and mapping mechanisms; exact declarations depend on library version, but the goal remains separating a **read model** from write entities when loading partial data.

### 10.3. Distinguishing `_id` in MongoDB from `id` in Java

MongoDB's field name is `_id`. Java entities commonly use a property named `id` (often annotated with `@Id`) mapped to `_id`. Even when the Java property is named `id`, MongoDB's projection rule remains unchanged: `_id` is returned by default when other fields are included, and must be excluded explicitly if not wanted.

## 11. Designing Projections for Real-World Endpoints

Suppose an e-commerce system has three views:

### 11.1. Product Listing

The listing needs name, price, thumbnail URL, and ID to open the detail page:

```javascript
db.products.find(
  { status: "PUBLISHED" },
  { _id: 1, name: 1, price: 1, thumbnailUrl: 1 }
).sort({ createdAt: -1, _id: -1 }).limit(20);
```

`createdAt` is used in sorting and is not strictly required in the response; however, if the API uses cursor pagination, that sort key may need to be encoded in the pagination token.

### 11.2. Product Detail Page

```javascript
db.products.findOne(
  { _id: productId, status: "PUBLISHED" },
  {
    _id: 1,
    name: 1,
    price: 1,
    description: 1,
    specifications: 1,
    images: 1
  }
);
```

Internal supplier details and operations-only fields do not need to be returned.

### 11.3. Inventory Management Page

```javascript
db.products.find(
  {},
  {
    _id: 0,
    sku: 1,
    name: 1,
    price: 1,
    stock: 1,
    updatedAt: 1
  }
).sort({ sku: 1 }).limit(50);
```

The same collection can serve multiple APIs with distinct projections. Each endpoint should design its filter, sort, and indexes around its access pattern rather than sharing one catch-all projection containing every field across all screens.

## 12. Misconceptions to Avoid

| Misconception | Accurate understanding |
|---|---|
| `{ name: 1 }` returns only `name` | `_id` is still included by default |
| `{ _id: 0 }` returns no fields | Returns every field except `_id` |
| You can mix `name: 1` and `price: 0` | Standard projection forbids mixing except for `_id` |
| Projection removes fields from the database | Affects only read results; does not modify stored data |
| Selecting `items: 1` returns one item | Returns the entire `items` array |
| `$elemMatch` returns all matching elements | This projection operator returns at most the first matching element |
| `$slice` projection shrinks documents in the DB | Slices only the returned array; does not alter stored documents |
| Projection always reduces disk I/O | The query may still need to `FETCH` documents |
| A plan with `IXSCAN` is guaranteed covered | There may still be a `FETCH` stage |
| Excluding secret fields secures the API by itself | Access control, allowlists, and response validation are still required |
| A partial Java entity can be saved like a full entity | Unloaded fields can be lost or overwritten |
| Picking fields in projection controls sort order | Sorting is handled independently via `sort()` |

## 13. Practice Exercises

### Exercise 1 — Inclusion, Exclusion, and `_id`

Insert data:

```javascript
db.employees.insertMany([
  {
    _id: "E01",
    name: "An",
    department: "Engineering",
    salary: 25000000,
    email: "an@example.com",
    address: { city: "Hà Nội", street: "Street A" }
  },
  {
    _id: "E02",
    name: "Bình",
    department: "Sales",
    salary: 18000000,
    email: "binh@example.com"
  }
]);
```

Write queries to:
1. Return only `name` and `department`, without `_id`.
2. Return all fields except `salary` and `email`.
3. Return only `_id` for employees in Engineering.
4. Return only `name` and `address.city`, and observe what happens when a document lacks `address`.

### Exercise 2 — Spot the Projection Errors

Evaluate:

```javascript
db.employees.find({}, { name: 1, salary: 0 });
db.employees.find({}, { name: 1, _id: 0 });
db.employees.find({}, { _id: 0 });
db.employees.find({}, { address: 1, "address.city": 1 });
```

Which statements are valid? Which fail due to mode mixing or path collision? Compare `{ _id: 0 }` with `{ _id: 1 }`.

### Exercise 3 — Array Projection

Using the `orders` document from Section 6:
1. Retrieve only `items.sku` and `items.quantity`.
2. Return the last two elements of `history`.
3. Use `$elemMatch` projection to retrieve the single item with `sku: "PN-02"`.
4. Use aggregation `$filter` to retrieve all items with `price >= 50000`.
5. Explain why `$slice` in a read query does not reduce BSON size stored in the collection.

### Exercise 4 — Covered Query

Create index `{ category: 1, name: 1 }` and compare:

```javascript
db.products.find(
  { category: "keyboard" },
  { name: 1 }
).explain("executionStats");

db.products.find(
  { category: "keyboard" },
  { name: 1, _id: 0 }
).explain("executionStats");
```

Predict the impact of default `_id`. Inspect `totalDocsExamined` and whether a `FETCH` stage appears. If the planner chooses a different plan on a tiny collection, analyze it against realistic dataset statistics.

### Exercise 5 — Projection for a Public API

A `users` collection contains `_id`, `displayName`, `avatarUrl`, `email`, `passwordHash`, `recoveryCodes`, and `role`. Design projections for a public profile and an admin profile. Explain why an exclusion like `{ passwordHash: 0, recoveryCodes: 0 }` can accidentally expose newly added sensitive fields and what additional controls the API should enforce.

## Conclusion

**Projection** selects which fields appear in **query results** without modifying stored documents. With `find()` or `findOne()`, use `1` to **include** and `0` to **exclude**, and never mix the two modes for ordinary fields other than `_id`. **`_id` is still returned by default** when an inclusion projection is used, so specify `_id: 0` if the response does not need the ID.

Dot notation selects nested fields; `$slice`, `$elemMatch`, and positional projection address different array-return requirements; and `$project` and `$filter` in aggregation handle complex transformations. Projection reduces payload size to the client and can enable **covered queries**, though I/O savings must be verified in the query plan. Design projections from API contracts, handle `_id` deliberately, and evaluate indexes together with real filters and sorts.
