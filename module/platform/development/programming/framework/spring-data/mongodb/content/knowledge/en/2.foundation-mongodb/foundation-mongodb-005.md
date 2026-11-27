# Distinguishing Missing Fields, `null`, Empty Strings, and Empty Arrays in MongoDB

## 1. Why distinguish them?

MongoDB stores documents in BSON. Two documents in the same collection can have different sets of fields; a single field can also carry values of different types. Therefore, **a missing field** (`missing`), **a field present with value `null`**, **the string `""`**, and **the array `[]`** are four distinct data states. Conflating them easily causes bugs when filtering data, performing partial updates, mapping to Java, or analyzing metrics.

In Spring Data MongoDB, this distinction directly affects `Criteria`, `MongoTemplate`, repositories, how Java properties are written, and how documents are read back. For example, a user management application needs to distinguish a user who has never set a nickname, a user who deliberately cleared their nickname, and a user who submitted an empty string; for a list of roles, "unknown list" may differ from "confirmed to have zero roles."

| State | Illustrative document | BSON-level meaning | Business question to decide |
|---|---|---|---|
| Missing field | `{ "_id": 1 }` | No `value` key | Never submitted, not applicable, or field deleted? |
| Explicit `null` | `{ "_id": 2, "value": null }` | Key present, BSON Null value (type 10) | Explicitly known to have no value or intentionally cleared? |
| Empty string | `{ "_id": 3, "value": "" }` | Key present, 0-length BSON String value | Is empty user input valid? |
| Empty array | `{ "_id": 4, "value": [] }` | Key present, 0-element BSON Array value | List is known and currently has zero elements? |

**There is no default business convention for these four states.** The development team must agree on the meaning and normalization rules per field. `""` is not equivalent to `null`; `[]` is not equivalent to a missing field. The number `0`, Boolean `false`, and a whitespace-only string `" "` are also not any of the empty states above.

## 2. Sample data for observing queries

Run in `mongosh` on a test database:

```javascript
db.valueStatesDemo.insertMany([
  { _id: 1, label: "missing" },
  { _id: 2, label: "explicit null", value: null },
  { _id: 3, label: "empty string", value: "" },
  { _id: 4, label: "empty array", value: [] },
  { _id: 5, label: "nonempty string", value: "hello" },
  { _id: 6, label: "array of strings", value: ["hello"] },
  { _id: 7, label: "array containing empty string", value: [""] },
  { _id: 8, label: "zero", value: 0 }
]);

db.valueStatesDemo.find({}, { _id: 1, value: 1 }).sort({ _id: 1 });
```

The `value` field is intentionally used with multiple types to compare MongoDB's behavior. In a real system, design each field with a stable type or explicitly declare the allowed types.

## 3. Querying the four states

| Goal | MongoDB filter | Matching `_id` values from sample data |
|---|---|---|
| Field does not exist at all | `{ value: { $exists: false } }` | `1` |
| Field exists, regardless of value | `{ value: { $exists: true } }` | `2, 3, 4, 5, 6, 7, 8` |
| Value is explicit BSON `null` | `{ value: { $type: "null" } }` | `2` |
| `null` **or** missing field | `{ value: null }` | `1, 2` |
| Empty string under standard matching | `{ value: "" }` | `3, 7` |
| Array with zero elements | `{ value: { $size: 0 } }` | `4` |
| Value is not `null` and field exists | `{ value: { $ne: null } }` | `3, 4, 5, 6, 7, 8` |

### 3.1. `$exists` checks key presence

```javascript
db.valueStatesDemo.find({ value: { $exists: false } }); // _id = 1
db.valueStatesDemo.find({ value: { $exists: true } });  // _id = 2..8
```

`$exists: true` **includes** `null`, `""`, and `[]`. Do not use `$exists: true` to infer "has useful data." Conversely, `$exists: false` only selects missing fields, not fields whose value is `null`.

### 3.2. `{ value: null }` does not mean "null only"

```javascript
db.valueStatesDemo.find({ value: null });                  // _id = 1, 2
db.valueStatesDemo.find({ value: { $type: 10 } });         // _id = 2
db.valueStatesDemo.find({ value: { $type: "null" } });     // _id = 2
db.valueStatesDemo.find({ value: { $exists: true, $eq: null } }); // _id = 2
```

MongoDB treats a regular `null` equality filter as matching both **explicit null** and **missing fields**. When a field only holds scalar values, use `$type: 10` (type name `"null"`) or combine `$exists: true` with `$eq: null` to find explicit nulls. **If the field can be an array containing `null`**, these query conditions can also match a null element inside the array. When you need to assert that **the value of the field itself** is BSON Null, use `$expr` to check whether `{ $type: "$value" }` equals `"null"`. Similarly, `{ value: { $ne: null } }` only returns documents where the field exists and its value is not null; do not assume it includes missing fields.

### 3.3. Empty string differs from empty array

```javascript
db.valueStatesDemo.find({ value: "" });             // _id = 3, 7
db.valueStatesDemo.find({ value: [] });             // _id = 4 in sample set
db.valueStatesDemo.find({ value: { $size: 0 } });   // _id = 4
```

When a field is an **array**, MongoDB normally matches equality conditions against an element of the array. Hence `{ value: "" }` also matches `{ value: [""] }`. The `$size: 0` query finds arrays with exactly 0 elements, excluding `null`, empty strings, and missing fields. `$size` requires the value to be an array but cannot directly leverage an index for length comparisons; for high-frequency filtering, you may need an additional consistently maintained element-count field.

**Note on `$type` in queries:** `{ value: { $type: "string" } }` can match an array containing a string element, not only a scalar string field. Check the type of **the field's own value** when data has mixed types.

### 3.4. Distinguishing precisely with `$expr` and `$type`

The aggregation expression `{ $type: "$value" }` returns the string `"missing"` when the field is absent; the remaining values in the example have types `"null"`, `"string"`, `"array"`, or `"int"`. Combine `$expr` to inspect the type of the entire field:

```javascript
// Only fields whose own value is BSON Null, excluding array [null]
db.valueStatesDemo.find({
  $expr: { $eq: [{ $type: "$value" }, "null"] }
}); // _id = 2

// Only scalar empty string, excluding array [""]
db.valueStatesDemo.find({
  $expr: {
    $and: [
      { $eq: [{ $type: "$value" }, "string"] },
      { $eq: ["$value", ""] }
    ]
  }
}); // _id = 3

// Only fields of type array with zero elements
db.valueStatesDemo.find({
  $expr: {
    $eq: [
      { $cond: [{ $isArray: "$value" }, { $size: "$value" }, -1] },
      0
    ]
  }
}); // _id = 4

// Classify all fields directly on the server
db.valueStatesDemo.aggregate([
  { $project: {
      label: 1,
      valueKind: { $type: "$value" }
  } },
  { $sort: { _id: 1 } }
]);
```

In the length expression, `$isArray` and `$cond` guard `$size` against errors when encountering strings, numbers, `null`, or missing fields. Do not use `$type: "missing"` in a standard query filter; `"missing"` is the **result of the `$type` expression operator** in this context, not a BSON type stored in a document.

## 4. Implementing with Spring Data MongoDB

`MongoTemplate` lets you build queries using `Query` and `Criteria`. The example below uses the `valueStatesDemo` collection and `org.bson.Document` to observe BSON values close to the raw data:

```java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.BasicQuery;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class ValueStateQueries {
    private final MongoTemplate template;

    public ValueStateQueries(MongoTemplate template) {
        this.template = template;
    }

    public void demonstrate() {
        Query missing = Query.query(Criteria.where("value").exists(false));
        Query present = Query.query(Criteria.where("value").exists(true));
        Query nullOrMissing = Query.query(Criteria.where("value").is(null));
        Query explicitNull = Query.query(Criteria.where("value").type(10));
        Query emptyArray = Query.query(Criteria.where("value").size(0));
        Query ordinaryEmptyString = Query.query(Criteria.where("value").is(""));

        // Java 17+: check scalar empty string with $expr.
        Query scalarEmptyString = new BasicQuery("""
            { "$expr": { "$and": [
                { "$eq": [ { "$type": "$value" }, "string" ] },
                { "$eq": [ "$value", "" ] }
            ] } }
            """);
        Query scalarNull = new BasicQuery("""
            { "$expr": { "$eq": [ { "$type": "$value" }, "null" ] } }
            """);

        long nMissing = template.count(missing, "valueStatesDemo"); // 1
        long nNull = template.count(explicitNull, "valueStatesDemo"); // 1
        long nNullOrMissing =
            template.count(nullOrMissing, "valueStatesDemo"); // 2
        long nEmptyArray = template.count(emptyArray, "valueStatesDemo"); // 1
        long nOrdinaryEmptyString =
            template.count(ordinaryEmptyString, "valueStatesDemo"); // 2
        long nScalarEmptyString =
            template.count(scalarEmptyString, "valueStatesDemo"); // 1
        long nScalarNull = template.count(scalarNull, "valueStatesDemo"); // 1

        // present: includes null, empty string, empty array, etc.
        template.find(present, Document.class, "valueStatesDemo");
    }
}
```

Note that query APIs such as `Criteria.where("value").is(null)` or derived repository methods comparing against null may inherit MongoDB's "null **or** missing" semantics. If business logic requires explicit null, express the BSON null type condition clearly. With repositories, inspect the generated query via logging or integration tests rather than guessing from the method name.

## 5. When updating documents: `$unset` vs. `$set`

This is a common source of discrepancies when receiving data from partial-update APIs:

```javascript
// Remove the key completely from the document
db.valueStatesDemo.updateOne({ _id: 5 }, { $unset: { value: "" } });

// Keep the key, set explicit null value
db.valueStatesDemo.updateOne({ _id: 5 }, { $set: { value: null } });

// Keep the key, set empty string
db.valueStatesDemo.updateOne({ _id: 5 }, { $set: { value: "" } });

// Keep the key, set empty array
db.valueStatesDemo.updateOne({ _id: 5 }, { $set: { value: [] } });
```

The commands above are **independent illustrative operations**; if run sequentially on the same `_id`, the final state is `[]`. In Spring Data MongoDB:

```java
import org.bson.Document;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

Query byId = Query.query(Criteria.where("_id").is(5));

template.updateFirst(
    byId, new Update().unset("value"), Document.class, "valueStatesDemo");
template.updateFirst(
    byId, new Update().set("value", null), Document.class, "valueStatesDemo");
template.updateFirst(
    byId, new Update().set("value", ""), Document.class, "valueStatesDemo");
template.updateFirst(
    byId, new Update().set("value", java.util.List.of()),
    Document.class, "valueStatesDemo");
```

For `PATCH` APIs, design a clear contract: **omitting a field** may mean "leave unchanged"; **sending `null`** may mean "clear value," "write null," or "reject," depending on the specification. If a DTO only uses a nullable `String` property, the distinction between "omitted" and "sent `null`" may already be lost at the JSON deserialization layer; when needed, track key presence using a dedicated PATCH structure or `JsonNode`/`Map`.

## 6. Java object mapping does not automatically preserve all states

When MongoDB is read into a Java POJO with `String value`, the property's value can be `null` for both BSON null and a missing field. Looking solely at the Java property after deserialization usually **cannot tell** whether the key previously existed in the document. In mixed-type collections, an incompatible Java type (such as `List<String>` when BSON actually holds a string) can also cause conversion errors or converter-dependent results.

When writing a POJO, Spring Data MongoDB by default skips `null` properties. In supported versions, `@Field(write = Field.Write.ALWAYS)` instructs it to write null values as well:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document("members")
public class Member {
    @Id
    private String id;

    // Write BSON null when nickname == null.
    @Field(write = Field.Write.ALWAYS)
    private String nickname;
}
```

This example only illustrates the write-null option; practical use requires constructors/getters/setters or your project's mapping style. Check your Spring Data MongoDB version and the actual BSON documents, especially when using custom converters, default values, record/constructor binding, or partial updates. With `List`, Java `null` and `Collections.emptyList()` express two different states; only initialize an empty list by default if that is the desired business convention.

If you need to preserve the distinction between missing and BSON null when reading, you can access `Document` or inspect key presence with `containsKey("value")`:

```java
Document raw = template.findById(2, Document.class, "valueStatesDemo");
if (raw != null) {
    boolean present = raw.containsKey("value");
    Object value = raw.get("value"); // Can be null even when present == true
    System.out.println("present=" + present + ", value=" + value);
}
```

## 7. Aggregating data: watch out for `$ifNull`

In aggregation, `$ifNull` treats both **null values** and **missing values** as null and applies the fallback. It does not automatically replace empty strings or empty arrays:

```javascript
db.valueStatesDemo.aggregate([
  {
    $project: {
      label: 1,
      originalType: { $type: "$value" },
      normalized: { $ifNull: ["$value", "not provided"] }
    }
  }
]);
```

With the sample data, `_id: 1` (missing) and `_id: 2` (null) both receive the fallback `"not provided"`. Meanwhile, `_id: 3` still has `""` and `_id: 4` still has `[]`. If a report requires four separate buckets, classify by `$type` before normalizing:

```javascript
db.valueStatesDemo.aggregate([
  {
    $project: {
      state: {
        $switch: {
          branches: [
            { case: { $eq: [{ $type: "$value" }, "missing"] },
              then: "missing" },
            { case: { $eq: [{ $type: "$value" }, "null"] },
              then: "explicit-null" },
            { case: { $and: [
                { $eq: [{ $type: "$value" }, "string"] },
                { $eq: ["$value", ""] }
              ] },
              then: "empty-string" },
            { case: { $isArray: "$value" },
              then: "array" }
          ],
          default: "other"
        }
      }
    }
  },
  { $group: { _id: "$state", count: { $sum: 1 } } },
  { $sort: { _id: 1 } }
]);
```

The `"array"` branch in the example groups empty and non-empty arrays together; if you need to split them further, check the size after confirming the value is an array.

## 8. Schema rules and indexes

MongoDB can accept mixed types, but applications usually benefit from an explicit schema contract. Use a `$jsonSchema` validator to enforce required fields and valid types. For example, an object requiring `tags` to be present and to be an array:

```javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: ["tags"],
    properties: {
      tags: {
        bsonType: "array",
        items: { bsonType: "string" }
      }
    }
  }
}
```

The rule above **accepts** `tags: []`; it **rejects** a missing field, `tags: null`, or `tags: ""`. If business logic forbids empty arrays, add `minItems: 1`. If explicit null is allowed while requiring the key to exist, you can use a list of allowed `bsonType` values, such as `["array", "null"]`, combined with `required`. Validators must be configured on the collection at creation time or when updating collection options.

Regarding indexes, `$exists: true` behaves differently from `$exists: false`; a **sparse index** skips documents missing the field, yet can still include documents with an explicit null value. A **partial index** with an appropriate filter can be useful for frequent queries on presence state, though you must consider the query filter and actual index selection. Do not assume that `$size: 0` will be accelerated by an index on the array itself. Use `explain("executionStats")` on real data and volume before optimizing.

## 9. Testing edge cases prone to confusion

When writing integration tests against a real MongoDB instance (or a test environment with equivalent behavior), create separate documents for each state and verify both query results and written BSON:

| Scenario | Result to verify |
|---|---|
| Query `is(null)` / `{value:null}` | Matches both missing and explicit null |
| Query `type(10)` | Matches explicit null; if arrays can contain null, test that too |
| Query `exists(false)` | Matches missing only |
| Query `is("")` | Can match both empty string and an array containing `""` |
| Query `size(0)` | Matches empty array only |
| Write with `unset` | `Document.containsKey("value")` is `false` |
| Write with `set("value", null)` | Key exists and value is BSON null |
| Mapping POJO with `null` property | Verify write behavior per annotation/converter in use |
| PATCH DTO missing key vs. key with `null` | Update logic follows the API contract accurately |

A test case containing only "non-empty" values will not catch these bugs. Include an array containing an empty string, the number `0`, and Boolean `false` to avoid confusing "falsy" values with missing fields.

## 10. Principles to apply in design

1. **Define data semantics** for each field: when missing, null, empty string, and empty array are allowed and how the system should respond.
2. **Choose query conditions matching the requirement:** `$exists` to check key presence; `$type: "null"` to find BSON null while noting array-element behavior; `$size: 0` to find empty arrays; use `$expr` when checking the type of the entire field.
3. **Standardize write operations:** `$unset` removes the key, `$set: null` keeps the key with null, and `$set: ""` vs. `$set: []` write two different empty types.
4. **Inspect the Java–BSON boundary:** POJOs, converters, annotations, and PATCH DTOs can drop key-presence information.
5. **Protect with tests and schemas:** test all four states, add validators, and measure real queries when needed.

Distinguishing these four states right in the data contract keeps repositories, `MongoTemplate`, aggregations, indexes, and update APIs consistent about what the data means.
