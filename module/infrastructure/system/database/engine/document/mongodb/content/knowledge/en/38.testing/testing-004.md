# Testing BSON, Nulls, Missing Fields, Arrays, and Schema Validation in MongoDB

> **Module:** MongoDB Document Database Engine  
> **Chapter:** Testing  
> **Lesson:** Testing BSON, Nulls, Missing Fields, Arrays, and Schema Validation

## 1. Why Do These “Small” Cases Corrupt Real Data?

A Java application receives order payloads over an API and writes them to MongoDB. In development, documents typically look like:

```javascript
{
  _id: ObjectId("66a000000000000000000414"),
  orderCode: "LAB-414",
  amountCents: NumberLong("125000"),
  contact: {
    email: "demo@example.test"
  },
  tags: ["paid", "priority"],
  lines: [
    { sku: "BOOK-A", quantity: NumberInt(2) }
  ],
  cancelledAt: null
}
```

Once real data arrives, the same collection may contain:

- `amountCents` as `int` in older documents, `long` in newer documents, `double` from a conversion bug, and `string` from bad API input.
- `contact` sometimes as an object, sometimes `null`, and sometimes completely absent.
- `tags` as an empty array, missing, containing `null`, having duplicate elements, or even stored as a string instead of an array.
- `lines` with multiple elements; dot-notation queries may match conditions across **two different elements**.
- `cancelledAt: null` meaning “not cancelled yet,” while a missing field means “an older client did not send this field.”
- A newly added validator rejecting an update on a legacy document even when the command only modifies an unrelated field.
- Java code calling `Document.get("field")`, receiving `null`, and **not knowing whether the field was actually null or missing**.

If unit tests only compare JSON as strings, many bugs go undetected: BSON has dedicated numeric and date types, MongoDB has distinct `null`/array query semantics, validators inspect **the resulting document after a write**, and the Java driver applies codec conversions.

This lesson demonstrates how to build a **test suite with explicit expected outcomes** for MongoDB, from `mongosh` to the Java Sync Driver and JUnit 5, and how to test validation on collections that already hold data.

### 1.1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish key BSON types: `int`, `long`, `double`, `decimal`, `date`, `timestamp`, `objectId`, `binData`, `null`, `array`, and `object`.
2. Write tests that preserve BSON types across serialize → insert → read.
3. Distinguish **null**, **missing fields**, **legacy undefined**, empty strings, `0`, `false`, empty objects, and empty arrays.
4. Predict and test `{field: null}`, `$exists`, `$type`, `$ne`, and `$ifNull`.
5. Test array queries by element, position, full array equality, and same-element matching with `$elemMatch`.
6. Write validators using `$jsonSchema`, `bsonType`, `required`, `items`, `enum`, and value constraints.
7. Understand the behavior of `validationLevel: strict/moderate/constraint` and `validationAction: error/warn/errorAndLog` across server versions.
8. Test inserts, updates, replacements, upserts, partial updates, and legacy data.
9. Build Java integration tests with isolated collections and fake data that never interfere with other tests.
10. Apply regression testing when schemas, mappers, or driver versions change.

## 2. Four Principles of MongoDB Test Design

### 2.1. Test **BSON**, Not Just Visible JSON

```text
HTTP JSON
   |
   v
Java DTO / Jackson
   |
   v
MongoDB Java Driver / Codec
   |
   v
BSON bytes
   |
   v
MongoDB validation + query engine
   |
   v
BSON decoded to Java objects
   |
   v
Application business behavior
```

A value rendered as `42` in JSON can be serialized as BSON `int32`, `int64`, or `double`. The string `"2026-11-14T00:00:00Z"` does not automatically become a BSON Date unless the mapper converts it. You must test across these boundaries.

### 2.2. Test **States**, Not Just a Single Value

For a `notes` field, at least these states exist:

| State | Document | Field present? | BSON type |
| --- | --- | --- | --- |
| Missing | `{}` | No | `missing` in aggregation expressions |
| Null | `{notes: null}` | Yes | `null` |
| Empty string | `{notes: ""}` | Yes | `string` |
| Non-empty string | `{notes: "x"}` | Yes | `string` |
| Empty array | `{notes: []}` | Yes | `array` |
| Empty object | `{notes: {}}` | Yes | `object` |
| Boolean false | `{notes: false}` | Yes | `bool` |
| Zero | `{notes: NumberInt(0)}` | Yes | `int` |

**Never collapse these states into “falsy/empty”** in application logic or test assertions unless the business contract explicitly specifies doing so.

### 2.3. Run Against Real MongoDB When Verifying Server Semantics

A mocked repository cannot guarantee the real behavior of:

- `{field: null}` or `$exists`;
- numeric BSON types and codecs;
- `$elemMatch` across array elements;
- `$jsonSchema` during inserts and updates;
- unique/partial/multikey indexes;
- `DocumentValidationFailure` errors and server version differences.

Unit tests remain valuable for pure business logic, whereas the rules above require **integration tests against a MongoDB Server** matching your production deployment.

### 2.4. Test Data Must Be Independent and Recoverable

- Use **synthetic** data with zero PII or customer details.
- Allocate a dedicated database/collection or randomized collection name per test.
- Tag every test document with a unique `runId`.
- Never run `deleteMany({})` or `dropDatabase()` on shared environments.
- Never alter FCV, server-level parameters, or production indexes solely for testing.
- Record server/driver versions, BSON types, queries, and expected outcomes.

## 3. What Is BSON and Why Do Types Matter?

BSON (Binary JSON) is the binary document format MongoDB stores and transmits. Beyond standard JSON types, BSON defines several distinct types.

### 3.1. Common Data Types Table

| BSON | Example in `mongosh` | Common Java Sync Driver type | Testing risk |
| --- | --- | --- | --- |
| `string` | `"hello"` | `String` | Unicode, normalization, collation |
| `int` (Int32) | `NumberInt(42)` | `Integer` | 32-bit integer overflow |
| `long` (Int64) | `NumberLong("42")` | `Long` | Precision loss via JS Number |
| `double` | `NumberDouble("3.14")` | `Double` | Floating-point rounding, NaN |
| `decimal` | `NumberDecimal("12.50")` | `Decimal128` | Precision, scale, and BigDecimal conversion |
| `bool` | `true` | `Boolean` | False differs from missing/null |
| `date` | `ISODate("2026-11-14T00:00:00Z")` | `java.util.Date` or other codec | UTC, milliseconds, timezone |
| `timestamp` | `Timestamp({t: ..., i: ...})` | `BsonTimestamp` | Not Date; mainly internals/oplog |
| `objectId` | `ObjectId()` | `ObjectId` | Not interchangeable with String |
| `binData` | `BinData(...)` | `Binary` / `BsonBinary` | UUID subtype, bytes, encoding |
| `null` | `null` | `null` / `BsonNull` | Differs from missing field |
| `array` | `[1, 2]` | `List` / `BsonArray` | Order, element types, multikey |
| `object` | `{a:1}` | `Document` / `BsonDocument` | Nested and missing fields |

In Java, `org.bson.Document` is a flexible `String → Object` map. `BsonDocument` holds strongly typed `BsonValue`s, making it ideal when asserting exact BSON types.

### 3.2. The Same Number 42 Does Not Mean the Same BSON Type

```javascript
const sample = {
  int32: NumberInt(42),
  int64: NumberLong("42"),
  doubleNumber: NumberDouble("42"),
  decimalNumber: NumberDecimal("42.00")
};

db.sample.insertOne(sample);
```

Use aggregation to inspect the actual stored types:

```javascript
db.sample.aggregate([
  {
    $project: {
      int32Type: { $type: "$int32" },
      int64Type: { $type: "$int64" },
      doubleType: { $type: "$doubleNumber" },
      decimalType: { $type: "$decimalNumber" }
    }
  }
]);
```

Expected output is `int`, `long`, `double`, and `decimal` for the respective fields.

**Note:** MongoDB query comparisons compare numbers across numeric BSON types, so an equality predicate may not strictly distinguish Int32, Int64, and Double. If your requirement demands an **exact BSON type**, check `$type` or codecs/validators rather than treating `find({x: 42})` as proof of identical types.

### 3.3. Large Numbers and JavaScript

Integers exceeding the safe range of IEEE-754 double (`Number.MAX_SAFE_INTEGER` in JavaScript) can lose digits if passed as a JS Number.

Wrong:

```javascript
// Never pass a huge 64-bit integer as a JS Number
// and assume exact precision.
const unsafe = 9007199254740993;
```

Better:

```javascript
const exact = NumberLong("9007199254740993");
```

In Java:

```java
Document d = new Document()
    .append("count32", 42)
    .append("count64", 42L);
```

`42` is an `Integer` and normally serializes as BSON Int32; `42L` is a `Long` and normally becomes BSON Int64. With `Document`, calling `getInteger("count64")` can throw a cast error; know the stored type or use `BsonDocument` when testing types.

### 3.4. Decimal128 for Currency

```java
import org.bson.types.Decimal128;
import java.math.BigDecimal;

Decimal128 amount = new Decimal128(
    new BigDecimal("123456.78")
);

Document d = new Document("price", amount);
```

Avoid:

```java
new BigDecimal(0.1)
```

when exact decimal representation is required: `double 0.1` has no exact binary representation. Prefer `new BigDecimal("0.10")`, or store money in minor units as an integer with clear bounds.

**Testing currency:** value, type, scale/rounding per business contract, negative numbers, overflow bounds, and serialization round-trip.

### 3.5. Dates and Times: BSON Date Differs from String

```javascript
{
  atDate: ISODate("2026-11-14T00:00:00.000Z"),
  atString: "2026-11-14T00:00:00.000Z"
}
```

Both look similar when printed, yet their types differ. Date stores milliseconds since the Unix epoch in UTC; MongoDB does not store the original timezone inside a BSON Date.

Test:

- Does input in timezone Asia/Ho_Chi_Minh convert to the exact UTC instant?
- Does round-trip preserve milliseconds?
- Are `null`/missing values handled for optional dates?
- Do Date sorts/filters use indexes rather than lexicographical String comparisons?
- Is DST handled in the application when business logic uses another local timezone?

Never substitute BSON `Timestamp` for Date for business timestamps; `Timestamp` encodes seconds plus an increment with internal semantics.

### 3.6. ObjectId, String, and UUID

```javascript
{
  _id: ObjectId("66a000000000000000000414")
}
```

differs from:

```javascript
{
  _id: "66a000000000000000000414"
}
```

Although both display the same 24 hex characters, `ObjectId` and `String` are distinct types in queries and indexes.

For UUIDs, the BSON Binary subtype (standard vs legacy) affects how drivers decode values. Test `UuidRepresentation.STANDARD` and migrate legacy subtypes if old data stores UUIDs—never assume every 16-byte binary uses the same UUID encoding.

### 3.7. Extended JSON Is Not Plain JSON

MongoDB Extended JSON preserves BSON types:

```json
{
  "i64": { "$numberLong": "42" },
  "money": { "$numberDecimal": "15.50" },
  "createdAt": {
    "$date": "2026-11-14T00:00:00Z"
  },
  "objectId": {
    "$oid": "66a000000000000000000414"
  }
}
```

If tests convert documents to plain JSON via Jackson or a frontend serializer, type fidelity can be lost.

Two key modes:

- **Canonical Extended JSON:** preserves detailed type tags.
- **Relaxed Extended JSON:** easier to read, but can lose type distinctions across incompatible parsers.

Never compare `toJson()` as an exact string if key order or Extended JSON formatting differs; assert directly on BSON values and business values.

## 4. Null, Missing, Empty, False, and Zero: Baseline Test Matrix

### 4.1. Clear Fixture Set

In a lab collection:

```javascript
[
  { _id: "missing" },
  { _id: "explicit-null", value: null },
  { _id: "empty-string", value: "" },
  { _id: "zero", value: NumberInt(0) },
  { _id: "false", value: false }
]
```

Write down the expected IDs **before running** any query.

### 4.2. Querying `{value: null}`

```javascript
db.c.find({ value: null });
```

MongoDB matches:

- `"missing"` — field is absent.
- `"explicit-null"` — field has BSON Null.

It does not match empty strings, `0`, or `false`.

**This is a critical difference from many SQL query semantics** and a frequent source of bugs when applications use the same filter for “unset” and “explicitly set to null.”

### 4.3. Querying for a **Missing** Field

```javascript
db.c.find({
  value: { $exists: false }
});
```

Matches only `"missing"` in the fixture above.

`$exists: false` checks field **presence**, not `null`.

### 4.4. Querying for a **Present Field, Including Null**

```javascript
db.c.find({
  value: { $exists: true }
});
```

Matches `"explicit-null"`, `"empty-string"`, `"zero"`, and `"false"`.

A field with value `null` is still **present**, not missing.

### 4.5. Querying Strictly for BSON Null

```javascript
db.c.find({
  value: { $type: "null" }
});
```

In a scalar fixture, matches only `"explicit-null"`. BSON type number 10 also works:

```javascript
db.c.find({
  value: { $type: 10 }
});
```

Be careful when the field is an **array**: query predicate `$type` can match the type of **an element inside the array**, not solely the outer field's type. Avoid placing an array containing `null` into a scalar fixture and assuming the count stays 1.

### 4.6. `$ne: null`

```javascript
db.c.find({
  value: { $ne: null }
});
```

On the scalar fixture, returns documents where the field exists and is non-null: `"empty-string"`, `"zero"`, `"false"`.

Do not casually rewrite:

```javascript
{ value: { $ne: null } }
```

into a non-equivalent SQL expression; if arrays or mixed types are present, add tests covering operator semantics.

### 4.7. Expected Results Table

| Filter | Matching IDs in the 5-document fixture |
| --- | --- |
| `{value:null}` | `missing`, `explicit-null` |
| `{value:{$exists:false}}` | `missing` |
| `{value:{$exists:true}}` | `explicit-null`, `empty-string`, `zero`, `false` |
| `{value:{$type:"null"}}` | `explicit-null` |
| `{value:{$ne:null}}` | `empty-string`, `zero`, `false` |
| `{value:""}` | `empty-string` |
| `{value:0}` | `zero` in this fixture |
| `{value:false}` | `false` |

Do not include `{value:[null]}` in this table: **array traversal** adds extra matches, which are tested separately in the arrays section.

## 5. Null in Java: `Document.get()` Is Not Enough

### 5.1. Distinguishing Missing from Explicit Null

```java
Document missing = new Document("_id", "missing");

Document explicitNull = new Document("_id", "explicit-null")
    .append("value", null);

System.out.println(missing.get("value"));       // null
System.out.println(explicitNull.get("value"));  // null
```

Both print `null`. To distinguish them:

```java
boolean missingHasField = missing.containsKey("value");
boolean nullHasField = explicitNull.containsKey("value");

// false vs true
```

Equivalently with `BsonDocument`:

```java
BsonDocument missingBson = new BsonDocument();

BsonDocument nullBson = new BsonDocument(
    "value", BsonNull.VALUE
);

boolean hasField = nullBson.containsKey("value");
boolean isNullValue = nullBson.get("value").isNull();
```

Tests must assert **both presence and value**.

### 5.2. POJO Codecs and Mappers Can Erase the Missing State

A DTO:

```java
public class Profile {
    private String nickname;
    // getters/setters
}
```

cannot on its own preserve all three states:

1. JSON omits the `nickname` key.
2. JSON contains `"nickname": null`.
3. Java field `nickname == null` after deserialization.

Behavior depends on Jackson configuration, POJO codec annotations, field defaults, and mapper update semantics.

If business logic must distinguish **PATCH: leave field unchanged** from **PATCH: set field to null**, design a command/DTO with explicit field presence (such as an absent/present wrapper, JSON Patch, or a tracked set of supplied fields). Do not rely on `Optional<String>` or Java `null` without testing the full serialization path.

### 5.3. `$set: null` Differs from `$unset`

```javascript
db.c.updateOne(
  { _id: "case-1" },
  { $set: { nickname: null } }
);
```

Afterward, `nickname` **exists with value null**.

```javascript
db.c.updateOne(
  { _id: "case-1" },
  { $unset: { nickname: "" } }
);
```

Afterward, `nickname` **does not exist**.

If a validator has `required: ["nickname"]`, `$unset` is rejected; `$set: null` succeeds only if the property schema permits BSON Null.

### 5.4. `$ifNull` Intentionally Merges Null and Missing

In aggregation:

```javascript
{
  $project: {
    normalized: {
      $ifNull: ["$nickname", "anonymous"]
    }
  }
}
```

`$ifNull` treats missing/undefined fields identically to null. This works well for fallback values, yet is **unsuitable when the two states must remain distinct**.

Use aggregation `$type` when you need to classify them:

```javascript
db.c.aggregate([
  {
    $project: {
      valueType: { $type: "$value" }
    }
  }
]);
```

The expression evaluates to `"missing"` for absent fields and `"null"` for BSON Null.

### 5.5. BSON Undefined Is a Legacy Type

BSON defines an `undefined` type (type 6), which is **deprecated**. Never use `undefined` as a new sentinel. Legacy systems may still contain old documents with this type; verify server/driver behavior and migrate carefully.

Do not assume every JavaScript `undefined` maps to BSON Null. Driver versions and serializer settings behave differently; always read back persisted BSON to verify the stored type.

## 6. Nested Fields: Dot Notation and Missing Fields

### 6.1. Three Profile States

```javascript
[
  { _id: "p-missing" },
  { _id: "p-null", profile: null },
  { _id: "p-object", profile: { city: "HCM" } },
  { _id: "p-empty", profile: {} }
]
```

Query:

```javascript
{ "profile.city": { $exists: false } }
```

can match:

- `profile` missing;
- `profile` null;
- `profile` object missing `city`.

Conversely:

```javascript
{ "profile.city": "HCM" }
```

matches documents where the nested `city` equals `"HCM"`.

### 6.2. Why Does `{"profile.city": null}` Need Careful Testing?

With dotted paths, an absent path can match a null query per query semantics, yet if the parent is an array, object, null, or malformed shape, results can surprise application code.

Never use `{"profile.city": null}` as the sole check for “city was explicitly set to null.” When business rules need explicit null distinction on a nested object, enforce parent `bsonType: "object"` in schema, combine `$type`/`$exists`, and test fixtures covering missing/null/array parents.

### 6.3. Avoid Arbitrary Whole-Object Equality

```javascript
db.c.find({
  profile: {
    city: "HCM",
    country: "VN"
  }
});
```

Whole embedded-document equality depends on **exact structure and field order**, unlike:

```javascript
db.c.find({
  "profile.city": "HCM",
  "profile.country": "VN"
});
```

If the application only intends to match child fields, use dot notation or `$elemMatch` instead of untested whole-object equality.

## 7. Testing Arrays: Membership, Equality, Order, and Size

### 7.1. Basic Array Fixture

```javascript
[
  { _id: "a1", tags: ["java", "mongodb"] },
  { _id: "a2", tags: ["mongodb", "java"] },
  { _id: "a3", tags: ["java"] },
  { _id: "a4", tags: [] },
  { _id: "a5" }
]
```

### 7.2. Matching a Single Element

```javascript
db.c.find({ tags: "java" });
```

Matches `a1`, `a2`, `a3`: a scalar predicate on an array field matches if any element satisfies it.

### 7.3. Matching the **Entire Array in Order**

```javascript
db.c.find({
  tags: ["java", "mongodb"]
});
```

In the fixture above, matches `a1`, does not match `a2` because the order differs, and does not match `a3` because an element is missing. Array equality is not set equality.

### 7.4. Matching All Elements Regardless of Order

```javascript
db.c.find({
  tags: {
    $all: ["java", "mongodb"]
  }
});
```

Matches `a1` and `a2` in the fixture. `$all` checks membership, not **element multiplicity** or order.

### 7.5. Matching Exact Array Length

```javascript
db.c.find({
  tags: { $size: 0 }
});
```

Matches only `a4`. Missing field `a5` is not the same as an empty array.

`$size` takes an exact integer; it does not accept ranges like `{$size: {$gt: 2}}`. To query lengths above 2, maintain a `tagsCount` field consistently or use an aggregation expression appropriate to your requirements and resources.

### 7.6. Matching by Position

```javascript
db.c.find({
  "tags.0": "java"
});
```

Matches `a1` and `a3`; does not match `a2` because the first element is `"mongodb"`.

Indexing positional/dot-notation array queries requires understanding multikey semantics. Never treat an array as a single scalar value in index design.

### 7.7. A String Field Differs from an Array Field

```javascript
{
  _id: "bad",
  tags: "java"
}
```

The query `{tags: "java"}` **also matches** this document. If `tags` must always be an array, membership queries alone **cannot enforce schema**. Use a `bsonType: "array"` validator or an explicit type filter.

## 8. `$elemMatch`: Multiple Conditions Must Hold on the **Same Element**

### 8.1. Classic Bug with Arrays of Objects

Fixture:

```javascript
{
  _id: "order-cross-match",
  lines: [
    { sku: "BOOK-A", quantity: NumberInt(1) },
    { sku: "BOOK-B", quantity: NumberInt(8) }
  ]
}
```

Wrong query when seeking **a single BOOK-A line with quantity >= 5**:

```javascript
db.orders.find({
  "lines.sku": "BOOK-A",
  "lines.quantity": { $gte: 5 }
});
```

**Matches the document above!** The `sku` predicate matches the first element, while `quantity` matches the second element. The two predicates are not forced onto the same element.

### 8.2. Correct Query with `$elemMatch`

```javascript
db.orders.find({
  lines: {
    $elemMatch: {
      sku: "BOOK-A",
      quantity: { $gte: 5 }
    }
  }
});
```

`order-cross-match` **does not match**, because no single element has both `sku: "BOOK-A"` and `quantity >= 5`.

Another document:

```javascript
{
  _id: "order-match",
  lines: [
    { sku: "BOOK-A", quantity: NumberInt(6) }
  ]
}
```

does match.

### 8.3. Numeric Arrays and Range Conditions

Fixture:

```javascript
{
  _id: "s-range",
  scores: [65, 105]
}
```

Query:

```javascript
{
  scores: {
    $gt: 80,
    $lt: 100
  }
}
```

matches because **two different elements** satisfy the two bounds: `105 > 80` and `65 < 100`.

To require a single score inside the range:

```javascript
{
  scores: {
    $elemMatch: {
      $gt: 80,
      $lt: 100
    }
  }
}
```

The fixture `[65, 105]` does not match. This is one of the most important regression checks when migrating a field from scalar to array.

### 8.4. `$elemMatch` Also Requires the Field to Be an Array

If a document has:

```javascript
{ _id: "object", lines: { sku: "BOOK-A", quantity: 6 } }
```

`$elemMatch` **does not match** because `lines` is not an array. Dot notation can still match fields inside a plain object; test both to catch malformed shapes.

### 8.5. Arrays Mixing Objects, Scalars, and Nulls

Example of dirty data:

```javascript
{
  lines: [
    { sku: "A", quantity: 1 },
    null,
    "invalid-element"
  ]
}
```

Do not test only “clean” object arrays. When a schema permits mixed arrays, query outcomes can surprise you; an `items` validator blocks mistyped elements on the write path.

## 9. Arrays Containing Null, Empty Arrays, and Missing Fields

### 9.1. Four Distinct Cases

```javascript
[
  { _id: "array-missing" },
  { _id: "array-null", items: null },
  { _id: "array-empty", items: [] },
  { _id: "array-with-null", items: [null] }
]
```

Key checks:

- `$exists: false` matches only the missing field.
- `$size: 0` matches the empty array, not null or missing.
- `{items: null}` combines null/missing **and array element matching**, so it can also match arrays containing `null`.
- `$type: "null"` on an array can match **a null element** inside the array per query predicate semantics.
- `$type: "array"` helps ensure the field itself is an array in standard cases.

Thus, a test containing only null and missing fields without `[]` and `[null]` misses array-specific bugs.

### 9.2. Nested Arrays, Objects, and Exact Matches

Additional cases:

```javascript
[
  { _id: "nested-array", items: [["A"], ["B"]] },
  { _id: "array-object", items: [{ code: "A" }] },
  { _id: "wrong-scalar", items: "A" }
]
```

Scalar queries can match array elements or scalar fields; exact array equality has specific ordering rules. For deeply nested arrays, never rely on intuition that “MongoDB traverses every level”—verify the exact query.

### 9.3. Query `$type` Differs from Aggregation Expression `$type`

Query predicate:

```javascript
db.c.find({
  items: { $type: "string" }
});
```

matches an array containing a String element.

Aggregation expression:

```javascript
db.c.aggregate([
  {
    $project: {
      itemsType: { $type: "$items" }
    }
  }
]);
```

returns the type of the **expression value itself**: `"array"` for an array, and `"missing"` for an absent field.

The two `$type` forms have different semantic contexts; tests checking the type of the **whole field** should favor BSON readback, aggregation `$type`, or schema validators.

## 10. Array Updates and Testing Idempotency

### 10.1. `$push` Differs from `$addToSet`

```javascript
db.c.updateOne(
  { _id: "a1" },
  { $push: { tags: "java" } }
);
```

`$push` appends even if the element already exists, creating duplicates.

```javascript
db.c.updateOne(
  { _id: "a1" },
  { $addToSet: { tags: "java" } }
);
```

`$addToSet` inserts only if the element is absent per equality semantics. However, it **does not remove pre-existing duplicates** in the array. For embedded documents, equality also depends on structure and field order.

### 10.2. `$pull`

```javascript
db.c.updateOne(
  { _id: "a1" },
  { $pull: { tags: "java" } }
);
```

Removes all matching elements. If a test expects only “the first matching element” to be removed, note that `$pull` strips every matching occurrence in the array.

### 10.3. Positional Updates and `arrayFilters`

```javascript
db.orders.updateOne(
  { _id: "order-match" },
  {
    $set: {
      "lines.$[line].checked": true
    }
  },
  {
    arrayFilters: [
      {
        "line.sku": "BOOK-A",
        "line.quantity": { $gte: 5 }
      }
    ]
  }
);
```

Tests must prove:

- Only elements matching the filter change.
- Non-matching elements remain untouched.
- No unexpected fields are created or altered.
- Updates can still be rejected by schema validation if the resulting document violates types.
- Under concurrent updates, version checks or transactions are needed when business invariants demand them.

### 10.4. Indexes Alone Do Not Deduplicate Inside a Single Array

A unique multikey index enforces uniqueness **across documents**, not across elements within the same array. To forbid duplicates inside an array, consider:

- `uniqueItems: true` in the validator where appropriate.
- `$addToSet` on writes.
- Application logic handling type canonicalization.
- Tests for duplicated scalar/object elements and concurrent writers.

## 11. Schema Validation: What Does MongoDB Check?

### 11.1. `$jsonSchema` Is Not a Java DTO Validator

MongoDB lets you declare a validator on the collection:

```javascript
db.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["orderCode", "amountCents"],
      properties: {
        orderCode: { bsonType: "string" },
        amountCents: { bsonType: "long" }
      }
    }
  }
});
```

The validator executes on the MongoDB Server for inserts and updates within validation scope. It protects data even when another service writes directly without going through your Java DTO validator.

However, MongoDB `$jsonSchema` **does not support every standard JSON Schema draft keyword** identically. Check the MongoDB Server documentation for supported keywords and `bsonType` syntax.

### 11.2. `required` Checks **Presence** Only

Example:

```javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: ["nickname"],
    properties: {
      nickname: {
        bsonType: ["string", "null"]
      }
    }
  }
}
```

- `{}` → **invalid** because `nickname` is missing.
- `{nickname: null}` → **valid** because the key exists and type `null` is allowed.
- `{nickname: ""}` → **valid** on type unless `minLength` is set.
- `{nickname: 5}` → **invalid** due to wrong type.

If the property changes to `bsonType: "string"`:

- `{nickname: null}` also becomes **invalid**;
- `{nickname: "x"}` is valid;
- `{}` remains invalid due to `required`.

To make a field **optional yet non-null**, omit `nickname` from `required` and set `bsonType: "string"`.

### 11.3. Four-Contract Matrix for a Field

| Required? | Allowed type | Missing | Null | String |
| --- | --- | --- | --- | --- |
| No | `string` | Valid | Invalid | Valid |
| Yes | `string` | Invalid | Invalid | Valid |
| No | `["string","null"]` | Valid | Valid | Valid |
| Yes | `["string","null"]` | Invalid | Valid | Valid |

This is an essential test matrix for every optional or nullable field.

### 11.4. Value Constraints

```javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: ["orderCode", "amountCents"],
    properties: {
      orderCode: {
        bsonType: "string",
        minLength: 3,
        maxLength: 40,
        pattern: "^[A-Z0-9-]+$"
      },
      amountCents: {
        bsonType: ["int", "long"],
        minimum: 0
      },
      status: {
        enum: ["CREATED", "PAID", "CANCELLED"]
      }
    }
  }
}
```

Cases to test:

- Empty, too-short, and too-long strings.
- Unicode characters, whitespace, and control characters.
- `-1`, `0`, and boundary values.
- Int32/Int64/Double/Decimal128 representing the same numeric value.
- Enum valid values and wrong casing.
- Missing and null required fields.

Never test only the happy path with a single valid document.

## 12. Validators for Arrays and Nested Objects

### 12.1. Enforcing Element Shapes

```javascript
const orderValidator = {
  $jsonSchema: {
    bsonType: "object",
    required: [
      "runId",
      "orderCode",
      "amountCents",
      "lines"
    ],
    properties: {
      runId: {
        bsonType: "string",
        minLength: 1
      },
      orderCode: {
        bsonType: "string",
        minLength: 1
      },
      amountCents: {
        bsonType: ["int", "long"],
        minimum: 0
      },
      note: {
        bsonType: ["string", "null"]
      },
      tags: {
        bsonType: "array",
        uniqueItems: true,
        items: {
          bsonType: "string",
          minLength: 1
        }
      },
      lines: {
        bsonType: "array",
        minItems: 1,
        items: {
          bsonType: "object",
          required: ["sku", "quantity"],
          properties: {
            sku: {
              bsonType: "string",
              minLength: 1
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
};
```

Explanation:

- `lines` is required and must be an array.
- `minItems: 1` forbids empty arrays.
- `items` requires every element to be an object.
- Each object requires `sku` and `quantity`.
- `quantity` must be BSON Int32 and at least `1`.
- `tags` is an optional array, and when present each element must be a non-empty String with no duplicates via `uniqueItems`.
- `note` is an optional nullable string.
- Avoid `additionalProperties: false` at the root level unless you account for `_id` and all valid metadata fields: `_id` is always assigned/stored by MongoDB and can cause writes to be rejected.

### 12.2. Test Matrix for `lines`

| `lines` value | Expected | Reason |
| --- | --- | --- |
| Missing | Reject | `required` |
| `null` | Reject | Not an array |
| `[]` | Reject | `minItems: 1` |
| `"BOOK-A"` | Reject | Wrong BSON type |
| `[null]` | Reject | Element is not an object |
| `["BOOK-A"]` | Reject | Element is not an object |
| `[{}]` | Reject | Missing sku/quantity |
| `[{sku:"BOOK-A"}]` | Reject | Missing quantity |
| `[{sku:"BOOK-A",quantity:"2"}]` | Reject | Wrong quantity type |
| `[{sku:"BOOK-A",quantity:0}]` | Reject | Minimum 1 |
| `[{sku:"BOOK-A",quantity:NumberInt(1)}]` | Accept | Valid type and bound |
| `[{sku:"BOOK-A",quantity:NumberLong("1")}]` | Reject | Validator allows only `int` |
| `[{sku:"BOOK-A",quantity:NumberInt(1)}, null]` | Reject | Every element must be valid |

These are boundary test cases, not results from running code in production.

### 12.3. Empty Objects and Extra Fields

```javascript
{ profile: {} }
```

differs from:

```javascript
{ profile: null }
```

and:

```javascript
{ }
```

If `profile` is optional and the property specifies only `bsonType: "object"`:

- Missing is accepted.
- Null is rejected.
- An empty object is accepted unless inner `required` fields are declared.

To forbid unknown fields, use `additionalProperties: false` **at the right nesting level**, remembering to include `_id` and valid metadata at root level. Rejecting unknown fields too aggressively can break backward-compatible rollouts.

### 12.4. Multi-Dimensional Arrays and `items`

Schema:

```javascript
{
  properties: {
    matrix: {
      bsonType: "array",
      items: {
        bsonType: "array",
        items: {
          bsonType: "int"
        }
      }
    }
  }
}
```

Forces `matrix` to be an array of arrays of Int32. Do not write a flat `items: {bsonType: "int"}` when the shape is 2D.

If each row needs a fixed length, add `minItems`/`maxItems` at the row level. For complex cross-field business invariants, enforce them in application code or transactions rather than stuffing unmanageable logic into validators.

## 13. Validator Actions and Levels Are Not Identical

### 13.1. `validationAction`: Error vs Warn

| Action | Primary behavior |
| --- | --- |
| `error` | Rejects invalid writes; default |
| `warn` | Allows invalid writes, logging a warning to the MongoDB log |
| `errorAndLog` | Rejects invalid writes and logs the violation; from MongoDB 8.1 |

With `warn`, an invalid insert **succeeds**. If a test only asserts that no exception was thrown, it **does not prove the data conforms to the schema**.

`errorAndLog` impacts log volume and risks sensitive data exposure; use it only on supported versions with an appropriate log-handling policy.

### 13.2. `validationLevel`: Which Documents Are Validated

| Level | Behavior |
| --- | --- |
| `off` | Disables schema validation |
| `moderate` | Validates inserts and updates to existing valid documents; updates to existing invalid documents may be accepted |
| `strict` | Validates all inserts/updates; default |
| `constraint` | MongoDB 9.0+, requires all documents to conform and checks legacy docs when enabled |

**Do not confuse `strict` with “all existing data is already fixed.”** Setting a strict validator on a collection containing legacy invalid documents does not automatically scan and migrate them. However, subsequent updates to those legacy invalid documents can fail.

### 13.3. Testing `moderate` with Legacy Documents

Sequence:

1. Insert an invalid document **before adding the validator**.
2. Run `collMod` setting `validationLevel: "moderate"`, `validationAction: "error"`.
3. Update an unrelated field on the legacy invalid document.
4. Observe the update succeeds because the document was already invalid before the update.
5. Insert a new invalid document → rejected.
6. Update a currently valid document into an invalid state → rejected.
7. Switch to `strict`.
8. Update the legacy invalid document again → rejected until repaired to match the schema.

Step 4 **is not an accidental loophole**; it is `moderate` semantics designed to support gradual legacy data migration.

### 13.4. MongoDB 9.0 `constraint`

Per MongoDB 9.0 documentation:

- `constraint` requires `validationAction: "error"` or `"errorAndLog"`.
- Enabling it on an existing collection requires a preparation step via `prepareConstraintValidationLevel`.
- MongoDB checks existing documents; if any violate the schema, the upgrade fails.
- Under this level, the validator cannot be modified directly; changing it requires downgrading the validation level first per procedure.
- Bypassing document validation is restricted.

```javascript
// EXAMPLE SEQUENCE ONLY FOR MONGODB 9.0+
// Strict validator already active and data repaired.
db.runCommand({
  collMod: "orders",
  prepareConstraintValidationLevel: true
});

db.runCommand({
  collMod: "orders",
  validationLevel: "constraint",
  validationAction: "error"
});
```

Do not run these 9.0 commands on MongoDB 6/7/8 or on unaudited production collections; scanning legacy docs can consume significant resources.

### 13.5. `bypassDocumentValidation` Requires Control

Certain MongoDB CRUD commands and driver options support `bypassDocumentValidation` when the caller holds the required privilege.

Tests must distinguish:

- Normal writes are rejected by the validator.
- Bypassed writes succeed only when privileges, server version, and validation level allow.
- Production write paths must never accidentally enable bypass globally.
- `constraint` level has rules blocking bypass.

Never use bypass just to “make tests pass,” as that defeats proving the validator works.

## 14. Validators Apply to Insert, Update, and Replace

### 14.1. New Insert

```javascript
db.orders.insertOne({
  runId: "lab",
  orderCode: "ORD-1",
  amountCents: NumberInt(150),
  lines: [{ sku: "BOOK-A", quantity: NumberInt(2) }]
});
```

When matching the validator, the insert succeeds.

### 14.2. Partial Updates Can Fail Due to Invalid Legacy Documents

Legacy:

```javascript
{
  _id: "old-1",
  amountCents: "150",
  status: "PAID"
}
```

With a strict validator requiring numeric `amountCents`, the command:

```javascript
db.orders.updateOne(
  { _id: "old-1" },
  { $set: { updatedAt: new Date() } }
);
```

fails because **the post-update document still violates the validator**, even though `updatedAt` is not the invalid field.

### 14.3. Replace Drops Fields Not Re-Sent

```javascript
db.orders.replaceOne(
  { _id: "ORD-1" },
  { status: "PAID" }
);
```

If the validator requires `orderCode`, `amountCents`, and `lines`, a replacement omitting them is rejected. Never use `replaceOne` when you intend a partial update and the client holds only a subset of fields.

### 14.4. Upsert Is Subject to Validation Like Insert

```javascript
db.orders.updateOne(
  { orderCode: "ORD-NEW" },
  { $set: { status: "CREATED" } },
  { upsert: true }
);
```

When no match exists and a new document is inserted, that upserted document must satisfy the validator. A filter containing only a few fields does not guarantee the resulting document has all required fields. Test both the **matched update** and **insert via upsert** branches.

### 14.5. Relationship to Atomicity and bulkWrite

- A single-document update is applied atomically by MongoDB, never leaving a “half-updated” document when validation fails.
- Multi-document `insertMany` or `bulkWrite` can **partially succeed** before hitting a failure, depending on ordered/unordered execution.
- A validator does not turn a multi-document operation into a transaction.

Tests for bulk errors must inspect `insertedCount`/per-item errors and query actual state rather than assuming “one bad doc rolls back the entire batch.”

## 15. Validators Cannot Replace All Business Invariants

### 15.1. Cross-Document Uniqueness

`$jsonSchema` cannot by itself prevent two different documents from sharing the same `orderCode`.

A suitable unique index is needed:

```javascript
db.orders.createIndex(
  { tenantId: 1, orderCode: 1 },
  { unique: true }
);
```

When testing, account for null/missing values, normalization, collation, and sharding constraints.

### 15.2. Unique Indexes with Null and Missing

For a **standard single-field unique index**, a document missing the field and a document with `field: null` both generate a corresponding null index key. Single-field unique semantics permit at most one such null entry, so subsequent inserts fail with duplicate key.

For **compound unique indexes**, rules depend on the combination of key values; combinations containing null/missing may or may not collide. Never assume simply that “unique always allows multiple missing values” or “unique always forbids all nulls” across every index shape.

### 15.3. Sparse and Partial Unique Indexes

A **sparse unique** index omits documents missing the indexed field (per index semantics), yet documents with an explicit `null` field are still indexed and can therefore collide.

A **partial unique** index indexes only documents matching a filter:

```javascript
db.people.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: {
      email: { $type: "string" }
    }
  }
);
```

This works well when uniqueness should apply only to valid String emails. You still must:

- Design normalization/case-folding.
- Check non-string values and validators.
- Check sharded unique restrictions if using sharding.
- Test all write paths and concurrency races.
- Never use an index as a substitute for authorization/tenant scoping.

### 15.4. Business Invariants Beyond a Single Document

Rules such as “total ordered quantity must not exceed inventory” across multiple documents require atomic conditional updates or transactions where appropriate. `$jsonSchema` only describes single-document structure and values, not cross-collection invariants.

## 16. Minimal Test Case Matrix for BSON and Schema

This is an **application test matrix**, not a review rubric for this lesson.

| Group | Positive case | Negative/boundary case |
| --- | --- | --- |
| Int32 | `NumberInt(42)` | `NumberLong("42")` if schema allows only `int` |
| Int64 | `NumberLong("42")` | Double `42.0` and string `"42"` |
| Decimal128 | Exact decimal value | Float input causing rounding |
| Date | UTC BSON Date | ISO timestamp string |
| ObjectId | BSON ObjectId | 24-char hex String |
| Null | Explicit null when allowed | Null when `bsonType: "string"` |
| Missing | Optional field absent | Missing required field |
| Empty | Empty string/array when allowed | Fails `minLength`/`minItems` |
| Array membership | Matching element | Scalar confused with array |
| Array exact | Exact elements and order | Reversed order |
| `$elemMatch` | Same element satisfies all | Conditions split across two elements |
| Array items | Every element right type | One null/wrong string element |
| Array duplicate | No duplicates | Violates `uniqueItems: true` |
| Nested object | Valid nested paths | Parent missing/null/wrong type |
| Validator strict | Valid insert/update | Invalid insert/update rejected |
| Validator moderate | Updates existing invalid per semantics | New invalid insert rejected |
| Validator warn | Invalid accepted + logged | Test must not mistake for “valid” |
| Upsert | Creates doc with all required fields | Insert branch missing field |
| Replace | Valid full replacement | Replacement drops required field |
| Index | Valid uniqueness | Duplicate null/missing/tenant scope |
| Upgrade | Old + new codecs both decode | Serialization changes BSON type |

For every negative test, never assert only the exception. **Re-read the document** and verify data was not partially mutated.

## 17. Java Testing with JUnit 5 and MongoDB Sync Driver

### 17.1. Dependencies and Environment

Example Maven structure:

```xml
<dependencies>
  <dependency>
    <groupId>org.mongodb</groupId>
    <artifactId>mongodb-driver-sync</artifactId>
    <version>PINNED_VERSION</version>
  </dependency>

  <dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>PINNED_VERSION</version>
    <scope>test</scope>
  </dependency>
</dependencies>
```

Use compatible versions from your project's dependency management/BOM rather than copying placeholder versions.

Run integration tests against a **dedicated testing MongoDB Server** via an environment variable:

```text
MONGODB_TEST_URI=<URI of test MongoDB>
```

Never hardcode URIs with usernames/passwords in source code or commit them to Git. The suite should not modify server configuration, call `dropDatabase()`, or touch production data.

### 17.2. Self-Contained Integration Test Class

Example with Java 17, JUnit Jupiter, and MongoDB Java Sync Driver:

```java
import com.mongodb.MongoWriteException;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;

import org.bson.BsonDocument;
import org.bson.BsonType;
import org.bson.Document;
import org.bson.types.Decimal128;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Assumptions;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

import static com.mongodb.client.model.Filters.*;
import static org.junit.jupiter.api.Assertions.*;

class BsonContract414IT {
    private MongoClient client;
    private MongoDatabase database;
    private MongoCollection<Document> collection;
    private String collectionName;
    private String runId;

    @BeforeEach
    void setup() {
        String uri = System.getenv("MONGODB_TEST_URI");
        Assumptions.assumeTrue(
            uri != null && !uri.isBlank(),
            "Runs only when test MongoDB is configured"
        );

        client = MongoClients.create(uri);
        database = client.getDatabase("mongo_bson_row414_lab");
        runId = "row414_" +
            UUID.randomUUID().toString().replace("-", "");
        collectionName = "cases_" + runId;

        database.createCollection(collectionName);
        collection = database.getCollection(collectionName);
    }

    @AfterEach
    void cleanup() {
        try {
            if (collection != null && runId != null) {
                // Delete only records belonging to this run's runId.
                collection.deleteMany(eq("runId", runId));
                // Random namespaces can be reclaimed by a lab
                // admin job after verifying ownership.
            }
        } finally {
            if (client != null) client.close();
        }
    }

    private Document fixture(String id) {
        return new Document("_id", id)
            .append("runId", runId);
    }

    @Test
    void nullAndMissingAreDifferent() {
        collection.insertMany(List.of(
            fixture("missing"),
            fixture("null").append("value", null),
            fixture("string").append("value", "ok")
        ));

        assertEquals(2, collection.countDocuments(eq("value", null)));
        assertEquals(
            1,
            collection.countDocuments(exists("value", false))
        );
        assertEquals(
            1,
            collection.countDocuments(
                type("value", BsonType.NULL)
            )
        );

        Document missing = collection.find(
            eq("_id", "missing")
        ).first();

        Document explicitNull = collection.find(
            eq("_id", "null")
        ).first();

        assertNotNull(missing);
        assertNotNull(explicitNull);

        assertFalse(missing.containsKey("value"));
        assertTrue(explicitNull.containsKey("value"));
        assertNull(explicitNull.get("value"));
    }

    @Test
    void preservesBsonNumericTypes() {
        collection.insertOne(
            fixture("typed")
                .append("i32", 42)
                .append("i64", 42L)
                .append(
                    "price",
                    new Decimal128(new BigDecimal("12.50"))
                )
        );

        MongoCollection<BsonDocument> bsonCollection =
            database.getCollection(
                collectionName, BsonDocument.class
            );

        BsonDocument result = bsonCollection.find(
            eq("_id", "typed")
        ).first();

        assertNotNull(result);
        assertEquals(BsonType.INT32, result.get("i32").getBsonType());
        assertEquals(BsonType.INT64, result.get("i64").getBsonType());
        assertEquals(
            BsonType.DECIMAL128,
            result.get("price").getBsonType()
        );
    }

    @Test
    void elemMatchRequiresSameArrayElement() {
        collection.insertMany(List.of(
            fixture("cross").append(
                "lines",
                List.of(
                    new Document("sku", "A").append("qty", 1),
                    new Document("sku", "B").append("qty", 8)
                )
            ),
            fixture("same").append(
                "lines",
                List.of(
                    new Document("sku", "A").append("qty", 8)
                )
            )
        ));

        assertEquals(
            2,
            collection.countDocuments(
                and(
                    eq("lines.sku", "A"),
                    gte("lines.qty", 5)
                )
            )
        );

        assertEquals(
            1,
            collection.countDocuments(
                elemMatch(
                    "lines",
                    and(eq("sku", "A"), gte("qty", 5))
                )
            )
        );
    }

    @Test
    void jsonSchemaRejectsMissingAndNullRequiredString() {
        Document validator = new Document("$jsonSchema",
            new Document("bsonType", "object")
                .append("required", List.of("name"))
                .append(
                    "properties",
                    new Document("name",
                        new Document("bsonType", "string"))
                )
        );

        database.runCommand(
            new Document("collMod", collectionName)
                .append("validator", validator)
                .append("validationLevel", "strict")
                .append("validationAction", "error")
        );

        assertThrows(
            MongoWriteException.class,
            () -> collection.insertOne(fixture("missing"))
        );

        assertThrows(
            MongoWriteException.class,
            () -> collection.insertOne(
                fixture("null").append("name", null)
            )
        );

        collection.insertOne(
            fixture("valid").append("name", "An")
        );

        assertEquals(
            1,
            collection.countDocuments(eq("_id", "valid"))
        );
        assertEquals(
            0,
            collection.countDocuments(eq("_id", "missing"))
        );
    }
}
```

### 17.3. Scope of the Test Code

- Requires a real MongoDB test Server; if `MONGODB_TEST_URI` is unset, JUnit assumptions skip the tests.
- Each test uses its own randomly named collection, and every test document carries `runId`.
- `cleanup()` deletes only records matching `runId`; it **never drops the database** or touches records from other runs.
- In the BSON numeric test, Int32/Int64/Decimal128 are checked via `BsonDocument`, not JSON strings.
- If a test crashes before cleanup, the lab collection may remain; an admin job should clean namespaces by prefix/owner/retention.
- On sharded/managed deployments or without `collMod` privileges, run schema validation tests in an appropriately privileged environment.
- The validation test only covers **new inserts**; `moderate`/legacy cases require a dedicated test set.

## 18. Testing Legacy Data When a Validator Is Added Later

### 18.1. Why Not Create the Validator Before Every Fixture?

To test behavior when adding a validator to a collection that already contains invalid data, follow this order:

```text
Create collection (no validator)
          |
Insert valid document
Insert invalid legacy document
          |
Apply collMod validator
          |
Test strict vs moderate behavior
          |
Fix legacy data
          |
Verify later updates/validator state
```

Always creating the collection with the validator upfront fails to reproduce production scenarios with legacy invalid data.

### 18.2. Illustrative `mongosh` Script

```javascript
const lab = db.getSiblingDB("mongo_bson_row414_lab");
const name = "legacy_row414_" +
  new ObjectId().toHexString();

lab.createCollection(name);
const c = lab.getCollection(name);

const runId = "row414_" + new ObjectId().toHexString();

c.insertMany([
  {
    _id: "valid-" + runId,
    runId,
    name: "An"
  },
  {
    _id: "invalid-" + runId,
    runId,
    name: NumberInt(99)
  }
]);

const validator = {
  $jsonSchema: {
    bsonType: "object",
    required: ["name"],
    properties: {
      name: { bsonType: "string" }
    }
  }
};

lab.runCommand({
  collMod: name,
  validator,
  validationLevel: "moderate",
  validationAction: "error"
});
```

Attempt updating the legacy invalid document:

```javascript
c.updateOne(
  { _id: "invalid-" + runId, runId },
  { $set: { reviewed: true } }
);
```

Under `moderate`, updating a pre-existing invalid document succeeds.

Attempt inserting a new invalid document:

```javascript
try {
  c.insertOne({
    _id: "new-invalid-" + runId,
    runId,
    name: NumberInt(99)
  });
  print("UNEXPECTED: invalid new insert accepted");
} catch (e) {
  print("Expected validation error: " + e.codeName);
}
```

Then switch to `strict`:

```javascript
lab.runCommand({
  collMod: name,
  validationLevel: "strict",
  validationAction: "error"
});

try {
  c.updateOne(
    { _id: "invalid-" + runId, runId },
    { $set: { reviewedAgain: true } }
  );
  print("UNEXPECTED: strict accepted invalid document");
} catch (e) {
  print("Expected strict validation error: " + e.codeName);
}
```

Never run this script on a production collection: it intentionally inserts invalid data and executes `collMod`.

### 18.3. Fixing Legacy Data According to Business Meaning

In the lab, you know `name: 99` is invalid and can replace it with a dummy string. In production, never guess account numbers or financial values just to pass validation.

A proper migration requires:

- categorizing field/type error groups;
- identifying the source of truth;
- reading in bounded batches;
- conditional writes matching `_id` and version/old value;
- reporting conflicts and unfixable records;
- checking counts and business invariants before/after;
- enabling `strict` only after both data and writers satisfy the contract.

## 19. `mongosh` Lab with Assertions for Nulls, Arrays, and BSON

### 19.1. Preparing an Isolated Namespace

This lab runs on a test deployment, creating a fresh collection per run. Never run in `admin`, `local`, `config`, or any collection holding user data.

```javascript
const lab = db.getSiblingDB("mongo_bson_row414_lab");
const runId = "row414_" + new ObjectId().toHexString();
const collectionName = "cases_" + runId;

if (lab.getCollectionNames().includes(collectionName)) {
  throw new Error("Namespace already exists; refusing overwrite");
}

lab.createCollection(collectionName);
const c = lab.getCollection(collectionName);

printjson({
  database: lab.getName(),
  collectionName,
  runId
});
```

### 19.2. Tiny Assertions Without External Libraries

```javascript
function assertCount(description, filter, expected) {
  const actual = c.countDocuments(filter);

  if (actual !== expected) {
    throw new Error(
      description +
      ": expected=" + expected + ", actual=" + actual
    );
  }

  print("PASS: " + description + " -> " + actual);
}

function assertValue(description, actual, expected) {
  if (actual !== expected) {
    throw new Error(
      description + ": expected=" + expected +
      ", actual=" + actual
    );
  }

  print("PASS: " + description);
}
```

### 19.3. Scalar Null/Missing Tests

```javascript
c.insertMany([
  { _id: runId + "-missing", runId },
  { _id: runId + "-null", runId, value: null },
  { _id: runId + "-empty", runId, value: "" },
  { _id: runId + "-zero", runId, value: NumberInt(0) },
  { _id: runId + "-false", runId, value: false }
]);

assertCount(
  "null query includes missing",
  { runId, value: null },
  2
);

assertCount(
  "missing only",
  { runId, value: { $exists: false } },
  1
);

assertCount(
  "present including null",
  { runId, value: { $exists: true } },
  4
);

assertCount(
  "BSON null only on scalar fixture",
  { runId, value: { $type: "null" } },
  1
);

assertCount(
  "not equal null",
  { runId, value: { $ne: null } },
  3
);
```

Note: if `{value: [null]}` were added to the same collection with the same `runId`, several counts would change due to array traversal semantics. Grouping fixtures and expected results carefully is essential.

### 19.4. BSON Type Assertions via Aggregation

```javascript
const typedId = runId + "-typed";

c.insertOne({
  _id: typedId,
  runId,
  i32: NumberInt(42),
  i64: NumberLong("42"),
  dbl: NumberDouble("42"),
  dec: NumberDecimal("42.50"),
  createdAt: ISODate("2026-11-14T00:00:00Z"),
  refId: ObjectId("66a000000000000000000414")
});

const actualType = c.aggregate([
  { $match: { _id: typedId, runId } },
  {
    $project: {
      i32: { $type: "$i32" },
      i64: { $type: "$i64" },
      dbl: { $type: "$dbl" },
      dec: { $type: "$dec" },
      createdAt: { $type: "$createdAt" },
      refId: { $type: "$refId" }
    }
  }
]).toArray()[0];

assertValue("int32 type", actualType.i32, "int");
assertValue("int64 type", actualType.i64, "long");
assertValue("double type", actualType.dbl, "double");
assertValue("decimal type", actualType.dec, "decimal");
assertValue("date type", actualType.createdAt, "date");
assertValue("ObjectId type", actualType.refId, "objectId");
```

### 19.5. Basic Arrays

To avoid mixing scalar cases with array semantics, use a separate field `tags`:

```javascript
c.insertMany([
  {
    _id: runId + "-tags-a",
    runId,
    tags: ["java", "mongodb"]
  },
  {
    _id: runId + "-tags-b",
    runId,
    tags: ["mongodb", "java"]
  },
  {
    _id: runId + "-tags-c",
    runId,
    tags: ["java"]
  },
  {
    _id: runId + "-tags-empty",
    runId,
    tags: []
  }
]);

assertCount(
  "array contains java",
  { runId, tags: "java" },
  3
);

assertCount(
  "exact ordered array",
  { runId, tags: ["java", "mongodb"] },
  1
);

assertCount(
  "array $all regardless of order",
  {
    runId,
    tags: { $all: ["java", "mongodb"] }
  },
  2
);

assertCount(
  "empty array only",
  {
    runId,
    tags: { $size: 0 }
  },
  1
);
```

Other documents in the lab lack the `tags` field and therefore do not match these filters.

### 19.6. Testing Cross-Element False Positives

```javascript
c.insertMany([
  {
    _id: runId + "-cross",
    runId,
    lines: [
      { sku: "BOOK-A", qty: NumberInt(1) },
      { sku: "BOOK-B", qty: NumberInt(8) }
    ]
  },
  {
    _id: runId + "-same",
    runId,
    lines: [
      { sku: "BOOK-A", qty: NumberInt(8) }
    ]
  }
]);

assertCount(
  "dot notation may match across elements",
  {
    runId,
    "lines.sku": "BOOK-A",
    "lines.qty": { $gte: 5 }
  },
  2
);

assertCount(
  "$elemMatch uses one element",
  {
    runId,
    lines: {
      $elemMatch: {
        sku: "BOOK-A",
        qty: { $gte: 5 }
      }
    }
  },
  1
);
```

The `2` vs `1` distinction is a valuable invariant to keep in regression tests when refactoring query builders or migrating to Spring Data criteria.

### 19.7. Cleaning Up Test Records by runId

First verify:

```javascript
print("DB=" + lab.getName());
print("COLLECTION=" + c.getName());
print("RUN=" + runId);

const owned = c.find(
  { runId },
  { _id: 1, runId: 1 }
).toArray();

printjson({
  ownedCount: owned.length,
  ownedIds: owned.map(x => x._id)
});
```

Only after confirming the collection and `runId` belong to you:

```javascript
for (const item of owned) {
  c.deleteOne({
    _id: item._id,
    runId
  });
}

print("remaining=" + c.countDocuments({ runId }));
```

**Never run `deleteMany({})` or `dropDatabase()`** on a shared database. The empty test collection may remain after cleanup; reclaiming random namespaces belongs to lab administration under ownership policies.

## 20. Testing the Validator Directly in the Lab

### 20.1. Dedicated Collection with a Validator

Run only on a new namespace **confirmed not to exist yet**:

```javascript
const validatorName =
  "validated_" + runId;

if (lab.getCollectionNames().includes(validatorName)) {
  throw new Error("Validator namespace already exists");
}

lab.createCollection(validatorName, {
  validator: orderValidator,
  validationLevel: "strict",
  validationAction: "error"
});

const validated = lab.getCollection(validatorName);
```

Here `orderValidator` is the object defined in section 12.1. Since it requires `runId`, every fixture must include it.

### 20.2. Valid Case

```javascript
validated.insertOne({
  _id: runId + "-valid",
  runId,
  orderCode: "ORD-414",
  amountCents: NumberInt(10000),
  tags: ["java", "mongodb"],
  lines: [
    { sku: "BOOK-A", quantity: NumberInt(2) }
  ],
  note: null
});
```

Expected: insert succeeds.

### 20.3. Invalid Case Set

```javascript
const invalidCases = [
  {
    name: "missing-lines",
    document: {
      runId,
      orderCode: "ORD-MISSING",
      amountCents: NumberInt(100)
    }
  },
  {
    name: "null-lines",
    document: {
      runId,
      orderCode: "ORD-NULL",
      amountCents: NumberInt(100),
      lines: null
    }
  },
  {
    name: "empty-lines",
    document: {
      runId,
      orderCode: "ORD-EMPTY",
      amountCents: NumberInt(100),
      lines: []
    }
  },
  {
    name: "wrong-amount-type",
    document: {
      runId,
      orderCode: "ORD-STRING-AMOUNT",
      amountCents: "100",
      lines: [{ sku: "A", quantity: NumberInt(1) }]
    }
  },
  {
    name: "wrong-line-type",
    document: {
      runId,
      orderCode: "ORD-LONG-QTY",
      amountCents: NumberInt(100),
      lines: [{ sku: "A", quantity: NumberLong("1") }]
    }
  },
  {
    name: "duplicated-tag",
    document: {
      runId,
      orderCode: "ORD-DUP-TAGS",
      amountCents: NumberInt(100),
      tags: ["java", "java"],
      lines: [{ sku: "A", quantity: NumberInt(1) }]
    }
  },
  {
    name: "null-note-not-a-problem",
    // This case IS VALID because note is optional nullable.
    document: {
      runId,
      orderCode: "ORD-NULL-NOTE",
      amountCents: NumberInt(100),
      note: null,
      lines: [{ sku: "A", quantity: NumberInt(1) }]
    }
  }
];
```

Expected conditions must be stated explicitly:

```javascript
for (const entry of invalidCases) {
  const document = {
    _id: runId + "-" + entry.name,
    ...entry.document
  };

  const expectedAccepted =
    entry.name === "null-note-not-a-problem";

  let accepted = false;

  try {
    validated.insertOne(document);
    accepted = true;
  } catch (e) {
    if (e.code !== 121) {
      throw e;  // other errors must be investigated
    }
  }

  if (accepted !== expectedAccepted) {
    throw new Error(
      "Unexpected validator result for " + entry.name
    );
  }

  print("PASS validator case: " + entry.name);
}
```

Error code **121** is `DocumentValidationFailure` in standard MongoDB Server; across different driver/server versions, check error categories/codeNames and readback rather than relying purely on error message text that may change.

### 20.4. A Validation Error Must Not Alter an Existing Document

Test:

```javascript
const validId = runId + "-valid";

try {
  validated.updateOne(
    { _id: validId, runId },
    { $set: { amountCents: "WRONG" } }
  );
  throw new Error("Unexpected successful invalid update");
} catch (e) {
  if (e.code !== 121) throw e;
}

const after = validated.findOne({
  _id: validId,
  runId
});

if (typeof after.amountCents === "string") {
  throw new Error("Invalid update changed persisted state");
}
```

The goal is verifying **not just the error response**, but also that the document was not partially mutated. For stricter type checks, use aggregation `$type` instead of JavaScript `typeof`.

### 20.5. Cleaning Up the Validator Collection

Delete only documents belonging to `runId`:

```javascript
const ownValidatedIds = validated.find(
  { runId },
  { _id: 1 }
).toArray();

for (const item of ownValidatedIds) {
  validated.deleteOne({
    _id: item._id,
    runId
  });
}

print(
  "remainingValidated=" +
  validated.countDocuments({ runId })
);
```

**Do not drop the entire lab database** as it may hold data from other test runs. Reclaiming random collections and validators should follow a separate namespace-administration process after verification.

## 21. Writing Parameterized and Property-Based Tests

### 21.1. Parameterized Tests for Boundary Values

Instead of writing 50 near-identical methods, JUnit 5 supports:

```java
@ParameterizedTest(name = "quantity={0}")
@ValueSource(ints = {-1, 0, 1, 2, Integer.MAX_VALUE})
void quantityBoundary(int quantity) {
    boolean accepted = quantity >= 1;

    // Build a valid order, assign quantity to lines[0].
    // Insert into validator-enabled collection and compare
    // outcome with accepted; verify zero partial mutation.
}
```

This is a test **skeleton**; add the corresponding setup and validator. Use a seeded generator so failures are reproducible.

### 21.2. Property-Based Tests

From invariants, generate controlled random inputs:

- For all Int32 `quantity >= 1`, the line is valid when other fields are valid.
- For all `quantity <= 0`, the line is invalid.
- For optional String `note`, missing/null/String are allowed per schema; numbers/arrays are rejected.
- For `lines`, valid only when non-empty and every element satisfies the schema.
- For any pair of array elements, `$elemMatch` must not match when predicates span separate elements.

Generators should intentionally emit **invalid shapes**, not just random valid Strings and numbers. Always log the seed and minimal shrunk test case on failure.

### 21.3. Mutation Testing for Predicates

A strong regression test catches someone changing:

```javascript
{
  lines: {
    $elemMatch: { sku: "A", qty: { $gte: 5 } }
  }
}
```

to:

```javascript
{
  "lines.sku": "A",
  "lines.qty": { $gte: 5 }
}
```

The cross-element fixture catches this discrepancy immediately. Likewise, replacing `$unset` with `$set: null` must fail field-presence tests when the contract requires missing.

## 22. Testing with Spring Data MongoDB and Java Applications

### 22.1. Mappers Can Alter Semantics

In Spring Data MongoDB, entity mapping, converters, and repository query derivation add another processing layer:

```text
HTTP JSON
    |
Jackson DTO
    |
Spring Data MappingMongoConverter
    |
BSON / Java Driver
    |
MongoDB Server
```

Areas needing integration tests:

- `@Id`: does String → ObjectId conversion trigger per annotations/mapping?
- `BigDecimal`: stored as String or Decimal128 per converter/config?
- `Instant`/`LocalDateTime`: how are timezones/UTC handled?
- Optional fields: omitted or written as null?
- `List<T>`: do empty/null/missing stay distinct after round-trip?
- `@Field`: are persisted field names accurate?
- `@Version`: does optimistic locking preserve type/version?
- Long derived query method names: do they generate `$elemMatch` or merely dotted predicates?
- Validation errors: are they translated to the expected exception classes so the API returns proper 4xx/5xx codes?

Never infer from a Java class definition alone that BSON stores the exact same field name or type.

### 22.2. `@DataMongoTest` and Real MongoDB

Spring Boot provides the `@DataMongoTest` test slice, while environment configuration determines whether it connects to real MongoDB, an embedded/mock server, or a container. Use a test MongoDB version matching production when verifying server semantics.

A test that only mocks `MongoRepository` does not prove validators or array queries actually work. In CI, use ephemeral containers or an authorized test server with strict data isolation and teardown.

### 22.3. PATCH API Tests

An endpoint call:

```text
PATCH /profiles/123
{ "nickname": null }
```

differs from:

```text
PATCH /profiles/123
{}
```

Expected behavior depends on contract:

- Key missing in PATCH = keep unchanged.
- Key present as null = remove via `$unset` or set to null via `$set`, decided explicitly.
- Key present as String = update.
- Key present as empty String = accepted or rejected per validator.

Test end-to-end from HTTP request → DTO → Mongo update → readback. Pure repository tests miss JSON missing/null mapping.

## 23. Type Strictness and Query Correctness

### 23.1. Type Validation Cannot Be Replaced by “The Query Still Matches”

MongoDB supports numeric comparison across BSON numeric types, so this query:

```javascript
db.c.find({ amountCents: 42 });
```

can match values stored with different numeric types. That **does not guarantee the client reads it back as Long** or that a validator accepts all of them.

A thorough test checks simultaneously:

1. Does the query locate the document?
2. What is the field's BSON type?
3. Does Java mapping decode it properly?
4. Does business arithmetic preserve precision?

### 23.2. Sorting and Indexing with Mixed BSON Types

MongoDB's BSON type comparison order sorts values of different types by type group. If a field mixes Strings and Numbers, sorts and range queries yield non-numeric ordering.

Never test queries exclusively on 100% numeric records. Include fixtures like:

```javascript
[
  { amountCents: NumberInt(2) },
  { amountCents: NumberLong("10") },
  { amountCents: "100" },
  { amountCents: null }
]
```

and enforce the contract: String inputs are errors to be rejected, not something business sorting should “work around.”

### 23.3. NaN and Infinity

If a system uses `double`, test how `NaN`/`Infinity` behave across serialization, comparison, validators, and frontend JSON. Standard JSON cannot represent these values as ordinary numbers.

For money or scores requiring finite bounds, validate and normalize in both application code and BSON schemas—do not rely solely on `instanceof Double`.

### 23.4. Collation and Unicode

String equality and sorting can depend on collation. For Vietnamese text, tests should cover:

- Accented vs unaccented characters.
- Uppercase vs lowercase.
- Composed vs decomposed Unicode.
- Leading/trailing whitespace.
- Business-defined normalization before unique lookups.

Never use an ASCII-only string test to claim unique indexes and equality queries work for Unicode names, addresses, or identifiers.

## 24. Indexes Alter Performance and Certain Constraints

### 24.1. Indexes Do Not Fix Malformed Shapes

A multikey index on `tags` accelerates array queries without forcing the field to be an array. If a document has `tags: "java"`, queries may still match while violating the array contract.

Both validators and query tests are needed.

### 24.2. Missing/Null in Unique Indexes

When adding a unique index to a legacy collection, two documents with missing or null values can cause the index build to fail. This is not a bug where “MongoDB misunderstands null,” but a direct result of index key semantics.

Safe procedure:

1. Audit missing/null/duplicate entries across the actual scope.
2. Choose the business uniqueness contract.
3. Consider sparse/partial indexes where valid.
4. Migrate legacy data if necessary.
5. Build the index with sufficient capacity headroom.
6. Test concurrent inserts and duplicate key errors.

### 24.3. Partial Indexes Must Match Query Filters

Example partial index:

```javascript
db.c.createIndex(
  { email: 1 },
  {
    name: "emails_nonnull",
    partialFilterExpression: {
      email: { $type: "string" }
    }
  }
);
```

The query planner selects a partial index only when it can guarantee the index holds complete results for the query filter. A filter containing only `{email: {$exists: true}}` does not necessarily match a string partial filter.

Likewise, **query correctness** must never depend on whether an index exists; indexes optimize lookups, while data and predicates must be correct first.

## 25. Regression Tests When Upgrading MongoDB or Drivers

### 25.1. Compatibility Matrix

| Axis | Test examples |
| --- | --- |
| MongoDB Server | Current release and target upgrade release |
| FCV | Enabled features and upgrade prerequisites |
| Java Driver | Codec behavior, BSON mappings, exception types |
| Java runtime | Decimal, Date/Instant, timezone, UUID |
| Spring Data/Boot | Entity conversions, repository predicates |
| JSON library | Missing/null/empty/numeric coercion |
| Topology | Standalone test vs replica set/sharded production |
| Index/collation | Unique, partial/multikey, query plans |
| Validator version | `strict/moderate/constraint`, actions |

Never run a suite against one arbitrary MongoDB version and treat it as proof for a different production deployment.

### 25.2. Snapshots / Golden Data Can Help

Where data usage is permitted, keep controlled, versioned **anonymized fixtures**:

```text
fixtures/
  bson-types-v1.extjson
  null-missing-v1.extjson
  arrays-v1.extjson
  legacy-invalid-v1.extjson
```

These illustrate organizing test assets, not a requirement to create extra files in the current task.

Use canonical Extended JSON to preserve BSON types and parse with an appropriate BSON library. Never store real PII or credentials in repositories.

### 25.3. Differential Testing

Run the same queries and test cases across:

- Current server version.
- Target upgrade server version.
- Current driver version.
- New driver version.

Compare:

- Round-trip BSON types.
- Query result IDs.
- Validator accepted/rejected cases.
- Error codes/categories.
- Serialization of ObjectId/Decimal128/Date/UUID.
- Query execution behavior and compatibility.

When differences emerge, classify them as **breaking changes, bugs, out-of-contract data, or incomplete test fixtures** instead of blindly editing expected outputs to pass.

## 26. Running Tests Safely in CI/CD

### 26.1. Isolated Environments

Prefer:

- A pinned-version MongoDB container in CI; or
- an isolated ephemeral test database; or
- a dedicated MongoDB test cluster with separated accounts, quotas, and namespaces.

The tests in this lesson do not require `rs.initiate()`; basic schema/query tests run on a single test MongoDB Server, though applications targeting sharded clusters in production need additional sharding/index-constraint tests.

### 26.2. Pass/Fail Conditions

For each test:

1. Fixtures are constructed with **explicit BSON types**.
2. Queries/operations execute against MongoDB.
3. Assert result IDs, counts, and exceptions.
4. Read back persisted data to check value, type, and presence.
5. Delete by `runId` within the test namespace.
6. Log server/driver versions and error context on failure.

If cleanup is skipped due to a process crash, test data may linger; CI should enforce retention/teardown scoped strictly to that job's namespaces without touching other jobs' data.

### 26.3. Never Use Fixed Sleeps to “Wait for MongoDB to Settle”

Schema validation runs synchronously inside the write path. Once a write is acknowledged, results can be queried and read back under the appropriate read/write concern. Never use `Thread.sleep(5000)` to paper over eventual consistency or test races.

Tests specifically covering replica set replication and read preferences must configure appropriate consistency/majority concerns. Single-document `null`, `$elemMatch`, and validator tests can run synchronously against the lab collection's primary.

### 26.4. Responsible Failure Diagnostics

When a test fails:

- Record namespace, `runId`, server/driver versions, and test ID.
- Log masked BSON types/shapes—never log PII.
- Distinguish validation errors, duplicate keys, wrong codecs, permission failures, and network errors.
- Never enable profiler level 2 or database-wide debug logs on production.
- Never re-run tests against real customer data to “verify” when fixtures already cover the case.

## 27. Counterexamples to Include in the Regression Suite

| Anti-pattern | Risk | Test that catches it |
| --- | --- | --- |
| Treating Java `get("field") == null` as missing | Conflates missing and null | `containsKey` presence test |
| Testing only JSON number `42` | Misses Int32/Int64 mismatches | BSON type round-trip |
| Using Double for money | Rounding errors | Decimal128/long exactness test |
| Serializing Date as ISO String | Wrong type in range/sort queries | Aggregation `$type` check |
| Turning ObjectId into String | `_id` lookups fail | ObjectId vs String test |
| Using `{x: null}` to find only null | Also matches missing | Scalar null/missing fixture |
| Using `$exists: true` to find non-null | Also matches explicit null | Presence/null test |
| Using `tags: "java"` to prove `tags` is an array | Scalar strings also match | Validator array type test |
| Exact-array equality for membership | Depends on order | `$all`/contains tests |
| Dotted array predicates instead of `$elemMatch` | Cross-element false positives | Two-element regression fixture |
| `$push` instead of `$addToSet` | Duplicates accumulate | Repeated update test |
| `uniqueItems` without testing object duplicates | Duplicate/semantic issues | Array duplicate fixtures |
| Validator with only `required` | Null may still be permitted | Required + type matrix |
| Creating validator and expecting legacy docs to auto-fix | Invalid docs persist | Existing-docs test |
| Enabling `strict` before older writers migrate | Write failures | Multi-version writer tests |
| Using `warn` and assuming invalid data is blocked | Invalid docs are saved | Assert persisted data |
| BulkWrite failure assumed to roll back everything | Partial writes persist | Readback after errors |
| Unique index on optional field without auditing nulls | DuplicateKey errors | Missing/null uniqueness fixtures |
| Mapper blindly casting `Long` to `Integer` | ClassCast/overflow | Codec and boundary tests |
| Running tests on production database | Modifies/deletes real data | Isolated namespace/credentials |
| Ignoring error codes and logging only `e.message` | Hard to classify errors | Error category assertions |
| Testing on only one driver/server version | Upgrade regressions | Compatibility matrix |
| Asserting via mocked repository | Never checks server semantics | Integration tests |

## 28. Design Scenario: Profile API Supporting PATCH

An API stores:

```javascript
{
  _id: ObjectId("66a000000000000000000414"),
  displayName: "An",
  nickname: "Anh",
  channels: ["email", "sms"],
  preferences: {
    marketing: false
  }
}
```

Business rules:

1. `displayName` required, non-empty String.
2. `nickname` optional; **if present, String or Null**.
3. `channels` optional String array, no duplicates.
4. `preferences.marketing` optional Boolean.
5. PATCH omitting key = keep unchanged; PATCH `nickname: null` = set explicit null; PATCH `nickname: ""` = reject.

### 28.1. Requests to Test

```json
{}
```

Expected: document unchanged.

```json
{"nickname": null}
```

Expected: `nickname` present with BSON Null (per chosen contract).

```json
{"nickname": ""}
```

Expected: rejected; persisted `nickname` unchanged.

```json
{"channels": []}
```

Expected: valid if schema allows empty arrays.

```json
{"channels": ["email", "email"]}
```

Expected: rejected if validator specifies `uniqueItems: true`.

```json
{"preferences": {"marketing": false}}
```

Expected: `false` is preserved, not dropped by a mapper treating falsy as absent.

### 28.2. What to Verify After the API Response

- HTTP status and error mapping.
- MongoDB document after write.
- Presence of fields.
- BSON types of values.
- Whether other fields inside nested objects survived.
- Validation action/level behavior.
- No unintended partial updates.
- Whether concurrent PATCHes need versioning/optimistic locking.

This tests the **end-to-end contract**, not merely input regexes.

## 29. Self-Practice Exercises

### Exercise A — Null and Missing

Given:

```javascript
[
  { _id: 1 },
  { _id: 2, x: null },
  { _id: 3, x: "" },
  { _id: 4, x: NumberInt(0) }
]
```

Predict the matching IDs for:

1. `{x: null}`.
2. `{x: {$exists: false}}`.
3. `{x: {$exists: true}}`.
4. `{x: {$type: "null"}}`.
5. `{x: {$ne: null}}`.

Explain why SQL `IS NULL` and MongoDB equality-to-null cannot be swapped mechanically in applications.

### Exercise B — BSON Numbers

A REST API sends:

```json
{"amount": 42}
```

Requirement: MongoDB must store BSON Int64.

1. Where in the mapper/driver might Int32 be produced?
2. Write a test using `BsonDocument`.
3. Why is `find({amount: 42})` insufficient to prove the exact type?
4. If `amount` exceeds $2^{53}$, how do you prevent precision loss through JavaScript?

### Exercise C — Nullable Required

Validator:

```javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: ["comment"],
    properties: {
      comment: { bsonType: ["string", "null"] }
    }
  }
}
```

Are `{}`, `{comment: null}`, `{comment: ""}`, and `{comment: 7}` valid? Which keyword must be added to forbid empty strings?

### Exercise D — Array Equality

Given:

```javascript
[
  { tags: ["a", "b"] },
  { tags: ["b", "a"] },
  { tags: ["a"] },
  { tags: [] },
  {}
]
```

Predict the results of:

1. `{tags: "a"}`.
2. `{tags: ["a", "b"]}`.
3. `{tags: {$all: ["a", "b"]}}`.
4. `{tags: {$size: 0}}`.

### Exercise E — `$elemMatch`

```javascript
{
  lines: [
    { sku: "A", qty: 1 },
    { sku: "B", qty: 10 }
  ]
}
```

Why does:

```javascript
{"lines.sku": "A", "lines.qty": {$gte: 5}}
```

match, while:

```javascript
{lines: {$elemMatch: {sku: "A", qty: {$gte: 5}}}}
```

does not match?

### Exercise F — Arrays Containing Null

Compare:

```javascript
{}
{items: null}
{items: []}
{items: [null]}
```

Design tests distinguishing all four via presence, type, size, and readback. Explain why query predicate `$type` can behave differently from aggregation `$type` on arrays.

### Exercise G — Nested Validator

Write a `$jsonSchema` for:

```javascript
{
  lines: [
    { sku: "A", qty: NumberInt(2) }
  ]
}
```

requiring:

- `lines` required non-empty array;
- every element is an object;
- `sku` required non-empty String;
- `qty` required positive Int32.

Create at least six invalid fixtures.

### Exercise H — Legacy Migration

A collection contains:

```javascript
{ _id: 1, amountCents: "1000" }
```

The team wants to enable a validator requiring `amountCents` to be `long`.

1. Does `strict` automatically convert legacy data?
2. Which updates does `moderate` allow on the legacy document?
3. When does `strict` begin rejecting updates?
4. How do you plan a backfill with compare-and-set and idempotency?

### Exercise I — Validator Warn

A collection sets `validationAction: "warn"`, `validationLevel: "strict"`. An invalid insert succeeds.

1. Is this a bug?
2. Should tests check for an error or inspect persisted data/logs?
3. Why should `warn` not be the final production safeguard?
4. How should log volume and PII be monitored?

### Exercise J — Unique Optional Field

Two documents both lack `email`, and one has `email: null`. A single-field unique index is planned.

1. What error can occur?
2. How does a sparse unique index treat missing vs null?
3. Does a partial unique index restricted to Strings fit the business rule?
4. Why test collation and case normalization?

### Exercise K — PATCH Semantics

One PATCH request omits `nickname`, while another sends `nickname: null`.

1. Which DTO design preserves field presence?
2. Does each map to `$set` or `$unset` per contract?
3. Write two MongoDB readback tests.
4. If the validator has `required: ["nickname"]`, what happens to `$unset`?

### Exercise L — Upgrade Regression

After upgrading the MongoDB Java Driver and Spring Data versions, BSON Int64 values read back as a different type.

1. Which serialization layers must be compared?
2. Which integration test catches this bug?
3. Why is comparing JSON strings insufficient?
4. How should the MongoDB Server version be pinned in CI?

### Exercise M — Partial Bulk Write

In a batch insert of 5 documents, the third violates the schema with `ordered: true`.

1. Are all 5 guaranteed to roll back?
2. What should you read from the bulk exception/result?
3. Which data should you query after the error?
4. When is a transaction needed?

### Exercise N — Arrays and uniqueItems

An array already had duplicates before a validator was added; the application later updates only `updatedAt`.

1. Under `strict + error`, can the update succeed?
2. Under `moderate + error`, how does behavior differ?
3. Does `$addToSet` automatically clean up old duplicates?
4. How do you design an array deduplication migration without losing business meaning?

### Exercise O — Safe Testing

Design a JUnit suite for CI featuring:

- 1 random namespace per test.
- Explicit `runId`/owner.
- Tests for BSON types, null/missing, arrays, and validators.
- Cleanup in `finally`/`@AfterEach`.
- Zero production credentials.
- Failure reports logging type/query/expected/actual with no PII.

## 30. Official References

Consult documentation matching your exact deployed MongoDB Server, FCV, Java Driver, and Spring Data versions:

- [MongoDB BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/) — list of BSON types and characteristics.
- [MongoDB Java Sync Driver — BSON Data Format](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/document-data-format-bson/) — BSON in Java.
- [MongoDB Java Sync Driver — Documents](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/documents/) — `Document`, `BsonDocument`, and type mappings.
- [Query for Null or Missing Fields](https://www.mongodb.com/docs/manual/tutorial/query-for-null-fields/) — `null`, missing, and query checks.
- [`$exists`](https://www.mongodb.com/docs/manual/reference/operator/query/exists/) — field presence/absence.
- [`$type` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/type/) — matching field and array-element types.
- [`$type` Aggregation Expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/type/) — `missing` vs `null` and expression semantics.
- [Query an Array](https://www.mongodb.com/docs/manual/tutorial/query-arrays/) — scalar membership, exact array match, `$all`, and array positions.
- [Query an Array of Embedded Documents](https://www.mongodb.com/docs/manual/tutorial/query-array-of-documents/) — dot notation and `$elemMatch`.
- [`$elemMatch`](https://www.mongodb.com/docs/manual/reference/operator/query/elemMatch/) — requiring multiple predicates on one array element.
- [`$addToSet`](https://www.mongodb.com/docs/manual/reference/operator/update/addToSet/) — handling duplicates on update.
- [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — declaring rules, MongoDB JSON Schema.
- [Specify JSON Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/specify-json-schema/) — `bsonType`, `required`, `properties`, and arrays.
- [Specify Validation Level](https://www.mongodb.com/docs/manual/core/schema-validation/specify-validation-level/) — strict, moderate, and constraint (MongoDB 9.0+).
- [Handle Invalid Documents](https://www.mongodb.com/docs/manual/core/schema-validation/handle-invalid-documents/) — warn/error/errorAndLog (8.1+).
- [`collMod`](https://www.mongodb.com/docs/manual/reference/command/collMod/) — modifying validators on existing collections.
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — null/missing and multikey index semantics.
- [Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/) — predicates scoping an index.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — CRUD, BSON codecs, error handling, and compatibility.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/) — parameterized and integration tests.

**Version note:** `validationAction: "errorAndLog"` is a new feature in MongoDB 8.1; `validationLevel: "constraint"` is a MongoDB 9.0 feature. Never copy version-specific syntax or behaviors to older clusters without verifying support and FCV.

## 31. Conclusion

**Proper MongoDB testing must inspect BSON and verify data states, rather than looking solely at JSON or HTTP responses.**

- BSON `int`, `long`, `double`, `decimal`, `date`, and `objectId` have distinct semantics; tests must preserve exact types across writes and reads.
- `null` differs from **missing**. `{field: null}` typically matches both, while `$exists`, `$type`, and presence checks distinguish them.
- Arrays have distinct membership, ordering, and size semantics. When multiple conditions apply to **one element**, `$elemMatch` prevents cross-element false positives.
- `$jsonSchema` protects document shape, types, required/optional/nullable fields, and individual array elements.
- `strict`, `moderate`, and `warn/error` produce very different behaviors; adding a validator does not retroactively fix legacy data.
- JUnit 5 + Java Sync Driver integration tests should use isolated namespaces, fixtures with explicit BSON types, assertions on both results and persisted state, and cleanup by `runId`.
- During driver/server upgrades or schema changes, test suites need **boundary, legacy, null/missing, array, and negative cases** to catch regressions.

**Core principle:** a valid document is not merely one that “can be read.” It must have the **right fields, the right presence states, the right BSON types, the right array structure, and the right invariants that the application depends on**. A reliable test suite makes those rules observable, reproducible, and protected across every MongoDB change.
