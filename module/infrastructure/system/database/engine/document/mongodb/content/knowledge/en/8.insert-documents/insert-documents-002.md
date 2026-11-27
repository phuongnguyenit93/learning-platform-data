# Auto-Generated `_id` and Application-Provided Identifiers in MongoDB

## 1. Every Document Needs an Identifier

When inserting data into a collection, MongoDB needs to distinguish one document from every other document in the same collection. The special **`_id`** field serves that role: it establishes the identity of the document and acts as the key to find, update, or delete an exact record.

For example, the `orders` collection has two orders:

```javascript
{
  _id: ObjectId("6718d4e0b7e24f52b064a001"),
  orderNumber: "VN-2026-0042",
  customerId: "C01",
  status: "NEW"
}

{
  _id: ObjectId("6718d4e0b7e24f52b064a002"),
  orderNumber: "VN-2026-0043",
  customerId: "C02",
  status: "PAID"
}
```

Here there are **two types of identifiers**:

- `_id`: the document identifier used by MongoDB and the driver.
- `orderNumber`: the order code following business rules, used in the UI, emails, or invoices.

The two fields can be different, and that is often an intentional choice. An application can also use the order code directly as `_id`, but first it must determine the requirements regarding uniqueness, mutability, data type, and code generation workflow.

### Fundamental Rules of `_id`

1. Every document stored in a regular collection has an `_id`.
2. In a regular collection, MongoDB creates a **unique index** on `_id` and does not allow two documents to have the same key value under that index's comparison rules.
3. Once inserted, a document's `_id` value **cannot be updated** via `$set` or replacement operations. When identity needs to change, the application typically must create a new document and handle migrating data/references at the business level.
4. `_id` is not required to be of type `ObjectId`; several other BSON types, such as String, numbers, or UUIDs stored as Binary, can also be used when valid.
5. Uniqueness of `_id` **does not mean a value must be unique across all collections or all databases**.

For sharded collections, there is an important additional condition regarding where uniqueness constraints are enforced across shards; Section 11 explains this.

## 2. Auto-Generating `_id`: The Default Case

When inserting a document without providing the `_id` field, MongoDB and standard drivers automatically ensure an identifier is added to the document. By default convention, the generated value is a **BSON ObjectId**.

```javascript
// Example run in mongosh.
db.customers.insertOne({
  name: "Nguyen An",
  email: "an@example.test"
});
```

Example response:

```javascript
{
  acknowledged: true,
  insertedId: ObjectId("6718d4e0b7e24f52b064a010")
}
```

The ObjectId value above is just an **illustrative example**. Each run on different data can generate a different ID. If you read back the saved document:

```javascript
db.customers.findOne({
  _id: ObjectId("6718d4e0b7e24f52b064a010")
});
```

you see that `_id` is a field in the document, even though the original `insertOne()` statement did not specify it.

### 2.1. Who Actually Creates the ObjectId?

Many MongoDB drivers **generate `_id` on the application side before sending the `insert` command**. This way, the application can know the identifier early and the server receives a document that already has `_id`. If a document arrives at the server missing `_id`, the server also has a mechanism to assign an `ObjectId` upon insertion.

Therefore, saying "MongoDB auto-generates `_id`" is merely a summary of overall behavior. You should not assume every ID generation happens **after** the server writes the data. Where the ID is generated also depends on the API, driver, codec type, and how the command is sent.

### 2.2. Auto-Generation Does Not Mean the ID Can Be Used for Security

ObjectId helps identify a document, but it **is not a password, login token, or authorization mechanism**. Knowing an `_id` does not automatically grant permission to read the document. The application must enforce permission checks and user/tenant data scoping when querying.

Similarly, `_id` does not replace `createdAt`, does not represent absolute business order, and does not by itself prove that a write operation has been durably acknowledged.

## 3. What Does an ObjectId Consist Of?

An ObjectId is a **12-byte** BSON value. When displayed in mongosh, it is typically represented as **24 hexadecimal characters**:

```text
ObjectId("6718d4e0b7e24f52b064a010")
          |------ 24 hex chars ------|
          |---| |--------| |----|
           4B       5B       3B
         timestamp  random   counter
```

In standard ObjectId generation:

| Component | Length | Role |
|---|---:|---|
| Timestamp | 4 bytes | Seconds since the Unix epoch |
| Process-specific random value | 5 bytes | Reduces collision likelihood across processes/machines |
| Incrementing counter | 3 bytes | Distinguishes ObjectIds generated consecutively within the same process |

MongoDB uses this structure to produce identifiers with a **very low collision probability** without needing to send a request to a central sequence generator for each document. This is not a mathematical proof that collisions are impossible, so the unique index is still necessary to detect actual conflicts.

### 3.1. Extracting Time from an ObjectId

In mongosh:

```javascript
const id = ObjectId();

print(id.toString());           // Form ObjectId("...") depending on shell context.
print(id.toHexString());        // 24 hex characters.
print(id.getTimestamp());       // UTC date/time, 1-second resolution.
```

`getTimestamp()` returns the time encoded in the ID at **one-second resolution**. This time is typically when the process generated the ID, **not necessarily** when the data was successfully inserted or committed on the server. Possible scenarios include:

- The application generates the ID and waits before sending the data.
- Machines generating IDs have clock skew.
- Data is imported from a legacy system with pre-existing ObjectIds.
- One process generates multiple IDs within the same second.

If the business logic requires an exact order creation timestamp, store a separate field such as `createdAt` of type BSON Date, with rules defining the time source and timezone.

### 3.2. Is ObjectId Monotonically Increasing?

ObjectIds generated close together within **a single process** tend to increase over time, but global ordering across multiple machines, multiple processes, or all inserts is not guaranteed. Therefore, the query:

```javascript
db.orders.find().sort({ _id: -1 }).limit(10);
```

can be useful for some data-inspection scenarios, but should not be the official definition of "the 10 most recently created orders." For strict business requirements, use `createdAt` and a stable secondary key to break ties:

```javascript
db.orders.find()
  .sort({ createdAt: -1, _id: -1 })
  .limit(10);
```

When data grows large, you need to design an index matching the filter and sort conditions; adding `createdAt` does not automatically guarantee fast queries.

## 4. Application-Provided `_id`

MongoDB allows a document to have an application-chosen `_id`. When the field is provided, the driver/server **must not interpret it as a request to generate a replacement ID**. If the ID collides with an existing document, the insert operation is rejected by the unique index.

### 4.1. Using a String as the ID

```javascript
db.orders.insertOne({
  _id: "ORDER-VN-2026-0042",
  customerId: "C01",
  status: "NEW"
});

db.orders.findOne({ _id: "ORDER-VN-2026-0042" });
```

Advantages:

- Easy to read and easy to look up in logs or when exchanging data with external systems.
- Can use a deterministic code generated from an event or business rule.
- Avoids managing a mapping table between a business code and `_id` when the two are truly identical.

Disadvantages:

- If values are long, indexes and storage keys are typically larger than a 12-byte ObjectId.
- If it has a composite structure like branch code, year code, and sequence number, you must handle code allocation, collisions, numbering contention, and rule changes.
- If the ID can be renamed for business reasons, using it as an immutable key introduces complexity.

### 4.2. Using an Integer

```javascript
db.products.insertOne({
  _id: NumberLong("100045"),
  name: "Mechanical Keyboard",
  price: NumberDecimal("1200000")
});

db.products.findOne({ _id: NumberLong("100045") });
```

MongoDB permits numeric identifiers when valid. However, MongoDB **does not automatically provide** an equivalent to relational `AUTO_INCREMENT` columns just because `_id` is numeric. If you want consecutive `100045`, `100046`, `100047`..., the application must design a safe numbering mechanism under concurrent writes.

A centralized counter collection with `findOneAndUpdate` + `$inc` can allocate numbers atomically, but it adds an extra write command and can become a bottleneck under heavy load. You must decide whether consecutive numbers are truly required or only unique IDs are needed.

### 4.3. Using a UUID

UUID is also an option when IDs must be generated independently across multiple systems. MongoDB supports storing UUIDs as BSON Binary subtype 4 when configured properly, or the application can proactively store the string representation of a UUID:

```javascript
// Simple approach: store an application-generated UUID as a String.
db.events.insertOne({
  _id: "c844f8c4-6a35-48cb-91b5-70db31f404f7",
  type: "ORDER_CREATED"
});
```

UUID strings are typically longer than the 16-byte Binary form and have different index characteristics. If using BSON Binary UUID in Java or other drivers, you must standardize the **UUID representation** across applications, especially when the system holds legacy data from different UUID representation modes.

### 4.4. `_id` Is a BSON Value, Not Just Display Text

The two identifiers below **differ in type**:

```javascript
{
  _id: ObjectId("6718d4e0b7e24f52b064a010"),
  label: "ObjectId"
}

{
  _id: "6718d4e0b7e24f52b064a010",
  label: "String"
}
```

A query `findOne({ _id: "6718..." })` is not equivalent to `findOne({ _id: ObjectId("6718...") })`. Do not pass a driver-returned ID as text and assume it will match a BSON ObjectId without type conversion.

Similarly, `"42"` is a String whereas `NumberLong("42")` is a number. BSON numeric types have their own comparison rules and can compare equal in value in certain cases; therefore, choose **one consistent ID type** for the entire collection instead of intentionally mixing types.

### 4.5. Not Every BSON Value Is Suitable for `_id`

MongoDB imposes restrictions on the types and shapes of the `_id` field. In particular, do not use an **array** as `_id`. Values with complex or unstable structures are also generally unsuitable as keys because they are difficult to compare, log, and pass through APIs.

In new designs, prefer a **small, stable, strongly typed, and uniquely generatable** value instead of cramming multiple business attributes into `_id`.

## 5. `insertOne()` Examples: Default and Self-Assigned IDs

### 5.1. Omitting `_id`

```javascript
const resultA = db.samples.insertOne({
  kind: "generated",
  description: "Let driver/MongoDB assign ID"
});

printjson(resultA);
```

The inserted document gets an ObjectId `_id` by default behavior. `insertedId` in the result is the ID of the submitted document, allowing the application to link subsequent tasks.

### 5.2. Passing a Stable String ID

```javascript
const resultB = db.samples.insertOne({
  _id: "sample-B",
  kind: "application-assigned"
});

printjson(resultB.insertedId); // "sample-B"
```

If another document with `_id: "sample-B"` is inserted into the same collection, MongoDB will report a duplicate key error.

### 5.3. Generating ObjectId Before Calling `insertOne()`

Even when choosing ObjectId, the application can still **proactively generate the ID**:

```javascript
const orderId = ObjectId();

db.orders.insertOne({
  _id: orderId,
  customerId: "C01",
  status: "NEW"
});

print(orderId.toHexString());
```

This is useful when a workflow needs to keep the ID stable across multiple attempts or attach it to another command. However, **knowing the ID in advance does not mean the document definitely exists**: after a network error, you still must check the write result or use a safe retry mechanism.

### 5.4. Inserting Multiple Documents with Both Auto-Generated and Application-Provided IDs

```javascript
db.samples.insertMany([
  { kind: "generated-1" },
  { _id: "external-01", kind: "custom" },
  { kind: "generated-2" }
]);
```

Documents missing `_id` receive an assigned identifier. The document with `"external-01"` keeps its provided ID. The result of a bulk insert can return the inserted IDs indexed by the input documents' positions.

If a batch contains duplicate IDs, whether it stops or continues with other documents depends on options like `ordered` and the error type. You should not assume a multi-insert batch is **an atomic transaction**.

## 6. Java MongoDB Driver: Working with ObjectId and Self-Assigned IDs

The examples below use the **MongoDB Java Sync Driver** and `org.bson.Document`. The goal is to illustrate how to assign and read identifiers; connection configuration, authentication, and `MongoClient` lifecycle management must suit a production application.

### 6.1. Letting the Driver Generate ObjectId

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.result.InsertOneResult;
import org.bson.Document;
import org.bson.types.ObjectId;

public class GeneratedIdExample {
    public static void main(String[] args) {
        String uri = "mongodb://localhost:27017";

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database = client.getDatabase("learn_id");
            MongoCollection<Document> orders = database.getCollection("orders");

            Document order = new Document("customerId", "C01")
                    .append("status", "NEW");

            InsertOneResult result = orders.insertOne(order);
            ObjectId id = result.getInsertedId().asObjectId().getValue();

            System.out.println("Inserted _id: " + id.toHexString());
            Document stored = orders.find(new Document("_id", id)).first();
            System.out.println(stored);
        }
    }
}
```

Points to remember:

- `InsertOneResult.getInsertedId()` provides the BSON ID of the acknowledged insert operation.
- `asObjectId()` is only valid when the ID is actually an ObjectId. For String or Binary UUID IDs, read the matching type.
- If the write operation is unacknowledged or fails, do not casually call `getInsertedId()` and treat it as proof the data committed. Handle exceptions and write concern requirements properly.

Many driver versions may populate `_id` into the input `Document` when encoding the insert operation, but using `InsertOneResult` clearly expresses receiving the command's ID.

### 6.2. Self-Assigning ObjectId in Java

```java
ObjectId id = new ObjectId();

Document order = new Document("_id", id)
        .append("customerId", "C02")
        .append("status", "NEW");

orders.insertOne(order);

// Use the exact BSON ObjectId when querying.
Document stored = orders.find(new Document("_id", id)).first();
```

Here `new ObjectId()` generates the value in the application, while MongoDB is responsible for checking uniqueness via the index on write.

### 6.3. Self-Assigning a Business String in Java

```java
String orderId = "ORDER-VN-2026-0042";

Document order = new Document("_id", orderId)
        .append("customerId", "C03")
        .append("status", "PAID");

orders.insertOne(order);

// Do not convert this string to ObjectId.
Document stored = orders.find(new Document("_id", orderId)).first();
```

If the same code is used again, the server detects the duplicate ID. The program must decide whether that is a **business error**, a **retry of the same request**, or **evidence of two requests contending for one code**.

### 6.4. Using an Application-Generated UUID

```java
import java.util.UUID;

String eventId = UUID.randomUUID().toString();

Document event = new Document("_id", eventId)
        .append("type", "ORDER_CREATED");

events.insertOne(event);
```

In this example the UUID is stored as a **BSON String** because the Java code called `toString()`. If you want to store the UUID as BSON Binary subtype 4, you must use the appropriate BSON/codec type and standardize the representation. The two storage formats are **not equivalent** in queries.

## 7. Uniqueness Rules, Duplicate Errors, and Immutability of `_id`

### 7.1. Duplicate Key Is Normal Behavior on ID Collision

```javascript
db.orders.insertOne({
  _id: "ORDER-0001",
  status: "NEW"
});

db.orders.insertOne({
  _id: "ORDER-0001",
  status: "PAID"
});
```

The second command will not create a new order with the same `_id`. The server reports a duplicate key error, typically identified by code **11000** and a message containing `E11000 duplicate key error`. The failed insert **does not automatically update** the existing document.

It is important not to handle every duplicate error the same way:

- Two genuinely different requests picking the same code: detect the collision and assign a new code or report a business error.
- A request retried after a timeout: the document may already exist because the earlier attempt succeeded; verify whether it belongs to **the same logical transaction**.
- The same code used for different payload content: never treat it as success merely because the key already exists.

### 7.2. Cannot Modify `_id` with `$set`

```javascript
// Invalid: MongoDB does not allow changing a document's _id.
db.orders.updateOne(
  { _id: "ORDER-0001" },
  { $set: { _id: "ORDER-0002" } }
);
```

Document replacement commands also cannot change the `_id` value of an existing document. If a business order code can change after issuance, it is usually better to keep that code in an `orderNumber` field and keep `_id` as a stable internal identifier.

### 7.3. `_id` Constraints and Business Constraints Are Separate

For example, if you want `orderNumber` to be unique within a single business/tenant:

```javascript
db.orders.createIndex(
  { tenantId: 1, orderNumber: 1 },
  { unique: true }
);
```

When using an ObjectId `_id`, a unique compound index on `tenantId, orderNumber` enforces a **separate business rule**. A customer could submit two requests with two different ObjectIds but the same order code; `_id` alone cannot prevent `orderNumber` collisions.

For sharded collections, unique indexes also carry constraints related to the shard key. Before deploying a unique compound index in a sharded cluster, verify whether the shard key configuration allows cluster-wide uniqueness enforcement.

## 8. ID Assignment and the Request Retry Problem

In real systems, an application can send `insertOne()`, the server writes successfully, and then the connection drops before the response returns. The application does not always know whether the insert occurred. That is why **ID choice affects retry behavior**.

### 8.1. Generating a New ID per Retry Can Create Business Duplicates

Suppose an HTTP order-creation request times out:

```text
POST /orders (request X)
        |
        v
Application generates ObjectId A
        |
        v
MongoDB writes order A successfully
        |
       response lost
        |
        v
Application retries request X
        |
        v
Application generates ObjectId B
        |
        v
MongoDB writes order B successfully
```

From the database perspective, A and B have different `_id`s, so the unique index does not prevent both documents. Business-wise, however, they may represent **the same order**.

Do not confuse this with the driver's **retryable writes**. When a driver supports retryable writes, it uses session info and operation sequence numbers to handle certain transient errors at the protocol level. That is different from an application rebuilding a request, generating a new `_id`, and submitting a new operation.

### 8.2. Keeping a Stable ID for the Same Logical Request

One solution is to determine an identifier at the request level and reuse it across all attempts:

```javascript
// requestId was generated beforehand and kept constant across retries.
const requestId = "REQ-2026-10-001";

db.orders.insertOne({
  _id: requestId,
  customerId: "C01",
  status: "NEW"
});
```

If an order with that `_id` already exists, the retried insert fails with a duplicate key error. On encountering the error, the application can look up the document by the same `_id`, compare the data or request verification token, and then decide to return the previous result. **Never treat a duplicate key as success if the content or ownership does not match.**

### 8.3. Using an Internal ObjectId and a Separate Idempotency Key

You do not have to use the request key as `_id`. For example, a multi-tenant API can keep ObjectId as its internal ID while setting a business constraint:

```javascript
db.orders.createIndex(
  { tenantId: 1, requestKey: 1 },
  { unique: true }
);

db.orders.insertOne({
  tenantId: "T01",
  requestKey: "REQ-2026-10-001",
  customerId: "C01",
  status: "NEW"
});
```

On retry, the application uses the **same `tenantId` and `requestKey`**. The unique index prevents adding another document for the same request key within that tenant. Ensure the request key is only used for the same business payload, has appropriate retention rules, and cannot be reused across accounts.

### 8.4. Upsert with `$setOnInsert`

If the business logic wants "insert if it does not exist; otherwise keep it unchanged," you can use `updateOne()` with `upsert: true`:

```javascript
db.orders.updateOne(
  { _id: "REQ-2026-10-001" },
  {
    $setOnInsert: {
      customerId: "C01",
      status: "NEW",
      createdAt: ISODate("2026-10-20T09:00:00Z")
    }
  },
  { upsert: true }
);
```

When `_id` already exists, the operation does not create a new document; when `_id` does not exist, it inserts the document. The unique index prevents two documents with the same `_id` when multiple requests arrive concurrently. Under concurrent contention, an operation may still receive a duplicate key or transient error depending on conditions, so the application should handle retries and readbacks appropriately.

Do not use `$set` to overwrite all business fields on every attempt if the goal is "create exactly once"; `$setOnInsert` clearly separates **data used only upon creation**.

If the request involves steps outside MongoDB such as charging payment or sending email, an idempotent insert **does not automatically guarantee the entire external workflow runs only once**. Dedicated business mechanisms and state tracking are needed for those side effects.

## 9. Should `_id` Be an Auto-Generated Key or a Business Key?

### 9.1. Surrogate Key

A key carrying no business meaning, such as an ObjectId or random UUID:

```javascript
{
  _id: ObjectId("6718d4e0b7e24f52b064a020"),
  employeeCode: "EMP-001",
  email: "an@example.test",
  fullName: "Nguyen An"
}
```

The advantage is that the ID remains stable even if email or employee code changes. It fits long-lived documents referenced by many collections whose business attributes may be updated.

The disadvantage is that the application sometimes needs an extra unique index for the business code and must pass/query both `_id` and that code.

### 9.2. Natural Key

A field that already has business meaning and is defined as unique, such as a catalog code that never changes:

```javascript
{
  _id: "COUNTRY-VN",
  displayName: "Vietnam"
}
```

The advantage is simplicity in systems where the code is already stable, small, and standardized across all applications.

The disadvantage is that if coding rules change or data has multiple representations (casing, whitespace, Unicode), normalization must be handled. In particular, **email addresses, phone numbers, and display names** often change and also involve personal data; they are poorly suited as an immutable `_id`.

### 9.3. Decision Matrix

| Scenario | Recommended Choice | Reason |
|---|---|---|
| New document with no stable business key | Auto-generated ObjectId | Minimal config, short ID, broad driver support |
| Distributed system needing IDs created before write | App-generated ObjectId or UUID | Avoids needing a synchronous sequence generator per operation |
| Business code is truly immutable and unique in the collection | Business code string as `_id` | Direct lookup by code, avoids extra mapping |
| Business code can change | ObjectId/UUID as `_id`, code in a separate field | Keeps references stable |
| Users can have colliding codes across tenants | Separate global ID and unique index per tenant | Separates document identity from tenant uniqueness scope |
| API with retries needing duplicate order protection | Stable ID/request key + unique index | Provides an anchor to identify one logical operation |
| Need sequentially incrementing invoice numbers to display | Keep internal ObjectId and allocate invoice numbers separately | Invoice numbering rules differ from document ID requirements |

Do not rely on ObjectId's "increasing-looking" property to satisfy consecutive accounting numbering requirements. If business rules legally mandate sequential numbers without gaps, design a dedicated numbering workflow with clear rollback/voiding and reconciliation rules.

## 10. Impact on Queries, Indexes, and Referenced Data

### 10.1. Queries by `_id` Have a Default Index

```javascript
db.orders.findOne({
  _id: ObjectId("6718d4e0b7e24f52b064a020")
});
```

A regular collection has a unique index on `_id`, so exact lookups by `_id` can usually use the index efficiently. However, actual performance also depends on network layers, document size, cache, and deployment conditions.

Try inspecting the query plan:

```javascript
db.orders.find({
  _id: ObjectId("6718d4e0b7e24f52b064a020")
}).explain("executionStats");
```

Fields such as `IXSCAN`, `FETCH`, `totalKeysExamined`, and `totalDocsExamined` show how the server read keys and documents. With very small datasets or across different storage/index engines, explain structures can vary; do not jump to conclusions from a single stage name.

### 10.2. References Must Preserve the Exact `_id` Type

Suppose the `customers` collection uses ObjectId as its key:

```javascript
{
  _id: ObjectId("6718d4e0b7e24f52b064a099"),
  fullName: "Nguyen An"
}
```

When an order references a customer, store the same BSON type:

```javascript
{
  _id: "ORDER-0001",
  customerId: ObjectId("6718d4e0b7e24f52b064a099")
}
```

If `customerId` stores the string `"6718d4..."` while `customers._id` is an ObjectId, direct comparisons or `$lookup` across the two fields may fail to match as expected. Normalize types at the API/driver boundary before saving references.

### 10.3. Do Not Change `_id` When Many References Exist

If a customer document has thousands of orders pointing to `customerId`, changing the customer's key to another value forces the application to migrate or update referencing relationships while resolving in-flight operations. Therefore, choosing an `_id` that is **durable across the entire document lifecycle** is usually more important than human readability.

### 10.4. Key Size and Distribution

ID types affect index structure:

- ObjectId is 12 bytes and generally increases roughly with creation time.
- UUID v4 is random, giving different value distribution but potentially affecting index insert locality.
- Long strings consume more index key space and transfer bandwidth.
- Sequential codes can create concentrated write hotspots on key ranges in certain topologies or sharding schemes.

There is no single "fastest" ID type for every system. Choose based on business requirements first, then measure write/index paths and shard distribution when real workload volume is significant.

## 11. `_id` with Sharding: Cluster-Wide Uniqueness Considerations

In an unsharded collection, the unique `_id` index guarantees no two documents share the same key in the collection. For a **sharded collection**, distinguish two cases:

- If **`_id` is the shard key** or sharding satisfies the conditions for enforcing uniqueness cluster-wide, MongoDB can guarantee key uniqueness under that design.
- If **`_id` is not the shard key** and the `_id` unique constraint does not span all shards, MongoDB can only guarantee `_id` uniqueness **within each individual shard**. The application is responsible for generating globally unique `_id`s across all shards if required by business logic.

For example, in a sharded collection distributed by `tenantId`, a key `_id: "ORDER-0001"` self-assigned by two tenants could be stored on different shards if the system lacks corresponding global controls. You should not assume `_id` enforcement substitutes for a **multi-tenant** identifier definition.

For custom unique indexes on other fields, MongoDB enforces rules involving the **shard key prefix** and sharding configuration. Design the shard key, tenant scope, and unique keys together before sharding data, especially if planning to use application-generated codes.

In multi-shard systems, random versus time-increasing IDs also affect how data is distributed and routed. However, changing the ID type alone **does not automatically fix** distribution issues if the shard key does not include that ID field.

## 12. Common Mistakes When Self-Assigning IDs

| Scenario | Consequence | How to Handle |
|---|---|---|
| Inserting two documents with the same `_id` | Duplicate key error | Determine whether it is a collision or a retry of the same request; do not blindly ignore |
| Passing an ObjectId as a string | `find` or `$lookup` fails type matching | Convert to proper BSON ObjectId before querying |
| Using email as `_id` | Cannot change the key when email changes | Keep ID stable; store email in a separate appropriately indexed field |
| Generating a new ObjectId on every HTTP retry | May insert multiple records for one logical request | Use a stable idempotency key or controlled business state |
| Treating ObjectId as an exact timestamp | Inaccurate order creation reporting | Store `createdAt` separately |
| Treating hard-to-guess ObjectId as access control | Risk of data exposure if ID is known | Enforce authentication, authorization, and tenant conditions |
| Assuming numeric `_id` auto-increments | ID collisions when multiple processes allocate numbers | Use an atomically designed sequence generator or distributed IDs |
| Using mismatched ID types in referenced data | Unable to join/correlate data | Standardize BSON types across collections |
| Assuming unique `_id` always applies across a whole sharded collection | Duplicates across shards when poorly designed | Define shard key and cluster-wide uniqueness strategy |
| Changing `_id` with `$set` | Error because the key is immutable | Keep `_id` stable; update business codes in a separate field |

## 13. Hands-On Practice in mongosh

Use a separate collection to observe behavior. The following examples create data and intentionally trigger duplicate key errors; do not run them on production collections.

### Exercise 1 — Comparing Auto-Generated and Application-Provided IDs

```javascript
db.idPractice.insertMany([
  { label: "auto-1" },
  { label: "auto-2" },
  { _id: "APP-001", label: "custom-string" },
  { _id: NumberLong("999"), label: "custom-number" }
]);

db.idPractice.find().sort({ label: 1 });
```

Observe the actual `_id` type and value of each document. Run the query:

```javascript
db.idPractice.aggregate([
  {
    $project: {
      label: 1,
      idType: { $type: "$_id" }
    }
  }
]);
```

The `idType` result shows that `objectId`, `string`, and `long` are distinct BSON types.

### Exercise 2 — Triggering a Duplicate Key Error

```javascript
db.idPractice.insertOne({
  _id: "APP-001",
  label: "duplicate"
});
```

Observe the duplicate key error. Then run:

```javascript
db.idPractice.findOne({ _id: "APP-001" });
```

The original document still exists; the second `insertOne()` did not replace it. Explain why the unique index on `_id` guarantees uniqueness but **does not by itself determine** whether two requests share the same business meaning.

### Exercise 3 — ID Type in Queries

```javascript
const id = new ObjectId();

db.idPractice.insertOne({
  _id: id,
  label: "object-id"
});

db.idPractice.findOne({ _id: id });
db.idPractice.findOne({ _id: id.toHexString() });
```

The first line queries with the exact ObjectId so it returns the document; the second queries with a String containing the same display characters so it does not match that document. Describe exactly why.

### Exercise 4 — Submitting the Same Request Twice

```javascript
const requestId = "REQ-001";

db.idempotentOrders.updateOne(
  { _id: requestId },
  {
    $setOnInsert: {
      customerId: "C01",
      status: "NEW"
    }
  },
  { upsert: true }
);

// Try sending the exact same command again.
db.idempotentOrders.updateOne(
  { _id: requestId },
  {
    $setOnInsert: {
      customerId: "C01",
      status: "NEW"
    }
  },
  { upsert: true }
);

db.idempotentOrders.find({ _id: requestId });
```

Observe `matchedCount`, `modifiedCount`, and `upsertedId` (if present) in each command's result. Why is there only one document after two executions? If the second submission carries a different `customerId`, what additional business check must the application add?

### Exercise 5 — Choosing an ID Strategy for Three Data Types

Design identifiers for:

1. A `products` collection whose SKU code can change due to the supplier.
2. An `orders` collection with invoice numbers that must follow a custom numbering rule.
3. An `events` collection recording events from multiple services that may receive duplicate deliveries from a queue.

For each case, decide the `_id` type, which business fields need unique indexes, the source of identifier generation, and how retries work. Do not pick an ID type solely because it is easy to read when the more important goal is **stability and avoiding duplicate data**.

## 14. Design Takeaways

**`_id` is the document's identity, while a business code can be a separate concept.** Letting MongoDB/the driver generate an ObjectId is a sensible default when no truly immutable business identifier exists.

**The application is free to assign its own `_id`**, provided the value is valid, consistently typed, and does not violate uniqueness within the scope enforced by MongoDB. Strings, numbers, UUIDs, and ObjectIds each have trade-offs in size, distribution, mutability, and error handling.

**ObjectId is not an official creation timestamp, an access credential, or an automatic idempotency key.** When a distributed system involves retries, use a stable request identifier or unique business key and verify payload matching.

**Choose a durable ID from the start.** Referenced data, indexes, sharding, and APIs depend on the type and value of `_id`; changing strategy after accumulating large amounts of data is usually harder than separating internal identity from mutable business fields up front.
