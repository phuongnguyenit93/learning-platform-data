# Rules for Mapping the id Property and @Id to _id

## 1. Goal and Context

In MongoDB, each document in a collection has an identifier field `_id`. In Java, developers commonly use an `id` property. Spring Data MongoDB bridges these two representations: it determines which property represents the document key, converts the value to the appropriate BSON type, and converts it back when reading.

This is foundational knowledge in the **Identity and State** chapter of the **SPRING_DATA_MONGODB** module. When using Spring Data MongoDB to connect and map documents, write queries with `MongoTemplate` or repositories, test, and diagnose data issues, a small mistake with the `_id` type can cause a query to miss a record even when the ID string looks identical.

After this lesson, you will be able to:

1. Explain the relationship between the Java `id` property, the `@Id` annotation, and the BSON `_id` field.
2. Distinguish between `String` IDs and `ObjectId` IDs, especially when a string has a 24-character hexadecimal format.
3. Choose `@Id`, `@MongoId`, or an appropriate naming convention and predict the resulting BSON.
4. Understand how Spring Data generates/reads identifiers and write queries and repositories by ID.
5. Detect errors caused by ID type mismatches and design tests when changing identifier rules.

**Core message:** `id` is the property name in Java; `_id` is the identifier field name in MongoDB; **the BSON type stored in `_id` determines how MongoDB matches data**.

## 2. What Is Special About the _id Field?

A simple document in the `books` collection:

```javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  title: "MongoDB Fundamentals",
  price: 180000
}
```

MongoDB uses `_id` as the document's identifier key and creates a unique `_id_` index by default for standard collections. If the application does not provide `_id` on insert, the driver/server can generate an identifier value, typically a BSON `ObjectId`.

Key distinctions:

| Property / Term | Meaning |
| --- | --- |
| `_id` | The identifier field name used by MongoDB |
| `ObjectId("...")` | A BSON data type used as an identifier; not a field name |
| `id` | Common Java property name that Spring Data can map to `_id` |
| `@Id` | Spring Data annotation marking the identifier property |
| `@MongoId` | MongoDB-specific annotation for controlling the stored ID type |
| `_id_` index | Default index supporting uniqueness and key lookups |

**Do not equate `_id` with ObjectId.** MongoDB can store `_id` as a String, integer, or several other valid BSON types, depending on the design. However, the chosen type must remain consistent with the code, existing data, and any collections referencing that ID.

MongoDB does not allow changing the `_id` value of an existing document via a regular update operation. Therefore, the identifier should remain **stable throughout the document lifecycle**; mutable business attributes such as email or phone number should not be used as `_id` by default.

## 3. Default ID Mapping Rules in Spring Data MongoDB

`MappingMongoConverter` relies on entity metadata to convert Java properties into a document. Important rules:

1. A property annotated with `@Id` maps to the MongoDB `_id` field, **even if the Java property has a name other than `id`**.
2. If no `@Id` or `@MongoId` property is declared, a Java property named `id` is typically recognized by convention as the ID and mapped to `_id`.
3. `@MongoId` also marks the identifier property, but offers a more specific choice for the **target BSON type**.
4. With `@Id` and a `String` property, Spring Data MongoDB can convert a valid ObjectId string representation into a BSON ObjectId; if it cannot be converted, the string value can be stored as a BSON String.
5. Identifying an ID field **does not mean** every document must contain a Java field named `id`. You can declare a `documentKey` property and annotate it with `@Id`; it is still stored under `_id`.

Type conversion rules apply according to the project's version, converter, and configuration. For critical data, confirm by inspecting the actual BSON and running round-trip tests on the Spring Data version in use.

### 3.1. Same BSON, Two Different Java Property Names

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("books")
public record BookA(@Id String id, String title) {}

@Document("books")
public record BookB(@Id String documentKey, String title) {}
```

These two examples illustrate **ID mapping**, not a recommendation to use two different classes to operate on the same collection in a real application.

| Java model | Java ID property | BSON field |
| --- | --- | --- |
| `BookA` | `id` | `_id` |
| `BookB` | `documentKey` | `_id` |

With `BookB`, use `documentKey` in Java code and entity-aware query methods. The name `documentKey` does not cause MongoDB to create a separate identifier field.

### 3.2. Naming Convention Without Annotations

```java
import org.springframework.data.mongodb.core.mapping.Document;

@Document("books")
public record BookByConvention(String id, String title) {}
```

Here, the `id` property is mapped to `_id` by mapper convention. However, using `@Id` explicitly makes the intent clearer to code readers, especially when a model has multiple fields such as `bookId`, `externalId`, and `referenceId`.

**Do not annotate every field containing "Id".** For example, `authorId` may simply be a reference key pointing to an author, stored normally as `authorId`; it does not automatically become the book's `_id`.

### 3.3. Things You Should Not Infer

- `@Field("id")` must not be used as a general replacement for `@Id`; that annotation primarily specifies the stored field name.
- Having the `_id` field name in mongosh **does not mean** every Java object must declare a property named `_id`.
- Simply changing `@Id`/`@MongoId` in source code does not automatically change the types of existing keys in the database.
- A property named `id` does not automatically make an identifier meaningful to the business, safe to expose publicly, or predictable.

## 4. A Common Pitfall: @Id String and the ObjectId Type

### 4.1. Two Values That Look Identical but Are Not Equal

```javascript
// BSON ObjectId:
{ _id: ObjectId("507f1f77bcf86cd799439011") }

// BSON String:
{ _id: "507f1f77bcf86cd799439011" }
```

MongoDB matches on both **value and BSON type**. Therefore, the query:

```javascript
db.books.findOne({
  _id: "507f1f77bcf86cd799439011"
});
```

does not match a record whose `_id` is `ObjectId("507f1f77bcf86cd799439011")`, even though the string content looks identical.

### 4.2. Conversion Rules When Using @Id String

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("books")
public record Book(@Id String id, String title) {}
```

The following example illustrates the common default behavior of `MappingMongoConverter`:

| Java `id` value | Expected stored form in MongoDB |
| --- | --- |
| `"507f1f77bcf86cd799439011"` | `ObjectId("507f1f77bcf86cd799439011")` |
| `"BOOK-001"` | `"BOOK-001"` (BSON String) |
| `null` on insert | MongoDB/driver can generate an ID, typically ObjectId |

Point to remember: merely declaring `@Id String` **does not guarantee** that BSON `_id` is always a String. When an application-assigned ID happens to consist of exactly 24 hex characters, this causes subtle bugs in other applications using the driver directly or services not going through Spring Data.

The solution is to choose a clear, consistent identification policy from the outset, especially if IDs come from an external system, URL format, or historical migrated data.

## 5. Using @MongoId to Control the ID Type

`@MongoId` resides in the `org.springframework.data.mongodb.core.mapping` package. It also marks the property mapped to `_id`, but provides a `FieldType` option to express the desired BSON data type.

### 5.1. Keeping String IDs as BSON String

```java
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document("books")
public record BookWithStringId(
    @MongoId(FieldType.STRING) String id,
    String title
) {}
```

With a business-assigned string ID:

```java
new BookWithStringId(
    "507f1f77bcf86cd799439011",
    "Book with String ID"
);
```

Expected document:

```javascript
{
  _id: "507f1f77bcf86cd799439011",
  title: "Book with String ID"
}
```

This is a suitable choice if the entire system uses String IDs, even when they resemble an ObjectId. With `@MongoId` without specifying `FieldType`, the default handling preserves the natural data type rather than applying `@Id`'s rule of coercing String IDs; explicitly specifying `FieldType.STRING` makes the code easier to read and audit.

### 5.2. Intentionally Using BSON ObjectId

```java
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("books")
public record BookWithObjectId(
    @Id ObjectId id,
    String title
) {}
```

Java `ObjectId` corresponds directly to BSON ObjectId. When working with external JSON serialization/deserialization, it is often converted to its 24-character hex string representation. If an API accepts IDs from clients, validate the format before constructing an `ObjectId`.

Spring Data also lets you express the intent to use ObjectId via `@MongoId(FieldType.OBJECT_ID)` on a compatible property, though this still requires accounting for input type conversion. For models intended to use ObjectId, using the `ObjectId` type directly is usually less confusing.

### 5.3. ID Configuration Selection Table

| Declaration | Intent | Notes |
| --- | --- | --- |
| `String id` without annotation | Uses naming convention to detect `id` | Less explicit; requires conversion testing |
| `@Id String id` | String-typed ID in Java, converting to ObjectId when applicable | Data may contain both BSON String and ObjectId |
| `@Id ObjectId id` | Uses ObjectId as the identifier | Services/APIs must convert types appropriately |
| `@MongoId(FieldType.STRING) String id` | Keeps BSON String identifier | Suitable for business IDs or external IDs |
| `@MongoId(FieldType.OBJECT_ID) String id` | Requests mapping to BSON ObjectId | Must validate invalid values and round-trip behavior |

**Do not switch ID types on a collection that already contains data without a migration plan.** A String and an ObjectId with the same display text are still two distinct keys in MongoDB.

## 6. ID Generation on Insert and Its Impact on Entity Lifecycle

### 6.1. Example with an Unassigned ID

Suppose an entity is a class with a writable ID property:

```java
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("books")
public class MutableBook {
    @Id
    private ObjectId id;
    private String title;

    public MutableBook(String title) {
        this.title = title;
    }

    public ObjectId getId() {
        return id;
    }

    public void setId(ObjectId id) {
        this.id = id;
    }

    public String getTitle() {
        return title;
    }
}
```

When calling:

```java
MutableBook book = new MutableBook("Document Design");
mongoTemplate.insert(book);
ObjectId generatedId = book.getId();
```

If no ID is present yet, during a normal insert flow the MongoDB driver can generate a BSON ObjectId and Spring Data can populate the ID back onto the entity according to the storage mechanism of the version in use. With a **mutable entity** like this example, you can inspect `getId()` after the write call. With an immutable object, the returned result/instance and whether the ID field is updated must be checked against the actual API contract.

Do not assume an auto-generated ID will match every ID property type. If the business uses numeric IDs or IDs from an external system, the application may need to assign values according to its own rules.

### 6.2. Insert and Save Have Different Semantics

```java
mongoTemplate.insert(book); // Intent to add a new document.
mongoTemplate.save(book);   // Save or replace/upsert by ID, depending on state.
```

`insert` is meant to create a new document, so colliding on `_id` raises a duplicate key error. `save` has different semantics and can replace/upsert by ID; misusing it risks unintentionally overwriting data if the object holds stale data or omits fields.

For repositories:

```java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface BookRepository
    extends MongoRepository<BookWithObjectId, ObjectId> {
}
```

`repository.save(entity)` decides whether an entity is "new" or "existing" based on Spring Data's state detection mechanism (typically checking ID or `@Version`, customizable via `Persistable`). Consequently, an ID assigned by the application before saving can alter which execution branch is taken. When an API means "create new or report duplicate", design and test those semantics explicitly rather than inferring them from the name `save`.

### 6.3. ID Is Not @Version

`_id` identifies **which document**, whereas `@Version` supports **concurrency control** on appropriate entities. Both affect how Spring Data determines entity state, but they solve two different problems:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("inventory")
public class InventoryItem {
    @Id
    private ObjectId id;

    @Version
    private Long version;

    private int quantity;
}
```

This example only shows that the two annotations are separate. `@Version` must be used with compatible save/update flows to achieve optimistic locking; it does not turn `_id` into a field that changes on every write. Direct driver updates or update commands that do not follow version rules can bypass this mechanism.

## 7. Querying IDs with mongosh, MongoTemplate, and Repositories

### 7.1. Matching the Exact BSON Type

Suppose MongoDB has the following document:

```javascript
db.books.insertOne({
  _id: ObjectId("507f1f77bcf86cd799439011"),
  title: "Spring Data MongoDB"
});
```

Correct query in mongosh:

```javascript
db.books.findOne({
  _id: ObjectId("507f1f77bcf86cd799439011")
});
```

A query with the same display value but a different type will not match:

```javascript
db.books.findOne({
  _id: "507f1f77bcf86cd799439011"
});
```

### 7.2. Finding with MongoTemplate

With the `BookWithObjectId` entity:

```java
import org.bson.types.ObjectId;

ObjectId bookId = new ObjectId("507f1f77bcf86cd799439011");
BookWithObjectId book =
    mongoTemplate.findById(bookId, BookWithObjectId.class);
```

`findById` relies on entity metadata to look up by ID. There is no need to write the `_id` field name manually in this API.

When using `Query`:

```java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
    Criteria.where("id").is(bookId)
);
BookWithObjectId result =
    mongoTemplate.findOne(query, BookWithObjectId.class);
```

When `Query` is bound to `BookWithObjectId.class`, Spring Data uses metadata to map the Java property `id` to BSON `_id`. This approach is convenient when you need to combine ID with other criteria.

### 7.3. Finding with MongoRepository

```java
// Assume repository is an injected BookRepository bean.
ObjectId id = new ObjectId("507f1f77bcf86cd799439011");
var maybeBook = repository.findById(id);
```

The generic ID type must match the model: `MongoRepository<BookWithObjectId, ObjectId>` differs from `MongoRepository<BookWithStringId, String>`. The repository API uses metadata and converters, but cannot make a collection containing mixed stored types uniform solely through a generic declaration.

### 7.4. When Using Business-Assigned IDs

```java
import org.springframework.data.mongodb.core.mapping.MongoId;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document("purchase_orders")
public record PurchaseOrder(
    @MongoId(FieldType.STRING) String id,
    String customerId
) {}
```

Lookup command:

```javascript
db.purchase_orders.findOne({
  _id: "PO-2026-0001"
});
```

In Java, you can declare `MongoRepository<PurchaseOrder, String>` and call `findById("PO-2026-0001")`. Choose a business ID for `_id` when the value is **stable, uniquely issued, unlikely to undergo format changes**, and satisfies the collection's uniqueness scope. If `orderNo` is only unique per tenant, an independent technical ID paired with a unique compound index on `(tenantId, orderNo)` may be easier to operate.

## 8. Common System Design Mistakes Around _id

### 8.1. Equating MongoDB IDs with Public Authorization

`ObjectId` is a storage key type, not an authorization mechanism. An API accepting `id` from a client must still verify access permissions to the document. An endpoint fetching an order solely by `_id` without checking tenant/owner can cause data exposure.

```java
Query query = Query.query(
    Criteria.where("id").is(orderId)
        .and("tenantId").is(authenticatedTenantId)
);
var order = mongoTemplate.findOne(query, OrderDocument.class);
```

This snippet assumes `OrderDocument` has `id` and `tenantId` properties along with appropriate authorization checks in the service layer. The `_id_` index still selects the record by key; the tenant condition restricts the business scope.

### 8.2. Using _id as a Pagination Key Without Business Ordering

`ObjectId` contains a timestamp component, but it does not guarantee strict ordering of business events across machines or within the same second. If the requirement calls for "newest orders", use a business timestamp field (for example, `createdAt`) and add `_id` as a tie-breaker:

```javascript
db.orders.find({ tenantId: "tenant-a" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
```

When using this sort in a large system, review the appropriate compound index. Do not rely solely on `_id` order to infer order placement date, payment date, or processing date.

### 8.3. Changing the ID When Business Information Changes

Suppose an order number can change due to a data-entry typo or adjustments from an integrated external system. If `orderNo` is used as `_id`, modifying the order number becomes difficult because `_id` cannot be updated like a regular field.

Alternative design:

```javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenantId: "tenant-a",
  orderNo: "ORD-0007",
  status: "NEW"
}
```

With this design, `_id` stays stable. `orderNo` is a business attribute that can be updated according to rules and constrained as unique if needed.

### 8.4. Type Mismatch Between Key and Reference

```javascript
// orders
{ _id: ObjectId("507f1f77bcf86cd799439011") }

// order_events: storing the wrong type for the reference key
{ orderId: "507f1f77bcf86cd799439011", event: "CREATED" }
```

If joins or queries expect `orderId` to be an ObjectId, the string will not match. Maintain a **consistent BSON type convention** between `orders._id` and `order_events.orderId`, as well as in DTOs, message queues, and migration jobs.

## 9. Changing ID Rules on a Collection With Existing Data

When a project switches from `@Id String` to `@MongoId(FieldType.STRING)`, you cannot assume existing documents will have their types converted:

```javascript
// Existing Document A with an ObjectId _id.
{ _id: ObjectId("507f1f77bcf86cd799439011"), title: "A" }

// Existing Document B with a String _id.
{ _id: "507f1f77bcf86cd799439011", title: "B" }
```

These two documents have two distinct keys even though their text representations match. Editing the annotation does not merge them; actually changing the `_id` type requires a strategy to migrate records and related references.

Pre-migration analysis process:

1. Identify the **actual BSON type** of `_id` in each collection and across data eras.
2. Inventory ID creation sources: Spring Data, raw driver, imports, batch jobs, external integrations, or scripts.
3. Locate collections referencing the key and inspect their types and read/write rules.
4. Define the target final state: all Strings or all ObjectIds.
5. Plan document and reference migration since `_id` cannot be reassigned in place with `$set`; consider downtime, dual-sync, rollback, and unique constraints.
6. Test concurrent reads/writes across the deployed service versions.

**Note:** Do not run ad-hoc `{$set: {_id: ...}}` updates to "fix" a collection. MongoDB does not permit altering an existing document's `_id` key that way. For production systems, switching ID types is typically a high-impact data change requiring a dedicated rollout plan.

## 10. Inspecting Actual Types and Diagnosing Errors

### 10.1. Checking BSON Types in MongoDB

```javascript
db.books.aggregate([
  {
    $project: {
      _id: 1,
      idBsonType: { $type: "$_id" },
      title: 1
    }
  },
  { $limit: 20 }
]);
```

The output may report `idBsonType: "objectId"` or `idBsonType: "string"`. To inspect the distribution across the entire collection, use a `$group` pipeline by BSON type (this can be resource-intensive on large collections, so evaluate the environment and load before running):

```javascript
db.books.aggregate([
  { $group: {
      _id: { $type: "$_id" },
      count: { $sum: 1 }
  }},
  { $sort: { count: -1 } }
]);
```

### 10.2. Verifying Converter Round-Trip

Assuming `MongoConverter` is injected in a Spring application:

```java
import org.bson.Document;
import org.springframework.data.mongodb.core.convert.MongoConverter;

public void inspectIdMapping(MongoConverter converter) {
    BookWithStringId entity = new BookWithStringId(
        "507f1f77bcf86cd799439011",
        "Test Book"
    );

    Document bson = new Document();
    converter.write(entity, bson);

    Object storedId = bson.get("_id");
    System.out.println(storedId.getClass().getName());

    BookWithStringId loaded =
        converter.read(BookWithStringId.class, bson);
    System.out.println(loaded.id());
}
```

With `@MongoId(FieldType.STRING)`, the ID in `Document` is expected to be `String`. Try switching the test entity to `Book` using `@Id String` and verify conversion behavior with a 24-character hex string, an arbitrary string, and a null ID. This checks in-memory conversion, not server-side storage.

### 10.3. Common Errors

| Symptom | Possible Cause | Diagnostic Direction |
| --- | --- | --- |
| `findById` returns empty even though `_id` is visible in mongosh | String/ObjectId type mismatch | Check `$type` and the entity's ID type |
| Saving the first entity produces an unexpected key type | `@Id String` rule converts valid hex values to ObjectId | Inspect actual BSON; consider `@MongoId(FieldType.STRING)` |
| Two services share string IDs but cannot find each other's documents | One uses String, the other coerces to ObjectId | Standardize the BSON type contract |
| Creating a new entity with `save` overwrites data | ID was pre-assigned; new/existing state detection and save semantics | Review insert/save branches, `@Version`, and `Persistable` |
| Reference query or `$lookup` fails to match | Reference field type differs from `_id` type | Inspect both sides simultaneously |
| Changing ID type breaks old data | Annotation changed but legacy BSON did not | Design a migration and compatibility tests |
| Attempting to change `_id` with `$set` fails in MongoDB | `_id` cannot be updated in place | Choose a stable key; migrate data if necessary |

### 10.4. Observed Data Differs From Metadata

Mapping metadata indicates how Spring Data **expects** to store IDs. A collection may already contain documents written by legacy apps, ETL pipelines, or other drivers. Therefore, when debugging, cross-check:

```text
Java entity & annotations
        |
        v
MappingMongoConverter / expected ID type
        |
        v
Actual BSON document stored in MongoDB
        |
        v
Query/ID type sent by client
        |
        v
Query results and integration tests
```

If the converter writes correctly but queries fail, inspect how `_id` criteria are constructed, String/ObjectId conversion, and any direct driver API calls. If legacy BSON differs from expectations, prioritize migration analysis rather than continuing to tweak field names in the repository.

## 11. Guided Practice

Use the entities illustrated in previous sections; each exercise below is independent.

### Exercise 1. Predict the Stored Field and Type

**Prompt.** Given the model:

```java
@Document("samples")
record Sample(
    @Id String id,
    String externalId
) {}
```

Determine the MongoDB field names when creating `new Sample("507f1f77bcf86cd799439011", "EXT-01")` and describe the expected ID type.

**Solution.** The `id` property maps to `_id`; the `externalId` property keeps the name `externalId`. Under the default `@Id String` rule, a valid 24-character hex value can be stored as a BSON ObjectId:

```javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  externalId: "EXT-01"
}
```

### Exercise 2. Force Storing IDs as Strings

**Prompt.** An application needs to preserve all partner-supplied codes as BSON Strings, including strings formatted like ObjectIds. Choose the appropriate annotation.

**Solution:**

```java
@Document("partner_orders")
record PartnerOrder(
    @MongoId(FieldType.STRING) String id,
    String partner
) {}
```

Thus `_id` is intentionally stored as a BSON String. You still need duplicate ID checks, input normalization, and authorization.

### Exercise 3. Why Does mongosh Not Find It?

**Prompt.** A document has `_id: ObjectId("507f1f77bcf86cd799439011")`. The following command returns `null`:

```javascript
db.books.findOne({ _id: "507f1f77bcf86cd799439011" });
```

**Solution.** A BSON String does not equal a BSON ObjectId. Query with:

```javascript
db.books.findOne({
  _id: ObjectId("507f1f77bcf86cd799439011")
});
```

In Spring Data, confirm the entity's ID type and call `repository.findById(...)` or `mongoTemplate.findById(...)` with the matching type.

### Exercise 4. When Order Numbers Need to Change

**Prompt.** A system allows modifying `orderNo` after creation. Should `orderNo` or a technical key be used as `_id`?

**Solution.** For this requirement, use a stable technical `_id` and store `orderNo` as a business property. If `orderNo` must be unique within a tenant, add a unique compound index on `{ tenantId: 1, orderNo: 1 }`, aligned with the system's tenant/shard key design. Changing `orderNo` will not require changing `_id`; references to the order remain stable.

### Exercise 5. Inspecting a Collection With Mixed ID Types

**Prompt.** Data was imported from two systems: one stored `_id` as String, the other used ObjectId. How do you assess risk before changing annotations?

**Solution.** First, inventory `_id` types using `$type` and trace all write sources. Next, locate every reference to the ID, agree on a target type, and then build a migration plan and compatibility tests. Never merely swap `@Id` for `@MongoId` and assume the data is standardized.

## 12. Identity Review Checklist

| Question | Evidence to Confirm |
| --- | --- |
| Which Java property is the ID? | `@Id`, `@MongoId`, or `id` naming convention |
| Which physical field stores the ID? | BSON `_id` in an actual document |
| What is the stored ID type? | `$type`: `objectId`, `string`, or another type |
| Is a String ID converted to ObjectId? | Tests with valid hex strings and business strings |
| Where is the ID generated? | Application, Spring Data/driver, or external system |
| What happens on duplicate IDs? | Duplicate key on insert, error handling, and idempotency |
| Do ID queries enforce authorization? | Tenant/owner criteria and authorization tests |
| Do references store the same type as _id? | BSON of both collections and integration contracts |
| Does changing the model require migration? | Legacy data, indexes, APIs, and dependencies |

### Key Takeaways

1. `_id` is MongoDB's identifier field; `id` is the Java property name typically mapped to that field.
2. `@Id` marks the identifier property regardless of Java name, but `@Id String` **does not guarantee** the BSON type is always String.
3. `@MongoId(FieldType.STRING)` explicitly expresses the intent to store String IDs; `ObjectId` is the natural choice when the system adopts BSON ObjectId.
4. A 24-character hex string and a BSON ObjectId with the same text representation **are not the same type**; IDs must match across storage, queries, and references.
5. `_id` is a stable key that cannot be updated in place; `@Version` is a separate concurrency control mechanism.
6. Verify mappings using actual BSON, converter round-trips, and integration tests before changing an identification strategy.
