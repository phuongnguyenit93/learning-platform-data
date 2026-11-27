# Nullability, Default Values, and Missing Fields

> **Chapter:** Data Types  
> **Module:** `SPRING_DATA_MONGODB` — using Spring Data MongoDB to connect, map documents, and manipulate data via `MongoTemplate` or repositories.  
> **Goal:** Distinguish BSON `null`, missing fields, and empty values; write accurate filters; understand how Spring Data MongoDB reads/writes `null`; place defaults at the right layer; and handle updates, indexes, validation, and legacy data consistently.

## 1. A MongoDB Field Can Exist in Multiple States

MongoDB stores data as BSON documents. Unlike a table with fixed columns, every document in a collection can carry a different set of fields. For a `note` field, distinguish at least three states:

1. **Field present, BSON `null` value:** `{ note: null }`.
2. **Field does not exist:** `{ }` (no `note` key).
3. **Field present, concrete value:** `{ note: "" }`, `{ note: "x" }`, `{ note: 0 }`, `{ note: false }`, or `{ note: [] }`.

In Java, the first and second documents may both map to `String note == null` on a standard `String` property. Therefore, **a Java object holding null is not enough to tell whether the underlying BSON field actually existed**.

### 1.1. State Distinction Table

| BSON Data | Field Present? | Is It BSON Null? | Is It Empty / Zero? |
| --- | --- | --- | --- |
| `{ note: null }` | Yes | Yes | Not an empty string |
| `{ }` | No | No value to check | Field absent |
| `{ note: "" }` | Yes | No | Empty string |
| `{ retryCount: 0 }` | Yes | No | Valid number 0 |
| `{ active: false }` | Yes | No | Valid boolean false |
| `{ tags: [] }` | Yes | No | Empty array |
| `{ settings: {} }` | Yes | No | Empty subdocument |

Values such as `0`, `false`, `""`, and `[]` all convey potentially important business meaning; never lump them together as “no data”.

### 1.2. Loading Sample Data

Practice in a dedicated database via `mongosh`:

~~~javascript
use spring_data_mongodb_lab

const workitems = db.workitems_null_demo_008;

// Run only on an empty test collection.
workitems.insertMany([
  {
    _id: "w001",
    title: "Register",
    note: null,
    active: false,
    retryCount: 0,
    tags: [],
    status: "NEW"
  },
  {
    _id: "w002",
    title: "Pending",
    active: true,
    status: "NEW"
    // Missing note, retryCount, and tags.
  },
  {
    _id: "w003",
    title: "Completed",
    note: "Approved",
    active: true,
    retryCount: 2,
    tags: ["urgent"],
    status: "DONE"
  },
  {
    _id: "w004",
    title: "Leave note blank",
    note: "",
    active: false,
    retryCount: 0,
    tags: [],
    status: null
  }
]);
~~~

The four documents use fixed `_id` values for easy comparison. Re-running `insertMany` will raise duplicate `_id` errors; only reset test collections that you own. Queries in the next section assume data has **not yet been modified** by later update examples.

## 2. Querying `null`, Missing, and Present Values

### 2.1. `{ field: null }` Includes Missing Fields

~~~javascript
// Result: w001 (note:null) and w002 (missing note).
workitems.find({ note: null });
~~~

This is a critical distinction: `{ note: null }` in MongoDB matches **two cases**—fields present with BSON null and missing fields. If the business rule asks for “notes explicitly set to null”, this filter is too broad.

### 2.2. Matching Only BSON Null with `$type`

~~~javascript
// Result: only w001.
workitems.find({ note: { $type: "null" } });

// Equivalent using BSON type code Null = 10.
workitems.find({ note: { $type: 10 } });
~~~

`$type: "null"` matches only BSON null on the examined field. Here `note` is a scalar field; for array fields, `$type` in queries also matches array elements, so test separately if your schema allows arrays containing `null`.

### 2.3. Matching Only Missing Fields with `$exists: false`

~~~javascript
// Result: only w002.
workitems.find({ note: { $exists: false } });

// Result: w001, w003, w004; includes note:null.
workitems.find({ note: { $exists: true } });
~~~

`$exists` asks **whether the key appears**; it does not ask whether the value is non-null. `$exists: true` includes BSON null, empty strings, and any other value.

### 2.4. Matching Only Fields with Non-Null Values

~~~javascript
// Result: w003 and w004.
workitems.find({ note: { $ne: null } });
~~~

Under the special `$ne: null` comparison, MongoDB selects documents where the field exists and is **not null**. Thus the empty string `""` in `w004` is still matched. For values other than `null`, `$ne` generally also matches documents missing the field; do not generalize `$ne: null` behavior to every `$ne`.

### 2.5. Matching Only Empty Strings

~~~javascript
// Result: only w004.
workitems.find({ note: "" });
~~~

An empty string is not synonymous with BSON null, even if UI forms often display both as a blank input box.

### 2.6. Query Comparison Table on Sample Data

| Filter | Matching `_id` | Meaning |
| --- | --- | --- |
| `{ note: null }` | w001, w002 | BSON null **or** missing |
| `{ note: { $type: "null" } }` | w001 | BSON null |
| `{ note: { $exists: false } }` | w002 | Key absent |
| `{ note: { $exists: true } }` | w001, w003, w004 | Key present, including null |
| `{ note: { $ne: null } }` | w003, w004 | Present with non-null value |
| `{ note: "" }` | w004 | Empty string |
| `{ active: false }` | w001, w004 | Boolean false |
| `{ retryCount: 0 }` | w001, w004 | Number 0 |
| `{ tags: [] }` | w001, w004 | Empty array |

**Self-check:** run `countDocuments(filter)` with the same filters and observe the counts. If counts differ from the table, the collection was modified by write examples or contains extra records.

## 3. Setting a Field to `null` vs. Removing It Are Two Different Operations

MongoDB does not treat `$set: { field: null }` and `$unset: { field: "" }` as equivalent.

~~~javascript
// Before operation: w002 has no note.
workitems.updateOne(
  { _id: "w002" },
  { $set: { note: null } }
);
// After operation: w002 has field note with value BSON null.

// Remove the note key completely from the document.
workitems.updateOne(
  { _id: "w002" },
  { $unset: { note: "" } }
);
// After operation: w002 again has no note.
~~~

Running these two statements back-to-back returns `w002` to its starting state. `$unset` does not mean “set a value to null”; it removes the field from the document. When calling `updateOne()`, inspect `matchedCount` and `modifiedCount` to distinguish “document not found” from “operation made no change”.

### 3.1. Business Impact

Suppose `note` represents a rejection reason:

- **Missing:** legacy system did not support reasons, or the user was never prompted.
- **BSON null:** the user or workflow confirmed there is no reason.
- **Empty string:** the user submitted blank text; may be rejected as invalid input.
- **Non-empty string:** a reason was provided.

This is an example of a **business convention**, not fixed semantics enforced by MongoDB. Decide upfront whether a `PATCH` API treats `null` as “delete field” or “write null”, and apply that convention consistently across all clients.

### 3.2. Do Not Use Falsy Checks to Detect Missing Fields

In JavaScript, the check:

~~~javascript
if (!payload.retryCount) {
  // Wrong if business logic must distinguish 0, null, and absent field.
}
~~~

treats `0`, `null`, and `undefined` all as falsy. Instead:

~~~javascript
const hasRetryCount = Object.prototype.hasOwnProperty.call(
  payload,
  "retryCount"
);

if (hasRetryCount) {
  // Field is present, even when its value is 0 or null.
}
~~~

Similarly, a Java DTO whose properties are all nullable `String`/`Integer` without tracking **field presence** is usually insufficient to express full HTTP PATCH semantics.

## 4. How Does Spring Data MongoDB Write Java Null Properties?

Spring Data MongoDB uses `MappingMongoConverter` to convert between Java entities and BSON documents. In versions supporting `@Field(write = ...)` (Spring Data MongoDB 3.3+), the default strategy for ordinary nullable properties is **`Field.Write.NON_NULL`**:

- If the property value is **non-null in Java**, the converter writes the corresponding value.
- If the property value **is Java null**, by default the converter **omits the field** when serializing the entity to a document.
- If you must persist an **explicit BSON null**, use `@Field(write = Field.Write.ALWAYS)` on the property.

### 4.1. Default Entity: Java Null Can Become Missing

~~~java
package com.example.workitems;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "workitems_null_demo_008")
public class WorkItemDefault {
    @Id
    private String id;

    private String title;
    private String note;  // Default: null is not written.

    protected WorkItemDefault() { }

    public WorkItemDefault(String id, String title, String note) {
        this.id = id;
        this.title = title;
        this.note = note;
    }

    public String getId() { return id; }
    public String getTitle() { return title; }
    public String getNote() { return note; }
}
~~~

For a new document written with the default converter:

~~~java
template.insert(new WorkItemDefault(
    "w005", "No note yet", null
));
~~~

The typical BSON result is:

~~~javascript
{
  _id: "w005",
  title: "No note yet"
  // No note field.
}
~~~

This example assumes `w005` does not already exist. The `note` field is omitted simply because the Java value is `null`; this differs from assuming “Java null must always become `note: null`”.

### 4.2. Using `@Field(write = ALWAYS)` to Persist BSON Null

~~~java
package com.example.workitems;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "workitems_null_demo_008")
public class WorkItemExplicitNull {
    @Id
    private String id;

    private String title;

    @Field(write = Field.Write.ALWAYS)
    private String note;

    protected WorkItemExplicitNull() { }

    public WorkItemExplicitNull(String id, String title, String note) {
        this.id = id;
        this.title = title;
        this.note = note;
    }

    public String getId() { return id; }
    public String getTitle() { return title; }
    public String getNote() { return note; }
}
~~~

~~~java
template.insert(new WorkItemExplicitNull(
    "w006", "Confirmed no note", null
));
~~~

Typical BSON result:

~~~javascript
{
  _id: "w006",
  title: "Confirmed no note",
  note: null
}
~~~

These two classes are **two mapping alternatives for comparison**, not a recommendation to create two repositories sharing a collection in a real project. Only use `write = ALWAYS` when business logic needs to distinguish BSON null from missing. Writing many unnecessary null fields inflates document size and can affect indexes.

**Note:** `@Field(write = ALWAYS)` governs Spring Data MongoDB's **entity-to-document serialization**. It does not rewrite existing documents, does not force other `mongosh`/driver clients to write null, and does not define a MongoDB server-level default.

### 4.3. Reading BSON Null and Missing into Java

With a reference property `String note`, after hydrating the entity, both cases below produce `getNote() == null`:

~~~javascript
{ _id: "w001", note: null }
{ _id: "w002" }
~~~

Inspecting `note` on the Java entity alone cannot recover whether MongoDB stored null or lacked the key. When you need **field presence**, query raw BSON directly or use `$type` in aggregation as shown in Section 8.

~~~java
import com.mongodb.client.model.Filters;
import org.bson.Document;

Document raw = template.getDb()
    .getCollection("workitems_null_demo_008")
    .find(Filters.eq("_id", "w002"))
    .first();

if (raw != null) {
    boolean present = raw.containsKey("note");
    boolean explicitNull = present && raw.get("note") == null;
    // present=false: missing; explicitNull=true: BSON null.
}
~~~

This snippet uses the MongoDB Java Driver directly via `template.getDb()`, inspecting key presence on the raw document. Standard mapping APIs fit most CRUD work, though they collapse the two states when the Java model exposes only a nullable value.

## 5. Java Defaults Differ from Defaults Persisted in MongoDB

There are at least four layers where default values are created or interpreted. They serve different purposes:

| Where Default Is Defined | When Applied? | Written to MongoDB? |
| --- | --- | --- |
| Java field initializer / constructor | When instantiating Java object | Only if the entity is subsequently persisted with that value |
| Business service / factory | When creating records per app rules | Yes, if the service includes the value in write operations |
| MongoDB `$setOnInsert` | When `upsert` inserts a new document | Yes, server-side |
| `$ifNull` in aggregation | When reading and projecting results | No; only computes a value in query output |

### 5.1. Initialization in the Java Entity

~~~java
@Document("workitems_null_demo_008")
public class WorkItemWithDefaults {
    @Id
    private String id;

    private String status = "NEW";
    private int retryCount = 0;
    private boolean active = false;
    private java.util.List<String> tags = new java.util.ArrayList<>();

    protected WorkItemWithDefaults() { }

    public WorkItemWithDefaults(String id) {
        this.id = id;
    }

    // Appropriate getters/setters or business methods.
}
~~~

When code instantiates a new object, `status` is `"NEW"`, `retryCount` is `0`, `active` is `false`, and `tags` is an empty list. If this object is then inserted/saved, the converter writes those values into the document.

However, a field initializer is **not** a server-enforced default for all writers. For instance, `mongosh` can still insert `{ _id: "w100" }` without `status` if the collection has no schema validation requiring it.

When reading a document **missing a field**, object construction and property population may preserve the Java initializer; with constructor binding or records, missing data may be passed differently, so verify your actual mapping rules. When reading a document with an **explicit null field**, the converter may set null onto reference properties.

Therefore, **do not use field initializers as an implicit migration mechanism**. Reading `status = "NEW"` on a hydrated object does not prove the underlying document contains a `status` field.

### 5.2. Primitives vs. Wrappers: 0 and `false` Can Be Misinterpreted

~~~java
private int retryCount;      // Cannot represent Java null.
private Integer retryCount;  // Can be null, 0, 1, ...

private boolean active;      // Cannot represent Java null.
private Boolean active;      // Can be null, false, true.
~~~

Primitive types must always hold a value in Java. Depending on instantiation, reading a document missing the field can leave `0` or `false`, making it impossible to tell a **Java default** from a **user-supplied value**. With constructors accepting primitives, missing/null fields can also cause binding issues depending on the converter and constructor signature.

Wrapper types `Integer`/`Boolean` can represent Java null, yet **Java null still does not distinguish BSON null from missing**. When business rules require three states, track presence explicitly or inspect raw BSON.

### 5.3. Setting Defaults in Services or Factories

When a state must exist in **every new document**, normalize it at creation time:

~~~java
public WorkItemWithDefaults createNewWorkItem(String id) {
    // Constructor establishes the entity's initial values.
    return new WorkItemWithDefaults(id);
}
~~~

This is an application-level rule; if multiple services or jobs write to the same collection, all writers must follow it or the database needs schema validation to reject non-conforming inserts. A default applied only in Service A does not guarantee records created by Service B are valid.

## 6. Default Values During `upsert` with `$setOnInsert`

MongoDB provides the `$setOnInsert` operator for fields that should only be initialized when an `upsert` **creates a new document**:

~~~javascript
workitems.updateOne(
  { _id: "w200" },
  {
    $set: {
      title: "Created or updated work item",
      active: true
    },
    $setOnInsert: {
      status: "NEW",
      retryCount: 0,
      tags: [],
      createdAt: new Date()
    }
  },
  { upsert: true }
);
~~~

If `w200` does not exist yet, MongoDB inserts a new document and applies both `$set` and `$setOnInsert`. If `w200` already exists, only `$set` executes; `$setOnInsert` does not overwrite existing status, retry history, or original creation time.

**Notes:**

- To modify a value on every upsert, use `$set`; to initialize only at creation, use `$setOnInsert`.
- Do not place the **same field path** in both `$set` and `$setOnInsert` in a single operation, as that causes an update conflict error.
- Use IDs or business keys backed by appropriate unique indexes to reduce duplicate-creation races under concurrency.
- `$setOnInsert` only applies to that upsert operation; it does not act as a global default for `insertOne` calls from other clients.

With Spring Data MongoDB:

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

Query query = Query.query(Criteria.where("id").is("w201"));

Update update = new Update()
    .set("title", "New work item")
    .setOnInsert("status", "NEW")
    .setOnInsert("retryCount", 0)
    .setOnInsert("createdAt", java.time.Instant.now());

template.upsert(query, update, WorkItemDefault.class);
~~~

`Query`/`Update` map according to the entity. `Instant` converts to BSON Date using the registered converters; this example assumes standard date-time conversion settings. If entity metadata or versioning uses custom field names, verify actual mapping.

## 7. Writing Null and Missing Queries with `MongoTemplate`

Spring Data MongoDB supports explicit null criteria on `Criteria`:

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

// WorkItemDefault from section 4.1 maps to the sample collection.

// Matches BSON null OR missing field.
List<WorkItemDefault> nullOrMissing = template.find(
    Query.query(Criteria.where("note").isNull()),
    WorkItemDefault.class
);

// Only BSON null (Criteria.isNullValue() in Spring Data MongoDB 3.3+).
List<WorkItemDefault> explicitNull = template.find(
    Query.query(Criteria.where("note").isNullValue()),
    WorkItemDefault.class
);

// Only missing note key.
List<WorkItemDefault> missing = template.find(
    Query.query(Criteria.where("note").exists(false)),
    WorkItemDefault.class
);

// Field exists with a non-null value.
List<WorkItemDefault> nonNull = template.find(
    Query.query(Criteria.where("note").ne(null)),
    WorkItemDefault.class
);
~~~

`Criteria.where("note").is(null)` also expresses standard null equality (null or missing), while `isNull()` communicates intent more clearly. When you need **BSON null only**, `isNullValue()` emits a BSON type check rather than plain null equality.

| Goal | `mongosh` | Spring Data `Criteria` |
| --- | --- | --- |
| Null or missing | `{ note: null }` | `where("note").isNull()` |
| Only BSON null | `{ note: { $type: "null" } }` | `where("note").isNullValue()` |
| Only missing | `{ note: { $exists: false } }` | `where("note").exists(false)` |
| Key present, including null | `{ note: { $exists: true } }` | `where("note").exists(true)` |
| Present with non-null value | `{ note: { $ne: null } }` | `where("note").ne(null)` |

In repositories, derived query method names can be convenient, but when business rules strictly distinguish null from missing, verify the generated BSON query or use `MongoTemplate` to express `$exists`/`$type` explicitly.

### 7.1. `Update.set()` and `Update.unset()` in Spring Data

~~~java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.query.Update;

Query byId = Query.query(Criteria.where("id").is("w002"));

// Write explicit BSON null.
UpdateResult setNull = template.updateFirst(
    byId,
    new Update().set("note", null),
    WorkItemDefault.class
);

// Remove the note field entirely.
UpdateResult removeField = template.updateFirst(
    byId,
    new Update().unset("note"),
    WorkItemDefault.class
);
~~~

These are **update operators**, not full-entity serialization, so `Update.set("note", null)` writes BSON null even when the entity property lacks `@Field(write = ALWAYS)`. Running these two statements sequentially leaves `note` removed.

## 8. Assigning Read-Time Defaults via Aggregation

### 8.1. `$ifNull` Merges BSON Null and Missing

~~~javascript
workitems.aggregate([
  {
    $project: {
      _id: 1,
      title: 1,
      displayNote: {
        $ifNull: ["$note", "(no note)"]
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Against the original dataset:

- `w001` (`note: null`) → `"(no note)"`.
- `w002` (no `note`) → `"(no note)"`.
- `w003` (`note: "Approved"`) → `"Approved"`.
- `w004` (`note: ""`) → `""`, because an empty string is a non-null value.

`$ifNull` treats undefined values and missing fields identically to null; it **does not update documents in the collection**. It only transforms aggregation output. If business logic must distinguish missing from null, `$ifNull` is insufficient.

### 8.2. `$type` in Aggregation Can Detect Missing

Unlike `$type` in a query predicate, `$type` as an **aggregation expression** returns `"missing"` when a field does not exist:

~~~javascript
workitems.aggregate([
  {
    $project: {
      title: 1,
      noteType: { $type: "$note" },
      noteState: {
        $switch: {
          branches: [
            {
              case: { $eq: [{ $type: "$note" }, "missing"] },
              then: "MISSING"
            },
            {
              case: { $eq: [{ $type: "$note" }, "null"] },
              then: "EXPLICIT_NULL"
            }
          ],
          default: "VALUE_PRESENT"
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

On the initial dataset: `w001 → EXPLICIT_NULL`, `w002 → MISSING`, `w003/w004 → VALUE_PRESENT`. This technique works well for data quality reports, migration audits, or handling missing-data states in pipelines.

### 8.3. Do Not Confuse Display Values with Stored Values

A report using `$ifNull: ["$retryCount", 0]` can display `0` for documents missing `retryCount`. Yet a database query `{ retryCount: 0 }` still will not match those documents. If defaults must exist physically in the database, backfill them or set them on write paths.

## 9. PATCH APIs: Missing, Null, and New Values

For HTTP PATCH, many systems adopt this convention:

| JSON Input | Action |
| --- | --- |
| `{}` | Leave `note` unchanged |
| `{"note":null}` | Remove `note` or write BSON null per API specification |
| `{"note":""}` | Write empty string (if allowed) |
| `{"note":"Checked"}` | Write new string |

If a DTO only has `String note` without tracking field presence, both `{}` and `{"note":null}` become `note == null`. The application loses the ability to distinguish “caller omitted the field” from “caller explicitly sent null”.

A clean implementation accepts a JSON tree and checks `has()`:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public void patchNote(String id, JsonNode body) {
    // note omitted: leave unchanged.
    if (!body.has("note")) {
        return;
    }

    JsonNode value = body.get("note");
    Update update = new Update();

    if (value.isNull()) {
        // This API's convention: null means remove the key.
        update.unset("note");
    } else if (value.isTextual()) {
        update.set("note", value.textValue());
    } else {
        throw new IllegalArgumentException(
            "note must be string or null"
        );
    }

    var result = template.updateFirst(
        Query.query(Criteria.where("id").is(id)),
        update,
        WorkItemDefault.class
    );

    if (result.getMatchedCount() == 0) {
        throw new IllegalArgumentException("Work item not found");
    }
}
~~~

This example method lives in a service with `MongoTemplate template` injected. It illustrates PATCH semantics without an HTTP controller, REST error mapping, or authorization checks. If your API requires “null must persist BSON null”, replace `update.unset("note")` with `update.set("note", null)`.

**Do not use `save()` on an entity with many nullable properties as a generic PATCH mechanism** when you only mean to update a couple of fields. Re-serializing the full entity can alter the presence of unrelated fields, especially when the mapper omits nulls by default. Using `Update` targeting only the modified fields makes intent explicit.

## 10. Indexes, Uniqueness, and `null`/Missing

Null and missing states also affect indexes.

### 10.1. Single-Field Unique Indexes Treat Missing and Null as One Null Key

Suppose a `users` collection has a single-field unique index:

~~~javascript
db.users_index_demo_008.createIndex(
  { email: 1 },
  { unique: true }
);
~~~

In a standard single-field unique index, MongoDB stores a null entry for documents **missing `email`** or having **`email: null`**. Consequently, the index permits at most **one** document with a null entry; a second document missing email or having `email: null` is rejected with `E11000 duplicate key`.

That typically contradicts the intent “email is optional, but when present it must be unique”.

### 10.2. Unique Sparse Indexes and Partial Indexes

`sparse` skips documents missing the indexed field, yet still indexes fields **present with null**:

~~~javascript
// Demonstrated on a dedicated test collection.
db.users_sparse_demo_008.createIndex(
  { email: 1 },
  { unique: true, sparse: true }
);
~~~

Result: multiple documents can lack `email`, yet documents with `email: null` still contend for a single null key in the unique sparse index.

To enforce uniqueness only on **string** emails, use a **partial unique index**:

~~~javascript
db.users_partial_demo_008.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: {
      email: { $type: "string" }
    }
  }
);
~~~

When `email` is a scalar string, this index ignores missing and BSON null emails while enforcing uniqueness across string emails. Pair this with validation so mistyped email values cannot sneak in; indexes do not validate email format or normalize casing.

If the collection already holds duplicates, MongoDB refuses to create the unique index until conflicts are resolved. Changing indexes in production requires data audits and query performance evaluation first.

## 11. Schema Validation and Bean Validation

MongoDB does not require all documents in a collection to share the same fields unless validation is configured. To distinguish **required presence** from **nullable**, MongoDB offers `$jsonSchema`.

### 11.1. `required` Checks Presence; `bsonType` Checks Type

Example creating a **new collection, separate from the Section 1 sample data**:

~~~javascript
db.createCollection("workitems_schema_demo_008", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["title", "status"],
      properties: {
        title: {
          bsonType: "string",
          description: "Must be a string"
        },
        status: {
          bsonType: "string",
          enum: ["NEW", "DONE", "CANCELLED"]
        },
        note: {
          bsonType: ["string", "null"],
          description: "May be absent, a string, or BSON null"
        }
      }
    }
  }
});
~~~

In this schema:

- `title` and `status` are **required** per `required`.
- `status` must be a string in `NEW/DONE/CANCELLED`; BSON null is rejected.
- `note` is not in `required`, so it may be **absent**. When present, it must be a string or BSON null.
- The schema only **validates** documents; it does not auto-populate `status = "NEW"` when missing.

If you list `status` in `required` without restricting `bsonType`, a document with `status: null` still satisfies “field present”. To enforce “non-null”, constrain both presence and type.

### 11.2. Java Validation Is a Separate Layer

Example:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class WorkItemRequest {
    @NotBlank
    private String title;

    @NotNull
    private String status;
}
~~~

Jakarta Bean Validation annotations apply when **validation is triggered** in a controller, service, or appropriate callback. They do not turn into MongoDB server-side `$jsonSchema`, and other clients can write directly to MongoDB if the database lacks a validator.

Furthermore, `@NotNull` is not equivalent to `@NotBlank`: the string `""` is **non-null** yet blank. Align validation constraints with business rules.

## 12. Fixing Legacy Documents Missing Fields: Deliberate Backfilling

When a new application version introduces `retryCount`, older documents may lack the field. If all records must store a default `0`, target missing fields:

~~~javascript
// Populate default only for documents missing retryCount.
workitems.updateMany(
  { retryCount: { $exists: false } },
  { $set: { retryCount: 0 } }
);
// On the original dataset: only w002 is updated.
~~~

This command **leaves `retryCount: null` untouched** if present. If business rules treat null and missing as identical states requiring backfill, filter with `{ retryCount: null }`, keeping in mind that it matches both cases.

### 12.1. Migration Plan

Before running on live data:

1. Profile counts of **missing**, **BSON null**, and **actual values** per field.
2. Define valid defaults per state; notably, never overwrite `0`, `false`, or empty strings when they carry meaning.
3. Verify all write paths (repositories, `MongoTemplate`, import jobs, raw driver) adhere to the new convention.
4. Run the backfill on test data, verify modified document counts, and test business queries.
5. Execute the production migration under operational procedures with backups and recovery options before enabling strict schema validation or unique indexes.

Applications can deploy temporary **compatibility reads** using `$ifNull` to keep features working while backfilling is underway. Read-time defaults do not replace fixing stored data if consistent persistence is the goal.

### 12.2. Profiling Current State with Aggregation

~~~javascript
workitems.aggregate([
  {
    $project: {
      retryCountType: { $type: "$retryCount" }
    }
  },
  {
    $group: {
      _id: "$retryCountType",
      total: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Running this on the sample dataset **before backfilling** shows three numeric documents and one `"missing"`. Results can be `"int"` or `"long"` depending on the BSON numeric type written; do not assume all Java/MongoDB numbers share the same BSON type.

## 13. Testing Nullability in Spring Data MongoDB

Null/missing bugs rarely appear in unit tests that only mock repositories, because mocks bypass `MappingMongoConverter` and MongoDB's query engine. For critical behaviors, write **integration tests** against MongoDB Testcontainers or an isolated MongoDB test instance.

### 13.1. Scenarios to Verify

| Test Scenario | What to Assert |
| --- | --- |
| Default converter writes `String note = null` | BSON document omits `note` |
| `@Field(write = ALWAYS)` writes `note = null` | BSON document contains `note: null` |
| `Criteria.isNull()` | Matches both null and missing |
| `Criteria.isNullValue()` | Matches only BSON null |
| `Criteria.exists(false)` | Matches only documents missing the field |
| `Update.set("note", null)` | Field exists with BSON null |
| `Update.unset("note")` | Field no longer exists |
| Upsert with `$setOnInsert` | Defaults set only when inserting new document |
| Reading into entity with field initializers | Do not confuse Java-initialized default with stored BSON value |

### 13.2. Example Inspecting Raw BSON After Insert

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@SpringBootTest
class WorkItemNullMappingTest {
    @Autowired MongoTemplate template;

    @Test
    void defaultMappingOmitsNullButAlwaysWritesExplicitNull() {
        // Run only against a dedicated test MongoDB; _id belongs to test fixture.
        template.insert(new WorkItemDefault(
            "fixture-default-008", "Default", null
        ));
        template.insert(new WorkItemExplicitNull(
            "fixture-always-008", "Explicit", null
        ));

        var collection = template.getDb()
            .getCollection("workitems_null_demo_008");

        Document defaultDoc = collection
            .find(Filters.eq("_id", "fixture-default-008"))
            .first();
        Document explicitDoc = collection
            .find(Filters.eq("_id", "fixture-always-008"))
            .first();

        assertThat(defaultDoc).isNotNull();
        assertThat(defaultDoc.containsKey("note")).isFalse();

        assertThat(explicitDoc).isNotNull();
        assertThat(explicitDoc.containsKey("note")).isTrue();
        assertThat(explicitDoc.get("note")).isNull();
    }
}
~~~

This is a **learning example** building on the two entities in Section 4 and a configured test MongoDB. In real projects, isolate collections per test or clean up fixtures in lifecycle hooks/`try-finally` to avoid duplicate-key errors on repeated runs with fixed `_id` values.

With reactive access, BSON semantics for null/missing remain identical; tests must subscribe/`StepVerifier` on `Mono`/`Flux` from `ReactiveMongoTemplate` or `ReactiveMongoRepository` to ensure execution actually occurs.

## 14. Common Errors and How to Diagnose Them

| Symptom | Common Cause | How to Investigate |
| --- | --- | --- |
| `find({ note: null })` returns more documents than expected | MongoDB matches missing fields too | Switch to `$type: "null"` when only BSON null is wanted |
| Reading a document with missing field yields `null` in Java | Mapping does not preserve field presence | Use raw driver/`$type` to inspect original BSON |
| After `save()`, a previously `null` field disappears | Default converter omits Java null properties on serialization | Check `@Field(write = ALWAYS)`; use `Update` for partial updates |
| PATCH API `{}` clears note | DTO fails to distinguish absent from explicit null | Inspect field presence before building `Update` |
| `retryCount = 0` gets overwritten by another default | Code treats 0 as “unset” | Distinguish missing/null from 0 before defaulting |
| `$ifNull` shows 0 yet `{ retryCount: 0 }` matches nothing | Default applies only inside aggregation | Backfill if business queries require persisted defaults |
| `E11000` error for optional email | Single-field unique index treats missing and null as one key | Inspect existing indexes; consider sparse/partial index |
| Validator rejects `note: null` | `bsonType` excludes `null` | Use `bsonType: ["string", "null"]` when null is valid |
| Validator still accepts `status: null` | Listed in `required` without type constraint | Enforce both `required` and `bsonType: "string"` |
| Entity status on read is `NEW` despite BSON lacking `status` | Java initializer or constructor assigns default | Check raw document; do not infer stored state from entity |

When diagnosing, inspect in order: **raw BSON document → exact filter → mapping metadata/constructors → write/serialization path → validation and indexes**. Never adjust annotations or run backfills before confirming whether actual data is null or missing.

## 15. Practice Exercises

The questions below assume the original dataset `w001` through `w004` from Section 1 with **no updates executed**.

### Exercise 1 — Find the Three States of `note`

Write three queries finding respectively: (a) BSON null, (b) missing, (c) present non-null value.

**Answer:**

~~~javascript
workitems.find({ note: { $type: "null" } });   // w001
workitems.find({ note: { $exists: false } }); // w002
workitems.find({ note: { $ne: null } });      // w003, w004
~~~

### Exercise 2 — Preserving `false` and `0`

You receive document `w001` with `active: false`, `retryCount: 0`. A JavaScript helper sets defaults using `if (!doc.retryCount)`. Why is that dangerous?

**Answer:** The condition evaluates `0` as falsy and can overwrite a valid counter. If defaults apply **only when a field is missing**, check key presence; if null must also be handled, check for null explicitly.

### Exercise 3 — Deliberate PATCH

For `PATCH /workitems/w003` with payload `{"note": null}`, the business requirement is to **completely remove the `note` field**. Write the MongoDB command:

~~~javascript
workitems.updateOne(
  { _id: "w003" },
  { $unset: { note: "" } }
);
~~~

If the business requirement were “write an explicit BSON null”, replace `$unset` with `$set: { note: null }`.

### Exercise 4 — Default Only When Creating a New Document

Add default `status: "NEW"` when `updateOne(..., { upsert: true })` inserts a new document, without overwriting `status` on existing documents.

**Answer:**

~~~javascript
workitems.updateOne(
  { _id: "w300" },
  {
    $set: { title: "New or existing record" },
    $setOnInsert: { status: "NEW" }
  },
  { upsert: true }
);
~~~

### Exercise 5 — Why Does a Unique Index Fail?

A collection has `{ unique: true }` on `email` and already contains one document without `email`. Why can inserting a second document lacking `email` be rejected? Propose an index design when email is optional yet string emails must be unique.

**Answer:** A single-field unique index creates a null entry for missing/null values, so the two documents collide. Use a partial unique index with `partialFilterExpression: { email: { $type: "string" } }` combined with schema validation for email type and format.

## References

- [MongoDB Manual — Query for Null or Missing Fields](https://www.mongodb.com/docs/manual/tutorial/query-for-null-fields/): meaning of `{field:null}`, `$ne:null`, `$exists`, and `$type`.
- [MongoDB Manual — `$exists`](https://www.mongodb.com/docs/manual/reference/operator/query/exists/): checking whether a field exists.
- [MongoDB Manual — `$ifNull`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/ifnull/): read-time defaults in aggregation.
- [MongoDB Manual — `$type` aggregation expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/type/): `"missing"` value when a field is absent.
- [MongoDB Manual — `$setOnInsert`](https://www.mongodb.com/docs/manual/reference/operator/update/setoninsert/): defaults when upsert creates a new document.
- [Spring Data MongoDB — `@Field` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/Field.html): `Field.Write.NON_NULL` and `Field.Write.ALWAYS`.
- [Spring Data MongoDB — `Criteria` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/Criteria.html): `isNull()`, `isNullValue()`, `exists()`.
- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): constructors, property population, collections, and nulls.
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) and [Sparse Indexes](https://www.mongodb.com/docs/manual/core/index-sparse/): impact of null/missing on indexes.
- [MongoDB Manual — JSON Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/specify-json-schema/json-schema-tips/): `required` and `bsonType` when null is permitted.
