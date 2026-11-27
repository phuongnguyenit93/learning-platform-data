# Distinguishing Missing Fields, null, Empty Strings, and Empty Arrays in MongoDB

## 1. Why Do Four States That Look Like "No Data" Behave Differently?

In MongoDB, a document is represented in **BSON**, consisting of field name and typed value pairs. A field *not written to the document* is fundamentally different from a field *that exists with an empty value*. Four very common situations are:

1. **Missing field:** the document does not contain that key.
2. **`null`:** the key exists and holds the BSON Null value.
3. **Empty string (`""`):** the key exists and holds a string of length 0.
4. **Empty array (`[]`):** the key exists and holds an array with 0 elements.

For example, these four documents carry distinct meanings:

```javascript
{ _id: 1 }                         // No value field at all
{ _id: 2, value: null }             // Has value, BSON Null
{ _id: 3, value: "" }               // Has value, empty String
{ _id: 4, value: [] }               // Has value, empty Array
```

If a data model permits all four, the application must distinguish them to know whether the user **did not submit a value**, **explicitly cleared a value**, **submitted an empty string**, or **has a list that currently holds zero items**.

| State | Field Exists? | BSON Type | Possible Business Semantics |
|---|---|---|---|
| No `value` | No | No type because there is no field | Undeclared, not provided, or not applicable |
| `value: null` | Yes | Null | Declared with no value yet, or explicitly cleared |
| `value: ""` | Yes | String | Has a string field left blank by the user |
| `value: []` | Yes | Array | Has a list that is currently empty |

These are **business interpretations**, not rules imposed automatically by MongoDB. The application must decide which states are valid. For instance, a `nickname` field should typically be a string or null, whereas `tags` should typically be an array; storing both types in one field here only illustrates type differences, not a recommended schema design.

## 2. Creating an Illustrative Dataset

Commands use **mongosh** syntax. Run them against a test database using a separate `fieldStatesDemo` collection to avoid affecting application data. Run `insertMany` once on an empty collection:

```javascript
db.fieldStatesDemo.insertMany([
  { _id: "missing",     note: "No value field" },
  { _id: "null",        note: "BSON Null",       value: null },
  { _id: "emptyString", note: "Empty string",    value: "" },
  { _id: "emptyArray",  note: "Empty array",     value: [] },
  { _id: "text",        note: "Non-empty string", value: "MongoDB" }
]);
```

In this dataset:

- `missing` has no `value` key.
- `null` has the `value` key set to `null`.
- `emptyString` has `value` set to an empty string.
- `emptyArray` has `value` set to an empty array.
- `text` is the control case: a non-empty string.

When running the queries below, use a projection returning only `_id` so matching documents are easy to spot:

```javascript
db.fieldStatesDemo.find(
  { value: null },
  { _id: 1 }
);
```

Matching `_id` results on the sample set are `"missing"` and `"null"`. This surprise is why you must carefully learn the difference between **null equality** and **checking whether a field actually exists**.

## 3. The `{ field: null }` Condition: Missing Field or Null Value

### 3.1. Two States Matching a Single Expression

In MongoDB's query language, the expression:

```javascript
db.fieldStatesDemo.find({ value: null });
```

matches documents where `value` **equals null** *or* **does not exist**. On the dataset just created, the result is:

```text
missing
null
```

Therefore, this query is **not an exact filter for documents containing BSON Null**. It fits cases where the business logic treats both "field absent" and "explicitly null" as the same "no value" bucket.

Equivalent syntax for the simple case:

```javascript
db.fieldStatesDemo.find({ value: { $eq: null } });
```

**Note on arrays:** MongoDB applies array-element matching semantics to many equality expressions. If real data contains arrays holding `null`, some `null` equality queries can also match because of an array element. Therefore, scenarios requiring strict type precision should combine `$type` awareness and schema design rather than inferring type from a single equality match.

### 3.2. Why Is `$ne: null` Also Noteworthy?

```javascript
db.fieldStatesDemo.find({ value: { $ne: null } });
```

On the sample set, this filter matches `emptyString`, `emptyArray`, and `text`. In MongoDB, **not equal to null** is used to find fields that **exist and hold a non-null value**.

Do not infer from this that every `$ne` condition automatically excludes missing fields:

```javascript
db.fieldStatesDemo.find({ value: { $ne: "" } });
```

In the example above, the `missing` document still matches because `$ne` against a regular value also matches documents **lacking the field**. That is an important difference between "not equal to empty string" and "exists with a non-null value."

When checking for a specific data type, express positive conditions with `$type` and targeted operators rather than relying solely on `$ne` negation.

## 4. `$exists`: Checking Key Presence

`$exists` answers one question: **does the document contain this field?** It does not evaluate whether the value is "meaningful," non-null, or non-empty.

### 4.1. Finding Missing Fields

```javascript
db.fieldStatesDemo.find({
  value: { $exists: false }
});
```

Matches only `missing`, because that document lacks the `value` key.

### 4.2. Finding Present Fields

```javascript
db.fieldStatesDemo.find({
  value: { $exists: true }
});
```

Matches four documents: `null`, `emptyString`, `emptyArray`, and `text`. Even though `null`, `""`, and `[]` may look "empty" in a UI, they are still **values of an existing field**.

| Sample Document | `$exists: false` | `$exists: true` |
|---|:---:|:---:|
| `{ _id: "missing" }` | Yes | No |
| `{ _id: "null", value: null }` | No | Yes |
| `{ _id: "emptyString", value: "" }` | No | Yes |
| `{ _id: "emptyArray", value: [] }` | No | Yes |
| `{ _id: "text", value: "MongoDB" }` | No | Yes |

### 4.3. Separating Missing and Null with Two Distinct Conditions

**Find only missing fields:**

```javascript
db.fieldStatesDemo.find({
  value: { $exists: false }
});
```

**Find only fields holding BSON Null in the sample set:**

```javascript
db.fieldStatesDemo.find({
  value: { $type: "null" }
});
```

In some cases `{ value: { $exists: true, $eq: null } }` can exclude missing documents, though equality still carries array-matching semantics if the field can be an array. If you want to determine the **exact field-level type**, evaluating `$type` in aggregation (see Section 7) is unambiguous.

## 5. `$type`: Inspecting the BSON Type of a Value

MongoDB does not assume an empty string is "equivalent" to null. `""` remains type `string`; `[]` remains type `array`.

```javascript
db.fieldStatesDemo.find({ value: { $type: "null" } });
// Sample set: null

db.fieldStatesDemo.find({ value: { $type: "string" } });
// Sample set: emptyString, text

db.fieldStatesDemo.find({ value: { $type: "array" } });
// Sample set: emptyArray
```

Points to remember:

- `$type: "string"` checks for the **string type**, not whether the string is empty.
- `$type: "array"` checks for the **array type**, not how many elements it holds.
- `$type: "null"` finds BSON Null values; it does not treat missing fields as null.
- For array fields, the `$type` query operator can match **the type of elements inside the array**. To classify the type of *the field itself*, use the aggregation expression `{ $type: "$value" }`.

This last point is easy to confuse:

```javascript
// $type in a filter: query operator on the field.
db.fieldStatesDemo.find({ value: { $type: "string" } });

// $type in aggregation: returns the type name of the "$value" expression.
db.fieldStatesDemo.aggregate([
  { $project: { valueType: { $type: "$value" } } }
]);
```

On the sample set, where no array contains strings, these two do not conflict. However, if you add `{ value: ["A"] }`, the query filter `$type: "string"` will match because of element `"A"`, whereas the aggregation expression classifies `value` itself as `"array"`.

## 6. Empty Strings and Empty Arrays: Both Empty, Different Types and Predicates

### 6.1. Empty String: `""`

```javascript
db.fieldStatesDemo.find({ value: "" });
// Sample set: emptyString
```

This compares against a string of length 0. It does not match `null`, missing fields, or empty arrays. However, due to array-element matching semantics, **an array containing an empty string** also matches an empty-string equality filter:

```javascript
// Separate illustration, not added to the main dataset.
{ value: ["", "MongoDB"] }
```

If you need to require that **the entire field is an empty string**, check the field-level type in aggregation:

```javascript
db.fieldStatesDemo.aggregate([
  {
    $match: {
      $expr: {
        $and: [
          { $eq: [{ $type: "$value" }, "string"] },
          { $eq: ["$value", ""] }
        ]
      }
    }
  }
]);
```

This expression separates two requirements: the root type must be `string` and its value must be `""`. Do not assume both query styles share the same index plan; run `explain` when performance matters.

### 6.2. Empty Array: `[]`

To find fields holding an **array with 0 elements**, the most expressive operator is `$size`:

```javascript
db.fieldStatesDemo.find({
  value: { $size: 0 }
});
// Sample set: emptyArray
```

`$size: 0` checks for array length 0; it does not match an empty string because a string is not an array.

You can also write direct array equality:

```javascript
db.fieldStatesDemo.find({ value: [] });
// Sample set: emptyArray
```

On this simple dataset, both return the same result. However, array equality has its own matching rules, including nested array element cases; to express "field is an array of length 0," `$size: 0` communicates intent more clearly.

Several values look "empty" yet are completely different:

| Value | Type | Matches `$size: 0`? |
|---|---|:---:|
| Missing field | Missing | No |
| `null` | Null | No |
| `""` | String | No |
| `[]` | Array | Yes |
| `[""]` | Array with 1 empty string | No |
| `[null]` | Array with 1 null element | No |
| `{}` | Empty object | No |

**Performance note:** `$size` is generally not directly index-accelerated for counting array lengths. On large collections, if filtering by element count is very frequent, consider maintaining a dedicated **count field** updated alongside the array. Add derived fields only when justified by measured needs.

### 6.3. Result Matrix for Key Predicates

The table below uses the exact five documents inserted in Section 2:

| Filter on `value` | `missing` | `null` | `emptyString` | `emptyArray` | `text` |
|---|:---:|:---:|:---:|:---:|:---:|
| `{ value: null }` | ✓ | ✓ | — | — | — |
| `{ value: { $exists: false } }` | ✓ | — | — | — | — |
| `{ value: { $exists: true } }` | — | ✓ | ✓ | ✓ | ✓ |
| `{ value: { $type: "null" } }` | — | ✓ | — | — | — |
| `{ value: "" }` | — | — | ✓ | — | — |
| `{ value: { $type: "string" } }` | — | — | ✓ | — | ✓ |
| `{ value: { $size: 0 } }` | — | — | — | ✓ | — |
| `{ value: { $ne: null } }` | — | — | ✓ | ✓ | ✓ |
| `{ value: { $ne: "" } }` | ✓ | ✓ | — | ✓ | ✓ |

This table describes **the exact defined sample set**, where values are single-level; if an application stores arrays containing strings or nulls, equality filters require further analysis of array-element matching rules.

## 7. Aggregation: Classifying All Four States in One Pipeline

When profiling data quality issues, classifying all four states in a single pass is often much more practical than running multiple `find()` queries.

### 7.1. `$type` in Aggregation Recognizes "missing" Too

```javascript
db.fieldStatesDemo.aggregate([
  {
    $project: {
      _id: 1,
      state: { $type: "$value" }
    }
  }
]);
```

Sample output (without assuming document return order):

```javascript
{ _id: "missing",     state: "missing" }
{ _id: "null",        state: "null" }
{ _id: "emptyString", state: "string" }
{ _id: "emptyArray",  state: "array" }
{ _id: "text",        state: "string" }
```

This is a critical distinction: **`"missing"` is a string returned by the aggregation `$type` expression**, not a BSON type you can assign directly to a field. Thus, `{ value: { $type: "missing" } }` is not a valid query-filter substitute for `$exists: false`.

### 7.2. `$ifNull` Merges Missing and Null While Preserving Both Empty Types

```javascript
db.fieldStatesDemo.aggregate([
  {
    $project: {
      valueType: { $type: "$value" },
      normalized: {
        $ifNull: ["$value", "(no value yet)"]
      }
    }
  }
]);
```

`$ifNull` treats **missing**, **undefined**, and **null** as cases to replace with a fallback value. In this example:

- `missing` → `"(no value yet)"`.
- `null` → `"(no value yet)"`.
- `emptyString` → stays `""`.
- `emptyArray` → stays `[]`.
- `text` → stays `"MongoDB"`.

This means `$ifNull` is not a "replace every empty value" function. To replace empty strings or empty arrays as well, add explicit business conditions; conversely, if you must **distinguish null from missing**, do not normalize with `$ifNull` before recording the original state.

### 7.3. Explicitly Classifying Empty Strings and Empty Arrays

You can use `$switch` to label states without conflating them:

```javascript
db.fieldStatesDemo.aggregate([
  {
    $set: {
      state: {
        $switch: {
          branches: [
            {
              case: { $eq: [{ $type: "$value" }, "missing"] },
              then: "MISSING"
            },
            {
              case: { $eq: [{ $type: "$value" }, "null"] },
              then: "NULL"
            },
            {
              case: {
                $and: [
                  { $eq: [{ $type: "$value" }, "string"] },
                  { $eq: ["$value", ""] }
                ]
              },
              then: "EMPTY_STRING"
            },
            {
              case: {
                $and: [
                  { $isArray: "$value" },
                  {
                    $eq: [
                      {
                        $cond: [
                          { $isArray: "$value" },
                          { $size: "$value" },
                          null
                        ]
                      },
                      0
                    ]
                  }
                ]
              },
              then: "EMPTY_ARRAY"
            }
          ],
          default: "OTHER_VALUE"
        }
      }
    }
  },
  { $project: { _id: 1, state: 1 } }
]);
```

In the `EMPTY_ARRAY` branch, `$cond` guards `$size` so it only evaluates on actual arrays. The aggregation `$size` expression requires an array operand; passing a string, null, or missing field directly without type guarding can cause the pipeline to fail. On collections where schema validation guarantees `value` is always an array, the expression can be simplified.

If you only want to **count** documents per state, append:

```javascript
// Place after the $set stage that produces state in the pipeline above.
{ $group: { _id: "$state", count: { $sum: 1 } } }
```

This classification pattern is great for auditing data before schema normalization, reporting, or preparing migrations; it does not need to run on every production request.

## 8. How Do Update Operations Change Field State?

MongoDB does not automatically convert empty strings to null or drop fields holding empty arrays. The resulting state depends strictly on the update operator used.

### 8.1. `$set` Writes Values, Including Empty Ones

```javascript
// Update a document to BSON Null.
db.fieldStatesDemo.updateOne(
  { _id: "text" },
  { $set: { value: null } }
);

// Change to empty string.
db.fieldStatesDemo.updateOne(
  { _id: "text" },
  { $set: { value: "" } }
);

// Change to empty array.
db.fieldStatesDemo.updateOne(
  { _id: "text" },
  { $set: { value: [] } }
);
```

These three commands illustrate successive states of the **same document** if run in sequence. Each command keeps the `value` key intact, changing only its value and type.

### 8.2. `$unset` Removes the Field Completely

```javascript
db.fieldStatesDemo.updateOne(
  { _id: "text" },
  { $unset: { value: "" } }
);
```

After this command, the `text` document no longer contains the `value` key. When querying `{ value: { $exists: false } }`, it now matches alongside `missing`. The value placed next to `$unset` simply marks the field to remove, rather than writing an empty string.

### 8.3. Adding a Field to a Document That Lacked It

```javascript
db.fieldStatesDemo.updateOne(
  { _id: "missing" },
  { $set: { value: null } }
);
```

This command **creates the `value` key with value null** inside `missing`. It does not leave the field in the missing state. To keep a field absent, omit it from new documents or delete it with `$unset`.

**Practice reminder:** after running the update examples in Section 8, the dataset no longer matches its initial states. The result tables in Section 6.3 apply only before running updates; to retry cleanly, use a fresh test collection.

## 9. Application Scenarios: "Omitted," "Cleared," "Blank," and "Zero Items"

### 9.1. User Profile Update API

Suppose a profile update API accepts `nickname` and `tags`. Define clear semantics for each field:

| Application Payload | Interpretation *If Defined by the API* | Possible MongoDB Operation |
|---|---|---|
| `nickname` omitted | Keep existing nickname | Omit `nickname` from update |
| `nickname: null` | Explicitly remove nickname | `$unset: { nickname: "" }` |
| `nickname: ""` | Store empty string, or return validation error | `$set` empty string, or reject |
| `nickname: "An"` | Set new nickname | `$set: { nickname: "An" }` |
| `tags` omitted | Keep existing tag list | Do not update `tags` |
| `tags: []` | Clear all tags while keeping array structure | `$set: { tags: [] }` |
| `tags: null` | Potentially invalid if schema requires an array | Validate and possibly reject |

**These policies are defined by your API.** MongoDB does not treat JSON `null` as a delete instruction on its own. If application code sends `$set: { nickname: null }`, MongoDB stores null; if it sends `$unset`, MongoDB removes the field.

This matters especially for partial-update APIs (`PATCH`). Code using `if (value == null)` to skip fields will **conflate** "field omitted" with "user sent null." To distinguish them, check whether the key was present in the request before choosing the database operation.

### 9.2. Java Driver: Distinguishing `containsKey` and `get`

In Java, a `Document` acts as a key/value map and can construct all four states explicitly:

```java
import java.util.List;
import org.bson.Document;

Document missing = new Document("_id", "missing");
Document withNull = new Document("_id", "null")
    .append("value", null);
Document emptyString = new Document("_id", "emptyString")
    .append("value", "");
Document emptyArray = new Document("_id", "emptyArray")
    .append("value", List.of());
```

Calling only `document.get("value")` returns Java `null` for both a **missing key** and a **key holding BSON Null**. Check key presence first:

```java
Object value = document.get("value");

if (!document.containsKey("value")) {
    System.out.println("Field does not exist");
} else if (value == null) {
    System.out.println("Field exists with BSON Null");
} else if (value instanceof String text && text.isEmpty()) {
    System.out.println("Empty string");
} else if (value instanceof List<?> items && items.isEmpty()) {
    System.out.println("Empty array");
} else {
    System.out.println("Other value");
}
```

This snippet applies to data read/represented as `org.bson.Document` with standard Java strings and lists. If your app uses POJO codecs, Spring Data, or JSON mappers, check how those tools serialize null vs. absent fields. Depending on configuration, a Java `null` property might be omitted during writes; **inspect the actual BSON stored**, not just Java object properties.

### 9.3. Should Every Field Be "Populated" for Schema Uniformity?

There is no single universal answer. Design guidelines:

- For **required** fields, enforce that they always exist with the expected type.
- For **optional** fields, choose consistently between "missing field" and "present with null" per business needs.
- For **list** fields, an empty array `[]` usually expresses "currently zero items" more clearly than `null` when the schema models a list.
- For **string** fields, decide upfront whether `""` is allowed; never let `null`, missing, and `""` act as three random ways to express the same state.

For example, `phoneNumber` can be allowed to be missing when a user has not provided one, while `tags` can default to `[]`. These choices are **data modeling** and **API contract** decisions first, rather than micro-optimizations for queries.

## 10. Schema Validation: Controlling Which States Can Be Persisted

MongoDB supports collection-level schema validation via `$jsonSchema`, which can enforce both **field presence** and **value types**.

Example profile collection where `displayName` must be a non-empty string, and `tags`, when present, must be an array:

```javascript
db.createCollection("validatedProfilesDemo", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["displayName"],
      properties: {
        displayName: {
          bsonType: "string",
          minLength: 1,
          description: "Required non-empty display name"
        },
        tags: {
          bsonType: "array",
          description: "Tag list when provided"
        }
      }
    }
  }
});
```

Effect of these rules:

| Value | `displayName` | `tags` |
|---|---|---|
| Missing field | Invalid because it is in `required` | Valid because it is not in `required` |
| `null` | Invalid due to `bsonType: "string"` | Invalid if supplied because it must be an array |
| `""` | Invalid due to `minLength: 1` | Invalid because String is not Array |
| `[]` | Invalid because Array is not String | Valid because an empty array is still an array |
| `"An"` | Valid | Invalid as a value for `tags` |

If `tags` must also exist, add `"tags"` to `required`. If `tags` must hold at least one item, add `minItems: 1` to `tags`. To allow a field to be either `null` **or** a non-empty string, explicitly specify both valid cases—for instance using `anyOf` with a BSON Null branch and a String branch with `minLength`.

Schema validation prevents "empty" states from being mixed arbitrarily at write time. Still, deploy it alongside application validation and a cleanup plan for existing inconsistent records.

## 11. Indexes and Performance When Filtering Special States

Filtering by field presence and data type affects how MongoDB uses indexes.

### 11.1. Regular Indexes and Absent Values

```javascript
db.fieldStatesDemo.createIndex({ value: 1 });
```

A standard single-field index generates index entries for both documents missing the indexed field and documents holding `null` according to MongoDB's indexing rules. Therefore, inspecting index keys alone may not trivially separate "missing" from "explicit null." Queries checking `$exists` may need to fetch documents or face different optimizer constraints.

### 11.2. Sparse Indexes and Partial Indexes

A single-field **sparse index** skips documents that lack the indexed field, yet documents with `value: null` still contain the field and are therefore indexed:

```javascript
// Example for a separate collection; do not create the same key pattern
// as a drop-in replacement for the test collection's default index.
db.sparseIndexDemo.createIndex(
  { optionalValue: 1 },
  { sparse: true }
);
```

A **partial index** indexes only documents matching a defined filter expression, which is useful when queries target a specific subset of states:

```javascript
db.optionalUsersDemo.createIndex(
  { nickname: 1 },
  {
    unique: true,
    partialFilterExpression: {
      nickname: { $type: "string" }
    }
  }
);
```

In this example, only documents whose `nickname` satisfies the string-type filter participate in the unique index constraint. **An empty string is still a string**, so multiple documents with `nickname: ""` will violate uniqueness; the "missing field" state behaves differently.

With a standard single-field unique index, documents with `null` or missing fields collide on the same null index key; a partial unique index works much better when multiple documents have no nickname yet, while enforcing uniqueness on **actually populated** nicknames.

Note: the query planner only uses a partial index when the query predicate implies the index's filter expression. Do not create a partial index solely to save space and assume every query will use it.

### 11.3. Measuring Real Execution Plans

```javascript
db.fieldStatesDemo.find({
  value: { $exists: false }
}).explain("executionStats");

db.fieldStatesDemo.find({
  value: { $type: "null" }
}).explain("executionStats");

db.fieldStatesDemo.find({
  value: { $size: 0 }
}).explain("executionStats");
```

Inspect `COLLSCAN`, `IXSCAN`, `FETCH`, `totalDocsExamined`, and `totalKeysExamined` in the output. With only five sample documents, MongoDB may choose a collection scan even when an index exists because scanning tiny data is cheap. To draw performance conclusions, benchmark on data matching production scale and distribution.

## 12. Common Misconceptions

| Misconception | Correct Understanding |
|---|---|
| `null` is the same as a missing field | `null` is a BSON value on an existing key; a missing field has no key |
| `{ value: null }` only finds explicit nulls | It also matches documents missing `value` and obeys array-matching rules |
| `$exists: true` means a non-null value exists | It still matches `null`, empty strings, and empty arrays |
| `$type: "string"` means a non-empty string | An empty string still has BSON type String |
| `[]` and `""` are both empty so they query the same way | They have different BSON types and require different operators |
| `$size: 0` matches any empty value | It applies strictly to arrays of length 0 |
| `$ifNull` replaces every empty value | It handles `null`/`missing`/`undefined`, leaving `""` and `[]` untouched |
| `$set: { value: null }` deletes the field | `$set` stores null; `$unset` removes the key |
| `document.get("value") == null` proves the field is missing | On Java `Document`, you also need `containsKey` |
| Indexes automatically resolve null/missing/empty inconsistencies | Indexes do not replace schemas; ingestion and storage rules must be consistent |

## 13. Practice Exercises

### Exercise 1 — Predict Filter Matches

On the five documents created in Section 2 **before running updates**, determine which `_id` values match:

```javascript
db.fieldStatesDemo.find({ value: null });
db.fieldStatesDemo.find({ value: { $exists: false } });
db.fieldStatesDemo.find({ value: { $type: "null" } });
db.fieldStatesDemo.find({ value: "" });
db.fieldStatesDemo.find({ value: { $size: 0 } });
db.fieldStatesDemo.find({ value: { $ne: null } });
```

After making your predictions, compare against the table in Section 6.3 and explain each result using **field presence**, **BSON type**, and **operator semantics**.

### Exercise 2 — Classify States in Aggregation

Write a pipeline returning `_id` and `state` with these labels:

```text
missing       -> MISSING
null          -> NULL
emptyString   -> EMPTY_STRING
emptyArray    -> EMPTY_ARRAY
text          -> OTHER_VALUE
```

Use `$type`, `$switch`, `$isArray`, and `$size` appropriately. Then append `$group` to count documents per state. You can start from the pipeline in Section 7 and trim branches unnecessary for normalized data.

### Exercise 3 — Determine Update Outcomes

Consider the document:

```javascript
{ _id: "profile-1", nickname: "An", tags: ["mongodb"] }
```

After each operation below, state **whether the key still exists, its BSON type, and its value**:

```javascript
db.profilesDemo.updateOne(
  { _id: "profile-1" },
  { $set: { nickname: null } }
);

db.profilesDemo.updateOne(
  { _id: "profile-1" },
  { $set: { tags: [] } }
);

db.profilesDemo.updateOne(
  { _id: "profile-1" },
  { $unset: { nickname: "" } }
);
```

Run these only after inserting the sample document into a test `profilesDemo` collection. Do not confuse these database operations with missing fields in a JSON request; translating request intent into update operators is the API layer's responsibility.

### Exercise 4 — Designing Data Conventions

An application stores `email` and `favoriteCategories`. Answer:

1. When a user has not entered an email, will the app store **missing** or **null**? Why?
2. When a user clears all favorite categories, should you store `[]` or remove the field? Which fits the UI and API contract better?
3. Should `email: ""` be accepted? If not, will you enforce it at the API layer or with `$jsonSchema`?
4. How will a partial-update API distinguish "email omitted" from "email=null"?
5. If you need to find profiles without a provided email, why might `{ email: null }` fail to reflect your exact business definition?

**Takeaway:** To query accurately, separate three questions: **does the field exist?** (use `$exists`), **what BSON type does the value have?** (use `$type`), and **is the value empty according to that type's rules?** (such as `""` for strings, `$size: 0` for arrays). In MongoDB, *missing field*, *BSON Null*, *empty string*, and *empty array* are four distinct data states that can trigger four distinct query and update behaviors.
