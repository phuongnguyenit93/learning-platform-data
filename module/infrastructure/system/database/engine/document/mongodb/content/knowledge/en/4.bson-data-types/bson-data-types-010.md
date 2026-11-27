# Document Size Limits, Nesting Depth, and Field Name Rules

MongoDB stores data as **BSON documents**. BSON (*Binary JSON*) can represent objects, arrays, strings, numbers, dates, binary payloads, and many other data types. BSON's flexible structure lets applications store business entities with nested components, yet a document cannot grow arbitrarily in size or depth, and field names are subject to dedicated technical rules.

Three limits to keep in mind when designing a MongoDB schema are:

| Aspect | Key Limit or Rule | Design Consequence |
| --- | --- | --- |
| Size of a single BSON document | **Maximum 16 MiB = 16,777,216 bytes.** | Do not embed unboundedly growing arrays or large binary blobs inside one document. |
| Nesting depth | **At most 100 levels** of BSON nesting; each nested object or array adds depth. | Avoid storing arbitrarily deep trees or recursive structures directly in one document. |
| Field names | Strings that **must not contain null characters** (`\u0000`); field names within the same document must be unique. | Validate and sanitize field names during ingestion and API design. |
| `.` and `$` prefixes | Modern MongoDB allows storing them, yet **significant restrictions apply to queries, indexes, shard keys, and import/export tools**. | Avoid them in application-designed field names. |
| `_id` field | Reserved for the primary identifier, unique within a collection and immutable after creation. | Choose a stable identifier and avoid hard-to-manage `_id` structures. |

The **16 MiB limit applies per individual document**, not to an entire collection or database. A collection can hold huge numbers of valid documents; conversely, a single oversized document cannot be saved merely by adding more disk space or RAM.

## 1. Understanding the 16 MiB Limit in Exact Units

### 1.1. MiB Differs from MB

MongoDB documentation uses **mebibytes (MiB)**:

```text
1 MiB  = 1,048,576 bytes
16 MiB = 16 x 1,048,576 = 16,777,216 bytes

1 MB   = 1,000,000 bytes (decimal)
```

Therefore, 16 MiB is not identical to 16 million bytes. When reviewing alerts, metrics, or capacity calculations, use consistent units.

### 1.2. What Size Is Being Bounded?

The limit is measured against the **BSON encoding of the entire document**. It includes top-level and nested fields, values, field names, `_id`, array elements, and all required BSON structural bytes. You cannot simply count the visible characters in a JSON string and treat that as the BSON size.

A BSON document contains length headers, type markers, null-terminated key names, and type-encoded values. Consequently:

- A Unicode string may occupy a different number of UTF-8 bytes than its visible character count.
- Long keys repeated across many sub-objects inflate document size.
- BSON arrays use string index keys like `"0"`, `"1"`, `"2"`, ..., which also incur overhead.
- `ObjectId`, `Date`, `Int32`, `Int64`, `Decimal128`, and `Binary` encode differently; printed JSON length is not BSON storage size.
- Binary payloads and sub-documents all count toward the same parent document limit.

For example, the following document is larger in BSON than the sum of characters in `name` and `description` due to field names, `ObjectId`, integer encoding, and BSON metadata:

```javascript
{
  _id: ObjectId("66a000000000000000000001"),
  name: "Engineering Handbook",
  description: "Unicode-enabled document",
  tags: ["mongodb", "bson", "database"],
  version: NumberInt(1)
}
```

### 1.3. On-Disk Compression Does Not Change the Document Limit

WiredTiger can compress data pages stored on disk. A document may occupy less physical disk space after compression, yet **the 16 MiB limit still applies to the uncompressed BSON document**. In other words, you cannot create a 30 MiB document and expect storage-engine compression to make it valid.

Likewise, adding RAM, switching storage engines, enabling replica sets, or sharding does not make an oversized >16 MiB document valid. Those mechanisms address different aspects of storage and scaling.

## 2. How Do Documents Grow in Applications?

Consider a customer profile management application:

```javascript
db.customers.insertOne({
  _id: "C101",
  fullName: "Nguyen An",
  preferences: {
    language: "vi",
    notifications: { email: true, push: false }
  },
  recentOrders: [
    { orderId: "O1001", amount: 245000 },
    { orderId: "O1002", amount: 389000 }
  ]
});
```

Keeping a few recent orders inside the customer document can be convenient for an overview screen. However, if `recentOrders` actually accumulates **every order ever placed**, the element count keeps growing. Eventually, a single `$push` can push the document over the allowed size limit.

```javascript
db.customers.updateOne(
  { _id: "C101" },
  {
    $push: {
      recentOrders: { orderId: "O1003", amount: 79000 }
    }
  }
);
```

This command is syntactically valid, yet whether it succeeds or fails depends on the document size **after the update**. MongoDB does not evict older elements just because an array grew large. When an update crosses the limit, the application receives an error and must handle it per business logic.

This is why a model that seems to work smoothly during testing with 10 elements can break down later if each user accumulates millions of history records.

### 2.1. Three Types of Fields That Commonly Cause Unexpected Growth

| Field Pattern | Examples | Risk |
| --- | --- | --- |
| Unbounded accumulating arrays | `events`, `orders`, `comments`, `auditLogs`. | Every appended element grows the parent document. |
| Large binary content | Images, PDFs, videos, or archives embedded directly. | A single file can consume most or all of the document limit. |
| Repetitive payloads | Detailed snapshots, raw third-party JSON, lists of objects with many verbose keys. | Accumulated overhead and higher network/read/write costs. |

Not all **arrays** or **nested objects** are bad. A multi-field address or a bounded list of line items on a single order is typically a great fit for embedding. The problem is **unbounded growth** and access/update patterns ill-suited to a single document.

## 3. Measuring BSON Size in `mongosh`

MongoDB provides the aggregation operator `$bsonSize` to compute the byte size of an object when BSON-encoded. Example on the `customers` collection above:

```javascript
db.customers.aggregate([
  {
    $project: {
      _id: 1,
      bsonBytes: { $bsonSize: "$$ROOT" }
    }
  },
  { $sort: { bsonBytes: -1 } },
  { $limit: 10 }
]);
```

`$$ROOT` refers to the current document in the pipeline. The output reveals the BSON size of each evaluated document, helping spot abnormally bloated records. On very large collections, computing sizes and sorting the whole dataset can be resource-intensive; run it during an appropriate maintenance window or narrow the dataset first.

You can check the maximum size within a specific customer tier:

```javascript
db.customers.aggregate([
  { $match: { accountTier: "ENTERPRISE" } },
  { $project: { documentBytes: { $bsonSize: "$$ROOT" } } },
  { $group: {
      _id: null,
      maxBytes: { $max: "$documentBytes" },
      avgBytes: { $avg: "$documentBytes" },
      count: { $sum: 1 }
  } }
]);
```

These expressions only illustrate measurement; the second example assumes the collection has an `accountTier` field. Filter according to your actual schema.

An illustrative way to define an alert threshold:

```javascript
const maxDocumentBytes = 16 * 1024 * 1024;
const cautionThreshold = 12 * 1024 * 1024;

print({ maxDocumentBytes, cautionThreshold });
```

The 12 MiB mark here is an **application-chosen threshold**, not a MongoDB limit. A system may need earlier alerts if documents grow rapidly, or a complete redesign if arrays are unbounded. Avoid waiting until a record approaches 16 MiB before splitting data.

### 3.1. Document Size Differs from Collection Size

Collection-level metrics such as data size, document count, and on-disk storage provide a macro view. They **do not replace** inspecting individual document sizes. A 100 GiB collection might consist of millions of tiny documents, or it might harbor a few anomalous documents nearing 16 MiB. Those two scenarios carry very different optimizations and risks.

Do not compare `JSON.stringify(document).length` against 16 MiB: that measurement counts JavaScript string code units, not actual BSON bytes or specialized BSON types.

## 4. What to Do When Content May Exceed 16 MiB?

The answer depends on the **nature of the data**. No single document-splitting strategy fits every domain.

### 4.1. Split Unbounded One-to-Many Relationships into a Separate Collection

Instead of keeping the entire order history inside a customer document:

```javascript
// customers
{
  _id: "C101",
  fullName: "Nguyen An",
  lastOrderAt: ISODate("2026-10-01T10:00:00Z")
}

// orders: each order is an independent document
{
  _id: "O1001",
  customerId: "C101",
  createdAt: ISODate("2026-10-01T10:00:00Z"),
  total: NumberDecimal("245000")
}
```

Orders can grow indefinitely without bloating the customer document. An appropriate index accelerates per-customer history queries:

```javascript
db.orders.createIndex({ customerId: 1, createdAt: -1 });

db.orders.find({ customerId: "C101" })
  .sort({ createdAt: -1 })
  .limit(20);
```

**Trade-offs:** fetching both customer and orders requires an extra query or `$lookup`, and multi-document updates require consistency management. In return, each entity has its own lifecycle and scales sustainably.

### 4.2. Keep Arrays Explicitly Bounded

If you only need the **10 most recent views** or **20 most recent notifications**, keep a capped array inside the document:

```javascript
db.users.updateOne(
  { _id: "U1001" },
  {
    $push: {
      recentViews: {
        $each: [{ productId: "P42", viewedAt: new Date() }],
        $slice: -10
      }
    }
  }
);
```

`$slice: -10` retains the last 10 elements after pushing in array order. This strategy is suitable only when the business requirement is genuinely a *recent list*. If full history is required for auditing, older events must be stored elsewhere; slicing an array must never discard mandatory records.

### 4.3. Bucket by Time or Size

A telemetry system can group a bounded number of samples by device and time window:

```javascript
{
  deviceId: "SENSOR-01",
  bucketDate: ISODate("2026-11-14T00:00:00Z"),
  readings: [
    { at: ISODate("2026-11-14T00:00:00Z"), temperature: 26.1 },
    { at: ISODate("2026-11-14T00:01:00Z"), temperature: 26.2 }
  ]
}
```

A bucket may represent an hour, a day, or a fixed element count depending on ingestion rate and sample size. **A bucket is still a document**, so it must remain under 16 MiB. Design bucket rollover boundaries and concurrency handling rather than merely renaming an unbounded array to `bucket`.

MongoDB also offers **time series collections** purpose-built for many telemetry workloads. Choosing between custom buckets and time series collections should be based on query patterns, retention, and update requirements.

### 4.4. Use GridFS for Large Files

**GridFS** is a mechanism for storing and retrieving files as parts (*chunks*) paired with metadata. It fits applications that must store files exceeding the document limit or want file storage managed inside MongoDB. A large file is split into multiple chunk documents, each valid within BSON limits; file metadata is stored separately.

```text
80 MiB PDF file
       |
       v
GridFS (via driver/API)
       |
       +--> File info/metadata
       |
       +--> Chunk 0
       +--> Chunk 1
       +--> ...
       `--> Chunk N
```

GridFS **does not raise the single-BSON-document limit**; it represents a file across multiple documents. Avoid inventing an ad-hoc chunking scheme if GridFS satisfies your requirements. However, if the workload primarily streams video, serves public images, or handles massive blobs, object storage and a CDN are also strong candidates to compare on cost, throughput, and delivery model.

### 4.5. Separate Metadata from Heavy Content

Example of a document record:

```javascript
{
  _id: "DOC-401",
  title: "Operations Manual",
  ownerId: "U12",
  fileId: ObjectId("66b000000000000000000401"),
  sizeBytes: 92000000,
  contentType: "application/pdf"
}
```

APIs can filter, authorize, and list documents without dragging along the entire binary payload. `fileId` points to GridFS or a suitable file store. On updates or deletes, the application must manage lifecycle and consistency between metadata and file contents.

## 5. Nesting Depth Limit: At Most 100 Levels

MongoDB permits nested documents and arrays up to **100 levels deep**. Each nested object or array adds one level to the BSON structure. This is a limit on **depth**, completely separate from the **16 MiB byte size** limit.

A document that is only a few kilobytes can still be rejected if its object/array nesting goes too deep. Conversely, a flat document with a single 20 MiB binary field is invalid for exceeding byte size despite minimal depth.

### 5.1. Depth Differs from Field Count

```javascript
// Shallow: fields are siblings inside one object
{
  _id: 1,
  title: "MongoDB",
  author: "Team A",
  published: true,
  rating: 5
}

// Deeper: objects nested inside objects
{
  _id: 2,
  a: {
    b: {
      c: {
        d: "value"
      }
    }
  }
}

// Both arrays and objects contribute to depth
{
  _id: 3,
  sections: [
    { title: "Part 1", blocks: [ { type: "text", value: "Content" } ] }
  ]
}
```

The third example is not overly deep, yet it shows that the `sections` array, objects inside it, the `blocks` array, and the `block` object all lie along a single nesting path. Depth is measured along the deepest nested path, not by summing objects across sibling branches.

### 5.2. Recursive Structures Likely to Hit the Limit

Real-world examples:

- Category trees where each node embeds all child and grandchild categories.
- Parser-generated JSON representing expressions nested hundreds of levels deep.
- Documents containing nested blocks, inside which layouts, groups, blocks, and groups repeat.
- Workflow definitions where each step embeds the entire next step.
- Third-party API objects embedded verbatim without depth bounds.

An example building a deeply nested object to visualize the issue:

```javascript
let value = { leaf: "end" };

for (let i = 0; i < 110; i++) {
  value = { child: value };
}

// Only to illustrate exceeding the depth limit;
// never put this structure into a real MongoDB schema.
// db.nestedExamples.insertOne(value); // would exceed nesting limit
```

Because the structure nests layer after layer, 110 iterations suffice to breach the limit without a large byte payload. In production applications, validate nesting depth of untrusted inputs before passing them to the driver or storage; errors can also trigger inside the driver's BSON encoder.

### 5.3. Replace Deeply Nested Trees with Node Relationships

When a hierarchy can grow deep and unbounded, storing **one document per node** generally scales much better:

```javascript
// categories
{ _id: "CAT-A", name: "Hardware", parentId: null }
{ _id: "CAT-B", name: "Computers", parentId: "CAT-A" }
{ _id: "CAT-C", name: "Laptops", parentId: "CAT-B" }
```

The `parentId` model does not increase document depth as the tree grows deeper. In exchange, querying an entire subtree or ancestor chain may require multiple reads or aggregations like `$graphLookup`, and the application must prevent cycles in parent–child links.

Some systems also store a *materialized path* or an array of ancestor IDs to optimize queries. Those fields still need size bounds and update logic when subtrees move. No single tree model fits all workloads.

## 6. Why Avoid Deep Nesting Even Below 100 Levels?

The 100-level cap is a **maximum storage ceiling**, not a schema design target. In most applications, a handful of deliberate nesting levels is far clearer and easier to query.

Problems usually appear long before reaching 100 levels:

1. **Long, error-prone query paths:** paths like `project.layout.sections.blocks.items.settings.color` are hard to maintain as schemas evolve.
2. **Complex targeted updates:** updating elements nested across multiple arrays can require `$`, `$[]`, or `$[identifier]` with `arrayFilters`.
3. **Harder schema governance:** validating types and constraints across many optional nested objects and arrays becomes cumbersome.
4. **Document limits and write contention:** holding an entire tree in one document forces every update to contend on the same atomic unit and size ceiling.
5. **Heavier reads and rendering:** APIs needing one node may end up loading or transmitting a large subtree without careful projections and access paths.
6. **Recursive structures fail outside the database too:** serializers, converters, and tree-traversal code in the app can hit stack limits or reference loops.

Example updating a moderately nested field:

```javascript
db.profiles.updateOne(
  { _id: "U-12" },
  { $set: { "settings.notifications.email": false } }
);
```

This is completely reasonable when `settings.notifications.email` represents a fixed path a few levels deep. If at coding time you do not know whether a field sits at level 5 or level 85, revisit your data boundaries instead of building ever-longer dynamic paths.

## 7. Field Name Rules in BSON Documents

A field name (*key*) is a string identifying each value inside an object. MongoDB does not apply the exact same naming rules across **fields**, **collections**, and **databases**. When reading limits documentation, check which target object is under discussion.

### 7.1. Basic Constraints

| Field Name | Notes |
| --- | --- |
| `firstName` | Common, clear, easy to query. |
| `shippingAddress` | Well suited for holding a nested address object. |
| `created_at` | Valid; pick one convention consistently such as `camelCase` or `snake_case`. |
| `họTên` | Representable in UTF-8 Unicode; consider normalizing key names across systems. |
| `firstName` and `firstname` | Two distinct keys; never rely casually on case differences. |
| Names containing null char `\u0000` | **Invalid**. |
| Two fields with the same name in one document | **Never store documents this way**; some BSON builders can emit duplicate keys, yet CRUD behavior is not reliably supported. |
| `_id` | Reserved for the primary identifier; carries additional rules. |

Example document without duplicate field names:

```javascript
{
  _id: "P10",
  productName: "Mechanical Keyboard",
  priceMinor: NumberLong(890000),
  stock: {
    available: NumberInt(5),
    reserved: NumberInt(2)
  }
}
```

Field names should remain stable semantically. Avoid naming keys after translated UI labels or raw user input. For example, instead of using `"màu sản phẩm"` as a key processed by multiple services, a uniform technical key like `color` paired with separate display metadata is much easier to maintain.

### 7.2. The Null Character Differs from the String `"null"`

The null character is the byte/character `\u0000`, not the four letters `n`, `u`, `l`, `l`. Field names `"nullable"` or `"null"` do not contain a null character simply because they resemble the keyword.

```javascript
const validKey = "null";       // just a normal text string
const invalidKey = "a\u0000b"; // contains a null character
```

Constructing keys by concatenating raw strings from untrusted sources can accidentally produce invalid or hard-to-query field names. Validate and map incoming keys before building BSON documents.

## 8. Periods (`.`): Literal Names vs. Nested Paths Differ

In MongoDB queries, a period normally denotes a **path to a nested field**:

```javascript
{
  _id: 1,
  address: {
    city: "Da Nang"
  }
}

// Query by path: address -> city
db.customers.find({ "address.city": "Da Nang" });
```

However, since MongoDB 5.0, support for storing **field names containing literal periods** was expanded. That creates an easy source of confusion:

```javascript
{
  _id: 2,
  "address.city": "Hanoi",     // a top-level field name
  address: { city: "Da Nang" } // a separate nested field
}
```

Top-level `"address.city"` and path-traversed `address.city` are **two separate pieces of data**, even though standard path syntax looks the same. Using the wrong operator can read or update the wrong field.

### 8.1. Using `$getField` to Read Literal Dotted Names

Example using a dedicated test collection:

```javascript
db.fieldNameExamples.insertOne({
  _id: 1,
  "metrics.cpu": 91,
  metrics: { cpu: 62 }
});

db.fieldNameExamples.aggregate([
  {
    $project: {
      _id: 0,
      literalKeyValue: { $getField: "metrics.cpu" },
      nestedPathValue: "$metrics.cpu"
    }
  }
]);
```

Expected output:

```javascript
{
  literalKeyValue: 91,
  nestedPathValue: 62
}
```

`$getField: "metrics.cpu"` looks up the exact literal key containing the period. The expression `"$metrics.cpu"` traverses the nested path `metrics` → `cpu`. This distinction matters when ingesting external payloads with partner-defined keys.

### 8.2. Using `$setField` to Modify Literal Names

To update the **literal key** `"metrics.cpu"`, do not write `$set: { "metrics.cpu": 95 }`, because that updates the `cpu` field inside the `metrics` object. Use `$setField` in an update pipeline:

```javascript
db.fieldNameExamples.updateOne(
  { _id: 1 },
  [
    {
      $replaceWith: {
        $setField: {
          field: "metrics.cpu",
          input: "$$ROOT",
          value: 95
        }
      }
    }
  ]
);
```

After this command, the literal key `"metrics.cpu"` becomes `95`, while the nested field `metrics.cpu` remains `62`. These operators were introduced in MongoDB 5.0; applications targeting older servers must check version compatibility constraints.

### 8.3. Why Still Avoid Periods in Field Names?

MongoDB can store these field names, yet official documentation advises against them due to significant limitations. Dotted names cannot be indexed like regular fields, cannot serve as shard keys or be validated directly with `$jsonSchema` like normal fields, and are easily misinterpreted as nested paths by CSV import/export tools.

When your application controls the schema, cleaner alternatives are:

```javascript
// Recommended: nested object with simple keys
{
  metrics: {
    cpu: 91,
    memory: 80
  }
}

// Or map external metadata names into a safe key
{
  attributes: [
    { originalName: "metrics.cpu", value: 91 }
  ]
}
```

Storing an `attributes` array has different query and index trade-offs from a direct object; adopt it only when you genuinely must preserve arbitrary external keys or special characters verbatim.

## 9. Dollar Signs (`$`): Field Names vs. MongoDB Operators

MongoDB uses `$` in query, aggregation, and update syntax:

```javascript
db.products.find({ price: { $gte: 100000 } });

db.products.updateOne(
  { _id: "P10" },
  { $set: { active: true } }
);
```

`$gte` and `$set` are **operators**, not application-stored field names. In modern MongoDB versions, the server can store a field name beginning with `$`, yet doing so is awkward to work with and shares restrictions similar to dotted field names.

Example document with a literal `"$price"` field:

```javascript
db.specialFieldExamples.insertOne({
  _id: 1,
  "$price": 450000,
  productName: "Backpack"
});
```

When reading it, combine `$getField` with `$literal` so the expression does not interpret a `$`-prefixed string as a field path:

```javascript
db.specialFieldExamples.aggregate([
  {
    $project: {
      _id: 0,
      priceValue: {
        $getField: { field: { $literal: "$price" }, input: "$$ROOT" }
      }
    }
  }
]);
```

In practice, choose `price` rather than `"$price"` whenever you control input design. Top-level fields starting with `$` also risk colliding with internal metadata names reserved by MongoDB, causing data not to be preserved or queried as expected in certain contexts.

## 10. Additional Limitations on `.` and `$`

MongoDB 5.0+ supports storing keys with `.` or leading `$` better than earlier versions, but you must still understand the limitations. According to MongoDB documentation, such fields cannot be used in several critical capabilities:

| Capability | Constraint for Fields with `.` or Leading `$` |
| --- | --- |
| Regular indexes | Cannot index these special fields the way normal fields are indexed. |
| Shard keys | Cannot use them as shard key components. |
| `$jsonSchema` validation | Cannot directly apply `$jsonSchema` validation rules to those fields. |
| Field Level Encryption | Not supported under this mechanism. |
| Subfields inside object `_id` | Cannot be used as subfields of `_id`. |
| Import/export tools | May be misinterpreted or lose fidelity in certain formats, especially CSV and Extended JSON. |
| Multiple dot-separated segments | The number of dot-separated components (*words*) must not exceed MongoDB's limit (maximum 255). |

The 255 limit **applies to the count of dot-separated name parts**, not a general rule that every field name is capped at 255 characters. Even within technical limits, avoid constructing keys with hundreds of segments or unwieldy paths.

### 10.1. Risks Across Mixed Driver and Server Versions

A MongoDB 5.0-compatible driver may allow field names with `.` or leading `$` that older drivers rejected client-side. If that application connects to a **pre-5.0 MongoDB server**, the write may be rejected server-side. Especially with unacknowledged writes (`w: 0`), the application might not even notice rejected writes.

Therefore, when upgrading drivers or onboarding new data sources, verify **server version, driver version, and actual write concern**, rather than assuming that if the driver encodes BSON, the server will persist it.

### 10.2. Import/Export Risks

- **CSV** commonly uses periods to represent nested paths; a literal key `"address.city"` can be interpreted as an `address` object containing a `city` field.
- **Extended JSON v2** reserves special keys like `$date` or `$numberLong` for BSON type wrappers. Application fields sharing those names can introduce ambiguity during export/import.
- Never rely on exporting and re-importing a JSON file without testing to assume special field names and types survive intact. Test round-trips using the exact tools, formats, and versions used in operations.

The simplest solution remains choosing clean, stable field names, avoiding `.` and `$` whenever possible, and using those special capabilities only with clear justification.

## 11. The `_id` Field: Primary Identifier with Dedicated Rules

Every document in a MongoDB collection has an `_id` field serving as its primary identifier. If the application omits it, the driver or MongoDB typically generates an appropriate `_id` value. The `_id` value must be **unique within the collection**, immutable after creation, and obeys type restrictions—specifically, arrays and regular expressions cannot be used as `_id`.

```javascript
{
  _id: ObjectId("66c000000000000000000401"),
  orderCode: "O2026-401",
  status: "NEW"
}
```

`_id` may be a string or a valid object when a composite identifier is truly warranted, provided you pick a stable, easily queried structure:

```javascript
{
  _id: { tenantId: "TENANT-01", externalId: "EXT-9001" },
  status: "ACTIVE"
}
```

If `_id` is an object, **never include subfields starting with `$`**; limitations on `.` in special fields also apply. Do not treat `_id` as a dumping ground for bulky metadata—it is an identifier, not the entity payload.

The unique index on `_id` does not automatically enforce uniqueness for separate business fields like `email`, `orderCode`, or `(tenantId, externalId)` outside `_id`. Those constraints require dedicated unique indexes, along with sharded-collection rules if the collection is sharded.

## 12. Why Are Duplicate Field Names Dangerous?

At the raw format level, some BSON builders can construct documents containing multiple elements with the **exact same field name**. However, MongoDB does not support reliable CRUD behavior on documents with duplicate field names, even if an insert occasionally appears to succeed.

Visualize the situation:

```text
// Example illustrating an INVALID design scenario:
{ "status": "PENDING", "status": "PAID" }
```

When parsed by most standard JSON libraries, one of the values gets overwritten before reaching MongoDB; other systems may preserve both keys in an internal representation. This discrepancy causes silent data corruption during serialization, import, or querying.

Preventive guidelines:

1. Never build BSON documents by inserting raw user-supplied field names without duplicate checks.
2. Distinguish normalized field names, such as `productCode` vs. `ProductCode`, via explicit application contracts.
3. When ingesting partner JSON, use parsers or validation steps capable of detecting duplicate keys if data integrity requires it.
4. Never use duplicate field names to represent a list; use an array or a child collection.
5. For existing corrupted data, design a dedicated read/repair script rather than relying on normal queries to "pick" one value.

## 13. Dynamic Field Names: How Should External Data Be Stored?

Suppose an API receives partner-defined metadata:

```json
{
  "manufacturer.code": "A-01",
  "$campaign": "summer",
  "label vi": "Featured product"
}
```

Copying every key verbatim to the root of a MongoDB document exposes the application to dotted names, `$` prefixes, shifting schemas, and potential collisions with internal fields. One approach is converting to an explicit key–value model:

```javascript
{
  _id: "P-100",
  name: "Jacket",
  externalMetadata: [
    { key: "manufacturer.code", value: "A-01" },
    { key: "$campaign", value: "summer" },
    { key: "label vi", value: "Featured product" }
  ]
}
```

The external names are now **string values of the `key` field**, rather than BSON field names containing special characters. This lets you enforce length limits, allowlists, maximum element counts, and controlled search indexing.

If metadata grows very large or updates independently, move each metadata group into a separate document linked by `productId`. The key–value array preserves original names at the cost of different indexing/query trade-offs and array growth risks; do not apply it blindly everywhere. When fields are fixed and known, an **object with clean field names** is usually much simpler.

### 13.1. Field Naming Conventions Should Stay Consistent

A popular convention in Java/Spring and JSON APIs is `camelCase`:

```javascript
{
  _id: "PRODUCT-01",
  productName: "Tablet",
  categoryId: "TABLET",
  createdAt: ISODate("2026-11-14T02:00:00Z"),
  price: { amountMinor: NumberLong(4500000), currency: "VND" },
  attributes: { screenSizeInches: 11, storageGb: 128 }
}
```

What matters is not that `camelCase` is always superior to `snake_case`, but **maintaining one consistent convention across models, serializers, queries, indexes, and APIs**. Avoid localized Vietnamese/English display labels as field keys when an application needs a language-independent schema. Field names expressing business meaning and units—such as `priceMinor` instead of `price` for minor-unit amounts—prevent confusion.

## 14. How Depth, Byte Size, and Field Names Interact

These three limit categories do not operate in isolation. A document can violate one limit while staying well within the other two.

| Design Example | Byte Size | Depth | Primary Issue |
| --- | --- | --- | --- |
| Single `fileData` field holding a 25 MiB binary | Exceeds 16 MiB. | May be very shallow. | Requires GridFS or an appropriate file store. |
| Object with 110 chained `child` layers | May be only a few KiB. | Exceeds 100 levels. | Must redesign the recursive model. |
| Metadata with `"source.version"` key | May be tiny. | Single level. | Confuses literal key with dotted path; index/query restrictions. |
| One million tiny items in `events` | Likely exceeds 16 MiB and slows updates. | May be only a few levels. | Store events as separate documents or bounded buckets. |
| Very long field names repeated across many sub-objects | Inflates BSON overhead. | May remain under 100. | Size bloat and brittle schema maintenance. |
| `_id` containing a `$`-prefixed subfield | May be tiny. | Shallow depth. | Violates `_id` naming constraints. |

A single redesign often solves multiple problems at once. For instance, moving a large tree from one document into a `nodes` collection with `parentId` eliminates nesting-depth risk, bounds individual document sizes, and allows independent node updates—at the trade-off of requiring traversal/joins and relationship consistency checks.

## 15. Application-Layer Error Handling and Guardrails

Do not wait for the database to reject payloads before fixing your design. APIs and services accepting BSON/JSON from clients can enforce business limits **stricter** than MongoDB's limits:

```text
Document upload API:
  - File exceeds threshold -> route to object storage/GridFS by design
  - Metadata -> MongoDB document with fixed schema and fields

Event ingestion API:
  - One event -> one document
  - Do not accumulate unboundedly in user.events[]

Expression/tree ingestion API:
  - Cap input depth per business rules (e.g., 20 levels)
  - Cap total nodes and payload size
  - Reject or map unsupported field names
```

The "20 levels" figure is solely an illustrative application cap, not a MongoDB rule. An expression language needing only 6 levels works well with a cap of 20; a system processing complex ASTs might need another limit. Choose thresholds from your API contract and load testing.

### 15.1. Controlling Size Before Updates

When arrays are permitted to grow within bounds, apply guardrails:

- **Cap element count:** use `$slice` or move to a separate collection if full history must be kept.
- **Cap payload size:** validate acceptable inputs and measure BSON size via appropriate driver/tooling checks.
- **Cap nesting depth:** validate at ingress/mappers to block runaway recursive payloads.
- **Restrict field names:** reject null characters, unexpected keys, excessive lengths, and reserved fields per internal conventions.
- **Monitor real sizes:** use `$bsonSize` or application-level BSON sizing on collections with growth risk.

HTTP request size limits cannot substitute for BSON limits: identical content can vary in size after serializing between JSON and BSON. Furthermore, a tiny update request can push an existing document past the threshold—such as `$push`-ing one item onto an array already near 16 MiB.

### 15.2. Distinguishing Encoding Errors from Server Write Errors

An invalid structure can be rejected at multiple stages:

1. **Application/validation layer:** violates business rules, payload bounds, or field name policies.
2. **Driver/BSON serializer:** cannot encode a type or structure per driver rules.
3. **MongoDB server:** rejects an oversized document or payload violating server limits.
4. **Schema/index constraints:** rejects via validator or unique index even when the document is small and field names are valid.

Exact error messages depend on driver language, version, and operation. Log structured error categories and necessary business context; avoid dumping full sensitive payloads into logs just for debugging.

For **document-too-large** errors, never retry endlessly with the exact same payload: subsequent attempts have the exact same size. Trim data per policy or change the storage model. Likewise, retrying an overly deep tree will never satisfy the depth constraint.

## 16. Four Scenarios Requiring Modeling Decisions

### Scenario A — An Article with Hundreds of Attached Images

**Requirement:** load article title/body, display an image list, download individual images; images may be tens of MB each.

**Design:** store metadata and resource references inside the article document; store image binaries in GridFS or object storage. If image counts grow unboundedly, consider a separate `attachments` collection instead of embedding all metadata in an oversized array.

**Trade-off:** coordinating deletes/updates across metadata and files is more involved, yet it avoids the 16 MiB limit and prevents article reads from transferring heavy binary blobs.

### Scenario B — Multi-Level Category Hierarchy

**Requirement:** categories can have child categories, each node carrying independent metadata; depth is user-defined.

**Design:** separate node documents containing `parentId`, indexed on `parentId`; add traversal or materialized paths for common queries. Enforce cycle prevention and depth limits if business rules require them.

**Trade-off:** fetching a full branch may require multiple operations, in exchange for adding 1,000 nodes without forcing everything into one deep or bloated document.

### Scenario C — Partner Metadata Containing `a.b` and `$code` Keys

**Requirement:** preserve partner-provided field names while querying on certain shared attributes.

**Design:** map core queryable attributes to dedicated, safe field names; retain original keys inside `key`/`value` entries or a controlled metadata payload. If forced to store literal special keys, use `$getField`/`$setField` and accept index/shard-key restrictions.

**Trade-off:** adds a mapping/validation step, in exchange for clean core queries and low import/export risk.

### Scenario D — User Profile with Multi-Year Activity History

**Requirement:** query the 20 latest events and occasionally retrieve full history across date ranges.

**Design:** store each event as a document in `userEvents` with `userId` and `occurredAt`, indexed for read patterns; optionally cache a short summary in the profile without treating it as the complete audit log.

**Trade-off:** requires an extra collection and index, while simplifying retention policies and independent event queries; profiles never grow toward 16 MiB.

## 17. Pre-Schema Checklist

For every new collection, answer in order:

1. **What is the primary entity?** Does one document map cleanly to a single entity/aggregate with a clear lifecycle?
2. **Which fields can grow unboundedly?** Are history lists, comments, files, events, or child trees bounded?
3. **What is the real BSON size?** Measure with `$bsonSize` or a BSON encoder, accounting for metadata and related indexes.
4. **Where does nesting depth come from?** If input data is recursive, what enforces depth limits prior to persistence?
5. **Who controls field names?** Defined by the engineering team or entered dynamically by users/partners? If external, is validation and mapping in place?
6. **Are there special `.` or `$` fields?** If so, have you accepted the query, index, shard key, validator, import/export, and version-compatibility constraints?
7. **Are `_id` rules appropriate?** Unique, immutable, clearly typed, and well structured.
8. **What is read/written together?** Embed only when lifecycle and size fit; reference when data evolves independently.
9. **How are limit errors handled?** Near thresholds, will the application reject, split data, offload files, or enforce retention?
10. **Have extreme cases been tested?** Test Unicode payloads, large arrays, deeply nested objects, unusual keys, near-limit documents, and concurrent writes.

A solid design not only stores today's sample data, it scales predictably as record counts, nesting depth, and external data sources evolve.

## 18. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| "MongoDB can only store up to 16 MB of data." | **Each individual document** is capped at 16 MiB; collections and databases can be vastly larger. |
| "If compression shrinks it to 8 MiB on disk, a 20 MiB BSON document will fit." | The limit applies to the BSON document representation, not compressed page size on disk. |
| "Adding RAM fixes document-too-large errors." | RAM and cache do not expand the document size limit. |
| "Having 100 sibling fields hits the 100-level depth limit." | Sibling field count differs from nesting depth; only nested objects/arrays add depth. |
| "Only objects count toward nesting depth; arrays don't." | Both objects and arrays increase nesting depth. |
| "MongoDB 5.0+ forbids `.` or `$` in field names." | MongoDB 5.0+ allows storing them in many cases, though with clear operational limits. |
| "`"a.b"` always means a literal key." | In standard path syntax, `a.b` refers to field `b` inside `a`; literal keys need `$getField`/`$setField`. |
| "`$price` is a normal field and can be queried like `price`." | `$` has operator syntax meaning in queries/aggregations; literal fields need special handling. |
| "If a JSON parser accepts duplicate keys, MongoDB handles them fine too." | Documents with duplicate field names are not reliably supported for CRUD operations. |
| "GridFS lets a single document hold more than 16 MiB." | GridFS splits files across multiple chunk documents; each document must still obey BSON limits. |
| "All child data should always be embedded in one document." | Unbounded or independently evolving child data should usually be separated via references. |
| "`JSON.stringify().length` is close enough to measure BSON." | JSON text length differs from BSON byte size; measure in BSON. |

## 19. Official References

- [MongoDB — Limits and Thresholds](https://www.mongodb.com/docs/manual/reference/limits/): BSON size limits, nesting depth, and field-naming rules.
- [MongoDB — Documents](https://www.mongodb.com/docs/manual/core/document/): document structure, `_id`, field names, and BSON.
- [MongoDB — Field Names with Periods and Dollar Signs](https://www.mongodb.com/docs/manual/core/dot-dollar-considerations/): restrictions on `.` and `$` in field names.
- [MongoDB — `$getField`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/getfield/): reading a literal field, including keys with periods or leading `$`.
- [MongoDB — `$setField`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/setfield/): updating literal keys containing special characters.
- [MongoDB — `$bsonSize`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bsonsize/): computing an object's BSON byte size.
- [MongoDB — GridFS](https://www.mongodb.com/docs/manual/core/gridfs/): storing and retrieving files as chunks.

When consulting documentation for a specific MongoDB deployment, verify both the **server** and **driver** versions in use, especially regarding `.` and `$` field names. The 16 MiB limit, 100-level depth limit, and field-naming constraints should translate directly into **schema design rules, input validation, and growth strategies**, rather than remaining three isolated trivia numbers.
