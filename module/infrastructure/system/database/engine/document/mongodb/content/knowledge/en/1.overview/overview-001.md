# What Is MongoDB and the Document-Oriented Database Model

## 1. What Problem Does MongoDB Solve?

MongoDB is a **NoSQL** database management system (DBMS) that stores data as **documents** rather than rows in tables like many relational database systems. A document typically represents an entity or a business object, such as a product, a user profile, or an order. Document fields can be scalar values, nested objects, or arrays.

For example, an e-commerce application can store product details together with inventory and technical attributes in a single document. When the application needs to display product details, much of the related data already resides in the same storage unit. This is the starting point of the **document-oriented data model**: organizing data according to how the application actually reads, writes, and updates it.

MongoDB does not mean “unstructured.” Every document has a defined structure; the difference is that the structure across documents within the same collection can be flexible, while the application still needs conventions for data types, required fields, and validation mechanisms.

## 2. Database, Collection, Document, and Field

MongoDB organizes data into the following levels:

| Component | Role | Example |
| --- | --- | --- |
| **Database** | Namespace containing the collections of an application or data domain | `shop` |
| **Collection** | A group of documents sharing the same business purpose | `products`, `orders`, `customers` |
| **Document** | A record consisting of field name–value pairs | A product `SP001` |
| **Field** | An attribute inside a document; its value can be scalar or composite | `name`, `price`, `stock.available` |

Visualizing the structure:

```text
Database: shop
├── Collection: products
│   ├── Document: product SP001
│   └── Document: product SP002
├── Collection: customers
│   └── Document: customer KH102
└── Collection: orders
    └── Document: order DH001
```

### What Does a Document Look Like?

In `mongosh` (MongoDB Shell), a product can be represented as follows:

```javascript
{
  _id: "SP001",
  name: "Mechanical keyboard",
  price: 1200000,
  categories: ["accessories", "keyboard"],
  stock: {
    available: 12,
    warehouse: "HCM"
  },
  specs: {
    switch: "Brown",
    layout: "TKL"
  },
  active: true
}
```

Here:

- `_id` uniquely identifies the document within the collection. MongoDB automatically generates an `_id` of type `ObjectId` if an insert operation does not provide this field; the application can also choose an appropriate `_id` value itself.
- `name`, `price`, and `active` hold scalar values.
- `categories` is an **array**, which can hold multiple values.
- `stock` and `specs` are **nested documents** (embedded documents). Subfields can be accessed using dot notation such as `stock.available`.

Documents are typically presented using a syntax close to JSON, but MongoDB stores them internally as **BSON** (*Binary JSON*). BSON supports additional data types beyond standard JSON, such as `ObjectId`, `Date`, binary data, and `Decimal128`. Therefore, it is important to distinguish examples in `mongosh` from pure JSON used when exchanging data via APIs. For example, `ObjectId(...)` and `ISODate(...)` are representations commonly seen in the shell, not pure JSON syntax.

**Two limits to remember:** field names are case-sensitive (`price` is different from `Price`); each BSON document has a size limit of **16 MiB**. You should not cram an unboundedly growing dataset into a single document.

## 3. Why Is It Called a “Document-Oriented” Model?

In a relational model, an order is usually split into a row in the `orders` table and multiple rows in the `order_items` table, linked via foreign keys. With MongoDB, you can store line items directly inside the order document if they are frequently read together.

Example of an order in `orders`:

```javascript
{
  _id: "DH001",
  customerId: "KH102",
  status: "NEW",
  shippingAddress: {
    city: "Ho Chi Minh City",
    district: "District 3"
  },
  items: [
    { productId: "SP001", name: "Mechanical keyboard", quantity: 2, unitPrice: 1200000 },
    { productId: "SP002", name: "Wireless mouse", quantity: 1, unitPrice: 650000 }
  ],
  totalAmount: 3050000,
  createdAt: ISODate("2026-01-05T09:00:00Z")
}
```

This document contains a **scalar value** (`status`), a **nested object** (`shippingAddress`), and an **array of objects** (`items`). Each line item carries the price and name at the time the order was placed, allowing the order to preserve its history even if product details in `products` change later.

The document-oriented model has three core characteristics:

1. **Group data that belongs together.** A query fetching an order can immediately return the list of line items and the shipping address.
2. **Structure can be nested.** A composite entity does not necessarily have to be spread across multiple tables.
3. **Design based on access patterns.** Even for the same customer–order relationship, whether to embed or reference depends on order volume, update frequency, and the queries that need to be supported.

You should not infer that “MongoDB always stores everything in one document.” Oversized documents, unboundedly growing arrays, or duplicated data that is hard to synchronize are usually signs that the model needs adjustment.

## 4. Basic Operations with Documents

The examples below use `mongosh` and a test database `shop`. The statements illustrate how to work with the `products` collection; they are not code intended to run against production data.

### 4.1. Creating and Inserting Data

```javascript
use("shop");

db.products.insertMany([
  {
    _id: "SP001",
    name: "Mechanical keyboard",
    price: 1200000,
    categories: ["accessories", "keyboard"],
    stock: { available: 12, warehouse: "HCM" },
    specs: { switch: "Brown", layout: "TKL" },
    active: true
  },
  {
    _id: "SP002",
    name: "Wireless mouse",
    price: 650000,
    categories: ["accessories", "mouse"],
    stock: { available: 8, warehouse: "HN" },
    specs: { connection: "2.4GHz" },
    active: true
  }
]);
```

`insertOne()` adds a single document; `insertMany()` adds multiple documents. A collection can be created explicitly or appear on the first data insert, depending on the operation and configuration.

The two documents above belong to the same `products` collection, yet `specs` has different fields because the characteristics of a keyboard and a mouse differ. This demonstrates the flexibility of document structure.

### 4.2. Reading and Filtering Data

```javascript
// In-stock products belonging to the "accessories" category
db.products.find(
  { "stock.available": { $gt: 0 }, categories: "accessories" },
  { _id: 0, name: 1, price: 1 }
);

// Find an exact product by _id
db.products.findOne({ _id: "SP001" });
```

`find()` accepts a **filter** and an optional **projection** to select which fields to return. The `$gt` operator means “greater than”; the `"stock.available"` syntax accesses a nested field. The condition `categories: "accessories"` can match an element inside the `categories` array.

### 4.3. Updating and Deleting

```javascript
// Decrement stock by one unit and record the update timestamp
db.products.updateOne(
  { _id: "SP001" },
  {
    $inc: { "stock.available": -1 },
    $set: { updatedAt: new Date() }
  }
);

// Delete a test record
db.products.deleteOne({ _id: "SP002" });
```

`$inc` modifies a numeric value, and `$set` assigns a field value. `updateOne()` and `deleteOne()` affect a single document matching the filter. When you need to update multiple documents, MongoDB also provides `updateMany()`; filters must be chosen carefully to avoid unintended modifications outside the target scope.

**Document-level atomicity:** a single write operation on one document is executed atomically, even when the operation modifies multiple fields or nested elements within that document. This is an advantage when data that must be updated together is appropriately grouped inside one document. If business logic requires modifying multiple documents as a single unit, you must design around transactions or another coordination mechanism.

## 5. Two Ways to Represent Relationships: Embedding and Referencing

In MongoDB, a key modeling decision is **embedding** (nested documents) versus **referencing** (storing reference keys). Both can be combined within the same system.

### 5.1. Embedding Documents

Embedding means placing dependent data inside the parent document:

```javascript
{
  _id: "KH102",
  name: "An",
  contact: {
    email: "an@example.test",
    phone: "0900000000"
  },
  addresses: [
    { label: "Home", city: "Ho Chi Minh City" },
    { label: "Office", city: "Da Nang" }
  ]
}
```

Embedding is suitable when data has a clear ownership relationship, is frequently read together with the parent document, and the number of elements is bounded. For example, a profile with one contact configuration or a handful of addresses is usually straightforward to handle via embedding.

Advantages: the application can read related information with fewer queries; updates to multiple fields in the same document are atomic. On the other hand, if embedded data becomes large, grows indefinitely, or is concurrently modified at high frequency, the document can become bloated and difficult to manage.

### 5.2. Referencing

Referencing means storing the identifier of another document and looking it up separately when needed:

```javascript
// Collection customers
{ _id: "KH102", name: "An", email: "an@example.test" }

// Collection orders
{ _id: "DH001", customerId: "KH102", totalAmount: 3050000 }
{ _id: "DH002", customerId: "KH102", totalAmount: 780000 }
```

Referencing makes sense when an entity has many child records whose count grows continuously, when data is shared, or when an independent update lifecycle is needed. For instance, you should not by default stuff a history of millions of orders into a customer document. Orders can reside in a separate collection with an index on `customerId`.

MongoDB allows querying across collections and provides the `$lookup` aggregation operator to combine data similarly to some `JOIN` use cases. However, a reference key stored by the application does not automatically become a foreign key constraint like in a relational database. The application must manage referential validity according to its own design.

### 5.3. Which One Should You Choose?

| Design Question | Usually Favors Embedding | Usually Favors Referencing |
| --- | --- | --- |
| Are parent and child usually read together? | Yes | Not necessarily |
| Is the number of child records clearly bounded? | Yes | No, can grow over the long term |
| Does child data need independent updates? | Rarely | Frequently |
| Is a child record shared across multiple parents? | Rare | Common |
| Must fields be updated in one atomic operation? | Very helpful | May require a transaction across documents |

For example, an e-commerce application might **reference** `orders.customerId` to the customer and **embed** `orders.items` in each order. This choice is based on query behavior, not a fixed rule for every application.

### 5.4. Intentional Denormalization

With document-oriented data, you sometimes duplicate a few fields to optimize queries or preserve a historical snapshot. For example, an order stores `unitPrice` and `name` of the product at the time of purchase, even though `productId` still points to the current product.

This duplication can be business-correct: a finalized order's price should not change because today's listed price changes. However, if a duplicated field must remain consistent across multiple places, you must define the source of truth, the synchronization timing, and how to handle failed updates.

## 6. Flexible Schema Does Not Mean Ignoring Constraints

MongoDB allows documents in the same collection not to have an identical set of fields. This is useful when different product types have distinct attributes or when an application evolves data versions incrementally.

Example in the same collection:

```javascript
{ _id: "SP001", name: "Keyboard", specs: { layout: "TKL" } }
{ _id: "SP002", name: "Mouse", specs: { dpi: 1600 } }
```

However, a production application should clearly define shared fields, data types, and valid values. This can be enforced through application-layer checks and MongoDB **schema validation**. For instance, a product collection might require `name` to be a string and `price` to be a non-negative number:

```javascript
db.createCollection("validatedProducts", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["name", "price"],
      properties: {
        name: { bsonType: "string" },
        price: {
          bsonType: ["int", "long", "double", "decimal"],
          minimum: 0
        }
      }
    }
  }
});
```

`validatedProducts` is simply an illustrative collection name for the validation rules. Detailed rules must match the data types the application actually uses; for example, currency may require an exact representation such as `Decimal128` or an integer in the smallest unit.

Some practical schema principles:

- Standardize field names and types for the same attribute; avoid storing `price` as a number in one place and as the string `"1200000"` in another.
- Distinguish between a missing field and a field with value `null`, because queries and application logic may treat them differently.
- Establish rules for required fields and data versioning when changing structure across releases.
- Avoid unboundedly growing arrays inside a document; split into separate collections or paginate child data when necessary.

## 7. Queries, Indexes, and Aggregation

Document design is only half the problem; the other half is how the application finds data. A collection with many documents can be scanned to filter results, but for common queries you should consider an **index**.

Example of querying products by category and stock:

```javascript
db.products.find({
  categories: "accessories",
  "stock.available": { $gt: 0 }
});

// Index serving the query pattern above
db.products.createIndex({ categories: 1, "stock.available": 1 });
```

An index gives the database engine an efficient search path instead of always inspecting every document. Because `categories` is an array, an index containing this field can become a **multikey index**. Every index has storage overhead and write-maintenance cost; therefore, indexes must be chosen based on actual queries rather than created mechanically for every field. You can use `explain()` to inspect the query plan.

Beyond simple queries, the **aggregation pipeline** processes data through a sequence of stages such as filtering, unwinding arrays, grouping, and sorting:

```javascript
db.products.aggregate([
  { $match: { active: true } },
  { $unwind: "$categories" },
  {
    $group: {
      _id: "$categories",
      productCount: { $sum: 1 },
      averagePrice: { $avg: "$price" }
    }
  },
  { $sort: { productCount: -1 } }
]);
```

The pipeline above retrieves active products, unwinds each category in the array, calculates the product count and average price per category, and then sorts by count in descending order. It illustrates that MongoDB both stores documents and supports transforming and aggregating structured data.

## 8. MongoDB vs. Relational Databases

| Aspect | MongoDB | Relational Databases (e.g., PostgreSQL, MySQL) |
| --- | --- | --- |
| Typical unit of data | BSON document | Row in a table |
| Organization | Database → collection → document | Database/schema → table → row |
| Nested attributes | Documents and arrays are native structures | Usually represented via related tables; some systems have JSON types |
| Schema | Flexible, validation can be configured | Usually explicit column definitions and constraints |
| Linking data | Embedding, referencing, `$lookup` | Foreign keys and `JOIN` |
| Modeling focus | Access patterns and document boundaries | Relationships, normalization, data constraints |

These are common differences in modeling approach, not a ranking of which system is “stronger.” Modern relational databases also support JSON; MongoDB also supports indexes, aggregation, and multi-document transactions. Choosing a database should be based on data characteristics, consistency requirements, query patterns, operational capability, and business needs.

## 9. Consistency, Scalability, and Operations

MongoDB is often discussed alongside the following capabilities; it is important to distinguish them from the document model itself:

**Atomicity and transactions.** Modifying a single document is atomic. When business logic requires multiple documents to succeed or fail together, MongoDB supports multi-document transactions in appropriate deployments. Transactions incur processing overhead; good document design can reduce the number of transactions needed but does not eliminate every need for them.

**Replication.** A *replica set* maintains copies of data across multiple members to increase availability and support recovery when a node fails. Replication does not replace a backup policy or restore testing.

**Sharding.** When data volume and processing load need to be distributed, MongoDB can partition a collection's data into chunks across multiple shards. Choosing the *shard key* affects data distribution and query efficiency. Not every small application needs sharding.

**Read concern and write concern.** Applications can configure appropriate guarantees for reads and writes. When specific durability and consistency guarantees are required, you must understand the deployment configuration and these options, rather than inferring guarantees solely from the fact that data lives in a document.

These aspects help build reliable systems, but they do not replace the initial design decisions: what a document contains, which data to separate, how the application will query it, and which fields must be constrained.

## 10. Suitable Use Cases and Common Mistakes

The document-oriented model is often advantageous for user profiles, content, catalogs with variable attributes, configuration data, and business objects with rich nested information. For instance, a course management application can store a lesson along with its content items and metadata in one document if the size is bounded and they are typically loaded together.

Conversely, for data with many complex relationships, strict cross-table integrity constraints, or heavy data joins, you should carefully evaluate a MongoDB design against a relational system. Even when using MongoDB, referencing across multiple collections is sometimes the right organization.

Common modeling mistakes:

| Practice | Problem | Improvement Direction |
| --- | --- | --- |
| Putting every order into `customer.orders` array | Array grows forever, document bloats | Create a separate `orders` collection, query by `customerId` |
| Duplicating data that must always stay consistent everywhere | Hard to update, prone to data drift | Identify source of truth and synchronization rules |
| Allowing arbitrary multiple data types for the same field | Complex query, filtering, and analytics logic | Standardize types, add validation and migration plan |
| Creating indexes on all fields | Wastes storage, increases write cost | Base on critical queries and measure with `explain()` |
| Treating references as self-enforced foreign keys | Invalid references can exist | Validate at the application layer and in write/delete workflows |
| Designing from an ER diagram while ignoring queries | Must read too many collections or redundant data | List primary read/write operations before choosing embedding or referencing |

A practical way to start designing for a real project is to write down the three most important queries, the three most common update operations, expected data sizes, and which relationships grow unboundedly. From there, define document boundaries, references, and needed indexes. Once representative data and traffic are available, measure queries again to refine the model.

## 11. Self-Check Comprehension Questions

1. An order document contains `items` as an array of purchased products. What makes embedding `items` reasonable, and in what situation should you consider splitting them out?
2. Why can two products have different `specs` yet still reside in the `products` collection? What needs to be standardized between them?
3. How does a `customerId` key in `orders` differ from an automatic foreign key constraint in a relational database?
4. When a `find()` query filtering on `stock.available` becomes slow, what factors should you inspect before adding an index?
5. If you need to update multiple documents simultaneously and cannot accept partial updates, is single-document atomicity sufficient?

After answering these questions, learners can shift from viewing MongoDB as “a place to store JSON” to designing data properly around the application's **document boundaries, relationships, and access patterns**.
