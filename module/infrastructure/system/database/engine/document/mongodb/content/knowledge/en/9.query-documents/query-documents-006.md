# Checking Fields with $exists, $type, and Null Queries in MongoDB

## 1. Why Distinguish Missing Fields, Null, and Wrong Types?

MongoDB stores documents in BSON and allows documents in the same collection to have structures that are not strictly identical. One user record might store `email` as a string, another might have **email: null**, an older record might omit `email` altogether, and an inconsistent import might store `email` as a Number or an Array. These cases require different query techniques.

~~~javascript
{ _id: "u01", email: "an@example.test" }
{ _id: "u02", email: null }
{ _id: "u03" }
{ _id: "u04", email: "" }
{ _id: "u05", email: [] }
~~~

| Document | State of email | Key takeaway |
| --- | --- | --- |
| u01 | Field exists, non-empty String | Normal value present |
| u02 | Field exists, BSON Null | Null is an explicitly stored value |
| u03 | **No email field** | Missing field |
| u04 | Field exists, empty String | Neither null nor missing |
| u05 | Field exists, empty Array | Field is present, but wrong type if the app expects String |

Within **query documents**, three main techniques answer different questions:

- **$exists:** Does the field or field path exist?
- **$type:** What BSON type is the value, and is the operator evaluating the whole field or array elements?
- **Null queries:** Do we want missing fields, fields containing null, or existing fields with non-null values?

After this lesson, you will know how to use these operators to filter data, detect type mismatches, audit records before a migration, and avoid "syntactically valid query returning the wrong documents" bugs.

> Examples run in **mongosh** against a dedicated practice database **mongo_query_lab**. Special values such as empty String, NumberInt(0), Boolean false, empty Array, and BSON Null are kept distinct so comparison outcomes are clear.

## 2. Three Fundamental Field States

### 2.1. Missing Field: No Key

~~~javascript
{ _id: "a01", profile: { name: "An" } }
~~~

The document above **does not have profile.email**, even though `profile` exists. A missing field means the property path does not exist, which differs from a property explicitly stored as Null.

### 2.2. Explicit Null: Key Present, Value Is BSON Null

~~~javascript
{ _id: "a02", profile: { email: null } }
~~~

In BSON, **Null** has type code **10** and alias **"null"**. It is an actual value stored inside the document.

### 2.3. Field Present with Empty Value or Wrong Type

~~~javascript
{ flag: "" }       // Empty String
{ flag: false }    // Boolean false
{ flag: 0 }        // Number
{ flag: [] }       // Empty Array
{ flag: {} }       // Empty Object
~~~

Every example above **has the flag field**. Just because a value is falsy in JavaScript does not make MongoDB treat the field as missing.

A field may intentionally represent three business states: **not applicable** (missing), **applicable but unknown** (null), and **value provided**. When an application needs to distinguish these three meanings, it should not normalize all cases into an empty string.

## 3. Creating a Re-runnable Practice Dataset

We use the **lab_field_checks** collection containing 12 documents with `_id` from **d01** to **d12**. Every document carries **dataset: "field-checks-v1"** to scope queries and cleanup accurately.

Run the entire block below in mongosh:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_query_lab");
  const c = lab.getCollection("lab_field_checks");
  const tag = "field-checks-v1";

  // Clean up only this lesson's data; do not drop the database or collection.
  c.deleteMany({ dataset: tag });

  c.insertMany([
    {
      _id: "d01", dataset: tag,
      flag: "active",
      qty: NumberInt(3),
      profile: { email: "an@example.test" },
      tags: ["red", "blue"]
    },
    {
      _id: "d02", dataset: tag,
      flag: null,
      qty: NumberInt(0),
      profile: { email: null },
      tags: []
    },
    {
      _id: "d03", dataset: tag,
      // No flag or qty.
      profile: {},
      tags: ["legacy"]
    },
    {
      _id: "d04", dataset: tag,
      flag: "",
      qty: null
      // No profile and tags.
    },
    {
      _id: "d05", dataset: tag,
      flag: false,
      qty: NumberLong(40),
      profile: { email: "" },
      tags: ["red", null]
    },
    {
      _id: "d06", dataset: tag,
      flag: NumberInt(0),
      qty: NumberDecimal("19.25"),
      profile: { email: NumberInt(123) },
      tags: [7]
    },
    {
      _id: "d07", dataset: tag,
      flag: [],
      qty: NumberDouble(3.5),
      profile: null
    },
    {
      _id: "d08", dataset: tag,
      flag: [null],
      qty: NumberInt(8),
      profile: { email: ["support@example.test", null] },
      tags: []
    },
    {
      _id: "d09", dataset: tag,
      flag: ["active", null],
      // No qty.
      profile: { email: ["team@example.test"] },
      tags: ["blue"]
    },
    {
      _id: "d10", dataset: tag,
      flag: ["active"],
      qty: true,
      profile: { email: "hello@example.test" },
      tags: ["red"]
    },
    {
      _id: "d11", dataset: tag,
      flag: {},
      qty: NumberInt(-5),
      profile: { email: ["list@example.test"] },
      tags: []
    },
    {
      _id: "d12", dataset: tag,
      flag: "pending",
      qty: NumberInt(10),
      profile: { name: "No email yet" },
      tags: ["legacy"]
    }
  ]);

  print("Document count: " + c.countDocuments({ dataset: tag }));
})();
~~~

**Expected output:** **12 documents**. The script uses fixed IDs and cleans up by dataset tag, so re-running it in a dedicated practice environment restores the data to its initial state. Delete/insert are separate commands rather than a transaction; do not use this pattern on a production system with concurrent writes.

### 3.1. State Table for flag

| ID | flag value | Type of the whole field |
| --- | --- | --- |
| d01 | "active" | string |
| d02 | null | null |
| d03 | Missing | missing |
| d04 | "" | string |
| d05 | false | bool |
| d06 | NumberInt(0) | int |
| d07 | [] | array |
| d08 | [null] | array |
| d09 | ["active", null] | array |
| d10 | ["active"] | array |
| d11 | {} | object |
| d12 | "pending" | string |

Pay special attention to **d08–d10**: the type of the whole field is **array**, yet elements inside the array can be of type **null** or **string**. This is the source of many bugs when using **$type** in `find`.

### 3.2. Helper Function to Display Matching IDs

To keep examples concise and easy to compare, define a helper function in the mongosh session:

~~~javascript
function showMatchedIds(label, filter) {
  const c = db.getSiblingDB("mongo_query_lab")
    .getCollection("lab_field_checks");

  const ids = c.find(
      { $and: [{ dataset: "field-checks-v1" }, filter] },
      { _id: 1 }
    )
    .sort({ _id: 1 })
    .toArray()
    .map(doc => doc._id);

  print(label + ": " + JSON.stringify(ids));
  return ids;
}
~~~

The following examples call this function. If you open a new mongosh session, run the function definition again before calling it. Any filter can still be passed directly to **db.collection.find()**.

## 4. $exists: Checking Whether a Field Exists

### 4.1. $exists: true

Syntax:

~~~javascript
{ fieldName: { $exists: true } }
~~~

MongoDB returns documents containing the specified field, **even when the field's value is null, false, 0, an empty string, an empty array, or an empty object**.

~~~javascript
showMatchedIds(
  "Has flag",
  { flag: { $exists: true } }
);
~~~

**Expected output:** **d01, d02, d04, d05, d06, d07, d08, d09, d10, d11, d12** — **11** in total. Document **d02** has `flag: null` and still matches; only d03 does not match.

### 4.2. $exists: false

~~~javascript
showMatchedIds(
  "Missing flag",
  { flag: { $exists: false } }
);
~~~

**Expected output:** only **d03**. This filter does not match fields stored with Null.

Distinguish clearly:

~~~javascript
{ flag: { $exists: false } }  // No flag key.
{ flag: { $exists: true } }   // Has flag key, including null.
~~~

A common mistake is using **$exists: false** to find all fields without a business value; it does not include explicit null or empty strings.

### 4.3. Checking Nested Paths with Dot Notation

~~~javascript
showMatchedIds(
  "Has profile.email",
  { "profile.email": { $exists: true } }
);

showMatchedIds(
  "Missing profile.email",
  { "profile.email": { $exists: false } }
);
~~~

Expected results:

- **Has profile.email:** d01, d02, d05, d06, d08, d09, d10, d11.
- **Missing profile.email:** d03, d04, d07, d12.

Document d03 has `profile` as an empty object but no `email`. Document d04 lacks `profile`; d07 has `profile: null`; d12 has `profile.name` but no `profile.email`.

If you check only **profile** instead of **profile.email**:

~~~javascript
showMatchedIds(
  "No profile",
  { profile: { $exists: false } }
);
// d04.
~~~

**The parent existing does not prove the child exists.** For nested documents, check the exact path you intend to use.

### 4.4. $exists Is Not SQL EXISTS

In MongoDB, **$exists** is a query predicate on a field. It does not run a subquery and is not equivalent to SQL's **EXISTS(subquery)** operator.

~~~javascript
{ profile: { $exists: true } }
~~~

only asks whether the current collection contains the `profile` field in each document.

## 5. Querying Null: Missing Fields Can Also Match

### 5.1. Equality Filter with Null

~~~javascript
showMatchedIds(
  "flag equals null",
  { flag: null }
);
~~~

**Expected output:** **d02, d03, d08, d09**.

| ID | Reason for match |
| --- | --- |
| d02 | `flag` is present and equals BSON Null |
| d03 | No `flag` field |
| d08 | `flag` is an array containing a null element |
| d09 | `flag` is an array containing String and null |

The equality filter **{ flag: null }** matches fields whose value is Null **or missing fields**. For Array fields, scalar comparison can also match a null element inside the array.

Writing **{ flag: { $eq: null } }** expresses the same equality intent.

### 5.2. Combining Null with $exists: true

~~~javascript
showMatchedIds(
  "flag exists and equals null",
  { flag: { $exists: true, $eq: null } }
);
~~~

**Expected output:** **d02, d08, d09**. The `$exists: true` condition excludes **d03** but **does not exclude arrays containing null**.

Remember this: requiring **the field to exist and match null** is not enough to guarantee **the whole field is a scalar BSON Null**.

### 5.3. Using $type: "null"

~~~javascript
showMatchedIds(
  "flag has type Null per query predicate",
  { flag: { $type: "null" } }
);
~~~

**Expected output:** **d02, d08, d09**.

**$type: "null"** and **$type: 10** both refer to BSON Null. In `find`, `$type` also inspects **Array elements**; hence d08 and d09 match as well.

If a field is guaranteed never to be an Array, `$type: "null"` is usually sufficient to find explicit null. If data can contain Arrays, use the technique in Section 7 to inspect **the type of the whole field**.

### 5.4. Using $ne: null

~~~javascript
showMatchedIds(
  "flag is not null",
  { flag: { $ne: null } }
);
~~~

**Expected output:** **d01, d04, d05, d06, d07, d10, d11, d12** — **8** in total.

Under MongoDB query semantics, **$ne: null** finds fields that are **present and do not match null**. Arrays containing null are also excluded by scalar null comparison. Empty String, false, 0, empty Array, and empty Object still differ from null.

Do not infer that **$ne: null** means "a valid value": if business logic requires a non-empty string, d04 still fails; if business logic requires a scalar String, d05–d07 and d10–d11 also fail.

**Important difference:** For ordinary values, such as **{ flag: { $ne: "active" } }**, `$ne` can match documents missing the field. Keep in mind the special behavior documented by MongoDB for **$ne: null**.

### 5.5. Comparison Table

| flag filter condition | Meaning | Matching IDs |
| --- | --- | --- |
| **{ flag: { $exists: false } }** | Missing field | d03 |
| **{ flag: { $exists: true } }** | Field is present | All except d03 |
| **{ flag: null }** | Null, missing, or array containing null | d02, d03, d08, d09 |
| **{ flag: { $type: "null" } }** | Has null value or null array element | d02, d08, d09 |
| **{ flag: { $ne: null } }** | Field is present and not null | d01, d04–d07, d10–d12 |

Each filter above serves a different purpose. State the business requirement clearly before picking an operator.

## 6. $type: Checking BSON Types

### 6.1. Syntax

~~~javascript
{ field: { $type: "string" } }
{ field: { $type: 2 } }
{ field: { $type: ["int", "long", "decimal", "double"] } }
~~~

The first two filters both match BSON String. With an array of aliases, MongoDB matches fields belonging to **at least one listed type**; behavior when the field is an Array is covered in Section 6.3.

| BSON type | Alias | Code |
| --- | --- | ---: |
| Double | "double" | 1 |
| String | "string" | 2 |
| Object | "object" | 3 |
| Array | "array" | 4 |
| Binary | "binData" | 5 |
| ObjectId | "objectId" | 7 |
| Boolean | "bool" | 8 |
| Date | "date" | 9 |
| Null | "null" | 10 |
| Int32 | "int" | 16 |
| Int64 | "long" | 18 |
| Decimal128 | "decimal" | 19 |

The special alias **"number"** accepts the BSON numeric group: int, long, double, and decimal. It does not include Boolean or strings containing digits.

### 6.2. Practicing on the qty Field

~~~javascript
showMatchedIds(
  "qty Int32",
  { qty: { $type: "int" } }
);

showMatchedIds(
  "qty Decimal128",
  { qty: { $type: "decimal" } }
);

showMatchedIds(
  "qty in number group",
  { qty: { $type: "number" } }
);
~~~

| qty type | Matching IDs |
| --- | --- |
| int | d01, d02, d08, d11, d12 |
| long | d05 |
| double | d07 |
| decimal | d06 |
| number | d01, d02, d05, d06, d07, d08, d11, d12 |
| bool | d10 |
| null | d04 |
| missing | d03, d09 (use $exists: false or aggregation $type) |

In production schemas, **Decimal128**, **Double**, **Int32**, and **Int64** all have different storage characteristics. If a monetary field must be Decimal128, do not accept a Double value merely because the printed number looks similar.

### 6.3. Special Behavior When the Field Is an Array

The **$type operator used as a query predicate** can match when **an Array element** has the target type:

~~~javascript
showMatchedIds(
  "flag is String or Array containing String",
  { flag: { $type: "string" } }
);

showMatchedIds(
  "flag is Array",
  { flag: { $type: "array" } }
);
~~~

Results:

- **$type: "string"** → **d01, d04, d09, d10, d12**.
- **$type: "array"** → **d07, d08, d09, d10**.

**d09 and d10 are not scalar Strings**; they are Arrays containing Strings. If the schema requires `flag` to be **a String at the field level**, **{ flag: { $type: "string" } }** alone is insufficient to validate conformance.

### 6.4. $type Query Predicate vs. $type Aggregation Expression

MongoDB has **two contexts for $type**:

| Context | Example | Behavior |
| --- | --- | --- |
| Query predicate in find | **{ flag: { $type: "string" } }** | Can match an array containing a String element |
| Query predicate in find | **{ flag: { $type: "array" } }** | Matches a field of type Array |
| Aggregation expression | **{ $type: "$flag" }** | Returns the type alias of **the whole field** |
| Aggregation expression on missing field | **{ $type: "$missingField" }** | Returns the string **"missing"** |
| Aggregation expression on Array | **{ $type: "$flag" }** | Returns the string **"array"**; does not inspect elements |

Consequently, **"missing" is not a valid BSON type for the $type query predicate**. In `find`, use **$exists: false** to locate missing fields; in aggregation expressions, you can compare the result of **$type** to the string **"missing"**.

## 7. Accurately Distinguishing Scalar Null, String, and Missing

### 7.1. Using $expr and Aggregation $type in find

To check **the type of the whole field** rather than array element types, use **$expr** with the aggregation expression:

~~~javascript
showMatchedIds(
  "Scalar BSON Null only",
  { $expr: { $eq: [{ $type: "$flag" }, "null"] } }
);
// d02.

showMatchedIds(
  "Scalar BSON String only",
  { $expr: { $eq: [{ $type: "$flag" }, "string"] } }
);
// d01, d04, d12.

showMatchedIds(
  "Missing field via $type expression",
  { $expr: { $eq: [{ $type: "$flag" }, "missing"] } }
);
// d03.
~~~

For **d08/d09**, the whole-field type is **array**, so they do not match the scalar Null condition even though their arrays contain null elements. For **d09/d10**, the whole-field type is array, so they do not match scalar String even though they contain String elements.

### 7.2. Inspecting Types Per Document with Aggregation

~~~javascript
db.getSiblingDB("mongo_query_lab")
  .getCollection("lab_field_checks")
  .aggregate([
    { $match: { dataset: "field-checks-v1" } },
    {
      $project: {
        _id: 1,
        flagType: { $type: "$flag" },
        qtyType: { $type: "$qty" },
        emailType: { $type: "$profile.email" }
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray();
~~~

Notable cases:

| ID | flagType | qtyType | emailType |
| --- | --- | --- | --- |
| d01 | string | int | string |
| d02 | null | int | null |
| d03 | missing | missing | missing |
| d04 | string | null | missing |
| d06 | int | decimal | int |
| d07 | array | double | missing |
| d08 | array | int | array |
| d09 | array | missing | array |
| d10 | array | bool | string |
| d11 | object | int | array |

Aggregation **$type** is especially helpful when auditing schemas before enforcing a new standard, because it reveals the type of the whole field rather than matching elements inside an array.

### 7.3. Summarizing BSON Type Distribution

~~~javascript
db.getSiblingDB("mongo_query_lab")
  .getCollection("lab_field_checks")
  .aggregate([
    { $match: { dataset: "field-checks-v1" } },
    {
      $group: {
        _id: { $type: "$flag" },
        count: { $sum: 1 }
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray();
~~~

Result:

| Type of flag | Document count |
| --- | ---: |
| array | 4 |
| bool | 1 |
| int | 1 |
| missing | 1 |
| null | 1 |
| object | 1 |
| string | 3 |
| **Total** | **12** |

This reporting pattern answers questions like: "How many documents currently store price as String, Double, or Decimal128?" or "How many legacy documents will the new schema affect?".

### 7.4. Finding profile.email as a Non-Empty Scalar String

According to the dataset, **profile.email** in d01, d05, and d10 is a scalar String, with d05 holding an empty string. Use an aggregation expression to check simultaneously that **the type is string** and **the value is not an empty string**:

~~~javascript
db.getSiblingDB("mongo_query_lab")
  .getCollection("lab_field_checks")
  .aggregate([
    { $match: { dataset: "field-checks-v1" } },
    {
      $match: {
        $expr: {
          $and: [
            { $eq: [{ $type: "$profile.email" }, "string"] },
            { $ne: ["$profile.email", ""] }
          ]
        }
      }
    },
    { $project: { _id: 1, "profile.email": 1 } },
    { $sort: { _id: 1 } }
  ]).toArray();
~~~

**Expected output:** **d01, d10**. Here **$ne** inside **$expr** is an aggregation expression taking **an array of two expressions**; it differs from the query predicate syntax **{ field: { $ne: value } }**.

This check only confirms the field is a non-empty scalar String; **it does not guarantee the email is valid according to business policy**. Email validation requires additional constraints at the application or schema layer.

## 8. Combining Operators When Cleaning Legacy Data

### 8.1. Classifying Missing Fields Before Migration

~~~javascript
db.getSiblingDB("mongo_query_lab")
  .getCollection("lab_field_checks")
  .find(
    {
      dataset: "field-checks-v1",
      "profile.email": { $exists: false }
    },
    { _id: 1, profile: 1 }
  )
  .sort({ _id: 1 })
  .toArray();
~~~

Result: **d03, d04, d07, d12**. Analyze why the email is missing before backfilling: the user genuinely did not provide one, data entry omitted it, or the information was anonymized. Never fabricate placeholder addresses if the application will use the email to contact users.

### 8.2. Detecting Incompatible Types

Suppose the new schema requires **flag to be only a scalar String or scalar Null**, while missing is tolerated during a transition period. Use aggregation to classify types:

~~~javascript
db.getSiblingDB("mongo_query_lab")
  .getCollection("lab_field_checks")
  .aggregate([
    { $match: { dataset: "field-checks-v1" } },
    { $addFields: { flagType: { $type: "$flag" } } },
    {
      $match: {
        flagType: { $nin: ["string", "null", "missing"] }
      }
    },
    { $project: { _id: 1, flag: 1, flagType: 1 } },
    { $sort: { _id: 1 } }
  ]).toArray();
~~~

**Expected output:** d05, d06, d07, d08, d09, d10, d11. These documents contain Boolean, Number, Array, or Object. If the new schema strictly requires a String, d02 (null), d03 (missing), and d04 (empty String) must also be addressed according to business rules.

### 8.3. Replacing Null with a Verified Value

Suppose it has been verified from an authoritative business source that d02's correct status is **pending**:

~~~javascript
db.getSiblingDB("mongo_query_lab")
  .getCollection("lab_field_checks")
  .updateOne(
    {
      _id: "d02",
      dataset: "field-checks-v1",
      flag: { $type: "null" }
    },
    { $set: { flag: "pending" } }
  );
~~~

The update targets the exact `_id` and pre-update value state before modifying. However, without evidence that `flag` ought to be `pending`, **never invent a default value** just to make documents pass validation.

### 8.4. $set Null and $unset Create Two Different States

~~~javascript
const c = db.getSiblingDB("mongo_query_lab")
  .getCollection("lab_field_checks");

c.updateOne(
  { _id: "d01", dataset: "field-checks-v1" },
  { $set: { flag: null } }
);

c.updateOne(
  { _id: "d02", dataset: "field-checks-v1" },
  { $unset: { flag: "" } }
);
~~~

Afterward:

- d01 still **has `flag`** with value Null → **$exists: true**.
- d02 **no longer has the `flag` field** → **$exists: false**.
- Both match **{ flag: null }**, even though their storage semantics differ.

Re-run the seed script in Section 3 after practicing to restore the dataset to its initial state.

## 9. Special Cases to Remember

### 9.1. $exists Cannot Be Used Directly Inside $expr

In aggregation, you can filter documents with:

~~~javascript
{ $match: { flag: { $exists: false } } }
~~~

However, **$exists** is a query predicate, not an aggregation expression you can place inside **$expr** or **$project**. To check for missing inside an expression, use:

~~~javascript
{
  $eq: [
    { $type: "$flag" },
    "missing"
  ]
}
~~~

### 9.2. Array and Scalar Do Not Have the Same Meaning

Example:

~~~javascript
{ flag: "active" }
{ flag: ["active"] }
~~~

These two documents have different structures. The query **{ flag: "active" }** matches both because scalar comparison matches Array elements. If the schema contract requires a String at the field level, check the whole-field type or enforce an appropriate MongoDB **$jsonSchema**.

### 9.3. Legacy BSON Undefined Data

BSON includes a deprecated **Undefined** type. Starting in **MongoDB 8.0**, equality with `null` no longer matches BSON Undefined values as it did in older versions. Do not conflate:

- JavaScript `undefined` in application variables.
- A field that does not exist at all.
- A field storing BSON Null.
- A field storing legacy BSON Undefined data.

When inspecting a historical collection, verify the MongoDB version and actual BSON types before writing a migration. Using **undefined** as a new data value only makes conventions unpredictable.

### 9.4. BSON Numbers Require Clear Conventions

MongoDB distinguishes Int32, Int64, Double, and Decimal128. The lab's `qty` field intentionally contains all four to illustrate this. When verifying that a monetary field is strictly Decimal128, filter or validate by the exact BSON type; if incoming data is String, validate format, precision, decimal separators, and unparseable cases before converting.

### 9.5. Null Checks Do Not Replace Business Validation

An email field of type String is not necessarily a valid email address; an amount field of type Decimal128 is not necessarily a valid monetary figure; a string `status` is not necessarily in the allowed status set. **$exists** and **$type** verify structure, whereas business validation and authorization must be designed separately.

## 10. Indexes and Performance for Existence Queries

**$exists** queries commonly appear when auditing legacy documents, measuring data completeness, or supporting migrations. On large collections, performance depends on indexes, data distribution, and selectivity.

### 10.1. Sparse Indexes for Optional Fields

~~~javascript
db.getSiblingDB("mongo_query_lab")
  .getCollection("lab_field_checks")
  .createIndex(
    { "profile.email": 1 },
    { name: "ix_email_sparse_lab", sparse: true }
  );
~~~

A **sparse index** contains entries only for documents that have the indexed field, **including documents where the field is null**, and omits documents missing the field. Thus, it can help **{ "profile.email": { $exists: true } }** queries when favored by the execution plan.

Conversely, a sparse index **has no entries for documents missing the field**, so it cannot by itself return complete results for **$exists: false**. Queries needing missing documents may require a collection scan. Using **hint** to force a sparse index when querying for missing fields can return incomplete results.

### 10.2. Partial Indexes and Standard Indexes

A **partial index** stores entries only for documents matching a specified filter expression; it is useful when queries target a specific subset. However, MongoDB uses a partial index only when it can guarantee complete results for the query predicate.

A standard (non-sparse) index includes entries for both missing fields and explicit null values in its index key representation, so the query engine may still need to fetch documents (**FETCH**) to distinguish them. Do not assume every **$exists: true/false** condition can be resolved solely from an index.

### 10.3. Inspecting explain

~~~javascript
db.getSiblingDB("mongo_query_lab")
  .getCollection("lab_field_checks")
  .find({
    dataset: "field-checks-v1",
    "profile.email": { $exists: true }
  })
  .explain("executionStats");
~~~

Examine **winningPlan**, **totalKeysExamined**, **totalDocsExamined**, and **nReturned**. With 12 documents, MongoDB may choose **COLLSCAN** even if an index exists; that alone does not prove the index is wrong. Evaluate on representative workloads and data sizes, including index maintenance overhead on writes.

## 11. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| **{ field: null }** also returns documents without the field | Null equality matches null or missing | Use `$exists: false` for missing, or `$type` expression for scalar Null |
| **$exists: true** returns null, 0, false, "" | `$exists` checks only key presence | Add type and value conditions |
| **$type: "string"** returns documents with an Array | Query `$type` can match Array elements | Use `$expr` + aggregation `$type` for scalar String |
| **$type: "null"** returns Arrays containing null | The Array contains a BSON Null element | Use aggregation `$type` to inspect the whole field |
| **$ne: null** returns empty String or 0 | Empty String/0 are not BSON Null | Add business validation |
| Querying `profile.email` returns unexpected results | Parent may exist while child is missing | Check `profile` and `profile.email` separately |
| **$type: "missing"** in `find` raises an error | `"missing"` is not a query BSON type | Use `$exists: false` or aggregation `$type` |
| Using `$exists` inside `$expr` raises an error | `$exists` is not an aggregation expression | Use `{ $type: "$field" }` to detect `"missing"` |
| Price/score stored as both String and Decimal128 | Writers did not enforce consistent BSON types | Audit types, plan a migration, and add schema validation |
| Sparse index does not help find missing fields | Index omits documents lacking the field | Inspect `explain` and choose an appropriate access pattern/index |
| Result IDs differ from examples | Data was modified or connected to wrong database | Re-run seed and verify database, collection, and dataset |

## 12. Practice Exercises

### Exercise 1 — Distinguishing Missing Fields and Null

Write queries to find: documents missing `flag`; documents having `flag`; documents where `flag` is scalar Null; documents where `flag` has a type other than null; documents where `flag` equals an empty Array. Record the `_id` sets and explain why **d02** differs from **d03**.

### Exercise 2 — Predicting Four Queries

Run:

~~~javascript
showMatchedIds("A", { flag: null });
showMatchedIds("B", { flag: { $exists: false } });
showMatchedIds("C", { flag: { $type: "null" } });
showMatchedIds("D", { flag: { $ne: null } });
~~~

Explain why d08/d09 match A/C but not B/D, and why d03 matches A/B.

### Exercise 3 — Checking Numeric Types

Find each group of documents where `qty` is **Int32**, **Int64**, **Double**, **Decimal128**, **Boolean**, **Null**, or **missing**. Use the **"number"** alias and compare against the total count of numeric documents. Why does d10 have `qty = true` yet is not counted as a number?

### Exercise 4 — Querying Embedded Documents

Write queries to find: documents without `profile`; with `profile` but without `profile.email`; `profile.email` as scalar String; `profile.email` as non-empty scalar String; `profile.email` as scalar Null; `profile.email` as Array. Compare the **$type query predicate** against **$type aggregation** on the `email` field.

### Exercise 5 — Changing Semantics via Updates

Use **$set: { flag: null }** on d01 and **$unset: { flag: "" }** on d02. Use **$exists**, **{ flag: null }**, and **$type** to observe the difference. Re-run the seed script before the next exercise.

### Exercise 6 — Planning a Fix for Mistyped Data

Suppose the requirement is **qty must be a non-negative Int32**. Tabulate the current documents that fall into missing, null, wrong type, or negative number categories. Specify which cases can be converted safely with proper justification and which must be retrieved from the business source of truth. Never cast Double/Decimal128 to Int32 arbitrarily and lose decimal precision.

### Exercise 7 — Performance Analysis

Create a sparse index on `profile.email` and run **explain("executionStats")** for **$exists: true** and **$exists: false**. Explain why an index containing only documents that have the field cannot replace scanning documents that lack the field.

## 13. Official References

- MongoDB Manual — [Query for Null or Missing Fields](https://www.mongodb.com/docs/manual/tutorial/query-for-null-fields/).
- MongoDB Manual — [$exists Query Predicate](https://www.mongodb.com/docs/manual/reference/operator/query/exists/).
- MongoDB Manual — [$type Query Predicate](https://www.mongodb.com/docs/manual/reference/operator/query/type/).
- MongoDB Manual — [$type Aggregation Expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/type/).
- MongoDB Manual — [BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/).
- MongoDB Manual — [Sparse Indexes](https://www.mongodb.com/docs/manual/core/index-sparse/).
- MongoDB Manual — [Migrate Undefined Data and Queries](https://www.mongodb.com/docs/manual/reference/bson-types/migrate-undefined/).

The core principle when inspecting a field is **stating explicitly whether you are checking existence, null, BSON type, or business validity**. **$exists** checks key presence; **query `$type`** can match elements inside arrays; **aggregation `$type`** reports the type of the whole value and the **"missing"** label; and **{ field: null }** can match missing fields or arrays containing null. Choosing the right query makes reading, updating, and migrating MongoDB data safer and more consistent.
