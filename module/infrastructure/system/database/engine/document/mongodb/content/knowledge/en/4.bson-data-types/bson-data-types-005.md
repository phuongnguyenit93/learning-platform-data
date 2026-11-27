# ObjectId, the _id Field, and Identifier Selection in MongoDB

## 1. Objectives and Context

Every document in a MongoDB collection must be uniquely identifiable so applications can find, update, delete, link data, or pass IDs over APIs. **The `_id` field** serves as the document's identifier key. **ObjectId** is the BSON type commonly used by MongoDB for that field's value. These two concepts are closely related but not synonymous: `_id` is a field name, whereas ObjectId is one kind of value that the field can hold.

After completing this lesson, you will be able to:

- Explain the 12-byte structure and 24-character hexadecimal representation of ObjectId.
- Understand how MongoDB assigns, indexes, matches, and enforces `_id` values.
- Avoid query bugs when an ID is stored as an ObjectId while the application passes a string.
- Choose appropriately among ObjectId, UUID, business-key strings, integers, and composite keys.
- Build a small dataset to inspect the BSON type of `_id`, query results, and join operations.
- Apply identifier conventions in the MongoDB Java Driver and multi-tenant applications.

The examples use **mongosh** and a dedicated practice database **mongo_identity_lab**. If you do not yet have MongoDB and mongosh ready, prepare a local MongoDB server or test environment with permissions to create collections, insert documents, and build indexes.

## 2. Distinguishing _id, ObjectId, and Business Keys

Consider a product document:

~~~javascript
{
  _id: ObjectId("66f000000000000000000001"),
  sku: "NOTE-A5-001",
  name: "A5 Notebook",
  price: NumberDecimal("45000.00")
}
~~~

| Component | Role | Mandatory? |
| --- | --- | --- |
| **_id** | Document identifier key, used to distinguish a document from others in the collection | Yes |
| **ObjectId** | 12-byte BSON type suitable as an `_id` value | No; other key types may be used |
| **sku** | Business product code, used for sales or inventory integration | Application-dependent |
| **Unique index on sku** | Enforces non-duplicate SKUs within the chosen business scope | Needed if you want MongoDB to enforce SKU uniqueness |

If a new document is inserted without specifying `_id`, the driver or server assigns an ObjectId depending on the write path. Standard MongoDB collections have a **default unique index on `_id`**, so there is no need to create another `_id` index with the same definition.

Uniqueness of `_id` applies within the scope of a collection, not across the entire database: two different collections can share the same `_id` value. For sharded collections specifically, if `_id` is not part of an appropriate shard key, MongoDB only enforces `_id` uniqueness per shard; the application must guarantee that duplicate IDs are not generated across shards. Therefore, shard key selection and ID strategy must be evaluated together.

MongoDB does not automatically know that `sku`, `email`, or `orderNo` are unique keys merely from their field names. Business rules must be expressed with corresponding unique indexes, for example:

~~~javascript
db.getSiblingDB("mongo_identity_lab")
  .getCollection("lab_products")
  .createIndex(
    { tenantId: 1, sku: 1 },
    { unique: true, name: "ux_tenant_sku" }
  );
~~~

In this example, the same SKU can exist across different tenants, but duplicates are prevented within the same tenant. Choosing index fields must derive from actual domain rules. If the collection is sharded, unique indexes must also satisfy shard key constraints.

## 3. What Kind of BSON Type Is ObjectId?

**ObjectId** is **12 bytes** in size and is commonly displayed in mongosh as **24 hex characters** (two characters `0–9` or `a–f` per byte):

~~~javascript
ObjectId("66f000000000000000000001")
~~~

MongoDB stores the BSON ObjectId type and its 12 bytes. The `ObjectId` word, parentheses, and quotes are simply how mongosh displays the type, not a literal string stored in the database.

### 3.1. The 12-Byte Structure

| Byte Offset | Byte Count | Content | Meaning |
| --- | ---: | --- | --- |
| 0–3 | 4 | Timestamp in seconds since the Unix epoch | Hints at when the **ID was generated** |
| 4–8 | 5 | Random value typically initialized per ID-generating process | Distinguishes ID-generating sources |
| 9–11 | 3 | Incrementing counter, initialized with a random value | Distinguishes sequentially generated IDs |
| **Total** | **12** | **24 hex characters when displayed** | **One ObjectId** |

~~~text
ObjectId: 66f00000 1122334455 000001
          | 4 bytes| | 5 bytes| |3 bytes|
          timestamp   random     counter
~~~

The byte segments in the diagram are chosen for readability. The random portion of modern ObjectIds should not be interpreted as an IP address, machine ID, or user identifier.

**Key properties:**

- ObjectId has a very low collision probability when generated properly, though it does not offer a mathematical proof of global uniqueness under every arbitrary condition.
- The four timestamp bytes make ObjectIds **roughly monotonically increasing over time**, but strict ordering is not guaranteed across multiple processes/machines, clock skew, or multiple IDs generated within the same second.
- The timestamp has only **one-second** granularity. An ObjectId can also be generated before insertion, assigned manually, or migrated from historical data.
- ObjectId is not a security token. Knowing an ObjectId must never allow a user to bypass authentication or authorization.

### 3.2. Creating ObjectIds and Reading Their Metadata

In mongosh:

~~~javascript
const generatedId = new ObjectId();

print(generatedId);                // Displays ObjectId(...)
print(generatedId.toHexString());  // 24-character hex string
print(generatedId.getTimestamp()); // Date derived from the ObjectId timestamp
~~~

You can construct a fixed ID for example queries:

~~~javascript
const fixedId = new ObjectId("66f000000000000000000001");
print(fixedId.toHexString());
print(fixedId.getTimestamp());
~~~

Do not rely on **`getTimestamp()`** as a high-precision creation timestamp. If your application needs creation, modification, or business event times, store separate **createdAt** and **updatedAt** fields as BSON Dates:

~~~javascript
{
  _id: new ObjectId(),
  createdAt: new Date(),
  updatedAt: new Date()
}
~~~

ObjectId identifies the document; `createdAt` records time per application semantics. They serve two different purposes.

## 4. Operational Rules of the _id Field

### 4.1. Uniqueness, Data Type, and Immutability

A document's `_id` field is its identifier key. MongoDB allows many BSON types as `_id`, but **arrays and regular expressions cannot be used as `_id`**. Common practice uses a single consistent type across the entire collection—typically ObjectId, String, integer, or UUID stored as Binary.

Once a document exists, **`_id` is immutable**. You can update content fields, but you cannot use a regular update operation to change an existing `_id` into a new `_id`.

~~~javascript
const lab = db.getSiblingDB("mongo_identity_lab");
const inserted = lab.getCollection("lab_auto_ids").insertOne({
  label: "Document without _id passed"
});

print(inserted.insertedId);

lab.getCollection("lab_auto_ids").updateOne(
  { _id: inserted.insertedId },
  { $set: { label: "Updated" } }
);

// INVALID example for an existing document:
// lab.getCollection("lab_auto_ids").updateOne(
//   { _id: inserted.insertedId },
//   { $set: { _id: new ObjectId() } }
// );
~~~

When an identifier must change, plan to create a new document, migrate related references, and remove the old document in a controlled manner. Never treat changing `_id` as an ordinary field edit.

### 4.2. String and ObjectId Are Two Different Types

The following two values are **not equal**, even though their printed characters look similar:

~~~javascript
{ _id: "66f000000000000000000001" }
{ _id: ObjectId("66f000000000000000000001") }
~~~

The first document stores a **BSON String**; the second stores a **BSON ObjectId**. MongoDB matches on both value and BSON type. Consequently:

~~~javascript
const sampleId = inserted.insertedId;
const hex = sampleId.toHexString();

lab.getCollection("lab_auto_ids").findOne({ _id: hex });
// Typically returns null because the query passes a String.

lab.getCollection("lab_auto_ids").findOne({
  _id: new ObjectId(hex)
});
// Matches the document if _id in the collection is ObjectId.
~~~

This is a frequent cause of the "ID looks right, yet `findOne` returns `null`" bug in APIs. If a collection intentionally uses String for `_id`, keep it as String; do not convert it to ObjectId merely because the string looks like 24 hex characters.

### 4.3. Passing Data Through JSON

Plain JSON has no ObjectId type. MongoDB uses **Extended JSON** when BSON types must be represented explicitly:

~~~json
{
  "_id": { "$oid": "66f000000000000000000001" },
  "createdAt": { "$date": "2026-01-10T08:00:00Z" }
}
~~~

A REST API may also expose the ID as a plain string:

~~~json
{
  "id": "66f000000000000000000001",
  "name": "Nguyen Lan"
}
~~~

These two representations carry different contracts. Extended JSON preserves BSON type metadata; a string in an API is often easier for consumers, yet must be converted back to ObjectId at the database access layer if the database stores ObjectId. Never assume standard JSON parsing automatically reconstructs an ObjectId.

### 4.4. Duplicate Key Errors

When inserting a document whose `_id` already exists, MongoDB returns a duplicate key error, typically coded **E11000**. This error also occurs for other unique indexes, such as a unique index on `(tenantId, email)`. Always inspect the index name in the error message to identify which key actually collided.

## 5. Identifier Selection Strategies

| Strategy | Advantages | Limitations | Best Fit |
| --- | --- | --- | --- |
| **ObjectId** | Compact, convenient default, client-generated, no centralized sequence generator needed | Contains timestamp; ordering is only approximate; APIs must handle type conversion | Most CRUD documents in MongoDB |
| **UUID BSON Binary subtype 4** | Independently generated, cross-service identifier, fixed 16-byte binary size | Requires consistent representation across drivers | Multi-service and polyglot data platforms |
| **UUID as String** | Easy to display and exchange as text | Larger than binary, type mismatch against BSON UUID | Integrations where String storage is an intentional contract |
| **Business-key String** | Human-readable, meaningful to users or legacy systems | Hard to change if business rules evolve; can grow long, sensitive to normalization | Strictly immutable keys managed by an authoritative source |
| **Sequential Integer** | Short, readable, compatible with legacy systems | Requires non-colliding generator, can create centralized bottlenecks or hotspots | Systems that already have a reliable ID generator |
| **Composite Document** | Expresses multi-part identifiers explicitly | Awkward for queries/APIs/migrations, requires strict field ordering | Domains with truly immutable composite keys |

### 5.1. Keep ObjectId Unless There Is a Strong Reason to Change

ObjectId is usually a strong choice when data lives primarily in MongoDB, the application has no pre-existing global ID, and business keys may change.

Example:

~~~javascript
{
  _id: new ObjectId(),
  tenantId: "t001",
  orderNo: "SO-2026-0001",
  status: "pending",
  createdAt: new Date()
}
~~~

Here **`_id`** preserves the long-term identity of the order, while **`orderNo`** is the user-facing order number. If `orderNo` must be unique per tenant, add a unique index **`{ tenantId: 1, orderNo: 1 }`**. This lets you change order-numbering rules without modifying document `_id` values.

### 5.2. When UUID Is Useful

UUIDs are typically generated at the application layer and can be shared across MongoDB, event streams, and external systems. In mongosh:

~~~javascript
const uuid = UUID("f47ac10b-58cc-4372-a567-0e02b2c3d479");

lab.getCollection("lab_uuid_examples").insertOne({
  _id: uuid,
  name: "UUID-keyed resource"
});
~~~

This value is stored as BSON UUID Binary subtype 4. A JSON string like **"f47ac10b-58cc-4372-a567-0e02b2c3d479"** does not have the same type as a BSON binary UUID. With the Java Driver or other drivers, standardize the **UUID representation**; pay close attention to legacy data that may have been written using a different byte-order convention.

UUIDs also come in multiple versions with different ordering characteristics, such as random UUID v4 and time-ordered UUID v7. Do not assume every UUID increases monotonically over time or is indexed by MongoDB in your exact desired business order.

### 5.3. Mutable Business Keys

Suppose you use email as `_id`:

~~~javascript
{ _id: "lan@example.test", name: "Nguyen Lan" }
~~~

When a customer changes their email, changing `_id` forces recreating the document and updating all references. Moreover, emails may require normalization rules, personal data protection, and per-tenant isolation.

A more maintainable design:

~~~javascript
{
  _id: new ObjectId(),
  tenantId: "t001",
  email: "lan@example.test",
  normalizedEmail: "lan@example.test",
  name: "Nguyen Lan"
}
~~~

Then create an index scoped to the business rule:

~~~javascript
lab.getCollection("lab_users").createIndex(
  { tenantId: 1, normalizedEmail: 1 },
  { unique: true, name: "ux_tenant_normalized_email" }
);
~~~

Producing **normalizedEmail** is the application's responsibility and must follow actual policy; lowercasing alone does not cover every email normalization rule. When sharding, unique indexes must conform to shard key requirements.

### 5.4. Composite Keys

A contract code may only be unique within an organization, such as **`(tenantId, contractNo)`**. Two common approaches exist:

**Option A — Independent `_id`, unique index on the business key:**

~~~javascript
{
  _id: new ObjectId(),
  tenantId: "t001",
  contractNo: "CT-2026-001"
}
~~~

~~~javascript
lab.getCollection("lab_contracts").createIndex(
  { tenantId: 1, contractNo: 1 },
  { unique: true }
);
~~~

**Option B — Composite document as `_id`:**

~~~javascript
{
  _id: { tenantId: "t001", contractNo: "CT-2026-001" },
  status: "active"
}
~~~

Option B can make sense when both parts of the ID are strictly immutable. However, embedded documents exhibit field-order sensitivity during whole-document equality checks, so key construction must be standardized. It is also harder to pass in URLs and evolve structurally. If you simply need uniqueness across two fields, Option A is generally simpler and more flexible.

## 6. Hands-On: Storing ObjectId and String Across Two Collections

We will create an account document with an **ObjectId** `_id` and an order document with a **String** `_id`. The order references the account using a properly typed ObjectId. Each collection keeps a single `_id` type convention rather than mixing types arbitrarily in production collections.

Run the following block in mongosh. It cleans up only documents tagged with **`labTag = identity-choice-v1`** across two practice collections in **`mongo_identity_lab`**. Every execution produces the same logical dataset.

~~~javascript
(() => {
  const labDb = db.getSiblingDB("mongo_identity_lab");
  const tag = "identity-choice-v1";
  const users = labDb.getCollection("lab_identity_users");
  const orders = labDb.getCollection("lab_identity_orders");

  // Delete only documents belonging to the practice dataset.
  orders.deleteMany({ labTag: tag });
  users.deleteMany({ labTag: tag });

  // ObjectId _id: fixed value for easy reference.
  const userId = new ObjectId("66f000000000000000000001");
  users.insertOne({
    _id: userId,
    labTag: tag,
    tenantId: "t001",
    email: "lan@example.test",
    displayName: "Nguyen Lan",
    createdAt: ISODate("2026-01-10T08:00:00.000Z")
  });

  // String _id; the customerId reference field remains ObjectId.
  orders.insertOne({
    _id: "order-t001-0001",
    labTag: tag,
    tenantId: "t001",
    customerId: userId,
    status: "pending",
    createdAt: ISODate("2026-02-03T09:30:00.000Z")
  });

  users.createIndex(
    { tenantId: 1, email: 1 },
    { unique: true, name: "ux_lab_identity_tenant_email" }
  );

  print("User ObjectId:");
  printjson(users.findOne({ _id: userId }));

  print("Order String ID:");
  printjson(orders.findOne({ _id: "order-t001-0001" }));

  print("Match user using String: " +
    users.countDocuments({ _id: userId.toHexString() }));
  print("Match user using ObjectId: " +
    users.countDocuments({ _id: new ObjectId(userId.toHexString()) }));
})();
~~~

Results of the final two counts:

~~~text
Match user using String: 0
Match user using ObjectId: 1
~~~

This demonstrates that MongoDB does not automatically coerce String to ObjectId in queries. Likewise, the order stores **customerId** as an ObjectId because it must reference the user's ObjectId `_id`.

### 6.1. Checking the `_id` Type with `$type`

~~~javascript
(() => {
  const labDb = db.getSiblingDB("mongo_identity_lab");
  const collections = ["lab_identity_users", "lab_identity_orders"];

  for (const name of collections) {
    print(name);
    printjson(labDb.getCollection(name).aggregate([
      { $match: { labTag: "identity-choice-v1" } },
      { $project: { _id: 1, idType: { $type: "$_id" } } }
    ]).toArray());
  }
})();
~~~

Expected output: **`idType = "objectId"`** in `lab_identity_users` and **`idType = "string"`** in `lab_identity_orders`. Inspecting actual BSON types is especially important when data flows through multiple languages or Object–Document Mappers.

### 6.2. Joining with `$lookup` When Key Types Match

~~~javascript
(() => {
  const labDb = db.getSiblingDB("mongo_identity_lab");
  printjson(labDb.getCollection("lab_identity_orders").aggregate([
    { $match: { labTag: "identity-choice-v1" } },
    {
      $lookup: {
        from: "lab_identity_users",
        localField: "customerId",
        foreignField: "_id",
        as: "customer"
      }
    },
    { $project: { _id: 1, customerId: 1, customer: 1 } }
  ]).toArray());
})();
~~~

The **customer** array will contain Nguyen Lan's user document. If you replace `customerId` in the order with a hex string, a direct `$lookup` against an ObjectId `_id` will fail to match. MongoDB does not enforce foreign key constraints automatically like an RDBMS: the application must maintain consistent references on writes and deletes.

### 6.3. Re-running and Cleaning Up Sample Data

Re-run the entire seed block from Section 6 to reset data to its initial state. When finished with the lab, remove only the documents tagged for this exercise:

~~~javascript
(() => {
  const labDb = db.getSiblingDB("mongo_identity_lab");
  const filter = { labTag: "identity-choice-v1" };
  printjson(labDb.getCollection("lab_identity_orders").deleteMany(filter));
  printjson(labDb.getCollection("lab_identity_users").deleteMany(filter));
})();
~~~

Do not use `dropDatabase` or drop collections just to clean up sample records: their scope is much broader. The delete-and-reinsert block in Section 6 is not an atomic transaction; use it only in an isolated practice environment, never as-is in production under concurrent writes.

## 7. ObjectId in Java Applications

An API typically receives an ID from a URL as a `String`:

~~~text
GET /users/66f000000000000000000001
~~~

If the database stores `_id` as ObjectId, the Java data access layer must convert the string into **`org.bson.types.ObjectId`** and build a properly typed filter. Example using the **MongoDB Java Sync Driver**:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.types.ObjectId;

public class FindUserByObjectId {
    public static void main(String[] args) {
        String idFromRequest = "66f000000000000000000001";

        if (!ObjectId.isValid(idFromRequest)) {
            throw new IllegalArgumentException("ID is not a valid 24-character hex string");
        }
        ObjectId mongoId = new ObjectId(idFromRequest);

        try (MongoClient client = MongoClients.create(
                "mongodb://127.0.0.1:27017")) {
            MongoDatabase database = client.getDatabase("mongo_identity_lab");
            MongoCollection<Document> users =
                    database.getCollection("lab_identity_users");

            Document user = users.find(
                    Filters.eq("_id", mongoId)
            ).first();

            if (user == null) {
                System.out.println("User not found");
            } else {
                System.out.println(user.toJson());
            }
        }
    }
}
~~~

**`ObjectId.isValid`** only checks whether the input string can be parsed as an ObjectId format; it does not prove that the document exists or that the caller has permission to read it. A clean API design distinguishes malformed IDs (HTTP 400), valid but missing IDs (HTTP 404), and access control (application security policy).

In multi-tenant applications, the filter must include a trusted tenant from the authenticated context:

~~~java
Document user = users.find(
    Filters.and(
        Filters.eq("_id", mongoId),
        Filters.eq("tenantId", authenticatedTenantId)
    )
).first();
~~~

In this snippet, **authenticatedTenantId** is a variable populated by the application's authentication layer. Never rely on a client-supplied tenant field as the sole source of authorization.

### 7.1. Note on ID Mapping in Spring Data MongoDB

Declaring a Java ID field as `String` does not automatically guarantee MongoDB stores `_id` as a BSON String. Spring Data MongoDB applies conversion rules based on property types and annotations such as **`@Id`** or **`@MongoId`**; depending on the mapping, a string that looks like an ObjectId may be converted into a BSON ObjectId.

When you intend to use BSON ObjectId, an explicit choice is:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("lab_identity_users")
public class LabUser {
    @Id
    private ObjectId id;

    private String tenantId;
    private String email;

    // Constructors, getters, and setters...
}
~~~

If you require storing a literal string untouched, configure String mapping explicitly instead of guessing. When integrating with collections containing legacy data, always verify the actual stored type with **`$type`** and ensure the driver, repository, DTO, and API agree on the ID representation.

## 8. ObjectId, Indexes, Time, and Sharding

### 8.1. Default Index

Standard collections have a default index named **`_id_`**, with key **`{ _id: 1 }`**. Inspect it with:

~~~javascript
db.getSiblingDB("mongo_identity_lab")
  .getCollection("lab_identity_users")
  .getIndexes();
~~~

When the application queries by `tenantId`, `email`, `customerId`, or `createdAt`, the `_id` index does not automatically optimize those filters. Add indexes aligned with real query patterns, such as **`{ tenantId: 1, email: 1 }`** or **`{ tenantId: 1, createdAt: -1 }`**.

### 8.2. Sorting by Time

ObjectIds tend to increase with **ID generation** time, yet sorting by `_id` is not a substitute for business requirements like "newest by order creation time" or "most recently updated." Across multiple machines with clock skew, or when importing historical data, ObjectId order may not reflect persistence time.

If a view needs the latest orders, store `createdAt` and sort by it, using `_id` as a deterministic tie-breaker:

~~~javascript
db.getSiblingDB("mongo_identity_lab")
  .getCollection("lab_identity_orders")
  .find({ labTag: "identity-choice-v1" })
  .sort({ createdAt: -1, _id: -1 })
  .toArray();
~~~

At scale, inspect the query plan and design indexes matching both filter predicates and sort order.

### 8.3. Shard Keys and Identifiers

In a sharded cluster, the shard key governs document distribution. Range sharding on a nearly monotonically increasing value like ObjectId can concentrate new writes onto a single data chunk/shard; evaluate distribution and write throughput carefully. Furthermore, if `_id` is not the shard key, MongoDB may only enforce `_id` uniqueness within individual shards. Consequently, when designing sharding, align **ID generation**, **shard key**, **unique indexes**, and **query patterns** together instead of relying solely on a non-sharded collection's `_id` unique index.

## 9. Common Errors and How to Spot Them

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `findOne` returns `null` even though the ID string looks right | Querying with a String when `_id` is ObjectId | Check `$type` and convert the ID to the matching BSON type |
| `BSONError` or ObjectId construction failure | Input is not a valid ObjectId format | Validate format before instantiating ObjectId |
| `E11000 duplicate key` | Duplicate `_id` or violation of another unique index | Read the index name in the error; fix ID generation or uniqueness rules |
| Immutable `_id` error | Attempting to modify `_id` on an existing document | Do not update `_id`; plan a migration if changing keys is mandatory |
| `$lookup` fails to find related documents | Reference field has a different BSON type than target `_id` | Standardize storage type and convert at write time |
| Sorting by `_id` differs from actual order sequence | ID timestamp does not match business timestamp | Store and sort by `createdAt` or the appropriate timestamp field |
| UUID stored as binary but queried as string | Mismatch between String and BSON UUID or differing representations | Standardize UUID contract and driver conversion |
| Users can guess IDs and read other users' resources | Application lacks authorization checks | Add owner/tenant filters from the authenticated context |
| Email changes cause painful key updates | Using a mutable business key as `_id` | Use an immutable `_id` and a separate unique index for the business key |

## 10. Self-Practice Exercises

1. **Inspect structure:** Generate three consecutive ObjectIds, print `toHexString()` and `getTimestamp()`. Explain why multiple IDs can share the same timestamp while remaining distinct, and why this timestamp lacks millisecond precision.
2. **Distinguish BSON types:** On the Section 6 dataset, query the user with a hex string and with an ObjectId of the same value. Use `$type` to explain why only one query returns the document.
3. **Type-matched joins:** Replace `customerId` in the order with a hex string, re-run `$lookup`, and then restore it as ObjectId. Record the `customer` array output in both runs.
4. **Product key design:** A store needs mutable SKU codes that are unique only per tenant. Propose an `_id` type, document fields, and appropriate unique index; explain why SKU should not be `_id`.
5. **Cross-service identity:** Compare ObjectId vs. BSON Binary UUID when the same ID is shared across MongoDB, event messages, and a Java API. Specify the conversion and representation rules the team must agree upon.
6. **Access safety:** Write a MongoDB query using both `_id` and an authenticated `tenantId`. Explain why a validly formatted ID does not imply the caller is authorized to view the document.
7. **Time and sorting:** Propose how to store `createdAt` and index orders per tenant sorted newest first. Give a scenario where sorting by `_id` yields unexpected ordering.

Across MongoDB lessons on CRUD, aggregation, indexing, referencing, and system design, identifier conventions must stay consistent from the data model, Java classes, and APIs down to related documents. **`_id` is the document's immutable key; ObjectId is a convenient default; unique indexes on business keys and access-control checks are separate responsibilities that must be designed explicitly.**
