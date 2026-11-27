# Combining Query Expressions with Schema Validation in MongoDB

MongoDB allows each document in a collection to have a flexible structure. This flexibility helps as data evolves with business needs, yet it can also yield documents missing required fields, carrying wrong types, or holding contradictory attributes. **Schema validation** establishes a data contract right inside the database: write operations that violate the rules can be rejected or logged with a warning.

Two common ways to express validation rules are:

- **`$jsonSchema`**: checks document shape, required fields, BSON types, allowed values, and string, numeric, object, or array constraints.
- **MongoDB query expressions**: use `find()`-style filter conditions, logical operators, and—where supported by the server version—`$expr` to express relationships between fields.

You can **combine both within a single `validator`**. For example, `$jsonSchema` requires `capacity` and `enrolled` to be non-negative integers, while `$expr` requires `enrolled <= capacity`. Another `$or` branch can require `publishedAt` to exist when `status` is `published`.

This lesson belongs to the **Schema validation** section and uses a `courses` collection to cover syntax, implementation, testing, and practical limits.

## 1. How Does MongoDB Use a Validator?

A collection can declare a `validator` upon creation or update its validator configuration via `collMod`. Conceptually, MongoDB checks the post-operation document state against the validator expression:

```text
Application sends insert / update
            |
            v
   Document after operation
            |
            v
   Collection validator
       /           \
    valid        invalid
      |               |
  write data    validationAction
                 /             \
              "error"         "warn"
               reject      write + warn
```

Validation can apply to both `insert` and `update` operations depending on `validationLevel`; it does not automatically repair or delete historical documents when you alter rules.

Structure when creating a collection:

```javascript
db.createCollection("courses", {
  validator: {
    // Document validation expression
  },
  validationLevel: "strict",
  validationAction: "error"
})
```

Structure when modifying an existing collection:

```javascript
db.runCommand({
  collMod: "courses",
  validator: {
    // New rule set
  },
  validationLevel: "strict",
  validationAction: "error"
})
```

A `validator` is neither a `find()` query to retrieve data nor a migration script. It is an **acceptance condition on document state** evaluated when MongoDB processes a write operation.

## 2. Dividing Responsibilities Between `$jsonSchema` and Query Expressions

Suppose each course has these properties:

```javascript
{
  _id: "course-101",
  code: "MDB-101",
  name: "MongoDB Fundamentals",
  status: "published",
  capacity: NumberInt(30),
  enrolled: NumberInt(12),
  startsAt: ISODate("2026-12-01T00:00:00Z"),
  endsAt: ISODate("2027-01-15T00:00:00Z"),
  publishedAt: ISODate("2026-11-01T00:00:00Z"),
  tags: ["database", "mongodb"]
}
```

We want to guarantee:

| Business Rule | Appropriate Expression |
| --- | --- |
| Must have `code`, `name`, `status`, `capacity`, `enrolled`, `startsAt`, `endsAt` | `$jsonSchema.required` |
| `code` and `name` are strings | `$jsonSchema.properties.*.bsonType` |
| `capacity` and `enrolled` are non-negative BSON integers | `bsonType: "int"` and `minimum: 0` |
| `status` is one of `draft`, `published`, `archived` | `$jsonSchema.enum` |
| `startsAt` and `endsAt` are BSON Dates | `bsonType: "date"` |
| `code` follows three uppercase letters, hyphen, three digits | `code: { $regex: "^[A-Z]{3}-[0-9]{3}$" }` or JSON Schema `pattern` |
| `enrolled` does not exceed `capacity` | `$expr: { $lte: ["$enrolled", "$capacity"] }` |
| `endsAt` must be after `startsAt` | `$expr: { $gt: ["$endsAt", "$startsAt"] }` |
| If `status: "published"`, `publishedAt` must be a Date | `$or` combining `status: { $ne: "published" }` with `publishedAt: { $type: "date" }` |
| `tags`, if present, is an array of strings | `bsonType: "array"` and `items` |

As a rule of thumb, `$jsonSchema` excels at defining the **shape and type contract**, while query expressions suit **value conditions and cross-field relationships**. Many checks can be written either way; pick whichever makes the rules easiest to read and maintain.

## 3. Building a Combined Validator with `$and`

First, select the practice database:

```javascript
use mongo_validation_lab
```

Define the `courseValidator` variable in `mongosh`:

```javascript
const courseValidator = {
  $and: [
    {
      $jsonSchema: {
        bsonType: "object",
        required: [
          "code",
          "name",
          "status",
          "capacity",
          "enrolled",
          "startsAt",
          "endsAt"
        ],
        properties: {
          code: {
            bsonType: "string",
            minLength: 1,
            description: "code must be a non-empty string"
          },
          name: {
            bsonType: "string",
            minLength: 1
          },
          status: {
            enum: ["draft", "published", "archived"]
          },
          capacity: {
            bsonType: "int",
            minimum: 0
          },
          enrolled: {
            bsonType: "int",
            minimum: 0
          },
          startsAt: {
            bsonType: "date"
          },
          endsAt: {
            bsonType: "date"
          },
          publishedAt: {
            bsonType: "date"
          },
          tags: {
            bsonType: "array",
            items: { bsonType: "string" }
          }
        }
      }
    },
    {
      code: { $regex: "^[A-Z]{3}-[0-9]{3}$" }
    },
    {
      $expr: {
        $and: [
          { $lte: ["$enrolled", "$capacity"] },
          { $gt: ["$endsAt", "$startsAt"] }
        ]
      }
    },
    {
      $or: [
        { status: { $ne: "published" } },
        { publishedAt: { $type: "date" } }
      ]
    }
  ]
};
```

Create the collection with the validator:

```javascript
db.createCollection("courses", {
  validator: courseValidator,
  validationLevel: "strict",
  validationAction: "error"
})
```

This example assumes `courses` does not already exist. If created previously, use another practice collection name or update the validator via `collMod`; never run `drop()` on a collection holding data you need to keep.

### Reading Each Layer of `$and`

Outer expression:

```javascript
{
  $and: [
    { $jsonSchema: { /* ... */ } },
    { code: { $regex: "..." } },
    { $expr: { /* ... */ } },
    { $or: [ /* ... */ ] }
  ]
}
```

A document is considered valid when **every branch** matches:

1. Required fields exist with the expected BSON types.
2. Course code matches the regex pattern.
3. Enrollment does not exceed capacity; end date follows start date.
4. A course in `published` status has a valid publication date.

Do not rely on `$and` branches executing strictly in written order or "short-circuiting" like JavaScript code. The validator is a predicate evaluated by the database; the goal is the logical conjunction of all rules, not an imperative sequence of steps.

### `$jsonSchema` Alone Cannot Replace Every Business Rule

`$jsonSchema` already verified that both `capacity` and `enrolled` are non-negative integers. However, checking `minimum: 0` on each field independently does not prove `enrolled <= capacity`: a document with `capacity: 10` and `enrolled: 15` still satisfies both `minimum` checks. Comparing **two fields against each other** is expressed with `$expr`.

Similarly, having both `startsAt` and `endsAt` as Dates does not guarantee chronological order. `$expr` enforces that relationship.

## 4. Query Expressions: Equality, Comparison, Regex, and Logic

Query expressions in a validator use the same operators familiar from filter queries. Example simple conditions:

```javascript
// Accept only VND currency
{ currency: "VND" }

// Total amount >= 0
{ total: { $gte: 0 } }

// Allow three listed statuses
{ status: { $in: ["draft", "published", "archived"] } }

// Code with specific pattern
{ code: { $regex: "^[A-Z]{3}-[0-9]{3}$" } }
```

These expressions are great for **value** checks, but watch how MongoDB treats missing fields or differing BSON types. For example:

```javascript
{ score: { $gte: 0 } }
```

does not by itself enforce that `score` **must be an integer**. A thorough validator pairs it with:

```javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: ["score"],
    properties: {
      score: { bsonType: "int", minimum: 0 }
    }
  }
}
```

Logical operators:

- `$and`: all conditions must evaluate to true.
- `$or`: at least one branch must evaluate to true.
- `$nor`: no branch may match.
- `$expr`: uses supported aggregation expressions to compare or transform values within **the same document**.

Example rule "disallow `archived` status while enrollments remain":

```javascript
{
  $or: [
    { status: { $ne: "archived" } },
    { enrolled: 0 }
  ]
}
```

This expression models the conditional relationship: status is not `archived`, **or** enrolled count equals `0`. If `status` is `archived` and `enrolled` is positive, the document fails. When `status` and `enrolled` are also mandated and typed by `$jsonSchema`, the rule's meaning becomes rock-solid.

### Expressing an "If A Then B" Condition

In logic:

```text
A => B  is equivalent to  (!A) OR B
```

For "if published, then publication date is required":

```javascript
{
  $or: [
    { status: { $ne: "published" } },
    { publishedAt: { $type: "date" } }
  ]
}
```

If `status: "draft"`, the first branch holds and `publishedAt` may be absent. If `status: "published"`, the first branch is false, so the second branch must hold. In the full example, `$jsonSchema` also ensures `publishedAt` is a Date **whenever the field appears**.

### Understanding `null` When Using `$exists`

```javascript
{ publishedAt: { $exists: true } }
```

only confirms the field is **present**. A document `{publishedAt: null}` still satisfies `$exists: true`. If a BSON Date is truly required, use `{publishedAt: {$type: "date"}}` alongside the schema.

Likewise, `{ field: null }` does not reliably express "field exists and equals null," because equality with `null` normally matches documents missing the field too. Always pick type/existence constraints suited to your intent.

## 5. `$expr`: Checking Cross-Field Relationships Within a Document

In MongoDB queries, `$expr` lets you embed aggregation expressions inside a filter. Standalone example for a reservations collection:

```javascript
{
  $expr: {
    $lte: ["$seatsBooked", "$seatsAvailable"]
  }
}
```

The notation `"$seatsBooked"` is a **field path reference** to the document's value, whereas `"seatsBooked"` without the `$` prefix would be treated as a literal string constant. This is a common pitfall when starting to combine query expressions with validation.

Temporal comparison expression:

```javascript
{
  $expr: {
    $gt: ["$endsAt", "$startsAt"]
  }
}
```

Because `$jsonSchema` already requires both fields to be BSON Dates, this expression enforces chronological ordering rather than lexicographical string comparison.

You can group multiple comparisons:

```javascript
{
  $expr: {
    $and: [
      { $gte: ["$enrolled", 0] },
      { $lte: ["$enrolled", "$capacity"] },
      { $gt: ["$endsAt", "$startsAt"] }
    ]
  }
}
```

Here, `$and` sits **inside `$expr`** using aggregation expression syntax, whereas the outer `$and` of `validator` combines **query predicates**. They look similar, yet cannot be swapped arbitrarily across syntactic contexts.

Which operators are allowed inside a validator is also governed by MongoDB rules. Not every `find()` or aggregation operator is permitted; for example, operators requiring arbitrary JavaScript execution, full-text search, or geospatial `$near` queries have specific restrictions. Always check your exact server version's `collMod`/schema validation docs before introducing uncommon operators into a validator.

## 6. Practice: Writing Valid and Invalid Documents

The following commands assume `courses` was created with `courseValidator` from Section 3.

### 6.1. A Valid Document

```javascript
db.courses.insertOne({
  _id: "course-101",
  code: "MDB-101",
  name: "MongoDB Basics",
  status: "published",
  capacity: NumberInt(30),
  enrolled: NumberInt(12),
  startsAt: ISODate("2026-12-01T00:00:00Z"),
  endsAt: ISODate("2027-01-15T00:00:00Z"),
  publishedAt: ISODate("2026-11-01T00:00:00Z"),
  tags: ["database", "mongodb"]
})
```

This document satisfies every branch: valid types, matching course code, enrolled within capacity, valid date ordering, and a publication date present.

### 6.2. Wrong Data Type

```javascript
db.courses.insertOne({
  code: "MDB-102",
  name: "BSON Data Types",
  status: "draft",
  capacity: "30", // String, not BSON int
  enrolled: NumberInt(0),
  startsAt: ISODate("2026-12-01T00:00:00Z"),
  endsAt: ISODate("2026-12-20T00:00:00Z")
})
```

With `validationAction: "error"`, the document is rejected because `capacity` lacks `bsonType: "int"`. Even though `"30"` looks numeric, MongoDB does not treat it as an integer.

### 6.3. Valid Types Yet Violating a Cross-Field Relationship

```javascript
db.courses.insertOne({
  code: "MDB-103",
  name: "Query Practice",
  status: "draft",
  capacity: NumberInt(10),
  enrolled: NumberInt(12), // Greater than capacity
  startsAt: ISODate("2026-12-01T00:00:00Z"),
  endsAt: ISODate("2026-12-20T00:00:00Z")
})
```

Both numeric values are non-negative ints, yet `$expr.$lte` fails. This case demonstrates why query expressions must complement BSON type checks.

### 6.4. Violating a State-Dependent Condition

```javascript
db.courses.insertOne({
  code: "MDB-104",
  name: "Document Structure",
  status: "published",
  capacity: NumberInt(20),
  enrolled: NumberInt(0),
  startsAt: ISODate("2026-12-01T00:00:00Z"),
  endsAt: ISODate("2026-12-20T00:00:00Z")
  // Missing publishedAt
})
```

The document includes every field listed in the schema's `required` array, yet the `$or` branch fails because `status` is `published` and `publishedAt` is not a Date.

### 6.5. Invalid Code Format

```javascript
db.courses.insertOne({
  code: "mdb101", // Does not match ^[A-Z]{3}-[0-9]{3}$
  name: "MongoDB Overview",
  status: "draft",
  capacity: NumberInt(20),
  enrolled: NumberInt(0),
  startsAt: ISODate("2026-12-01T00:00:00Z"),
  endsAt: ISODate("2026-12-20T00:00:00Z")
})
```

The `code` value is a string, but fails the regex pattern. This failure comes from the `$regex` query predicate branch rather than the type-checking branch.

These examples intentionally use distinct codes to avoid colliding on `_id`. Re-running a valid insert with the same `_id` triggers a duplicate key error independent of schema validation.

## 7. Validation on `update`: Checking the Post-Update Document State

Suppose `course-101` currently has `capacity: 30` and `enrolled: 12`. A request to shrink capacity to 10:

```javascript
db.courses.updateOne(
  { _id: "course-101" },
  { $set: { capacity: NumberInt(10) } }
)
```

violates `enrolled <= capacity` and is therefore rejected under `strict` + `error`. MongoDB evaluates the **resulting document**, not just the fields supplied in `$set`.

A conforming update:

```javascript
db.courses.updateOne(
  { _id: "course-101" },
  {
    $set: {
      capacity: NumberInt(40),
      enrolled: NumberInt(15)
    }
  }
)
```

When transitioning from `draft` to `published` while preserving the data contract, update both status and publication date in a single operation:

```javascript
db.courses.updateOne(
  { code: "MDB-105" },
  {
    $set: {
      status: "published",
      publishedAt: new Date()
    }
  }
)
```

This update only modifies a document if `MDB-105` exists; otherwise `matchedCount` is 0. On an existing `draft` document missing `publishedAt`, updating `status` alone will fail validation.

MongoDB guarantees atomicity for an update within a **single document**, ensuring related fields transition together into a valid state. If business rules span **multiple documents** (such as total enrollment across multiple collections not exceeding a cap), a single validator cannot solve the whole problem; design appropriate transactions, data models, or application-level controls.

## 8. Updating a Validator with `collMod`

Once a collection holds data, you can update its validator instead of dropping and recreating it. Suppose a new policy requires `archived` courses to have `enrolled: 0`. You can extend the validator declared in the current `mongosh` session:

```javascript
const updatedCourseValidator = {
  $and: [
    courseValidator,
    {
      $or: [
        { status: { $ne: "archived" } },
        { enrolled: NumberInt(0) }
      ]
    }
  ]
};

db.runCommand({
  collMod: "courses",
  validator: updatedCourseValidator,
  validationLevel: "strict",
  validationAction: "warn"
})
```

Notes:

- `courseValidator` was defined in Section 3 and exists only in the same `mongosh` session. In a fresh session, redefine it or fetch/compose the complete validator.
- `collMod` takes the **entire new validator expression**; it does not automatically append a new condition onto the previous validator.
- `warn` mode here illustrates observing failures during a rollout phase. Violating writes still proceed; applications must not treat `warn` as enforcement.
- Before switching to `validationAction: "error"`, identify and remediate historical documents that fail the new rules.

After the change, inspect metadata:

```javascript
db.getCollectionInfos({ name: "courses" })
```

Or extract just the options:

```javascript
const infos = db.getCollectionInfos({ name: "courses" });
if (infos.length !== 1) {
  throw new Error("Expected exactly one courses collection");
}
printjson(infos[0].options);
```

Once transition work is complete, raise enforcement:

```javascript
db.runCommand({
  collMod: "courses",
  validationLevel: "strict",
  validationAction: "error"
})
```

This changes write enforcement behavior; it does not modify existing documents.

### `validationLevel`: `strict`, `moderate`, `off`

| Value | Effect |
| --- | --- |
| `strict` | Validates normal inserts and updates against the validator |
| `moderate` | Validates inserts and updates to previously valid documents; relaxes update validation on documents that were already invalid |
| `off` | Disables document validation |

`moderate` helps when legacy data does not yet satisfy a new schema and an upgrade window is needed. However, it does not automatically bring legacy data into compliance.

### `validationAction`: `error` and `warn`

| Value | When Document Violates Validator |
| --- | --- |
| `error` | MongoDB rejects the write operation |
| `warn` | MongoDB allows the write and logs a warning |

Some MongoDB versions introduce additional action values, so consult your server version's documentation before deploying.

## 9. Combining Multiple `$or` and `$and` Branches in Practical Rules

Consider a `payments` collection with this model:

```javascript
{
  paymentId: "PAY-101",
  method: "card",
  status: "settled",
  amount: NumberDecimal("120.50"),
  card: {
    token: "tok_example"
  },
  settledAt: ISODate("2026-11-10T09:00:00Z")
}
```

Requirements:

1. `paymentId`, `method`, `status`, and `amount` must have valid types.
2. `method` is only `card` or `bank`.
3. If `card` is used, `card.token` must be a string.
4. If `status` is `settled`, `settledAt` must be a Date.

Corresponding validator fragment:

```javascript
const paymentValidator = {
  $and: [
    {
      $jsonSchema: {
        bsonType: "object",
        required: ["paymentId", "method", "status", "amount"],
        properties: {
          paymentId: { bsonType: "string" },
          method: { enum: ["card", "bank"] },
          status: { enum: ["pending", "settled", "failed"] },
          amount: {
            bsonType: "decimal",
            minimum: NumberDecimal("0.00")
          },
          settledAt: { bsonType: "date" },
          card: {
            bsonType: "object",
            properties: {
              token: { bsonType: "string" }
            }
          }
        }
      }
    },
    {
      $or: [
        { method: { $ne: "card" } },
        { "card.token": { $type: "string" } }
      ]
    },
    {
      $or: [
        { status: { $ne: "settled" } },
        { settledAt: { $type: "date" } }
      ]
    }
  ]
};
```

Both independent `$or` blocks sit inside `$and` because both conditional rules must hold simultaneously. Merging everything into one big `$or` would let a document pass via one satisfied branch even while violating the other requirement.

This example also shows that for currency, `NumberDecimal` and `bsonType: "decimal"` are far better suited than strings or binary floating-point numbers when business rules require decimal precision.

## 10. Configuring Schema Validation via the Java Sync Driver

In Java, the MongoDB Sync Driver uses `Bson` and `Document` classes to express validators. You can construct the same combined rule set as in `mongosh` and pass it to `CreateCollectionOptions`.

The following snippet illustrates a simplified version of the course rules, covering types and two cross-field relationships:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.CreateCollectionOptions;
import com.mongodb.client.model.ValidationAction;
import com.mongodb.client.model.ValidationLevel;
import com.mongodb.client.model.ValidationOptions;
import org.bson.Document;

public class CourseValidationSetup {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        Document schema = Document.parse("""
            {
              "$jsonSchema": {
                "bsonType": "object",
                "required": [
                  "code", "capacity", "enrolled", "startsAt", "endsAt"
                ],
                "properties": {
                  "code": { "bsonType": "string" },
                  "capacity": { "bsonType": "int", "minimum": 0 },
                  "enrolled": { "bsonType": "int", "minimum": 0 },
                  "startsAt": { "bsonType": "date" },
                  "endsAt": { "bsonType": "date" }
                }
              }
            }
            """);

        Document relation = Document.parse("""
            {
              "$expr": {
                "$and": [
                  { "$lte": ["$enrolled", "$capacity"] },
                  { "$gt": ["$endsAt", "$startsAt"] }
                ]
              }
            }
            """);

        Document validator = new Document(
            "$and", java.util.List.of(schema, relation));

        ValidationOptions validation = new ValidationOptions()
            .validator(validator)
            .validationLevel(ValidationLevel.STRICT)
            .validationAction(ValidationAction.ERROR);

        CreateCollectionOptions options =
            new CreateCollectionOptions().validationOptions(validation);

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database =
                client.getDatabase("mongo_validation_lab");
            database.createCollection("javaCourses", options);
        }
    }
}
```

This example uses Java text blocks (Java 15+) and requires a matching MongoDB Java Sync Driver dependency. It **creates a new collection**, so it will fail if `javaCourses` already exists. When the collection already exists, invoke `collMod` via `runCommand` with proper privileges and a change plan.

In Spring Data MongoDB applications, validators can be configured via Spring Data's corresponding APIs. Whether using the driver directly or a framework, final validation runs on MongoDB Server—ensure your driver and server versions support all operators used.

## 11. Scope and Limits of Combining Validators

### 11.1. Validators Do Not Replace Unique Indexes

If `code` must be unique across all documents, neither `$jsonSchema` nor single-document query expressions can reliably verify that no other document already uses that code. Use a **unique index**:

```javascript
db.courses.createIndex(
  { code: 1 },
  { unique: true, name: "code_unique" }
)
```

Before building a unique index on existing data, resolve duplicates. Once built, MongoDB enforces uniqueness independently of validation.

### 11.2. Validators Do Not Query Other Collections

A rule like "`studentId` must exist in the `students` collection" cannot be enforced by writing a standard validator that runs `$lookup` against another collection. Cross-collection references must be managed by the application, appropriate data modeling, or multi-document transactions when updating across documents/collections.

### 11.3. Not All Standard JSON Schema Features Are Available

MongoDB supports **a subset plus BSON extensions** of JSON Schema. `bsonType` is a crucial extension for checking types like `objectId`, `date`, `int`, `long`, and `decimal`. Never paste an external JSON Schema library's schema verbatim and assume MongoDB accepts every keyword.

### 11.4. Not Every Query Expression Is Permitted

Validators forbid certain specialized query operators and arbitrary code execution mechanisms. `$expr` is supported as documented by MongoDB, but that does not mean every aggregation operator inside `$expr` is permitted; certain operators or combinations are restricted. Check your server version's rules and test expressions in an equivalent staging environment before releasing.

### 11.5. Performance and Complexity

MongoDB evaluates the validator on write operations subject to validation. A clean schema with a handful of comparisons is far easier to reason about and cheaper than a sprawling expression with many branches, string transforms, and nested conditions. For write-heavy workloads, measure performance impact, keep error messages and rules clear, and avoid unnecessarily expensive expressions.

### 11.6. Schema Transition for Historical Data

When changing a validator on an existing dataset:

1. Count documents failing the new rules.
2. Decide how to remediate data accurately for the business; avoid stuffing dummy values just to pass validation.
3. Consider a `validationAction: "warn"` or `validationLevel: "moderate"` phase if a gradual transition is needed.
4. Enable `strict` and `error` only after assessing the impact on active writers.

Certain operations with appropriate privileges and options can pass `bypassDocumentValidation`; therefore, validators must pair with access control and application checks. Validation changes also do not automatically re-check previously stored documents.

## 12. Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Inserting `30` triggers a type error | Schema specifies `bsonType: "int"`, while client sends BSON Double/Long/Decimal | Inspect actual BSON type; standardize types and constructors (`NumberInt` in `mongosh`) |
| Checked `minimum`, yet `enrolled > capacity` still enters | Cross-field constraint was never declared | Add `$expr` comparing the two fields |
| `publishedAt: null` still passes presence check | `$exists: true` does not verify type or non-null | Check `$type: "date"` alongside schema |
| Merging two rules into one `$or` lets one rule slip | Confused `$or` with `$and` | Put mandatory rules inside `$and`; use `$or` only for valid alternatives |
| Updating an unrelated field still fails | Post-update document violates validator on another field | Fix legacy data or plan migration; check `validationLevel` |
| `collMod` succeeds, yet old documents remain invalid | Validation does not auto-migrate documents | Run a dedicated data update job |
| Using a query operator in validator fails | Operator is disallowed or version-dependent | Check validator rules for your server version |
| `warn` is set, yet invalid documents still save | `warn` is observation-only and does not block writes | Switch to `error` when data and apps are ready |
| Trying to check unique `code` with `$jsonSchema` | Cross-document uniqueness is outside schema scope | Use a unique index |

For validation rejections, MongoDB typically returns an error like `Document failed validation` (usually error code 121). Depending on server and driver, error details may describe the failing rule. Log the error code and enough context to remediate data, while keeping sensitive fields out of logs.

## 13. Practice Exercises

### Exercise 1: Add a Range Condition for Scores

An `exams` collection has a schema requiring `score` to be a BSON int. Add a query condition accepting only scores from 0 to 100.

**Reference solution:**

```javascript
{
  $and: [
    {
      $jsonSchema: {
        bsonType: "object",
        required: ["score"],
        properties: {
          score: { bsonType: "int" }
        }
      }
    },
    {
      score: { $gte: 0, $lte: 100 }
    }
  ]
}
```

You can also use `minimum: 0` and `maximum: 100` directly inside `$jsonSchema`. The combined form is shown here to practice reading both styles together.

### Exercise 2: Validate Start and End Dates

An `events` collection has `startAt` and `endAt`, both BSON Dates. Write an `$expr` branch accepting only `endAt > startAt`.

**Reference solution:**

```javascript
{
  $expr: {
    $gt: ["$endAt", "$startAt"]
  }
}
```

When placing this into a full validator, pair it with `$jsonSchema` ensuring both fields exist and have the right type.

### Exercise 3: State-Dependent Condition

An order has `status` in `pending`, `paid`, `cancelled`. If `status: "paid"`, `paidAt` must be present as a BSON Date. Write the corresponding query expression.

**Reference solution:**

```javascript
{
  $or: [
    { status: { $ne: "paid" } },
    { paidAt: { $type: "date" } }
  ]
}
```

Add `$jsonSchema` to require `status` and restrict its allowed values so a missing or wrong-typed status is never treated as valid.

### Exercise 4: Spot the Logic Bug in a Validator

Someone writes:

```javascript
{
  $or: [
    {
      $jsonSchema: {
        bsonType: "object",
        required: ["amount"],
        properties: {
          amount: { bsonType: "decimal" }
        }
      }
    },
    { amount: { $gt: 0 } }
  ]
}
```

The goal is "`amount` must be Decimal128 **and** greater than 0." Is the expression above correct?

**Answer:** No. `$or` requires only one branch to pass, so a document with `amount` as Decimal128 equal to 0 would pass, or another numeric type greater than 0 would pass. Change `$or` to `$and`, or use `bsonType: "decimal"` combined with appropriate `minimum` and greater-than-zero rules.

### Exercise 5: Combine Structure Checks and Array Constraints

Every document in `teams` must have `members` as an array of strings with at least one element, and `active: true`. Write the combined validator.

**Reference solution:**

```javascript
{
  $and: [
    {
      $jsonSchema: {
        bsonType: "object",
        required: ["members", "active"],
        properties: {
          members: {
            bsonType: "array",
            minItems: 1,
            items: { bsonType: "string" }
          },
          active: { bsonType: "bool" }
        }
      }
    },
    { active: true }
  ]
}
```

Here `active: true` is a value constraint, while `bsonType: "bool"` checks the type. Both rules reinforce each other.

## 14. Summary of Design Rules

When you need to enforce both data types and intra-document business constraints, follow this order:

1. **Describe structure with `$jsonSchema`**: required fields, BSON types, `enum`, numeric/string bounds, objects, and arrays.
2. **Write remaining query conditions**: `$in`, `$regex`, `$or`, `$nor`, or `$expr` for value rules and cross-field relationships.
3. **Use `$and` to combine mandatory rules**, and `$or` for valid alternatives or "if ... then ..." implications.
4. **Create the collection or update `validator` via `collMod`**, deliberately choosing `validationLevel` and `validationAction`.
5. **Test valid documents, wrong types, missing fields, and relationship violations**, along with update operations that change document state.
6. **Separate validation from other mechanisms**: unique indexes for cross-document uniqueness; application logic/transactions for multi-document invariants; migrations for legacy data.

The core takeaway is that `$jsonSchema` and query expressions play **complementary roles**: one guards shape and BSON types, while the other expresses value rules and relationships that type declarations alone cannot capture.
