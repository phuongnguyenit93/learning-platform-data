# Database, collection, document, and data organization

> **Chapter:** MongoDB Foundations  
> **Module:** `SPRING_DATA_MONGODB`

In MongoDB, data is stored as **BSON documents** inside a **collection** of a **database**. Understanding these three units properly is the first step toward designing a data model that fits your queries and maps cleanly to Java objects with Spring Data MongoDB.

The `SPRING_DATA_MONGODB` module focuses on connecting to MongoDB, mapping documents, and manipulating data using `MongoTemplate` or repositories. Subsequent skills such as query design, aggregation, indexing, transactions, reactive access, testing, and performance diagnostics all depend on how data is organized initially.

## Learning objectives

After this lesson, you will be able to:

1. Distinguish between a database, collection, document, and field; explain BSON, `_id`, and structural flexibility.
2. Organize data for a real-world business use case; decide when to embed documents and when to store references.
3. Write basic `mongosh` operations to create and read data, and visualize how MongoDB stores it.
4. Relate collections and fields to `@Document`, `@Id`, `@Field`, `MongoRepository`, and `MongoTemplate` in Spring Data MongoDB.
5. Identify common mistakes regarding document size, data types, consistency, and queryability.

## 1. Structure from database to field

```text
MongoDB deployment (server or cluster)
└── Database: shop
    ├── Collection: customers
    │   ├── Document: {_id: ..., name: ..., email: ...}
    │   └── Document: {_id: ..., name: ..., email: ...}
    ├── Collection: products
    │   └── Document: {_id: ..., sku: ..., price_vnd: ...}
    └── Collection: orders
        ├── Document: {_id: ..., customer_id: ..., items: [...]}
        └── Document: {_id: ..., customer_id: ..., items: [...]}
```

| Component | Function | Example | Relation in Spring Data MongoDB |
| --- | --- | --- | --- |
| **Database** | Logical namespace containing multiple collections | `shop` | The database that `MongoDatabaseFactory` / connection configuration points to |
| **Collection** | Group of documents, which may have its own indexes and validation rules | `orders` | `@Document(collection = "orders")` or the collection name passed to `MongoTemplate` |
| **Document** | BSON unit of data consisting of field name and value pairs | An order | A domain object mapped to a document |
| **Field** | Attribute in a document; can hold a scalar value, nested object, or array | `status`, `items` | A Java property, whose stored name can be changed with `@Field` |

You can roughly picture a database like a database in a relational database management system, a collection like a table, and a document like a row. **This is only an analogy to orient yourself:** a document can contain nested objects and arrays, and documents in the same collection are not required to have the exact same set of fields.

MongoDB does not use a separate "child table" for every nested structure. Multiple pieces of information that need to be read together can live right inside a single document; therefore, choosing document boundaries matters more than translating a relational table model straight into collections.

## 2. Database: high-level organizational boundary

A database groups collections that serve a particular data scope. For example, `shop` contains `customers`, `products`, and `orders`; another system might have an `analytics` database for analytical data.

- **Name and scope:** every collection belongs to a specific database. Two databases can both have a collection named `orders`, but they are two distinct collections.
- **Connection and permissions:** the application needs to select the right database and be granted appropriate permissions. Separating databases can help with administration and access control, but **does not by itself guarantee physical resource isolation**, because multiple databases can reside on the same MongoDB deployment.
- **Data creation:** the `use shop` command in `mongosh` only selects the current database. The database is typically created physically when data is written or a collection is created, provided the account has permission.

Example in `mongosh`:

```javascript
use shop
db.getName()               // "shop"
db.createCollection("orders")
show collections
```

In a Java application, the database is determined by the connection configuration or `MongoDatabaseFactory`; the `@Document` annotation specifies the **collection**, not an independent database per entity. If you want to work with multiple databases, you must configure the corresponding mechanism explicitly.

**Practical rule:** choose database boundaries according to deployment, access control, and operational requirements; design collections and documents according to how the business reads and updates data.

## 3. Collection: grouping documents by query purpose

A collection holds documents sharing a business role—for example, `orders` holds orders. MongoDB allows documents in a collection to have different structures, but that **does not mean you should mix every kind of data into one collection**.

A collection can have:

- **Indexes** to support filtering and sorting; every regular collection has a unique index on `_id`.
- **Schema validation** to check the types or structure of written documents; by default, MongoDB does not require every document to share the same schema.
- **Collection creation options** for specialized needs. This lesson focuses on regular collections.

For example, two order documents may differ in optional fields:

```javascript
db.orders.insertMany([
  {
    customer_id: "CUS-001",
    status: "CREATED",
    channel: "WEB",
    total_vnd: 350000
  },
  {
    customer_id: "CUS-002",
    status: "PAID",
    total_vnd: 820000,
    coupon_code: "WELCOME"
  }
])
```

Omitting `coupon_code` in the first order is valid when no required rule has been set. However, if the application expects `total_vnd` to always be a number and `status` to belong to a defined set of statuses, you need to maintain a data contract at the application layer and consider a validator in the database.

Example of enforcing partial structure control when **creating a new collection**:

```javascript
db.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["customer_id", "status", "total_vnd"],
      properties: {
        customer_id: { bsonType: "string" },
        status: { enum: ["CREATED", "PAID", "CANCELLED"] },
        total_vnd: { bsonType: ["int", "long"], minimum: 0 }
      }
    }
  }
})
```

The snippet above is for a **collection that does not exist yet**. If you already ran `db.createCollection("orders")` in the previous example, try the validator in a new practice database or use `collMod` to update the existing collection. Validators should be tailored to real business rules, such as return statuses, refund amounts, and how monetary values are stored.

## 4. BSON document: data and update boundary

A **document** is a set of field–value pairs. MongoDB stores documents using BSON (Binary JSON), supporting types such as string, boolean, 32/64-bit integers, double, `Decimal128`, date, `ObjectId`, nested objects, and arrays.

Example of a more complete order:

```javascript
use shop

db.orders.insertOne({
  _id: ObjectId("66a000000000000000000001"),
  customer_id: "CUS-001",
  status: "PAID",
  created_at: ISODate("2026-01-15T08:30:00Z"),
  items: [
    { sku: "KB-01", quantity: 1, unit_price_vnd: NumberLong(350000) },
    { sku: "MS-02", quantity: 2, unit_price_vnd: NumberLong(120000) }
  ],
  shipping_address: {
    recipient: "Nguyen A",
    city: "Ha Noi"
  },
  total_vnd: NumberLong(590000)
})
```

In this example:

- `_id` uniquely identifies the order **within the `orders` collection**. If `_id` is not provided on insert, the driver typically generates an `ObjectId` value. MongoDB also allows other `_id` types; do not assume all IDs are `ObjectId`.
- `created_at` is a BSON Date value (via `ISODate` in `mongosh`), distinct from a text string representing a date. BSON Date stores an instant in UTC; the UI can display it in the user's time zone.
- `items` is an array of nested objects. Line items live in the same order document so an order can be read without joining separate line-item records.
- `shipping_address` is a nested object describing the shipping address at the time of purchase.
- `total_vnd` and `unit_price_vnd` use 64-bit integers to represent VND amounts, avoiding floating-point rounding errors in the example. For currencies with fractional units, you can choose the smallest currency unit or `Decimal128` according to a consistent convention.

**Two design limits to remember:** a regular BSON document has a maximum size of **16 MiB**, and a write operation on a **single document** is atomic. Do not assume that multiple documents across different collections always update atomically as a single unit; those cases require considering transactions or redesigning data boundaries.

> **Syntax note:** `ObjectId(...)`, `ISODate(...)`, and `NumberLong(...)` are ways to represent data types in `mongosh`; they are not pure JSON syntax. The data stored on the server is BSON.

### Accessing fields and arrays

```javascript
// Find a customer's orders, newest first.
db.orders
  .find(
    { customer_id: "CUS-001" },
    { _id: 1, status: 1, created_at: 1, total_vnd: 1 }
  )
  .sort({ created_at: -1 })
  .limit(20)

// Query a field inside an object of an array element.
db.orders.find({ "items.sku": "KB-01" })

// Query a field of a nested object.
db.orders.find({ "shipping_address.city": "Ha Noi" })
```

**Dot notation** (for example `items.sku`) lets you query along field paths inside a document. When multiple conditions must all hold on **a single array element**, use `$elemMatch`; independent dot-notation conditions can match across different array elements.

```javascript
db.orders.find({
  items: {
    $elemMatch: { sku: "KB-01", quantity: { $gte: 1 } }
  }
})
```

## 5. Designing data around how the application uses it

Suppose a retail system has three main data groups:

- `customers`: customer profiles, where names or contact details can change.
- `products`: product information, current prices, and inventory stock.
- `orders`: placed transactions, including status, line items, locked-in prices, and shipping address at purchase time.

Two common ways to organize relationships are **embedding** (embedding data) and **referencing** (storing reference IDs).

### 5.1. Embedding

Embed when child data belongs to one primary entity, is typically read together with it, and has a controllable size. For example, `items` and `shipping_address` are embedded in `orders`.

Advantages:

- Read an order along with its line items in a single document.
- Update fields within one order in a single atomic write operation.
- Preserve "point-in-time snapshot" information at order placement, such as unit price and shipping address, even when product or customer profiles later change.

Trade-offs:

- Information is duplicated across orders; modifying historical data broadly requires updating many documents.
- Arrays can grow unboundedly if embedding is chosen poorly, causing large documents and heavy writes.

**Good example:** a few line items per order. **Risky example:** embedding millions of orders inside a single customer document.

### 5.2. Referencing

Store an ID when an entity is used independently, shared by multiple documents, changes frequently, or has a relationship set that grows large.

In `orders`, the `customer_id` field points to the customer, and `items.sku` identifies the product. The application may need to query `customers` or `products` additionally when current data is required.

The advantage is avoiding duplication of large or constantly changing data. The trade-off is that reads may require multiple queries or `$lookup` in aggregation; consistency across multiple documents must be handled explicitly.

Spring Data MongoDB supports reference mechanisms such as `@DBRef` or `@DocumentReference`, but you should not assume they automatically create cascade writes or behave like SQL foreign keys. For simple links, **storing an explicit ID** usually makes read/write flows and performance easier to control.

### 5.3. Decision rules

| Question about child data | Favors embedding | Favors referencing |
| --- | --- | --- |
| Is it always read together with the parent data? | Yes | Rarely |
| Is the size/total element count reasonably bounded? | Yes | Grows continuously, hard to bound |
| Does it need to be updated with the parent in one atomic operation? | Yes | Not often |
| Is it shared by many other entities? | Rarely | Often |
| Is historical data at transaction time needed? | Yes, store a snapshot | When current state needs to be accessed |

There is no rule that "embedding is always faster" or "referencing is always more proper." Good boundaries depend on **query patterns, data lifecycle, element count, update frequency, and consistency requirements**.

## 6. A scalable order design

For the example system, we use:

```text
shop
├── customers
│   └── {_id, name, email, ...}
├── products
│   └── {_id, sku, name, current_price_vnd, stock, ...}
└── orders
    └── {
          _id,
          customer_id,               // customer reference
          status,
          created_at,
          items: [
            {sku, quantity, unit_price_vnd}, // line item snapshot
            ...
          ],
          shipping_address: {...},   // shipping address snapshot
          total_vnd
        }
```

Here, the order stores `sku` to know which product was purchased, while also storing `unit_price_vnd` because the transaction price must not automatically change when the list price in `products` changes. If the product name must appear on the invoice exactly as it was at purchase time, you can also store `product_name` inside each line item.

Example access scenarios:

| Need | Primary collection | Design direction |
| --- | --- | --- |
| View details of one order | `orders` | Embed `items`, `shipping_address` to read with the order |
| List a customer's 20 most recent orders | `orders` | Filter `customer_id`, sort `created_at` descending |
| Edit a customer's email | `customers` | Update profile independently; no need to edit order history |
| Change current selling price | `products` | Update only the product; preserve locked-in prices in past orders |
| Monthly revenue report | `orders` | Aggregation by date/status with appropriate indexes |

**Principle:** choose the document model based on what data needs to be read and updated **together**, not merely based on a Java class diagram or the number of tables in an existing relational database.

## 7. Mapping to Spring Data MongoDB

Spring Data MongoDB uses mapping to turn BSON documents into Java objects. With the order design above, you can use Java records for a concise example:

```java
import java.time.Instant;
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "orders")
public record Order(
    @Id String id,
    @Field("customer_id") String customerId,
    String status,
    @Field("created_at") Instant createdAt,
    List<OrderLine> items,
    @Field("shipping_address") ShippingAddress shippingAddress,
    @Field("total_vnd") long totalVnd
) {}

record OrderLine(
    String sku,
    int quantity,
    @Field("unit_price_vnd") long unitPriceVnd
) {}

record ShippingAddress(String recipient, String city) {}
```

Key points to understand:

- `@Document(collection = "orders")` maps the `Order` entity to the `orders` collection. Without this annotation, Spring Data applies default rules to determine the collection name, but using an explicit name helps prevent mismatches during refactoring.
- `@Id` marks the property mapped to MongoDB's `_id` field. With `String`, Spring Data has a mechanism to convert IDs to `ObjectId` when possible; when designing APIs, define and test a consistent ID type.
- `@Field("customer_id")` maps the Java property `customerId` to the stored field `customer_id`. Similar annotations resolve naming differences between Java and BSON.
- `List<OrderLine>` is mapped to an array of nested documents; `ShippingAddress` becomes a nested object.
- With `Instant`, the corresponding value is converted to a MongoDB time type via mapping/conversion. Establish a consistent approach to time zones and time precision across the entire application.

A simple repository:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository extends MongoRepository<Order, String> {
    Page<Order> findByCustomerIdOrderByCreatedAtDesc(
        String customerId, Pageable pageable);
}
```

Spring Data derives the query from the **Java property names** (`customerId`, `createdAt`), then maps them to the actual fields (`customer_id`, `created_at`). An equivalent query can be built with `MongoTemplate`:

```java
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class OrderQueryService {
    private final MongoTemplate mongoTemplate;

    public OrderQueryService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<Order> latestOrders(String customerId) {
        Query query = Query.query(Criteria.where("customerId").is(customerId))
            .with(Sort.by(Sort.Direction.DESC, "createdAt"))
            .limit(20);
        return mongoTemplate.find(query, Order.class);
    }
}
```

`MongoTemplate` uses `Order`'s mapping metadata to determine the collection and corresponding field names. In this example, Spring injects `MongoTemplate` via the service constructor.

### How to choose between Repository and MongoTemplate?

`MongoRepository` fits entity-based operations with common CRUD and derived query methods. `MongoTemplate` is useful when you need fine-grained control over filters, updates, bulk operations, aggregations, or how queries execute. Both operate on the same MongoDB collections and documents; they do not require two different data storage layouts.

## 8. Organizing data for efficient queries

A sound document design still needs indexes aligned with access patterns. For example, if the application frequently lists a customer's orders, filtering only paid statuses and sorting newest first:

```javascript
db.orders
  .find({ customer_id: "CUS-001", status: "PAID" })
  .sort({ created_at: -1 })
  .limit(20)

db.orders.createIndex({
  customer_id: 1,
  status: 1,
  created_at: -1
})
```

This compound index is a **candidate** for the query pattern above: equality filter fields come first, followed by the sort field. Do not create an index merely because a field exists; indexes consume storage and increase write cost.

Inspect the execution plan in an environment with representative data:

```javascript
db.orders
  .find({ customer_id: "CUS-001", status: "PAID" })
  .sort({ created_at: -1 })
  .explain("executionStats")
```

Observe metrics such as `totalDocsExamined`, `totalKeysExamined`, and execution time, and check whether the plan uses the right index. Running an example on a few documents is not enough to draw performance conclusions when the system has millions of orders.

Additional points to consider:

- Frequent queries on `items.sku` may need an index on that path; for arrays, MongoDB creates a **multikey index** according to its indexing rules.
- Overly large or continuously growing arrays can bloat documents even when indexed. In that case, split the data into an appropriate collection.
- Field names, data types, and time storage must be consistent so filtering, sorting, aggregation, and mapping do not produce hard-to-trace discrepancies.
- Sensitive data must comply with the system's access control and data protection policies; choosing a document/collection layout does not replace permission checks.

## 9. Common mistakes

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| Treating collections like SQL tables and splitting every child object into its own collection | Requires multiple queries/joins to view one entity | Embed child data with a tightly coupled lifecycle and bounded size |
| Embedding an unboundedly growing list into a single document | Document grows large, approaches the 16 MiB limit, and becomes hard to update | Paginate using a separate collection or design data with growth bounds |
| Mixing the type of `total_vnd` between numbers and strings | Filtering, comparison, and aggregation produce wrong or unpredictable results | Standardize numeric types, validate inputs, and apply appropriate schema validation |
| Casually using `double` for money | Risk of floating-point precision errors | Use integers in the smallest currency unit or `Decimal128` consistently |
| Storing only the product code and always reading current price for old orders | Payment history is misinterpreted | Store a snapshot of price and immutable details at purchase time |
| Assuming `@DBRef` automatically enforces foreign keys/cascades like JPA | Referenced data may be missing or not updated as expected | Design existence checks, updates, and consistency at the business layer |
| Indexing every field or ignoring query patterns | Wastes write resources or causes slow reads | Base indexes on real queries and `explain("executionStats")` |
| Thinking `use shop` has already created and persisted the database | Database does not appear in listings before data is written | Create a collection/write test data and verify the result |

## 10. Design workflow when starting a feature

1. **List screens and operations:** view details, filter lists, update statuses, compute statistics.
2. **Identify the root document:** group fields that need to be read/written together; set reasonable bounds on arrays.
3. **Choose embedding vs. referencing:** evaluate ownership, sharing level, historical snapshots, and growth rate.
4. **Define the data contract:** field names, BSON types, `_id`, required fields, optional values, and conversion rules.
5. **Configure collections and indexes:** prioritize critical queries, avoid duplicate indexes; consider validators when needed.
6. **Map in Java:** use `@Document`, `@Id`, `@Field`, nested entities, and repository/`MongoTemplate` consistently.
7. **Test with representative data:** verify insert/read/update, type mapping, array queries, and performance with `explain`.

### Self-check scenario

A system needs to display an order with five line items and a shipping address, allowing users to view the order years later. At the same time, administrators must be able to edit current product details and customer profiles.

The right design is typically to keep `orders` independent, **embed the five line items along with snapshots of the shipping address/unit prices**, and **reference** `customers` and `products` by ID or SKU to access current data. This choice keeps viewing an order simple and protects transaction history from future changes.

## Key takeaways

A **database** partitions data scopes; a **collection** groups documents with the same purpose; a **BSON document** is the unit of storage and atomic updates. MongoDB allows flexible document structures, but applications still need a clear data contract. In Spring Data MongoDB, the document model determines Java mapping, the choice between repository and `MongoTemplate`, indexing strategy, and performance limits as data grows.
