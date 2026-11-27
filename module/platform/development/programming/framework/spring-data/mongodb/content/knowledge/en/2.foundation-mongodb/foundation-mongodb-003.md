# The `_id` Field, `ObjectId`, and Document Identity

In MongoDB, every document in a collection needs an `_id` field to identify that exact document. When working with Spring Data MongoDB, this field is typically mapped to the `id` property of a Java entity. Understanding `_id`, the BSON `ObjectId` type, and type conversion rules helps prevent queries that fail to find data, duplicate key errors, and updating the wrong document.

After this lesson, you will be able to:

- Explain the role of `_id`, its default unique index, and the immutability of identifiers.
- Read, create, and query `ObjectId`, and understand the limits of the timestamp portion inside it.
- Choose and map identifiers using `@Id` and `@MongoId` in Spring Data MongoDB.
- Distinguish `ObjectId` from a 24-character hex string, and use the appropriate type when querying and designing APIs.
- Decide when to use technical identifiers vs. business keys, and how to diagnose related errors.

## 1. What is `_id`?

Example of a document in the `books` collection:

```javascript
{
  _id: ObjectId("665f1f2a4b6c7d8e9f001234"),
  title: "MongoDB Fundamentals",
  isbn: "978-604-00-0000-1",
  stock: 12
}
```

`_id` is the document's identifier key **within the scope of a single collection**. MongoDB automatically creates a unique index on `_id` (typically named `_id_`), enabling lookups and preventing two documents in the same collection from having the same `_id` value under BSON comparison rules. Two different collections may contain documents with the same `_id`.

Key properties:

| Property | Practical meaning |
| --- | --- |
| Present when stored | A persisted document always has `_id`. If not supplied, the driver or MongoDB generates a value, usually an `ObjectId`. |
| Unique within the collection | Inserting a document with a duplicate `_id` is rejected due to unique index violation. |
| Immutable after insertion | Updating or replacing a document cannot change its `_id` value. Changing an identifier requires a workflow to create a new document and handle references accordingly. |
| Has a BSON type | `_id` does not have to be `ObjectId`; you can use strings, numbers, UUID/Binary, or another valid BSON type subject to MongoDB limits. Do not use an array as the `_id` value. |
| Not an automatic foreign key | MongoDB does not automatically enforce relationships when another document stores a referencing `_id`. The application must guarantee any required integrity. |

Do not equate `_id` with business keys such as ISBN, employee code, or email. `_id` identifies the record; business keys may have different rules, such as changing over time, needing uniqueness per tenant, or requiring case normalization.

## 2. `ObjectId`: structure and meaning

`ObjectId` is a **12-byte** BSON type, usually displayed as **24 hexadecimal characters**. A commonly generated `ObjectId` has the structure:

| Component | Length | Role |
| --- | ---: | --- |
| Timestamp | 4 bytes | Seconds since the Unix epoch, reflecting the identifier creation time at 1-second resolution. |
| Random value | 5 bytes | A component typically generated once per process, helping reduce collisions across ID-generating environments. |
| Counter | 3 bytes | An incrementing value per generated ID, helping distinguish multiple IDs created close together. |

For example, the string `665f1f2a4b6c7d8e9f001234` is only the **display representation** of a BSON `ObjectId` value. It does not automatically become an `ObjectId` merely by being 24 characters long. A document storing `_id` as a String and a document storing `_id` as an ObjectId have **two differently typed identifiers**, even when the character strings look identical.

You can generate an `ObjectId` and read its timestamp in `mongosh`:

```javascript
const id = new ObjectId();
print(id.toHexString());   // Example: 24-character hex string
print(id.getTimestamp());  // UTC date/time from the 4-byte timestamp
```

### Do not confuse the timestamp in `ObjectId` with `createdAt`

`ObjectId` generally increases roughly with creation time, making it convenient for some approximate sorting patterns. However, it **does not guarantee strict creation ordering**: its resolution is only to the second, different machines have different clocks, and the ID may be generated before the document is actually written to the database. Therefore:

- Use a dedicated `createdAt` field when you need record creation time for business logic, auditing, or accurate filtering.
- Use a dedicated `updatedAt` field when you need to track modification time.
- Do not assume `ObjectId` is a secret or authorization token: anyone holding an ID must still pass access control checks.

## 3. Practicing with `mongosh`

### 3.1. Letting MongoDB auto-generate `_id`

```javascript
use library

const result = db.books.insertOne({
  title: "Spring Data MongoDB",
  stock: 8
});

const bookId = result.insertedId;
printjson(bookId);
printjson(db.books.findOne({ _id: bookId }));
```

When `_id` is omitted, a normal insert generates an `ObjectId`. The value returned via `insertedId` can be used directly in subsequent queries, avoiding manual re-entry.

### 3.2. String IDs and `ObjectId` are two different types

```javascript
const hex = "665f1f2a4b6c7d8e9f001234";

db.books.insertOne({ _id: new ObjectId(hex), title: "ObjectId-typed ID" });
db.books.insertOne({ _id: hex, title: "String-typed ID" });

db.books.findOne({ _id: new ObjectId(hex) }); // First document
db.books.findOne({ _id: hex });               // Second document
```

Both inserts succeed because `_id` has different **BSON types**, even though the displayed text looks the same. Querying with a string will not match the corresponding `ObjectId`, and vice versa. This is a common cause when direct queries on MongoDB and a Spring Data application return different results than expected.

### 3.3. Checking duplicate identifiers

```javascript
db.books.insertOne({ _id: "book-001", title: "Copy A" });
db.books.insertOne({ _id: "book-001", title: "Copy B" });
// The second command fails with a duplicate key error (E11000).
```

This operation is purely illustrative on test data. When creating new records, handle duplicate ID errors explicitly; avoid automatically substituting `save`/upsert when the requirement is "create only if it does not already exist."

## 4. Mapping `_id` in Spring Data MongoDB

Spring Data MongoDB maps Java entities to BSON documents, supporting both `MongoRepository` and `MongoTemplate`. Annotations used in the examples:

| Annotation | Purpose |
| --- | --- |
| `@Document(collection = "books")` | Specifies the collection containing the entity. |
| `@Id` | Marks the property as the identifier mapped to `_id`; includes String ↔ ObjectId conversion when feasible. |
| `@MongoId` | Marks the `_id` property with more explicit control over the stored type; by default preserves the declared type instead of coercing String to ObjectId like `@Id`. |
| `@MongoId(FieldType.OBJECT_ID)` | Requests storing the identifier as BSON ObjectId, used when you intentionally want type conversion. |

### 4.1. Approach 1: storing the ID as `ObjectId` in Java

This is a straightforward choice when the application uses `ObjectId` as its technical identifier:

```java
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "books")
public class Book {
    @Id
    private ObjectId id;
    private String title;

    protected Book() {} // For data mapping

    public Book(String title) {
        this.title = title;
    }

    public ObjectId getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
```

Declare the repository with the **exact ID type of the entity**:

```java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface BookRepository extends MongoRepository<Book, ObjectId> {
}
```

Usage:

```java
Book saved = bookRepository.insert(new Book("Spring Data MongoDB"));
ObjectId id = saved.getId(); // ID assigned on insert

Book found = bookRepository.findById(id)
    .orElseThrow(() -> new IllegalStateException("Book not found"));
```

When receiving an ID via a REST path as a string, validate/parse it at the API boundary:

```java
String pathId = "665f1f2a4b6c7d8e9f001234";
if (!ObjectId.isValid(pathId)) {
    throw new IllegalArgumentException("Invalid ObjectId format");
}
ObjectId id = new ObjectId(pathId);
Book book = bookRepository.findById(id)
    .orElseThrow(() -> new IllegalStateException("Book not found"));
```

In a real application, the API should return `400 Bad Request` when the ID format is invalid and `404 Not Found` when the ID is valid but no document exists. Authorization checks on the document must be performed independently of whether the ID is valid.

### 4.2. Approach 2: Java uses `String` while MongoDB stores `ObjectId` when possible

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "books")
public class BookWithStringId {
    @Id
    private String id;
    private String title;
}
```

With `@Id String id`, Spring Data MongoDB typically converts strings in valid `ObjectId` format into BSON `ObjectId` when saving or querying. Strings that cannot be converted are stored as BSON String. When an ID is auto-generated for this entity, Java receives the string form of the generated `ObjectId`.

Consequence: two input IDs that both have Java type `String` may be stored using **two different BSON types**. Do not rely on "looking like 24 hex characters" to conclude that the field in the database is a String; check the actual stored value or choose explicit mapping.

### 4.3. Approach 3: keeping ID as String with `@MongoId`

If the business identifier is `"book-001"`, `"vn-hcm-001"`, or if you want even 24-character hex strings to be stored **as BSON String**, you can declare:

```java
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "catalog_items")
public class CatalogItem {
    @MongoId
    private String id;
    private String title;

    protected CatalogItem() {}

    public CatalogItem(String id, String title) {
        this.id = id;
        this.title = title;
    }
}
```

In this case, the application explicitly supplies the string ID when creating the entity. If you need `ObjectId` in the database while keeping the Java property as `String`, `@MongoId(FieldType.OBJECT_ID)` is the explicit option; make sure the String value can be validly converted. Avoid mixing multiple identifier strategies in the same collection unless there is an explicit requirement and conversion tests.

## 5. Finding, updating, and immutability

Once an ID type is chosen, use it consistently in repositories and queries:

```java
// If Book.id is ObjectId:
ObjectId id = new ObjectId("665f1f2a4b6c7d8e9f001234");
bookRepository.findById(id);
bookRepository.existsById(id);
```

With `MongoTemplate`, query against the entity class so the Spring Data mapper has full context to handle field names and values:

```java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

ObjectId id = new ObjectId("665f1f2a4b6c7d8e9f001234");
Query query = Query.query(Criteria.where("id").is(id));
Book found = mongoTemplate.findOne(query, Book.class);
```

In this example, the `id` property of `Book` is mapped to the MongoDB `_id` field. When using the MongoDB driver directly or writing raw JSON queries, the actual field name is `_id` and the value must have the right BSON type.

You cannot update `_id` of an existing document:

```javascript
// Attempting to change _id will be rejected by MongoDB.
db.books.updateOne(
  { _id: "book-001" },
  { $set: { _id: "book-002" } }
);
```

If a business code needs to change, a better model is usually keeping `_id` stable and placing that code in a separate field (with a unique index if required). This avoids having to update documents referencing the old ID.

Distinguish two operations at the Spring Data layer:

- `insert(entity)` is for **creating new documents**. If `_id` already exists, MongoDB rejects it with a duplicate key error.
- `save(entity)` can update/replace an existing document when an ID is already assigned (depending on entity state and versioning). Do not use `save` as a workaround to avoid duplicate errors when business logic requires preventing overwrites.

For concurrent updates, you can use `@Version` (optimistic locking) or appropriate conditional update operations; the `_id` index alone only guarantees identifier uniqueness, not content conflict resolution.

## 6. Choosing an identifier strategy

| Strategy | Suitable when | Considerations |
| --- | --- | --- |
| `ObjectId` | Need an auto-generated technical ID with no business meaning, widely used with MongoDB. | APIs usually represent it as a hex String; must parse to the right type. Its timestamp does not replace `createdAt`. |
| Structured String ID | Need a meaningful code, already provided by another system, or using an external key from another service. | Guarantee unique generation, avoid changing values, and avoid overly long strings that inflate index size. |
| UUID (BSON Binary) | System already standardizes on UUIDs or needs independent ID generation across systems. | Standardize representation/codec; string UUID and BSON Binary UUID are two different types. |
| Business key in a separate field | ISBN, SKU, email, or codes that change with workflow. | Create a unique index according to business rules, possibly a compound index with `tenantId`. |

For example, a multi-tenant system can keep `_id: ObjectId(...)`, with `tenantId` and `sku` as separate fields, and create a unique index on the pair:

```javascript
db.products.createIndex(
  { tenantId: 1, sku: 1 },
  { unique: true, name: "uniq_tenant_sku" }
);
```

That way, the same SKU can appear in two different tenants but cannot repeat within one tenant. The uniqueness scope of `_id` remains the collection; the compound index expresses a different **business rule**.

**Sharding note:** in a sharded collection, if `_id` is not the shard key, enforcing global uniqueness of `_id` across the entire cluster must be designed carefully; `_id` uniqueness may only be enforced per shard. Do not assume that the `_id` index mechanism solves every cross-shard uniqueness requirement.

## 7. Inspecting indexes and diagnosing errors

Check available indexes and execution plans with `mongosh`:

```javascript
db.books.getIndexes();

db.books.find({
  _id: new ObjectId("665f1f2a4b6c7d8e9f001234")
}).explain("executionStats");
```

`explain` output depends on the MongoDB version and query executor. Inspect `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, and the number of documents returned to evaluate it, rather than looking for a single fixed stage name.

When an ID lookup returns nothing or an insert fails, check in order:

1. **Right collection/database?** A valid `_id` in collection A does not mean it exists in collection B.
2. **Right BSON type?** Use `ObjectId("...")` for ObjectId data and plain strings for String data; check `@Id`/`@MongoId` on the entity.
3. **Does the ID actually exist?** `ObjectId.isValid(...)` only checks format, not existence.
4. **Is a unique index violated?** An `E11000 duplicate key` error can come from `_id` or another unique index; read the index name in the error message.
5. **Are you trying to modify `_id`?** MongoDB rejects updates that change the identifier.
6. **Are you using `save` for creation?** Review its overwrite/upsert behavior and consider `insert`.

When writing integration tests, cover at least: creating a document without an ID, querying back by the returned ID, attempting a duplicate-ID insert, and testing mismatched String/ObjectId queries. With Spring Data, you can use Testcontainers MongoDB or a test MongoDB instance to verify the **actual BSON type**, rather than only checking the Java ID string.

## 8. Self-practice exercises

1. Create two documents with `_id` values `ObjectId("665f1f2a4b6c7d8e9f001234")` and `"665f1f2a4b6c7d8e9f001234"`, respectively. Write two separate queries to retrieve each exact document; explain why MongoDB allows both to exist.
2. Write a `Customer` entity with `@Id ObjectId id`, its corresponding repository, and an API accepting a path ID as a string. Handle invalid ID format and nonexistent document cases separately.
3. Write an `InventoryItem` entity using `@MongoId String id` with a business-assigned code; test a 24-character hex ID and verify that it is still stored as BSON String.
4. Design multi-tenant product data: propose `_id`, `tenantId`, `sku`, required unique indexes, and how to handle when a product's SKU is allowed to change.

### Key takeaways

`_id` is the stable and unique identifier of a document within a collection. `ObjectId` is a **BSON type**, whereas a hex string is only a representation of it. When using Spring Data MongoDB, declare and maintain a consistent ID type from the entity, repository, and query all the way to the API; choose `@Id` or `@MongoId` intentionally for conversion behavior. Place business keys in separate fields whenever business rules differ from document identity rules.
