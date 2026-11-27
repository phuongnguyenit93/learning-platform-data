# Implicit and Explicit Collection Creation with Options in MongoDB

## Learning Objectives

In MongoDB, a **collection** stores **BSON documents** belonging to the same data group, such as `customers`, `orders`, `products`, or `application_logs`. A collection is often compared to a table in a relational database, though documents within the same collection do not have to share an identical structure unless the designer declares data validation rules.

MongoDB supports two ways of forming a collection:

1. **Implicit creation:** a collection that does not yet exist is automatically created by MongoDB when an appropriate write operation occurs, such as inserting the first document.
2. **Explicit creation:** deliberately calling `db.createCollection()`, even when there are no documents yet, to name it and configure required options up front.

After this lesson, learners will be able to:

- Explain when a database and a collection are actually materialized on the server.
- Practice creating collections via `insertOne()`, `insertMany()`, and `db.createCollection()`.
- Distinguish key `db.createCollection()` options: **validator**, **validationLevel**, **validationAction**, **collation**, **capped**, **size**, **max**, **timeseries**, and **expireAfterSeconds**.
- Inspect whether a collection exists, its collection type, and its stored options.
- Recognize the risks of letting an application auto-create collections when the system requires schema validation, collation, or specialized configuration.
- Choose the right collection creation approach for learning environments, Java/Spring Boot applications, migrations, and production.

> **Key takeaway:** If you only need a standard collection with default settings, the first write command is usually sufficient. If a collection must follow a **data contract or custom configuration**, create it explicitly before the application begins writing.

---

## 1. How Do Databases, Collections, and Documents Relate?

MongoDB organizes data according to this conceptual hierarchy:

~~~text
MongoDB deployment
|
+-- Database: shop_demo
|   |
|   +-- Collection: customers
|   |   +-- Document: { _id: ..., name: "An" }
|   |   +-- Document: { _id: ..., name: "Binh" }
|   |
|   +-- Collection: products
|   |   +-- Document: { _id: ..., sku: "P-001", price: 120000 }
|   |
|   +-- Collection: orders
|       +-- Document: { _id: ..., orderCode: "O-101", items: [...] }
|
+-- Database: audit_demo
    |
    +-- Collection: events
        +-- Document: { _id: ..., action: "LOGIN" }
~~~

Components:

| Component | Meaning | Example |
|---|---|---|
| Database | Logical namespace containing collections and related objects | `shop_demo` |
| Collection | Grouping of documents, optionally with a validator, default collation, and other properties | `orders` |
| Document | BSON record made up of field–value pairs with a unique `_id` within the collection | `{ _id: 1, status: "NEW" }` |
| Index | Structure that accelerates queries or enforces constraints such as uniqueness | `{ orderCode: 1 }` with `unique: true` |

A document can contain string, number, date, array, nested object, ObjectId, or Decimal128 fields. MongoDB does not automatically infer that all documents in a collection must follow a fixed structure just because the first document had certain fields.

### 1.1. The `use` Command Does Not Create a Physical Database

In **mongosh**:

~~~javascript
use shop_demo
~~~

This command switches the working context to the `shop_demo` database. If the database does not yet exist, **merely switching context does not make the database appear on the server as a database containing data**.

Similarly, operations that only obtain a reference to a collection do not create it:

~~~javascript
db.getCollection("customers");
db.customers.findOne();
~~~

They only return a reference object or an empty read result. A collection is created only when an appropriate create or write operation executes.

**Important distinction:**

~~~text
use shop_demo
    -> Selects the database context.

db.customers.findOne()
    -> Reads the collection; if missing, does not auto-create it.

db.customers.insertOne({ name: "An" })
    -> Can implicitly create the database + collection,
       then store the first document.

db.createCollection("orders")
    -> Explicitly creates the collection, even while empty.
~~~

### 1.2. What Does a Default Collection Have?

A standard collection created implicitly uses server default settings, has no user-defined validator, and has no specialized application-set default collation. Every document must have an **`_id`**; if an inserted document omits it, the driver or MongoDB generates an appropriate value.

Do not confuse **having `_id`** with **having full schema validation**. A collection can contain documents with different fields:

~~~javascript
db.customers.insertMany([
  { name: "An", age: 20 },
  { name: "Binh", email: "binh@example.test" },
  { name: "Chi", interests: ["Java", "MongoDB"] }
]);
~~~

This is the flexibility of a document database, while also placing responsibility for data design on the application and administrators.

---

## 2. Implicit Collection Creation

### 2.1. Creating via `insertOne()`

Assume the MongoDB connection already has write permissions on the practice database.

~~~javascript
use shop_demo

db.products.insertOne({
  sku: "JAVA-101",
  name: "Java Programming Book",
  price: 125000,
  available: true,
  tags: ["book", "java"]
});
~~~

If `products` does not yet exist and the write operation is permitted, MongoDB automatically creates the collection and stores the document.

The insert result typically looks like:

~~~javascript
{
  acknowledged: true,
  insertedId: ObjectId("...")
}
~~~

MongoDB adds an `_id` value if the document did not provide one:

~~~javascript
db.products.findOne({ sku: "JAVA-101" });
~~~

Sample output:

~~~javascript
{
  _id: ObjectId("..."),
  sku: "JAVA-101",
  name: "Java Programming Book",
  price: 125000,
  available: true,
  tags: ["book", "java"]
}
~~~

**The hallmark of implicit creation** is that the collection did not exist before the insert command but appears after the insert succeeds.

### 2.2. Creating via `insertMany()`

~~~javascript
db.categories.insertMany([
  { code: "BOOK", title: "Book" },
  { code: "COURSE", title: "Course" },
  { code: "DEVICE", title: "Device" }
]);
~~~

If the `categories` collection does not exist, it is created to hold these documents.

Note: `insertMany()` does not automatically enforce uniqueness on `code`. By default, uniqueness is guaranteed only on `_id`. If you want `code` to be unique, create a **unique index**:

~~~javascript
db.categories.createIndex(
  { code: 1 },
  { unique: true, name: "uk_categories_code" }
);
~~~

An index is a separate configuration object, not an attribute automatically inferred from the `code` field.

### 2.3. Certain Other Write Operations Can Also Create a Collection

An **upsert** command can insert a document into a nonexistent collection:

~~~javascript
db.settings.updateOne(
  { key: "currency" },
  { $setOnInsert: { value: "VND" } },
  { upsert: true }
);
~~~

If no matching document is found, MongoDB can create the `settings` collection and insert the new document. Creating an index on a nonexistent namespace can also result in creating the collection.

**Do not rely on this side effect** for production schema design. If a collection requires custom configuration, create it explicitly before running writes, upserts, or index creation.

### 2.4. Verifying That the Collection Was Created

~~~javascript
db.getCollectionNames();
~~~

Example:

~~~javascript
[
  "products",
  "categories",
  "settings"
]
~~~

Checking a specific name:

~~~javascript
db.getCollectionInfos({ name: "products" });
~~~

`db.getCollectionInfos()` returns details for matching collections/views, including fields such as `name`, `type`, and `options`. Exact structure may vary by MongoDB version.

You can run:

~~~javascript
show collections
~~~

in mongosh to quickly list collections.

### 2.5. When Is Implicit Creation Enough?

This approach is convenient for:

- Introductory CRUD lessons.
- Prototypes that need quick data persistence.
- Temporary tests with standard collections requiring no special options.
- Scripts seeding data into a lab environment that can easily be wiped and rebuilt.

However, implicit creation has limitations:

- No business-required validator unless configured afterward.
- Cannot proactively set a default collation at creation time.
- Cannot intentionally create a **capped collection** or **time series collection**.
- A typo in a collection name can cause an unintended new namespace to appear, if the user has create privileges.
- When a service writes data before migrations run, the collection may be created with default options; a subsequent `createCollection()` call may then fail as already existing.

Therefore, in multi-service environments or deployment pipelines, critical collections should be managed via **controlled migrations/provisioning**.

---

## 3. Explicit Collection Creation with `db.createCollection()`

### 3.1. Basic Syntax

In mongosh:

~~~javascript
db.createCollection("orders");
~~~

General syntax:

~~~javascript
db.createCollection("<collectionName>", {
  // Collection creation options
});
~~~

`db.createCollection()` creates a named collection even when it has no documents yet. For example:

~~~javascript
use shop_demo

db.createCollection("draft_orders");

db.getCollectionNames();

db.draft_orders.countDocuments({});
~~~

Immediately after creation, `draft_orders` exists, while `countDocuments({})` returns **0**.

If the collection already exists, calling `createCollection` again with the same name is not treated as an options update. The server can return a namespace-already-exists error. Depending on the application context, decide between **skipping if options match**, **running a valid migration**, or **raising a configuration error**.

### 3.2. Why Create Explicitly?

There are three main categories of reasons:

1. **Create structure before data:** the collection must exist when a service starts, even before any write events occur.
2. **Define a data contract:** attach a validator, validation level, and behavior when data is invalid.
3. **Select specialized characteristics:** default collation, capped collection, time series, or other version- and deployment-dependent features.

For instance, an `orders` collection might only accept orders with a valid code, amount, and status. If left to auto-creation on the first insert, malformed documents could slip in before a validator is applied.

### 3.3. Overview Table of Common Options

| Option | Purpose | Example |
|---|---|---|
| `validator` | Expression validating documents on insert/update | `{ $jsonSchema: { ... } }` |
| `validationLevel` | Controls how strictly validation is applied | `"strict"`, `"moderate"`, `"off"` |
| `validationAction` | Behavior when a document violates the validator | `"error"`, `"warn"` |
| `collation` | Default string comparison and sorting rules | `{ locale: "vi", strength: 2 }` |
| `capped` | Size-bounded collection that automatically overwrites/evicts oldest data as needed | `true` |
| `size` | Expected maximum storage size in bytes for capped collections | `10485760` |
| `max` | Maximum document count limit for capped collections | `10000` |
| `timeseries` | Creates a collection optimized for time-stamped data | `{ timeField: "recordedAt", metaField: "sensor" }` |
| `expireAfterSeconds` | Sets automatic data retention for time series where supported | `2592000` |
| `clusteredIndex` | Selects a clustered collection when supported by deployment/version | Use only after verifying specific requirements |
| `changeStreamPreAndPostImages` | Configures storing pre/post images for Change Streams when supported | `{ enabled: true }` |

**Note:** Not every combination of options is valid. For example, capped collections and time series collections have mutually distinct structural constraints. Features such as clustered collections, pre/post images, and queryable encryption depend on server version and tier, so consult official documentation before deploying.

The following sections focus on the option groups that appear most frequently when learning and designing MongoDB schemas.

---

## 4. Creating a Collection with Schema Validation

### 4.1. Why Does Flexible MongoDB Still Need Validation?

Being able to store non-uniform documents is an advantage as data evolves, but it can allow an application to persist invalid data:

~~~javascript
// Desired data
{ orderCode: "ORD-001", total: NumberDecimal("250000.00"), status: "NEW" }

// Invalid: missing order code
{ total: NumberDecimal("250000.00"), status: "NEW" }

// Invalid: total is a string instead of Decimal128
{ orderCode: "ORD-002", total: "two hundred thousand", status: "NEW" }

// Invalid: status outside the allowed list
{ orderCode: "ORD-003", total: NumberDecimal("200000"), status: "UNKNOWN" }
~~~

Without validation, a standard MongoDB collection accepts any document that is structurally valid BSON. That increases error-handling cost in services, reporting, and migrations.

**Schema validation** lets the server evaluate each write operation against defined rules.

### 4.2. Creating an `orders` Collection with `$jsonSchema`

The example below requires:

- Presence of `orderCode`, `customerId`, `total`, `status`, `createdAt`, and `items`.
- `orderCode` is a non-empty string.
- `total` has BSON type **decimal** and is non-negative.
- `status` accepts only three values.
- `createdAt` is a BSON date.
- `items` is an array with at least one element; each element has `sku` and `quantity`.

~~~javascript
use shop_demo

db.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "orderCode",
        "customerId",
        "total",
        "status",
        "createdAt",
        "items"
      ],
      properties: {
        orderCode: {
          bsonType: "string",
          minLength: 1,
          description: "Order code is required"
        },
        customerId: {
          bsonType: "string",
          minLength: 1
        },
        total: {
          bsonType: "decimal",
          minimum: 0,
          description: "Total amount must be non-negative Decimal128"
        },
        status: {
          enum: ["NEW", "PAID", "CANCELED"]
        },
        createdAt: {
          bsonType: "date"
        },
        items: {
          bsonType: "array",
          minItems: 1,
          items: {
            bsonType: "object",
            required: ["sku", "quantity"],
            properties: {
              sku: {
                bsonType: "string"
              },
              quantity: {
                bsonType: "int",
                minimum: 1
              }
            }
          }
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

This is **MongoDB JSON Schema**, using keywords like `bsonType`; it is not completely identical to every JSON Schema draft or Java Bean Validation. When using decimal and integer types, send the exact BSON types.

Inserting a valid document:

~~~javascript
db.orders.insertOne({
  orderCode: "ORD-1001",
  customerId: "CUS-001",
  total: NumberDecimal("250000.00"),
  status: "NEW",
  createdAt: new Date(),
  items: [
    { sku: "BOOK-01", quantity: NumberInt(2) }
  ]
});
~~~

This insert succeeds unless another violation occurs (such as duplicate `_id`).

Testing an invalid document:

~~~javascript
db.orders.insertOne({
  orderCode: "ORD-1002",
  customerId: "CUS-002",
  total: "250000",
  status: "INVALID_STATUS",
  createdAt: new Date(),
  items: []
});
~~~

In a collection with `validationAction: "error"`, MongoDB rejects the violating operation, typically raising **Document failed validation**. The failure occurs at write time, not only later when the application reads the data.

### 4.3. Roles of `required`, `bsonType`, and `enum`

| Rule | Meaning | Invalid Example |
|---|---|---|
| `required` | Mandatory fields must be present | Missing `orderCode` |
| `bsonType` | Checks the BSON data type | `total: "250000"` when `decimal` is required |
| `enum` | Accepts only values from the specified set | `status: "UNKNOWN"` |
| `minLength` | Minimum string length | `orderCode: ""` |
| `minimum` | Minimum numeric value | `total: NumberDecimal("-1")` |
| `minItems` | Minimum number of array elements | `items: []` |
| `properties` and `items` | Validates nested fields or array elements | Wrong type for `quantity` |

Do not confuse a validator with a **unique index**. To prevent two orders from having the same code, add:

~~~javascript
db.orders.createIndex(
  { orderCode: 1 },
  { unique: true, name: "uk_orders_orderCode" }
);
~~~

`required` only guarantees that the field is present; it does not enforce uniqueness across the collection.

### 4.4. `validationLevel`: strict, moderate, and off

| Value | Behavior | Use Case |
|---|---|---|
| `"strict"` | Applies validation to all inserts and updates subject to checking | New collections where data must conform to the schema |
| `"moderate"` | Applies to inserts and updates of currently valid documents; previously invalid documents follow moderate rules | Gradually rolling out validation on legacy data |
| `"off"` | Disables validator checks | Special controlled situations; requires careful consideration |

`moderate` does not mean "warn only." This level determines **which documents are checked**, whereas `validationAction` determines **what happens when a checked document violates the rules**.

`strict` is the straightforward choice for a new collection with a well-defined data contract.

### 4.5. `validationAction`: error and warn

| Value | Behavior |
|---|---|
| `"error"` | Rejects write operations that fail validation |
| `"warn"` | Allows the write but emits a warning via MongoDB's logging mechanism |

For example, when preparing to enforce a schema on an existing collection, a team might use `warn` to observe violations before switching to `error`.

However, `warn` **does not protect data quality by blocking bad writes**. Any system that depends on valid order states needs a cleanup plan for invalid records and a clear cutover configuration.

Newer MongoDB versions introduce additional advanced `validationAction` options; verify your specific version rather than copying an option unsupported by your current server.

### 4.6. Does Validation Automatically Fix Existing Data?

**No.** Adding or modifying a validator does not retroactively scan and rewrite previously stored documents. For a collection with historical data, you may need to:

1. Query documents that do not match the target schema.
2. Build a migration to normalize BSON types and required fields.
3. Check for uniqueness conflicts or legacy enum values.
4. Apply the validator with `strict/error` once both data and applications are ready.

Certain privileged operations can bypass document validation; therefore database permissions and operational procedures are also part of data integrity assurance.

---

## 5. Creating a Collection with Default `collation`

### 5.1. What Problem Does Collation Solve?

**Collation** defines how MongoDB compares strings for sorting, matching, and certain index operations. This is especially important when applications handle specific languages, accented characters, or case-insensitivity requirements.

If no explicit collation is declared, the collection uses default binary/simple comparison rules in relevant contexts.

Example creating a `contacts` collection with Vietnamese collation:

~~~javascript
db.createCollection("contacts", {
  collation: {
    locale: "vi",
    strength: 2
  }
});
~~~

`locale: "vi"` selects Vietnamese locale rules supported by the collation system. `strength: 2` generally considers diacritic differences while ignoring letter case at the corresponding comparison level. Exact behavior also depends on locale rules and the ICU version.

Insert data:

~~~javascript
db.contacts.insertMany([
  { fullName: "Nguyễn An", city: "Hà Nội" },
  { fullName: "nguyễn bình", city: "Đà Nẵng" },
  { fullName: "Trần Chi", city: "Huế" }
]);
~~~

Sort:

~~~javascript
db.contacts.find().sort({ fullName: 1 });
~~~

If a specific query needs a different collation, specify it on the query:

~~~javascript
db.contacts
  .find({ fullName: "Nguyễn An" })
  .collation({ locale: "vi", strength: 3 });
~~~

### 5.2. Collation Affects Indexes

Indexes on a collection inherit the default collation unless specified otherwise. A query that needs to use an index for string comparisons must use a collation compatible with that index in relevant cases.

~~~javascript
db.contacts.createIndex(
  { fullName: 1 },
  { name: "idx_contacts_fullName" }
);
~~~

When using a **unique index** on a string field, collation affects whether two values are treated as duplicates. For instance, a case-insensitive unique index may treat `"Lan"` and `"lan"` as the same key within the index's comparison scope.

**Design before writing data:** A collection's default collation is a creation-time property and cannot simply be replaced by another `db.createCollection()` call once the collection exists. If misconfigured, you may need to create a new collection and perform a planned data migration.

---

## 6. Creating a Capped Collection with `capped`, `size`, and `max`

### 6.1. What Is a Capped Collection?

A **capped collection** is a size-bounded collection that preserves documents in insertion order and can automatically evict older documents when space is needed for new ones. It behaves differently from a standard collection.

Example creating a practice log collection capped at roughly 10 MiB and at most 10,000 documents:

~~~javascript
db.createCollection("recent_logs", {
  capped: true,
  size: 10 * 1024 * 1024,
  max: 10000
});
~~~

Meaning:

- `capped: true` enables the size-bounded collection type.
- `size` specifies the expected maximum storage size in bytes and is a required option when creating a capped collection.
- `max` adds a document-count ceiling, though the collection may evict old documents sooner if the size limit is reached first.

When the corresponding limit is exceeded, MongoDB removes older documents to make room for new ones. Actual storage capacity and internals have implementation-specific details; **do not interpret `size` as an exact SLA guaranteeing N hours of log retention**.

### 6.2. Using a Capped Collection

~~~javascript
db.recent_logs.insertMany([
  { event: "APP_START", createdAt: new Date() },
  { event: "USER_LOGIN", userId: "u-01", createdAt: new Date() },
  { event: "REQUEST_DONE", durationMs: 18, createdAt: new Date() }
]);
~~~

Read in natural order:

~~~javascript
db.recent_logs.find().sort({ $natural: 1 });
~~~

Check whether a collection is capped:

~~~javascript
db.recent_logs.isCapped();
~~~

### 6.3. Limitations to Keep in Mind

Capped collections carry notable constraints:

- Unsuitable for business data that must be retained long-term.
- Does not support arbitrary document deletion like standard collections.
- Update operations must not grow a document in a way that violates capped collection constraints.
- Old data can be evicted automatically; never treat this as a backup or archive.
- Capped collections are typically tied to recent-event stream use cases, including historical MongoDB features like tailable cursors.

**Do not use capped collections to store orders, accounting records, or data that must persist indefinitely.**

If the system requirement is "retain logs for exactly 30 days," a standard collection with a **TTL index** or a time series collection with a retention policy is usually more appropriate. Capped collections primarily bound **storage size / document count**, not minimum data age.

---

## 7. Creating a Time Series Collection with `timeseries`

### 7.1. Which Workloads Fit Time Series?

**Time series** fits sequences of timestamped measurements or events, often accompanied by metadata describing the source:

- Temperature, humidity, or pressure from sensors.
- CPU, memory, latency, and operational metrics.
- Measurements tracked over time.
- Telemetry with many records at different timestamps.

MongoDB provides time series collections to organize and optimize storage for timestamped measurements. This collection type must be **created explicitly**; simply inserting documents with a date field into a regular collection **does not turn it into a time series collection**.

### 7.2. Creating the `sensor_readings` Collection

~~~javascript
db.createCollection("sensor_readings", {
  timeseries: {
    timeField: "recordedAt",
    metaField: "sensor",
    granularity: "minutes"
  },
  expireAfterSeconds: 30 * 24 * 60 * 60
});
~~~

Key options:

| Option | Meaning |
|---|---|
| `timeField` | Name of the field holding the measurement timestamp; documents must supply a valid BSON Date |
| `metaField` | Field holding grouping/source metadata, e.g., device ID, location, sensor type |
| `granularity` | Hint about how closely spaced timestamps are: `"seconds"`, `"minutes"`, `"hours"` |
| `expireAfterSeconds` | Sets data retention based on timestamp; deletion occurs asynchronously, not to the exact second |

Insert data:

~~~javascript
db.sensor_readings.insertMany([
  {
    sensor: { deviceId: "D-01", room: "A1" },
    recordedAt: new Date("2026-11-14T08:00:00Z"),
    temperatureC: 27.2,
    humidityPercent: 65
  },
  {
    sensor: { deviceId: "D-01", room: "A1" },
    recordedAt: new Date("2026-11-14T08:01:00Z"),
    temperatureC: 27.4,
    humidityPercent: 64
  },
  {
    sensor: { deviceId: "D-02", room: "A2" },
    recordedAt: new Date("2026-11-14T08:01:00Z"),
    temperatureC: 26.9,
    humidityPercent: 67
  }
]);
~~~

Query by device and time range:

~~~javascript
db.sensor_readings.find({
  "sensor.deviceId": "D-01",
  recordedAt: {
    $gte: new Date("2026-11-14T08:00:00Z"),
    $lt: new Date("2026-11-14T09:00:00Z")
  }
});
~~~

MongoDB may store time series data in **internal buckets** to save space and optimize queries. Applications still interact with the logical `sensor_readings` collection; do not manually modify internal bucket collections.

### 7.3. Why Does `metaField` Matter?

Measurements from the same device usually share metadata. Placing that metadata appropriately helps MongoDB group and organize data efficiently.

For example:

~~~javascript
sensor: {
  deviceId: "D-01",
  room: "A1",
  sensorType: "THERMOMETER"
}
~~~

Conversely, values that change with every reading, such as temperature, belong in measurement fields:

~~~javascript
temperatureC: 27.2
~~~

Avoid putting values that change continuously with every measurement inside `metaField`, as doing so reduces data-grouping efficiency.

### 7.4. How Do Time Series Collections Differ from Regular Collections?

| Criterion | Standard Collection | Time Series Collection |
|---|---|---|
| Purpose | General business data | Timestamped measurement data |
| Implicit creation via insert | Yes | Cannot become time series via insert alone |
| Time configuration | Application chooses its own schema/indexes | Declares `timeField` at creation |
| Storage optimization | Standard collection mechanism | Internal bucket organization |
| Updates/deletes | Supports general CRUD rules | Version-specific limitations apply |
| Retention | Can use TTL indexes | Can use `expireAfterSeconds` as supported |
| Index design | Workload-driven | Must account for time series behavior and version support |

Support for document updates, transactions, indexes, sharding, and other constraints in time series collections varies by MongoDB version. Do not carry over assumptions from standard collections without checking deployment documentation.

### 7.5. `expireAfterSeconds` Is Not an Exact-Second Timer

For example, `30 * 24 * 60 * 60` corresponds to 30 days in seconds. However, expiration runs via background processes and bucket cleanup, so a document may remain visible for some time after crossing its target age.

Therefore:

- Do not rely on TTL to guarantee deletion at an exact legal/compliance second.
- Verify application time and timezone logic.
- Distinguish **active collection retention** from **backup retention**; a document deleted from a collection is not automatically purged from all backups.

---

## 8. Modifying Options After a Collection Exists

### 8.1. You Cannot Re-run `createCollection()` to Update Options

Suppose `orders` was created implicitly:

~~~javascript
db.orders.insertOne({
  orderCode: "OLD-001",
  status: "UNKNOWN"
});
~~~

Then you call:

~~~javascript
db.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["orderCode"],
      properties: {
        orderCode: { bsonType: "string" }
      }
    }
  }
});
~~~

**This does not "attach" a validator to the existing collection.** You need a MongoDB-supported configuration change/migration, and you must evaluate existing data.

### 8.2. `collMod` for Supported Attributes

MongoDB provides the **collMod** command to modify certain properties of an existing collection.

For example, changing only the configured validation level and action:

~~~javascript
db.runCommand({
  collMod: "orders",
  validationLevel: "moderate",
  validationAction: "warn"
});
~~~

This example modifies validation enforcement behavior; it does not create a validator if none exists.

You can use `collMod` to adjust validators when supported by your version and collection type, such as updating validation rules after a migration. However, **not every option available in `createCollection()` can be changed with `collMod`**.

### 8.3. Properties That Should Be Decided Before Data Exists

Certain decisions directly affect collection structure:

- **Default collation**: cannot simply be swapped in place like a normal setting; typically requires a new namespace and migration.
- **Capped collection**: has its own mechanism and limits; do not assume you can toggle freely between capped and standard collections without impacting data.
- **Time series `timeField`/`metaField`**: tied to data organization and subject to modification restrictions; check your exact version.
- **Clustered/indexed storage**: depends on collection type, version, and storage requirements.

The safe workflow for major structural changes is **create a new collection with target options → migrate data → verify → cut over the application**. Production procedures also need to handle concurrent writes during migration, consistency, indexes, and rollback.

---

## 9. Inspecting Collection Type and Active Options

### 9.1. `getCollectionInfos()`

~~~javascript
db.getCollectionInfos({ name: "orders" });
~~~

The output contains metadata for matching collections, conceptually like:

~~~javascript
[
  {
    name: "orders",
    type: "collection",
    options: {
      validator: {
        $jsonSchema: {
          bsonType: "object",
          // ...
        }
      },
      validationLevel: "strict",
      validationAction: "error"
    }
    // Other metadata fields depending on version
  }
]
~~~

This is how you inspect what **actual options** MongoDB has stored, rather than relying only on migration scripts the team thinks were executed.

### 9.2. The `listCollections` Command

You can query directly via database command:

~~~javascript
db.runCommand({
  listCollections: 1,
  filter: { name: "sensor_readings" },
  nameOnly: false
});
~~~

The output can include metadata about the collection type and time series options. This command requires appropriate privileges for the connected user.

### 9.3. Inspecting Indexes

~~~javascript
db.orders.getIndexes();
~~~

Declaring a `validator` with a required `orderCode` **does not automatically create a unique index** on `orderCode`. Therefore, inspect both layers independently:

~~~javascript
db.getCollectionInfos({ name: "orders" }); // Options, validator, collation...
db.orders.getIndexes();                    // Index definitions
~~~

### 9.4. Distinguishing Collections and Views

MongoDB also supports **views**: a namespace specifying a source and an aggregation pipeline that does not store its own documents like a regular collection.

~~~javascript
db.createView(
  "paid_orders_view",
  "orders",
  [
    { $match: { status: "PAID" } }
  ]
);
~~~

When listed with `getCollectionInfos()`, `type` will be `"view"` instead of `"collection"`. Do not lump views together with capped or time series collections, or treat them as standard physical collections.

---

## 10. Comprehensive Practice: From Implicit to Explicit

This section uses a lab database named **`collection_lab`**. Commands should only be executed in a test database where creating and deleting data is permitted.

### Step 1 — Select the Database and Observe State

~~~javascript
use collection_lab

db.getCollectionNames();
~~~

If this is a brand-new database, the collection list is typically empty.

### Step 2 — Implicitly Create a Collection

~~~javascript
db.notes.insertOne({
  title: "First note",
  body: "Creating a collection via an insert operation",
  createdAt: new Date()
});
~~~

Verify:

~~~javascript
db.getCollectionNames();
db.notes.find().pretty();
~~~

The `notes` collection was created by the successful insert.

### Step 3 — Explicitly Create an Empty Collection

~~~javascript
db.createCollection("tasks");

db.getCollectionInfos({ name: "tasks" });
db.tasks.countDocuments({});
~~~

The `tasks` collection exists even though it contains no documents.

### Step 4 — Create a Collection with a Simple Validator

~~~javascript
db.createCollection("students", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["studentCode", "fullName"],
      properties: {
        studentCode: {
          bsonType: "string",
          minLength: 1
        },
        fullName: {
          bsonType: "string",
          minLength: 1
        },
        age: {
          bsonType: "int",
          minimum: 0
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

Valid insert:

~~~javascript
db.students.insertOne({
  studentCode: "ST-001",
  fullName: "Nguyễn An",
  age: NumberInt(20)
});
~~~

Invalid insert to observe the error:

~~~javascript
db.students.insertOne({
  studentCode: "ST-002",
  fullName: "Binh",
  age: "twenty"
});
~~~

MongoDB rejects the second operation under `error` mode because `age` does not match `bsonType: "int"`.

### Step 5 — Add a Unique Index

~~~javascript
db.students.createIndex(
  { studentCode: 1 },
  { unique: true, name: "uk_students_studentCode" }
);
~~~

Try inserting another document with `studentCode: "ST-001"` and a different `_id`. With the unique index present, MongoDB rejects it due to duplicate key violation, independently of the validator.

### Step 6 — Create a Capped Collection

~~~javascript
db.createCollection("lab_events", {
  capped: true,
  size: 1024 * 1024,
  max: 1000
});

db.lab_events.insertOne({
  type: "LAB_STARTED",
  occurredAt: new Date()
});

db.lab_events.isCapped();
~~~

### Step 7 — Create a Time Series Collection

~~~javascript
db.createCollection("room_temperatures", {
  timeseries: {
    timeField: "recordedAt",
    metaField: "room",
    granularity: "minutes"
  },
  expireAfterSeconds: 7 * 24 * 60 * 60
});

db.room_temperatures.insertOne({
  room: { id: "A101", floor: 1 },
  recordedAt: new Date(),
  temperatureC: 27.5
});
~~~

### Step 8 — Inspect Created Metadata

~~~javascript
db.getCollectionInfos({ name: "notes" });
db.getCollectionInfos({ name: "tasks" });
db.getCollectionInfos({ name: "students" });
db.getCollectionInfos({ name: "lab_events" });
db.getCollectionInfos({ name: "room_temperatures" });
~~~

Note the differences in `options` across a regular collection, a validated collection, a capped collection, and a time series collection.

### Step 9 — Clean Up Lab Data When Finished

If you want to delete **a single test collection**:

~~~javascript
db.lab_events.drop();
~~~

`drop()` **deletes the collection along with all its documents and indexes**. Run it only after confirming it is lab data. Never run this command on a collection holding data you must preserve.

---

## 11. Integration with Java and Spring Boot Applications

### 11.1. Does the Application Need to Call `createCollection()`?

In Java, the driver or Spring Data MongoDB can write to a new namespace and trigger implicit collection creation. For example, a repository calling `save()` for the first time usually does not require the developer to run `createCollection()` separately if standard collections are allowed to be created.

However, this **does not automatically configure validators, collation, or time series characteristics required by the business**. Annotations, mappings, or Java types in the application do not automatically mean MongoDB has stored a matching collection validator.

Therefore, separate responsibilities:

~~~text
Provisioning / migration:
  Create collections with desired options
  Create required indexes
  Verify version and metadata
            |
            v
Application startup:
  Connect and verify permissions
  Read/write data according to contract
  Do not rely on the first request to configure schema
~~~

For collections with no special options used in tests or demos, implicit creation is simple. For systems requiring schema-compliant data, consistency across dev/staging/prod outweighs the convenience of a single ad-hoc insert.

### 11.2. Example Calling `createCollection` via the MongoDB Java Driver

This snippet illustrates the concept. In real projects, connections, `MongoClient` lifecycle, exception handling, and secret management must follow application standards.

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;

public class CreateCollectionExample {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database =
                    client.getDatabase("collection_lab");

            database.createCollection("java_events");
        }
    }
}
~~~

The connection reads the `MONGODB_URI` environment variable to avoid hardcoding credentials. If `java_events` already exists, the call must handle the duplicate-namespace case; **do not loop blindly or swallow all exceptions**.

When schema validation or specialized collection types are needed, the Java Driver provides corresponding creation options via `CreateCollectionOptions` and related configuration classes. Exact syntax depends on driver version; consult the Java Driver documentation and verify server capabilities before implementing.

### 11.3. How Should a Spring Boot Project Organize Collection Creation?

A manageable approach:

- **Local dev:** mongosh scripts or migrations create collections and indexes before integration tests run.
- **CI:** spin up a fresh MongoDB instance, run migrations, run tests, then tear down data.
- **Staging:** run the exact production migration version and verify metadata.
- **Production:** apply schema changes in controlled deployments with dedicated create/alter permissions and a rollback plan.

If you choose to auto-create collections at startup, design it so **multiple instances starting concurrently do not cause race conditions**, and startup does not fail simply because the namespace already exists with the expected configuration. Verify options, not just names.

---

## 12. Migration Design and Access Permissions

### 12.1. Risk of Unintended Collection Creation

Suppose a service intends to write to `customer_profiles` but makes a typo:

~~~javascript
db.customer_profiels.insertOne({
  customerId: "C-100",
  enabled: true
});
~~~

If the user has collection-creation privileges, MongoDB silently creates the misspelled **`customer_profiels`** namespace without knowing the original intent.

In a multi-service system, namespace typos lead to:

- Two collections storing data for the same purpose incompatibly.
- One service writing to the new collection while another reads from the old one.
- Expected validators/indexes missing on the misspelled namespace.
- Backups, monitoring, dashboards, or permission policies failing to cover the new data.

Recommendations:

1. Lock down collection names in configuration or shared constants where appropriate.
2. Explicitly create important collections via migrations.
3. Apply least privilege: grant create/alter collection rights only to components that need them.
4. Detect unexpected namespaces via metadata checks or deployment monitoring.
5. Validate required collections at startup instead of letting errors surface on the first user request.

### 12.2. Re-runnable Migration Pattern

A deployment script should satisfy two properties:

- The first run creates the exact collection and indexes.
- Subsequent runs verify the configuration is already correct rather than silently ignoring misconfiguration.

Example logic skeleton in mongosh:

~~~javascript
const targetName = "validated_events";

const existing = db.getCollectionInfos({
  name: targetName
});

if (existing.length === 0) {
  db.createCollection(targetName, {
    validator: {
      $jsonSchema: {
        bsonType: "object",
        required: ["eventType", "createdAt"],
        properties: {
          eventType: { bsonType: "string" },
          createdAt: { bsonType: "date" }
        }
      }
    },
    validationLevel: "strict",
    validationAction: "error"
  });
} else {
  print("Collection exists: verify its options before proceeding");
}
~~~

This is an **illustrative skeleton**, not a complete migration framework. In multi-instance deployments, two processes can both observe the collection missing and try to create it concurrently. One will receive an already-exists error; the script must distinguish acceptable contention from real configuration failures and **re-read metadata to verify**.

In particular, comparing collection names alone is insufficient. Two environments can both have `validated_events` while one has a validator and the other does not.

### 12.3. Database Permissions

To create a collection, a MongoDB user needs appropriate privileges on the database or collection. Built-in roles such as `readWrite` can include collection-creation rights within their granted scope; production systems should design role-based permissions per task instead of granting broad rights to every service.

A common model:

- **Migration principal:** allowed to create/alter collections and indexes within the needed scope.
- **Application principal:** allowed only to read/write the collections the application uses, restricting structural changes where possible.
- **Monitoring principal:** permitted to read relevant metadata/metrics without modifying data.

When moving from implicit creation to explicit creation, confirm both **migration privileges** and **application privileges**.

### 12.4. Collection Naming and Conventions

Use clear, searchable, consistent names:

~~~text
products
customers
orders
payment_attempts
audit_events
sensor_readings
~~~

Avoid arbitrary mixed casing, spaces, ambiguous names, or names easily confused with system collections. MongoDB enforces specific naming rules and reserved namespaces; verify naming restrictions for your server version before standardizing schemas.

---

## 13. Choosing the Method Based on Needs

| Context | Suitable Creation Method | Reason |
|---|---|---|
| Learning insert commands for the first time | **Implicit** via `insertOne()` | Fewer steps; focuses on documents |
| Prototyping a simple collection | **Implicit** | No special options needed |
| Empty collection must exist when the application starts | **Explicit** | Created before any data arrives |
| Orders requiring type and field constraints | **Explicit + validator** | Blocks documents violating the contract |
| Contacts requiring locale-aware string sorting | **Explicit + collation** | Defines string comparison behavior |
| Rotating logs bounded by approximate storage size | **Explicit + capped** | Evicts old data by size/document limits |
| Time-stamped sensor telemetry | **Explicit + timeseries** | Optimized for timestamped data |
| Multi-service production requiring consistency | **Explicit via migration** | Controlled, verifiable, repeatable configuration |
| Temporary test without custom schema | **Implicit or simple migration** | Fast to create, easy to clean up |
| Legacy collection needing validation added | **Migration/`collMod` where supported** | Cannot re-run `createCollection()` to alter |

Choosing between the two approaches is not about how "modern" the syntax looks. It depends on **how much structural control is needed before the first write operation**.

---

## 14. Common Misconceptions

### "Running `use databaseName` creates the database"

Not quite. `use` only switches the database context in mongosh. The database and collection are materialized when an appropriate operation creates an object or writes data.

### "`db.collection.find()` auto-creates the collection if it doesn't exist"

No. Reading a nonexistent namespace does not create that namespace.

### "`insertOne()` creates a collection with a schema inferred from the first document"

No. MongoDB does not automatically generate a validator from the fields and types of the first document. A default collection remains flexible unless schema validation is explicitly configured.

### "`db.createCollection()` is only used when you need a validator"

No. You can also use it to create an empty collection, specify a collation, or create a capped or time series collection.

### "If a collection already exists, call `createCollection()` with new options to modify it"

No. That is a creation operation, not an arbitrary configuration update. Some changes use `collMod`; others require a new collection and data migration.

### "Having a validator means you don't need a unique index"

False. `$jsonSchema` checks document structure and values according to its rules; uniqueness across documents is enforced by a unique index.

### "`validationAction: "warn"` prevents invalid data from being saved"

False. `warn` logs violations as warnings while still allowing the write. To block invalid writes, use `error` behavior where appropriate.

### "A capped collection guarantees retaining logs for at least 30 days"

False. It is bounded by storage size and/or document count. Higher write throughput can cause older documents to be evicted sooner than expected.

### "Inserting a document with a timestamp automatically turns a collection into a time series collection"

False. A time series collection must be created explicitly with the `timeseries` configuration.

### "TTL deletes documents at the exact moment they expire"

No. Expiration runs asynchronously and involves specific mechanics, especially for time series buckets.

### "Java annotations determine all options in MongoDB"

Not necessarily. Application-layer mapping and actual database metadata are two separate layers; always inspect collection options on the server.

### "Having a collection means optimal query indexes already exist"

No. MongoDB maintains an index on `_id` as required by the collection type, while query fields such as `customerId`, `status`, and `createdAt` generally require indexes designed for the workload.

---

## 15. Hands-On Exercises

### Exercise 1 — Distinguishing Creation Operations

In a fresh `lesson_creation` database, execute in sequence:

~~~javascript
use lesson_creation
db.getCollectionNames()

db.books.findOne()
db.getCollectionNames()

db.books.insertOne({
  isbn: "978-000001",
  title: "MongoDB Basics"
})
db.getCollectionNames()
~~~

Explain at which step the `books` collection was created and why the preceding read operation did not create it.

### Exercise 2 — Schema Validation for Courses

Create a `courses` collection using `db.createCollection()` with these constraints:

- `courseCode` and `title` are required, non-empty strings.
- `durationHours` is an int, greater than or equal to 1.
- `level` may only be `BEGINNER`, `INTERMEDIATE`, or `ADVANCED`.
- `createdAt` is a BSON date.

Insert two documents: one valid document and one with `durationHours` as a string. Describe the response when `validationAction` is `error` versus `warn`.

Afterward, create a unique index on `courseCode` and try inserting two courses with the same code.

### Exercise 3 — Comparing Collations

Create a `people` collection with collation locale `vi`, `strength: 2`. Insert names differing in letter case and diacritics. Compare the results:

~~~javascript
db.people.find().sort({ fullName: 1 });

db.people
  .find()
  .collation({ locale: "simple" })
  .sort({ fullName: 1 });
~~~

Explain why the same data can sort differently when collation changes.

### Exercise 4 — Choosing Capped vs. Time Series

For the two problems below, pick one collection type and explain:

1. A display buffer for the 500 most recent application events, where evicting older events is acceptable and long-term history is not needed.
2. Storing per-minute temperature readings from 1,000 sensors, frequently queried by device and date range, with automatic data expiration after 90 days.

Specify the appropriate `capped/size/max` or `timeseries/timeField/metaField/granularity/expireAfterSeconds` options.

### Exercise 5 — Detecting Environment Configuration Drift

Dev has an `orders` collection with a validator; staging also has an `orders` collection, but it was created implicitly without a validator.

Explain:

- How to use `getCollectionInfos()` to inspect the difference.
- Why running only `db.getCollectionNames()` misses this issue.
- Why you should not drop the staging collection containing live/test data as a quick fix.
- A safe migration workflow before enabling `validationAction: "error"`.

---

## 16. Review Questions

1. Does `use` in mongosh immediately create the database on the server?
2. What is the most common operation that creates a collection implicitly?
3. Why is `findOne()` not a collection-creation operation?
4. When should you use `db.createCollection("name")` with no options?
5. How do `validator` and a `unique index` differ?
6. Do `validationLevel: "moderate"` and `validationAction: "warn"` mean the same thing?
7. How does a collection's default collation affect string comparisons and indexes?
8. In a capped collection, what limits do `size` and `max` control?
9. Why should sensor data be considered for a time series collection?
10. Can you change any collection creation option by calling `createCollection()` again?
11. How do you verify that a collection actually has the validator specified in the design?
12. Why should production environments manage collections through controlled migrations?

## 17. Conclusion

**Implicit collection creation** is simple and convenient when first learning MongoDB: a single `insertOne()` can create a standard collection and immediately store a document. However, it does not automatically define a validator, collation, or specialized capped/time series structure.

**Explicit collection creation** with `db.createCollection()` lets you prepare namespaces before data arrives and declare properties affecting data quality, string comparison, and storage layout. For business applications requiring reliable operations, combine explicit creation with **indexes, access control, migrations, and metadata verification**.

Practical rule of thumb:

- **Standard collections and quick experiments:** implicit creation is fine.
- **Collections with data contracts or specialized behavior:** create explicitly before the first write.
- **Production environments:** manage collection definitions via verifiable, repeatable migration workflows to prevent unintended namespaces.

## Official References

- [MongoDB Manual — Databases and Collections](https://www.mongodb.com/docs/manual/core/databases-and-collections/)
- [MongoDB Manual — db.createCollection()](https://www.mongodb.com/docs/manual/reference/method/db.createCollection/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — Specify JSON Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/specify-json-schema/)
- [MongoDB Manual — Collation](https://www.mongodb.com/docs/manual/reference/collation/)
- [MongoDB Manual — Capped Collections](https://www.mongodb.com/docs/manual/core/capped-collections/)
- [MongoDB Manual — Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/)
- [MongoDB Manual — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [MongoDB Manual — collMod Command](https://www.mongodb.com/docs/manual/reference/command/collMod/)
- [MongoDB Java Sync Driver — Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
