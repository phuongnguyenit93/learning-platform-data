# Running a CRUD Cycle and Inspecting Documents with mongosh or Compass

MongoDB stores data as **BSON documents** inside **collections**. Before working with Spring Data MongoDB's `MongoRepository` or `MongoTemplate`, you should walk directly through a **Create – Read – Update – Delete (CRUD)** cycle and observe how documents are actually stored. This hands-on lesson uses `mongosh` to show repeatable commands, while pointing out the equivalent actions in MongoDB Compass.

After this lesson, you will be able to:

- Connect to MongoDB with `mongosh` or Compass and select the right database and collection.
- Create documents, read with filters, perform conditional updates, and delete only the intended data.
- Distinguish an `ObjectId` `_id` from a string, and inspect BSON field types and nested documents.
- Read `acknowledged`, `insertedId`, `matchedCount`, `modifiedCount`, and `deletedCount` results to confirm operations.
- Use filters, projections, sort, limit, and `explain` to inspect data and query behavior.
- Map manual shell operations to their corresponding Spring Data MongoDB mappings and APIs.

## 1. Preparing the Lab Environment

You need a running MongoDB server and one of these two tools:

| Tool | How it is used | Strengths |
| --- | --- | --- |
| **mongosh** | Type JavaScript commands in the MongoDB Shell | Easy to copy, save, repeat, and verify step-by-step results |
| **MongoDB Compass** | Graphical UI; open collections to inspect and edit documents | Easy to visualize BSON structures, filter data, edit fields, and view query plans |

In the examples, assume a local MongoDB instance is listening on `127.0.0.1:27017` and **does not require authentication**. This setup is only appropriate for an isolated local/training environment.

Open a terminal:

```bash
mongosh "mongodb://127.0.0.1:27017"
```

If the server requires authentication, use an appropriate URI or pass `--username` and `--authenticationDatabase` so `mongosh` prompts for a password; never put real passwords into examples or commit passwords into repositories. For MongoDB Atlas or remote servers, use the provided URI with proper authentication and TLS settings.

In Compass, click **New Connection**, paste the connection string, and click **Connect**. The rest of this lesson uses the same server and database so you can observe changes from both tools. If your Spring Boot application also accesses MongoDB, ensure all three connect to the exact same database.

### 1.1. Selecting the Test Database and Collection

In `mongosh`:

```javascript
use spring_data_training

db.getName();                       // "spring_data_training"
show collections

const books = db.getCollection("crud_lab_books");
const labRun = "setup-007-" + new ObjectId().toHexString();
print("Lab run ID: " + labRun);
```

The `crud_lab_books` collection is strictly for this exercise. Each run generates a fresh `labRun` value to isolate your data from previous attempts. **Keep this `mongosh` session open** for subsequent commands so you can reuse `books` and `labRun`.

MongoDB may create a collection lazily when you insert the first document; calling `getCollection` alone does not necessarily create the collection in the database. If `show collections` does not list the new name before an insert, that is normal behavior.

**Lab safety rule:** every update and delete query in this lesson filters by `labRun`. Never run `deleteMany({})`, `drop()`, or unguarded deletes on collections holding real data.

## 2. Create — Inserting Documents

### 2.1. Creating Three Documents with `insertMany`

Run in the `mongosh` session where `books` and `labRun` are defined:

```javascript
const batch = books.insertMany([
  {
    labRun: labRun,
    sku: "BK-101",
    title: "Introduction to MongoDB",
    priceVnd: 129000,
    stock: 10,
    tags: ["database", "beginner"],
    publisher: { name: "Tech Press", country: "VN" },
    createdAt: new Date()
  },
  {
    labRun: labRun,
    sku: "BK-102",
    title: "Document Design",
    priceVnd: 99000,
    stock: 2,
    tags: ["database", "design"],
    publisher: { name: "Tech Press", country: "VN" },
    createdAt: new Date()
  },
  {
    labRun: labRun,
    sku: "BK-103",
    title: "Aggregation in Practice",
    priceVnd: 149000,
    stock: 0,
    tags: ["database", "aggregation"],
    publisher: { name: "Software Press", country: "VN" },
    createdAt: new Date()
  }
]);

printjson(batch);
const firstId = batch.insertedIds[0];
```

The result will include `acknowledged: true` and `insertedIds` containing the identifiers of the three documents. Since `_id` was omitted, the driver normally auto-generates a BSON `ObjectId`. The exact generated values differ on each run.

The created fields illustrate several BSON types:

| Field | Expected Type | Meaning |
| --- | --- | --- |
| `_id` | ObjectId | Unique identifier within the collection |
| `labRun`, `sku`, `title` | String | Lab run marker, book SKU, book title |
| `priceVnd`, `stock` | BSON numeric types | Integer price in VND and stock count; exact numeric BSON type depends on value/driver |
| `tags` | Array | List of strings |
| `publisher` | Embedded document | Publisher details |
| `createdAt` | Date | Timestamp created by `new Date()` |

Note: **displayed JSON is only a textual representation** of the data. BSON has richer specific types than JSON, such as `ObjectId`, `Date`, `Int32`, `Int64`, and `Decimal128`. When working with currency or large integers in an application, choose the appropriate data type rather than relying on how a UI renders the value.

### 2.2. Creating One More Document with `insertOne`

```javascript
const single = books.insertOne({
  labRun: labRun,
  sku: "BK-104",
  title: "Spring Data MongoDB",
  priceVnd: 189000,
  stock: 5,
  tags: ["spring", "database"],
  publisher: { name: "Software Press", country: "VN" },
  createdAt: new Date()
});

printjson(single.insertedId);
books.countDocuments({ labRun: labRun }); // Expected: 4
```

`insertOne` returns a single `insertedId`; `insertMany` returns `insertedIds`. If you manually provide an `_id` that duplicates an existing document in the same collection, the insert is rejected with a duplicate key error (typically `E11000`).

## 3. Read — Finding, Filtering, Sorting, and Inspecting Documents

### 3.1. Reading One Document by `_id`

```javascript
const oneBook = books.findOne({ _id: firstId });
printjson(oneBook);
```

`firstId` is an `ObjectId`. Do not casually replace it with a hex string in the filter, because BSON `ObjectId` and BSON `String` are two distinct types. If you only have a valid hex string, convert it explicitly:

```javascript
const idText = firstId.toHexString();
books.findOne({ _id: new ObjectId(idText) });
```

### 3.2. Reading Multiple Documents with Filters

`find` returns a **cursor**, not an array. In `mongosh`, you can call `toArray()` to display results for a small set:

```javascript
books.find({ labRun: labRun }).toArray();

// Books with at least one unit in stock:
books.find({
  labRun: labRun,
  stock: { $gte: 1 }
}).toArray();

// Find books containing tag "database":
books.find({
  labRun: labRun,
  tags: "database"
}).toArray();

// Query by nested field (dot notation):
books.find({
  labRun: labRun,
  "publisher.country": "VN"
}).toArray();
```

Common operators:

| Operator | Example | Meaning |
| --- | --- | --- |
| `$eq` | `{ stock: { $eq: 0 } }` | Equals value |
| `$gte` / `$lte` | `{ stock: { $gte: 1 } }` | Greater than or equal / less than or equal |
| `$in` | `{ sku: { $in: ["BK-101", "BK-103"] } }` | Matches any value in a set |
| `$and` / `$or` | `{ $or: [{stock: 0}, {stock: 2}] }` | Combines conditions |
| `$exists` | `{ updatedAt: { $exists: true } }` | Checks field presence |

In real commands, always combine your filter with `labRun` or a business key so you do not pick up records from other runs.

### 3.3. Projection, Sort, and Limit

Select only the fields needed for display, sort by stock descending, and limit to 3 results:

```javascript
books.find(
  { labRun: labRun },
  { _id: 0, sku: 1, title: 1, stock: 1 }
).sort({ stock: -1, sku: 1 }).limit(3).toArray();
```

Explanation:

- The first filter selects only documents from the current lab run.
- The projection `{ _id: 0, sku: 1, title: 1, stock: 1 }` returns the three display fields and hides `_id`.
- `sort({ stock: -1, sku: 1 })` sorts by `stock` descending, then `sku` ascending on ties.
- `limit(3)` returns at most three documents.

Regular projections cannot arbitrarily mix inclusion (`1`) and exclusion (`0`) fields; `_id` is the standard exception. On large datasets, avoid calling unbounded `toArray()`, as it can exhaust client memory.

### 3.4. Counting and Inspecting Field Types

```javascript
books.countDocuments({ labRun: labRun }); // Expected: 4
books.distinct("publisher.name", { labRun: labRun });

const current = books.findOne({ _id: firstId });
printjson({
  idType: typeof current._id,
  idIsObjectId: current._id instanceof ObjectId,
  dateIsDate: current.createdAt instanceof Date,
  tagsIsArray: Array.isArray(current.tags)
});
```

`typeof` on an `ObjectId` instance returns the JavaScript type `"object"`; use `instanceof ObjectId` when you need to distinguish it precisely. `printjson` in `mongosh` and the Compass UI may format the same value differently, but the underlying BSON type stored in the database is what governs query matching.

## 4. Update — Modifying Documents Safely

### 4.1. `updateOne` with `$set` and `$inc`

Decrease stock of `BK-101` by 2 while recording the update timestamp:

```javascript
const updated = books.updateOne(
  {
    labRun: labRun,
    sku: "BK-101",
    stock: { $gte: 2 }
  },
  {
    $inc: { stock: -2 },
    $set: { updatedAt: new Date() }
  }
);

printjson({
  matchedCount: updated.matchedCount,
  modifiedCount: updated.modifiedCount
});

books.findOne(
  { labRun: labRun, sku: "BK-101" },
  { _id: 0, sku: 1, stock: 1, updatedAt: 1 }
);
// Expected: stock = 8 after the first run.
```

The `stock: { $gte: 2 }` filter and `$inc` update happen atomically on **a single document**: two concurrent requests cannot both pass the filter against stale stock and oversell, as long as both use this guarded update condition.

**Note on repeatability:** rerunning the command above decreases stock by another 2 as long as sufficient stock remains. This is a cumulative update and is **not idempotent**. In real business workflows, when retrying after timeouts or handling duplicate events, design an idempotency key or state guard.

Distinguishing return fields:

| Field | Meaning |
| --- | --- |
| `matchedCount` | Number of documents matching the filter (for `updateOne`, at most 1) |
| `modifiedCount` | Number of documents actually modified |
| `upsertedId` | Generated ID when `upsert: true` is used and a new document is inserted |

`matchedCount = 1` and `modifiedCount = 0` can happen when `$set` assigns the exact value already stored. `matchedCount = 0` can mean no matching ID/SKU exists or the precondition failed; do not assume it is a connection error.

### 4.2. `updateMany` with a Filter

Tag **only the documents belonging to the current lab run**:

```javascript
const many = books.updateMany(
  { labRun: labRun },
  { $set: { source: "setup-007" } }
);

printjson(many);
books.countDocuments({
  labRun: labRun,
  source: "setup-007"
}); // Expected: 4
```

`updateMany` can modify multiple documents. Atomicity is still guaranteed **per individual document**, which does not mean the entire set of documents is updated as one multi-document transaction. If multiple documents must commit or roll back together, evaluate multi-document transactions on an appropriate MongoDB deployment.

### 4.3. Distinguishing Update vs. Replace

- `$set`, `$inc`, `$push`, and `$unset` are **update operators**: they modify only the specified parts.
- `replaceOne(filter, replacement)` replaces **the entire document body** (subject to `_id` rules): fields omitted from `replacement` disappear.
- `upsert: true` inserts a document when no match is found; this behavior should be chosen intentionally to avoid creating stray records.

Example updating only the title safely:

```javascript
books.updateOne(
  { labRun: labRun, sku: "BK-102" },
  { $set: { title: "Document Design with MongoDB" } }
);
```

Do not write `updateOne(filter, { title: "..." })` as a replacement in modern MongoDB: update commands require update operators or an update pipeline. Use `replaceOne` when you truly intend to replace the whole document.

### 4.4. Updating Arrays and Nested Fields

Add a tag to `BK-103`:

```javascript
books.updateOne(
  { labRun: labRun, sku: "BK-103" },
  {
    $addToSet: { tags: "practice" },
    $set: { "publisher.country": "VN" }
  }
);
```

`$addToSet` avoids inserting duplicate tag values in this update, whereas `$push` always appends an element. Use dot notation to update `publisher.country` alone; if you `$set` the entire `publisher` object to a new object, existing nested fields not included in that object may be lost.

## 5. Delete — Conditional Deletion and Verifying Results

### 5.1. Deleting One Document

```javascript
const deletedOne = books.deleteOne({
  labRun: labRun,
  sku: "BK-104"
});
printjson(deletedOne); // Expected: deletedCount = 1

books.countDocuments({ labRun: labRun }); // Expected: 3
```

`deleteOne` deletes at most one document matching the filter. If the filter is underspecified and matches multiple documents, MongoDB picks one of them; therefore, filter by `_id` or an unambiguous unique key when deleting a specific record.

### 5.2. Cleaning Up Data from the Current Lab Run Only

After finishing Compass inspection and the exercises, delete **only documents carrying the current session's `labRun` marker**:

```javascript
const beforeCleanup = books.countDocuments({ labRun: labRun });
print("Documents about to be deleted: " + beforeCleanup);

const cleanup = books.deleteMany({ labRun: labRun });
printjson({ deletedCount: cleanup.deletedCount });

books.countDocuments({ labRun: labRun }); // Expected: 0
```

If you still want to inspect the documents in Compass, **do not run the cleanup step yet**. Most importantly, never replace the filter above with `{}` as that deletes every document in the collection. `deleteMany` removes matching documents without dropping the collection or its indexes.

## 6. Inspecting the Same Data in MongoDB Compass

Open Compass and connect to the **exact same URI** that `mongosh` is using. In the left navigation panel:

1. Select the `spring_data_training` database.
2. Select the `crud_lab_books` collection and open the **Documents** tab.
3. Enter the JSON filter matching the marker printed by `mongosh` into the **Filter** bar:

   ```json
   { "labRun": "setup-007-REPLACE_WITH_PRINTED_VALUE" }
   ```

4. Apply the filter so only documents from the current run are visible.
5. Expand a document and inspect `_id`, `tags`, `publisher`, `createdAt`, and the updated values after running updates.

The string `setup-007-REPLACE_WITH_PRINTED_VALUE` is a **placeholder**: replace it with the full string printed by `print("Lab run ID: " + labRun)`. If you enter the wrong marker, Compass will display zero documents even though the connection works.

### 6.1. Inserting a Document in Compass

In the **Documents** tab, click **Add Data** / **Insert Document** (button labels vary slightly across versions). For example, insert a test record directly:

```json
{
  "labRun": "setup-007-REPLACE_WITH_PRINTED_VALUE",
  "sku": "BK-COMPASS",
  "title": "Inserted from Compass",
  "priceVnd": 75000,
  "stock": 1,
  "tags": ["compass"]
}
```

After clicking **Insert**, observe the `_id` generated by the tool/server. Because this document shares the same `labRun`, it will also be cleaned up by `deleteMany({ labRun: labRun })`. If you inserted this Compass document, add 1 to the "expected 3/4" document counts from earlier sections from this point forward.

### 6.2. Filtering, Sorting, and Limiting Results

In the same collection, use the **Documents** tab's filter and options inputs:

| What you want to see | Corresponding Filter / Project / Sort |
| --- | --- |
| All documents from this lab run | Filter: `{ "labRun": "..." }` |
| Books in stock | Filter: `{ "labRun": "...", "stock": { "$gt": 0 } }` |
| Books from publishers in Vietnam | Filter: `{ "labRun": "...", "publisher.country": "VN" }` |
| Only title and stock | Project: `{ "title": 1, "stock": 1, "_id": 0 }` |
| Sort by stock descending | Sort: `{ "stock": -1 }` |
| Show only a subset of documents | Adjust **Limit** if your Compass version displays that option |

In JSON input boxes, follow the JSON/Extended JSON syntax accepted by your Compass version. Querying by `ObjectId` can use Extended JSON syntax:

```json
{ "_id": { "$oid": "665f1f2a4b6c7d8e9f001234" } }
```

The ID value here is an example; when searching for an actual document, replace it with the `_id` you observe. In `mongosh`, the equivalent syntax is `{ _id: ObjectId("...") }`.

### 6.3. Updating and Deleting from the UI

To test **Update**, filter by `labRun` and `sku`, open the document, click **Edit Document** or the edit icon, change `stock` from its current value to a new value, and save. Verify in `mongosh`:

```javascript
books.findOne(
  { labRun: labRun, sku: "BK-102" },
  { _id: 0, sku: 1, stock: 1 }
);
```

To test **Delete**, filter for the `BK-COMPASS` document you created from the UI, click delete, and confirm. Then verify:

```javascript
books.countDocuments({
  labRun: labRun,
  sku: "BK-COMPASS"
}); // 0 if the document was deleted properly.
```

Editing data directly through Compass bypasses business rules enforced by the Java application. Only do this on test data; in real environments, route updates through appropriate aggregates/services.

### 6.4. Schema and Explain Plan

Beyond the Documents tab, Compass usually provides schema analysis and query execution plan tools (tab names/features vary by version):

- **Schema**: displays observed fields, data types, and value distributions across a **sample of documents**; this is not an exhaustive schema check across the entire collection.
- **Explain Plan**: inspects stages of the execution plan, showing collection scans vs. index scans and corresponding query statistics.
- **Indexes**: lists existing indexes, including the default index on `_id`.

Never conclude an index is "good" merely because its name shows up in the UI; evaluate it against query patterns, selectivity, and the number of keys/documents scanned.

## 7. Inspecting Query Plans in mongosh

For a typical filter:

```javascript
books.find({
  labRun: labRun,
  sku: "BK-101"
}).explain("executionStats");
```

Without a matching index, the plan may scan many documents in the collection. To test an index directly on this lab collection:

```javascript
books.createIndex(
  { labRun: 1, sku: 1 },
  { name: "idx_lab_run_sku" }
);

books.find({
  labRun: labRun,
  sku: "BK-101"
}).explain("executionStats");
```

When reading the output, pay attention to `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, and `nReturned`. MongoDB may choose different plans depending on statistics, version, and data volume; a sample of just a few documents is too small to benchmark real index performance benefits. In real applications, design indexes around actual queries and test with representative data volumes and workloads.

**Remember:** `explain` is a diagnostic tool for observing query execution mechanics. It does not replace latency testing, application monitoring, or analyzing expensive queries in production.

## 8. Mapping to Spring Data MongoDB

When working through Spring Data MongoDB, Java objects map to BSON documents. The very same collection modified via `mongosh`/Compass can be read via `MongoRepository` or `MongoTemplate` when connected to the same database.

Abbreviated entity example representing the main fields:

```java
import java.util.Date;
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "crud_lab_books")
public class LabBook {
    @Id
    private ObjectId id;
    private String labRun;
    private String sku;
    private String title;
    private long priceVnd;
    private int stock;
    private List<String> tags;
    private Publisher publisher;
    private Date createdAt;
    private Date updatedAt;
    private String source;

    protected LabBook() {}

    public ObjectId getId() { return id; }
    public String getSku() { return sku; }
    public String getLabRun() { return labRun; }
    public String getTitle() { return title; }
    public int getStock() { return stock; }

    public static class Publisher {
        private String name;
        private String country;

        protected Publisher() {}
        public String getName() { return name; }
        public String getCountry() { return country; }
    }
}
```

Because `@Id` maps `id` to `_id`, the repository declares the matching Java ID type:

```java
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface LabBookRepository
        extends MongoRepository<LabBook, ObjectId> {
    List<LabBook> findByLabRun(String labRun);
    List<LabBook> findByLabRunAndStockGreaterThan(
        String labRun, int stock
    );
}
```

In a service, `findByLabRun(...)` corresponds semantically to `books.find({ labRun: ... })`; `findById(...)` corresponds to filtering by `_id`. With `MongoTemplate`:

```java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public boolean reduceStock(
        MongoTemplate template, String labRun, String sku) {
    Query query = Query.query(
        Criteria.where("labRun").is(labRun)
                .and("sku").is(sku)
                .and("stock").gte(1)
    );
    Update update = new Update()
        .inc("stock", -1)
        .currentDate("updatedAt");

    return template.updateFirst(query, update, LabBook.class)
                   .getModifiedCount() == 1;
}
```

The snippet above keeps the stock guard directly inside the update operation. If you modify an entity and call `repository.save(entity)` after reading it, watch out for overwriting concurrent changes; when needed, use `@Version` and optimistic locking.

**Mapping note:** `save` generally rewrites the document state from the entity. If an entity maps only a subset of fields while the actual document holds additional fields, saving the entity can drop unmapped fields. When updating only a specific field on existing documents, prefer a targeted conditional update or full entity mapping.

### Operation Comparison Table

| Need | mongosh | Spring Data MongoDB |
| --- | --- | --- |
| Create one document | `insertOne(document)` | `repository.insert(entity)` or `mongoTemplate.insert(entity)` |
| Fetch by ID | `findOne({ _id: id })` | `repository.findById(id)` or `mongoTemplate.findById(id, Type.class)` |
| Find multiple documents | `find(filter)` | Derived repository query or `mongoTemplate.find(query, Type.class)` |
| Update fields | `updateOne(filter, { $set: ... })` | `mongoTemplate.updateFirst(query, update, Type.class)` |
| Delete by condition | `deleteOne(filter)` | `mongoTemplate.remove(query, Type.class)` or delete by ID via repository |
| Inspect update counts | `matchedCount` / `modifiedCount` | `UpdateResult.getMatchedCount()` / `getModifiedCount()` |

In applications, encapsulate operations inside clear service boundaries; Java code must validate inputs, enforce permissions, handle ID type conversions, and manage errors properly.

## 9. Common Errors During CRUD Practice

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `ECONNREFUSED` on connect | MongoDB not running or wrong host/port | Verify server status, URI, port, and network |
| `Authentication failed` | Wrong username, password, or auth database | Check authentication config without leaking secrets into logs |
| `find()` returns nothing | Wrong database, collection, `labRun`, or BSON type | Check `db.getName()`, collection name, marker, and `_id` |
| Querying `_id` by string fails to match | Document uses BSON `ObjectId` | Use `ObjectId("...")` or matching type in query |
| `E11000 duplicate key` error | Duplicate `_id` or unique index violation | Read index name in the error; fix ID generation/validation strategy |
| `matchedCount = 0` | No document matches filter or precondition | Re-read by `labRun`, `sku`, and `stock` condition |
| `modifiedCount = 0` while matched is 1 | Assigning the exact value already stored | Compare before/after state and inspect update operators |
| Different data appears in Compass vs. mongosh | Connected to different cluster/database or using different filters | Compare URI, database, collection, and active filter |
| Updating nested document drops sibling fields | Replaced entire subdocument or misused replace | Update via dot notation or explicitly supply the whole object |
| Accidentally deleted too many records | Delete filter was too broad | Always run `countDocuments(filter)` first and filter by specific marker/ID |

MongoDB does not enforce every business rule on behalf of the application. For example, updating `stock` to a negative number succeeds unless prevented by a write condition, schema validator, or application guard. Lab data lets you observe exact command behavior, while real applications must add validation layers and proper tests.

## 10. Practice Exercises

**Exercise 1 — Full CRUD.** Create a new document with `sku: "BK-EX-01"` and your current `labRun`, read it back by ID, update `stock` from 3 to 5, and delete only that document. After each step, inspect the result in both `mongosh` and Compass.

**Exercise 2 — Filtering and projection.** Write a query returning books with `stock >= 1`, displaying only `sku`, `title`, and `priceVnd`, sorted by price descending. Explain why the `labRun` filter must be preserved.

**Exercise 3 — Testing conditional updates.** Given `BK-103` has stock 0, try `$inc: {stock: -1}` with filter `stock: {$gte: 1}`; explain why `matchedCount` is 0. Next, add inventory with `$inc: {stock: 5}` and retry.

**Exercise 4 — Observing types.** Use Compass to inspect `ObjectId`, dates, the `tags` array, and the `publisher` subdocument. Rewrite the `_id` filter in `mongosh` and explain the difference between an `ObjectId` value and a hex string.

**Exercise 5 — Java integration.** Create `LabBookRepository`, call `findByLabRun` with your active marker, and compare the count against `countDocuments` in `mongosh`. Try reducing stock via `MongoTemplate` and refresh Compass.

**Exercise 6 — Reading query plans.** Run `explain("executionStats")` for the `labRun + sku` query before and after creating the compound index. Compare `totalDocsExamined` and `totalKeysExamined`; explain why testing on a handful of documents is insufficient to conclude production performance.

### Self-Check Results

If you ran the main commands sequentially **and have not added/deleted/edited documents from Compass**:

1. After `insertMany`: **3** documents matching `labRun`.
2. After `insertOne`: **4** documents.
3. After the first `updateOne`: `BK-101.stock` drops from **10 to 8**.
4. After `updateMany`: all **4** documents have `source: "setup-007"`.
5. After `deleteOne` on `BK-104`: **3** documents remain.
6. After `deleteMany({labRun})` in cleanup: **0** documents remain for that lab run.

Cumulative update operators such as `$inc` change results when rerun. Generate a fresh marker whenever starting from scratch and check data before updating or cleaning up.

### Takeaway

The **Create – Read – Update – Delete** cycle lets you trace data end to end from write commands to persisted BSON documents. `mongosh` excels at running exact commands and checking results; Compass excels at visualizing documents, data types, queries, and indexes. When moving to Spring Data MongoDB, the same rules hold: **filter accurately, use matching BSON types, check affected counts, apply conditional updates, and verify results** before embedding operations into business logic.
