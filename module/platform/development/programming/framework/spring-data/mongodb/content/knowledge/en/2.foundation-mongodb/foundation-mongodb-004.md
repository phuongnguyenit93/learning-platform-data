# Nested Documents, Arrays, and Field Paths

## 1. Objectives and context

In MongoDB, a BSON document can contain **nested documents** (embedded documents), **arrays**, and multiple combined levels of these two structures. This is the foundation for modeling data close to business objects—for example, an order containing a shipping address, tags, and a list of items.

In the **SPRING_DATA_MONGODB (Spring Data MongoDB)** module, understanding this structure helps you design documents, map them to Java, build queries with repositories or `MongoTemplate`, update array elements, write aggregations, and choose appropriate indexes. After this lesson, you will be able to:

- Distinguish scalar fields, nested documents, scalar arrays, and arrays of documents.
- Read and write **field paths** using dot notation for querying, projection, and updating.
- Understand array conditions accurately, especially the difference between independent conditions and `$elemMatch`.
- Manipulate arrays with update operators and process arrays using aggregation.
- Apply document structures in Spring Data MongoDB and recognize limitations around indexing, size, and atomicity.

## 2. One document used throughout the examples

Suppose the `orders` collection contains an order:

```javascript
db.orders.insertOne({
  customerId: "KH-101",
  status: "NEW",
  shippingAddress: {
    city: "Da Nang",
    district: "Hai Chau",
    geo: {
      lat: 16.05,
      lng: 108.22
    }
  },
  tags: ["priority", "gift"],
  items: [
    {
      sku: "BOOK-01",
      quantity: 2,
      unitPrice: 120000,
      options: { color: "blue" }
    },
    {
      sku: "PEN-02",
      quantity: 1,
      unitPrice: 30000,
      options: { color: "black" }
    }
  ]
});
```

MongoDB auto-generates `_id` if not provided. The structure in this example consists of:

| Component | Data type | Meaning |
| --- | --- | --- |
| `customerId`, `status` | Scalar (string) | Single values |
| `shippingAddress` | Nested document | Groups fields belonging to the same address |
| `shippingAddress.geo` | Deeper nested document | Coordinates of the address |
| `tags` | Array of strings | Multiple tags for one order |
| `items` | Array of documents | Multiple product lines, each with multiple attributes |
| `items.options` | Document inside an array element | Product options |

You can visualize the data tree as follows:

```text
orders (collection)
└── order document
    ├── customerId: "KH-101"
    ├── shippingAddress
    │   ├── city: "Da Nang"
    │   ├── district: "Hai Chau"
    │   └── geo
    │       ├── lat: 16.05
    │       └── lng: 108.22
    ├── tags: ["priority", "gift"]
    └── items: [document, document]
        ├── items[0]: sku, quantity, unitPrice, options
        └── items[1]: sku, quantity, unitPrice, options
```

**Embedding documents** enables reading related data in a single order fetch and updating multiple fields of the same document atomically. However, unboundedly growing arrays can bloat documents; embedding fits best when child data has clear ownership and a controlled size.

## 3. Field paths and dot notation

MongoDB uses a dot (`.`) to access nested levels inside a document. This is a **field path**, not a new field name.

| Path | Points to |
| --- | --- |
| `shippingAddress.city` | City inside the address document |
| `shippingAddress.geo.lat` | Latitude at the second nesting level |
| `items.sku` | The `sku` field of documents in the `items` array |
| `items.options.color` | Color inside `options` of `items` elements |
| `items.0.sku` | `sku` of the first element in `items` |

When putting a dotted path into a JavaScript query object, wrap **the entire key in quotes**:

```javascript
// Address with city Da Nang
db.orders.find({ "shippingAddress.city": "Da Nang" });

// Orders with at least one line item having this SKU
db.orders.find({ "items.sku": "BOOK-01" });

// SKU at the first position of the items array
db.orders.find({ "items.0.sku": "BOOK-01" });
```

The last two queries differ: `items.sku` can match **any element**, whereas `items.0.sku` only checks the element at index `0`. Relying on fixed positions is usually fragile because array order may change.

Field paths also work in comparisons and existence checks:

```javascript
// At least one line item with quantity 2 or greater
db.orders.find({ "items.quantity": { $gte: 2 } });

// Has the lat coordinate field
db.orders.find({ "shippingAddress.geo.lat": { $exists: true } });

// lat has BSON type double
db.orders.find({ "shippingAddress.geo.lat": { $type: "double" } });
```

Note: `$exists: true` only checks whether the field is present; it **does not guarantee a non-`null` value**. In normal queries, the condition `{ "shippingAddress.geo.lat": null }` can match both a field with value `null` and a nonexistent field. When you need to match specifically the BSON Null type, you can use `$type: "null"`.

## 4. Querying arrays: values, elements, and multiple conditions

### 4.1. Scalar arrays

With `tags: ["priority", "gift"]`:

```javascript
// Contains an element equal to "gift"
db.orders.find({ tags: "gift" });

// Contains both tags, regardless of order
db.orders.find({ tags: { $all: ["gift", "priority"] } });

// Array has exactly 2 elements
db.orders.find({ tags: { $size: 2 } });

// Matches the entire array value, including order
db.orders.find({ tags: ["priority", "gift"] });
```

Meanings to distinguish:

- `{ tags: "gift" }` finds documents where **at least one element** equals `"gift"`.
- `$all` requires **all specified values** to be present, even if in a different order.
- `$size` matches array length, but `$size` cannot be combined directly with a range condition such as `$gte`.
- Querying with a full array requires the array to match both values and order exactly.

### 4.2. Arrays of documents and the "two different elements" trap

Consider the query:

```javascript
db.orders.find({
  "items.sku": "BOOK-01",
  "items.quantity": 1
});
```

**The sample document still matches this query**, even though product `BOOK-01` has `quantity: 2`. Reason: the `items.sku` condition can match the first element, while `items.quantity` can match the second element. Two independent conditions do not automatically force both to apply to the same element.

When multiple conditions must hold within **the same element**, use `$elemMatch`:

```javascript
// Does not match sample document: BOOK-01 has quantity = 2
db.orders.find({
  items: {
    $elemMatch: {
      sku: "BOOK-01",
      quantity: 1
    }
  }
});

// Matches sample document: the same BOOK-01 line has quantity >= 2
db.orders.find({
  items: {
    $elemMatch: {
      sku: "BOOK-01",
      quantity: { $gte: 2 }
    }
  }
});
```

| Syntax | Meaning |
| --- | --- |
| `"items.sku": "BOOK-01"` | At least one element has that SKU |
| `"items.sku": "BOOK-01", "items.quantity": 1` | May match across two different elements |
| `items: { $elemMatch: { sku: "BOOK-01", quantity: 1 } }` | A single element must satisfy **both** conditions |

`$elemMatch` is especially important for lists of line items, status histories, class schedules, member lists, or any case where multiple attributes of the same element must stay coupled.

### 4.3. Projection: returning only needed fields

Projection limits which fields are returned:

```javascript
db.orders.find(
  { "shippingAddress.city": "Da Nang" },
  {
    _id: 0,
    customerId: 1,
    "shippingAddress.city": 1,
    "items.sku": 1
  }
);
```

The result keeps only the requested paths rather than returning the entire order. **Projecting `"items.sku": 1` does not mean returning only the array element that matched the filter**; normally it projects the `sku` field of all elements in the array. If you need to select individual elements matching a condition, consider `$elemMatch` in projection or `$filter` in aggregation.

## 5. Updating nested documents and array elements

### 5.1. Updating a child field without replacing the parent document

```javascript
db.orders.updateOne(
  { customerId: "KH-101" },
  { $set: { "shippingAddress.city": "Hue" } }
);
```

Using a dotted path preserves `district` and `geo`. Conversely, `$set: { shippingAddress: { city: "Hue" } }` would **replace the entire value of `shippingAddress`**, causing subfields missing from the new object to disappear. The update examples across these sections are independent operations and do not need to be run sequentially.

### 5.2. Adding and removing array elements

```javascript
// Add a tag; if the string already exists, do not add a duplicate
db.orders.updateOne(
  { customerId: "KH-101" },
  { $addToSet: { tags: "fragile" } }
);

// Append a new line item to the end of the array
db.orders.updateOne(
  { customerId: "KH-101" },
  {
    $push: {
      items: {
        sku: "NOTE-03",
        quantity: 1,
        unitPrice: 45000,
        options: { color: "white" }
      }
    }
  }
);

// Remove all line items with sku = PEN-02
db.orders.updateOne(
  { customerId: "KH-101" },
  { $pull: { items: { sku: "PEN-02" } } }
);
```

`$push` always appends an element, while `$addToSet` avoids adding an **element value** that already exists under MongoDB comparison rules; it does not automatically enforce uniqueness for a subfield like `items.sku` across distinct objects.

### 5.3. Positional operators: `$`, `$[]`, and `$[identifier]`

Three common ways to update array elements:

| Operator | Scope |
| --- | --- |
| `$` | The first element matching the array condition in the query |
| `$[]` | All elements of the array |
| `$[line]` | All elements satisfying `arrayFilters` for the `line` identifier |

```javascript
// Increase quantity of the first element with sku = BOOK-01
db.orders.updateOne(
  { customerId: "KH-101", "items.sku": "BOOK-01" },
  { $inc: { "items.$.quantity": 1 } }
);

// Increase price of every line item by 1,000
db.orders.updateOne(
  { customerId: "KH-101" },
  { $inc: { "items.$[].unitPrice": 1000 } }
);

// Increase price only for lines with quantity >= 2
db.orders.updateOne(
  { customerId: "KH-101" },
  { $inc: { "items.$[line].unitPrice": 1000 } },
  { arrayFilters: [{ "line.quantity": { $gte: 2 } }] }
);
```

`$` is the positional array operator and requires an appropriate array condition in the query filter. With `$[line]`, the `line` name in the path and in `arrayFilters` must match. If there are multiple line items with the same SKU, `$` only affects the first matching element; use the filtered positional operator when you want to affect all matching elements.

MongoDB guarantees that a write operation on a **single document** is atomic, even when it modifies multiple fields or array elements in that document. However, an operation across multiple documents does not automatically become an atomic transaction for the whole set; if business logic requires cross-document constraints, you must design an appropriate consistency mechanism or transaction.

## 6. Processing arrays in aggregation

`find` queries return documents that match conditions. When you need to compute, transform, or aggregate over individual array elements, use an aggregation pipeline.

### 6.1. `$unwind`: splitting each element into a pipeline document

```javascript
db.orders.aggregate([
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      totalQuantity: { $sum: "$items.quantity" },
      totalAmount: {
        $sum: { $multiply: ["$items.quantity", "$items.unitPrice"] }
      }
    }
  },
  { $sort: { totalQuantity: -1 } }
]);
```

Each line item in `items` becomes a temporary document in the pipeline; `$group` then sums quantities and line totals by `sku` across all orders. By default, `$unwind` skips documents whose array field is empty, `null`, or missing; you can pass `preserveNullAndEmptyArrays: true` when you need to retain those documents.

### 6.2. `$filter`: keeping array elements that satisfy a condition

```javascript
db.orders.aggregate([
  {
    $project: {
      _id: 0,
      customerId: 1,
      highQuantityItems: {
        $filter: {
          input: "$items",
          as: "line",
          cond: { $gte: ["$$line.quantity", 2] }
        }
      }
    }
  }
]);
```

For the sample order, `highQuantityItems` contains only the `BOOK-01` line. Unlike filtering documents with `"items.quantity": { $gte: 2 }`, `$filter` **creates a result array containing only the matching elements**. In aggregation expressions, `$items` references the field of the current document while `$$line` references the variable defined by `as`. The `$map` operator can transform each element—for example, producing a list of line amounts `quantity × unitPrice`.

## 7. Mapping and querying with Spring Data MongoDB

### 7.1. Mapping embedded documents and lists to Java

Spring Data MongoDB maps nested documents to Java objects and BSON arrays to Java collections. The example below uses Java 17+ `record` types to keep declarations concise:

```java
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record Order(
    @Id String id,
    String customerId,
    String status,
    ShippingAddress shippingAddress,
    List<String> tags,
    List<LineItem> items
) {}

record ShippingAddress(String city, String district, Geo geo) {}
record Geo(double lat, double lng) {}
record LineItem(String sku, int quantity, long unitPrice, ItemOptions options) {}
record ItemOptions(String color) {}
```

If a project uses POJOs with constructors, getters, and setters, the structural mapping remains similar. This example uses `long` for integer prices in the smallest currency unit; for values requiring decimals, choose an appropriate numeric type and storage convention, avoiding `double` for monetary calculations.

Points to remember:

- `shippingAddress` is a child object, not an independent collection.
- `List<LineItem>` is stored as an array of documents inside the order itself.
- `@Id` maps the identifier property to `_id`; the exact stored ID type is influenced by Spring Data's configuration and conversion rules.
- Default field names are based on property names; if using `@Field` to customize stored names, keep queries and mapping consistent.

### 7.2. Repository: traversing nested properties

```java
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

public interface OrderRepository extends MongoRepository<Order, String> {

    // Underscore explicitly marks the nested property boundary.
    List<Order> findByShippingAddress_City(String city);

    // Ensure sku and quantity are in the same line item.
    @Query("{ 'items': { $elemMatch: { 'sku': ?0, 'quantity': { $gte: ?1 } } } }")
    List<Order> findByItemSkuAndMinQuantity(String sku, int minimumQuantity);
}
```

Spring Data can derive many queries from method names. However, when multiple conditions are needed on **the same array element**, `@Query` with `$elemMatch` expresses the constraint much more clearly than combining independent dot-notation conditions. Parameters `?0` and `?1` are bound by Spring Data from the method call.

### 7.3. MongoTemplate: direct control over query and update

```java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public class OrderOperations {
    private final MongoTemplate mongoTemplate;

    public OrderOperations(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<Order> findOrdersWithBookQuantityAtLeastTwo() {
        Criteria itemCriteria = Criteria.where("sku").is("BOOK-01")
            .and("quantity").gte(2);
        Query query = new Query(
            Criteria.where("items").elemMatch(itemCriteria)
        );
        return mongoTemplate.find(query, Order.class);
    }

    public void increaseBookQuantity(String customerId) {
        Query query = new Query(
            Criteria.where("customerId").is(customerId)
                .and("items.sku").is("BOOK-01")
        );
        Update update = new Update().inc("items.$.quantity", 1);
        mongoTemplate.updateFirst(query, update, Order.class);
    }
}
```

`Criteria.where("items").elemMatch(...)` corresponds semantically to MongoDB's `$elemMatch` query. `Update.inc("items.$.quantity", 1)` uses the positional operator to increment the quantity of the first matching element. When multiple threads update concurrently, atomic updates like `$inc` are usually safer than the "read object → increment in memory → overwrite entire document" pattern.

**Note on paths in applications:** When writing queries/updates, follow the mapped property names of the model and inspect the actual structure in the collection, especially when the project uses `@Field` or custom converters. For complex queries, inspect the generated MongoDB command and test with data containing multiple array elements.

## 8. Indexes, schema design, and performance

### 8.1. Indexes on nested paths

MongoDB supports creating indexes on nested paths:

```javascript
db.orders.createIndex({ "shippingAddress.city": 1 });
db.orders.createIndex({ "items.sku": 1 });

db.orders.find({ "items.sku": "BOOK-01" })
  .explain("executionStats");
```

An index on `shippingAddress.city` serves filtering by city. An index on `items.sku` is a **multikey index** when `items` is an array: MongoDB indexes values corresponding to the array elements. This helps lookups by SKU, though overly large arrays also increase the number of index entries and write overhead.

For compound multikey indexes, MongoDB imposes restrictions on indexing **parallel array fields** in the same document. When querying multiple attributes of the same array element simultaneously, `$elemMatch` not only provides correct semantics but can also help the optimizer use appropriate index conditions. Evaluate with `explain("executionStats")` on actual data and queries rather than assuming from index existence alone.

### 8.2. When to embed, when to reference?

| Criterion | Embed document/array | Reference another collection |
| --- | --- | --- |
| Read pattern | Parent and child data are usually read together | Child data is accessed independently |
| Lifecycle | Child is tightly coupled to parent | Child has its own lifecycle or ownership |
| Size | Bounded and predictable | Element count can grow very large |
| Updates | Want atomic updates within one document | Need to update individual objects independently |
| Trade-offs | Large documents, long arrays, and many index entries | Requires extra queries or `$lookup` when combining |

For example, the shipping address recorded when placing an order should usually be embedded in the order because it is a **historical data snapshot**. The list of line items is also usually reasonable to embed if each order has a bounded number of lines. By contrast, a continuously generated event log of millions of records usually fits a separate collection or partitioning strategy better.

MongoDB has a **16 MiB limit per BSON document**. Embedding unboundedly growing arrays risks hitting this limit while increasing data transfer and index maintenance costs. Do not rely on `$slice` at read time to fundamentally solve an endlessly growing document.

## 9. Common mistakes

| Symptom | Cause | How to handle |
| --- | --- | --- |
| Query requiring SKU and quantity returns the "wrong" line item | Dot-notation conditions matched different elements | Use `$elemMatch` when the same element is required |
| Updating city wipes out district and coordinates | `$set` replaced the entire `shippingAddress` object | Use `$set` on `shippingAddress.city` |
| Adding a tag creates duplicate entries | Used `$push` instead of `$addToSet` | Choose the operator matching business semantics |
| Update modifies only one of several matching lines | Used positional `$` | Use `$[identifier]` combined with `arrayFilters` |
| Query matches the order but result still contains the entire `items` array | Filtering documents differs from filtering array elements | Use `$filter` or an appropriate projection |
| Nested query is slow on large data | Missing appropriate index or multikey index is too large | Measure with `explain`; evaluate query pattern and array size |
| Data errors from assuming a field always exists | Flexible schema; `null` and missing can differ | Check `$exists`, `$type`, and apply appropriate validation/mapping |

Another subtle mistake is overusing positional paths like `items.0`. This is safe only when position carries stable business meaning; for product lists, identify line items with an explicit field (such as `lineId`) when a specific line must be edited accurately.

## 10. Guided practice

Use the `orders` collection structured as in section 2. The queries below are independent of each other; run them on fresh sample data if you already tested update commands.

**Exercise 1.** Find orders delivered to Da Nang, tagged `priority`, and containing a `BOOK-01` line with quantity 2 or greater.

```javascript
db.orders.find({
  "shippingAddress.city": "Da Nang",
  tags: "priority",
  items: {
    $elemMatch: {
      sku: "BOOK-01",
      quantity: { $gte: 2 }
    }
  }
});
```

**Exercise 2.** Increment the quantity of **all** lines with SKU `BOOK-01` in order `KH-101`, even if the data accidentally contains multiple lines with the same SKU.

```javascript
db.orders.updateOne(
  { customerId: "KH-101" },
  { $inc: { "items.$[line].quantity": 1 } },
  { arrayFilters: [{ "line.sku": "BOOK-01" }] }
);
```

**Exercise 3.** Return only `customerId` and the line items with `unitPrice` of 100000 or more.

```javascript
db.orders.aggregate([
  {
    $project: {
      _id: 0,
      customerId: 1,
      expensiveItems: {
        $filter: {
          input: "$items",
          as: "line",
          cond: { $gte: ["$$line.unitPrice", 100000] }
        }
      }
    }
  }
]);
```

These exercises illustrate three distinct processing levels: **filtering documents** with `find` and `$elemMatch`, **updating selected elements** with `arrayFilters`, and **filtering arrays in the output** with `$filter`.

## 11. Key takeaways

1. Nested documents describe composition relationships; arrays describe multiple values or multiple objects inside the same document.
2. Dot notation accesses nested fields and fields of array elements. In array queries, a path generally means "at least one element matches."
3. Multiple dot-notation conditions on the same array can match **different elements**. Use `$elemMatch` when the same element is required.
4. Use a field path when updating subfields, `$` for the first matching element, `$[]` for all elements, and `$[identifier]` with `arrayFilters` for a selected subset of elements.
5. Use `$unwind` to aggregate per element and `$filter` to produce a filtered output array.
6. In Spring Data MongoDB, objects and `List<T>` map naturally to nested documents and arrays; verify query semantics rather than relying solely on method names.
7. Index along paths, measure real performance, and keep array sizes within bounds appropriate for the business domain.
