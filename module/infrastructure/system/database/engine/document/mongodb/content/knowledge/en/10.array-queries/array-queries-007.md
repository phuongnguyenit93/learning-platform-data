# Empty Arrays, `null` Elements, and Non-Existent Fields in MongoDB

When querying arrays in MongoDB, three situations that look similar on the surface carry very different data meanings: **an empty array `[]`**, **an array containing a `null` element**, and **a non-existent field**. There are also cases where the field exists with value `null`, or was mistakenly stored as a single scalar value instead of an array. Ignoring these distinctions can cause filters to return unexpected documents, miss records, or lead the application to misinterpret state.

For example, a system stores an article's list of tags:

```javascript
{ _id: "a", tags: [] }               // Field present, array type, no tags yet
{ _id: "b", tags: [null] }           // Array consisting of one null element
{ _id: "c", tags: ["mongo", null] }  // Has a tag and a null element
{ _id: "d", tags: null }             // Field present, but entire value is null
{ _id: "e" }                         // No tags field
```

These are **five distinct BSON document states**. This lesson progresses from a practice dataset to `$size`, `$exists`, `$type`, `$elemMatch`, and `null` comparisons, then to arrays of objects, aggregation, and the Java MongoDB Driver.

## 1. Distinguishing Structures Before Writing Queries

A field in MongoDB can take multiple BSON types. Specifically, `null` is a **BSON value**; the absence of a field is a property of document structure, not a `null` value.

| Storage Form | Does Field Exist? | Field Type | Array Length | Possible Meaning |
| --- | --- | --- | --- | --- |
| `{ tags: [] }` | Yes | Array | 0 | List initialized, no elements yet |
| `{ tags: [null] }` | Yes | Array | 1 | One slot holds an undefined/null value |
| `{ tags: ["mongo", null] }` | Yes | Array | 2 | One valued element and one `null` element |
| `{ tags: null }` | Yes | Null | N/A | The entire field has no defined value yet |
| `{ /* no tags */ }` | No | Missing | N/A | Field has never been written to the document |
| `{ tags: "mongo" }` | Yes | String | N/A | Field was stored as a single scalar value |
| `{ tags: [[]] }` | Yes | Array | 1 | Array containing one element that is itself an empty array |

Do not equate `[]` with `[null]`: the first array has **0 elements**, while the second has **1 element**. Likewise, do not equate `null` with a missing field: a document with `tags: null` still has the `tags` key.

From a business perspective, define these states clearly. For instance, a recipient list `[]` may mean “confirmed no recipients”, whereas a missing field may mean “data not yet synced”. MongoDB does not know these conventions automatically; the application and schema designer must agree consistently.

## 2. Creating Sample Data to Observe Exact Results

In `mongosh`, use a dedicated database for practice:

```javascript
use mongo_array_lab
```

Insert the documents:

```javascript
db.arrayCases.insertMany([
  {
    _id: "a",
    name: "Empty array",
    tags: []
  },
  {
    _id: "b",
    name: "Array containing null",
    tags: [null]
  },
  {
    _id: "c",
    name: "Array containing string and null",
    tags: ["mongo", null]
  },
  {
    _id: "d",
    name: "Field with null value",
    tags: null
  },
  {
    _id: "e",
    name: "Missing tags field"
  },
  {
    _id: "f",
    name: "Array containing string",
    tags: ["mongo"]
  },
  {
    _id: "g",
    name: "Array containing an empty array",
    tags: [[]]
  },
  {
    _id: "h",
    name: "tags field is a string",
    tags: "mongo"
  },
  {
    _id: "i",
    name: "Array containing objects",
    tags: [
      { label: null },
      { label: "index" }
    ]
  }
])
```

Queries in the following sections assume the data **has not been modified**. To read results cleanly in a deterministic order, add projection and sort:

```javascript
db.arrayCases.find(
  { tags: { $exists: true } },
  { _id: 1, name: 1, tags: 1 }
).sort({ _id: 1 })
```

Run `insertMany` only once on an empty collection; fixed `_id` values will trigger a duplicate key error if inserted repeatedly. Later data-modification examples use separate commands and will mutate the dataset when executed.

## 3. Finding Truly Empty Arrays with `$size: 0`

When you need documents where `tags` is **an array with zero elements**, use:

```javascript
db.arrayCases.find({
  tags: { $size: 0 }
})
```

On the sample dataset, this query matches **only `a`**.

`$size` matches the element count of the array at the queried field. It does not treat `null`, missing fields, or strings as length-0 arrays.

| Document | `tags` Value | Matches `$size: 0`? |
| --- | --- | --- |
| `a` | `[]` | Yes |
| `b` | `[null]` | No, has one element |
| `c` | `["mongo", null]` | No, has two elements |
| `d` | `null` | No, not an array |
| `e` | Does not exist | No |
| `f` | `["mongo"]` | No |
| `g` | `[[]]` | No, outer array has one element |
| `h` | `"mongo"` | No, not an array |
| `i` | Two objects | No |

You can find arrays with exactly one element:

```javascript
db.arrayCases.find({
  tags: { $size: 1 }
})
```

On the sample data, the result is **`b`, `f`, `g`**. The query does not distinguish whether that element is `null`, a string, or another array; it only checks the **outermost array size**.

### Why Isn't `{ tags: [] }` Completely Identical to `$size: 0`?

MongoDB supports **array equality**:

```javascript
db.arrayCases.find({
  tags: []
})
```

One point to watch when arrays can be nested: an equality condition with an array value can match the **whole array**, or match when the field contains **an element that is an array equal to the specified value**. In the sample data, `tags: []` matches the document with `tags: []` and can also match the document `tags: [[]]` because the inner element is `[]`.

Therefore, when the requirement is **field `tags` must be an array with exactly 0 elements at the outer level**, `{ tags: { $size: 0 } }` expresses it most clearly. `{ tags: [] }` should be read according to MongoDB's array equality semantics, especially when data contains nested arrays.

Do not use `$all: []` to find empty arrays:

```javascript
db.arrayCases.find({
  tags: { $all: [] }
})
```

`$all` requires the field to contain **all** elements in the query list; with an empty argument, this operator **does not act as an empty-array finder** and does not return results like `$size: 0`.

## 4. Finding Non-Existent Fields with `$exists: false`

To find documents completely **lacking the `tags` key**:

```javascript
db.arrayCases.find({
  tags: { $exists: false }
})
```

Result on the sample dataset: **only `e`**.

To find every document that **has the `tags` key**, regardless of its value:

```javascript
db.arrayCases.find({
  tags: { $exists: true }
})
```

Results include **`a`, `b`, `c`, `d`, `f`, `g`, `h`, `i`**. `$exists: true` still matches `tags: null` and `tags: []`: the field is present, even though its value is null or an empty array.

In practice:

- `$exists: false` is useful when looking for legacy records that have not yet received a field or uninitialized data sections.
- `$exists: true` confirms only **presence**, not data type or element count.
- To check whether the field is an array, add a BSON type condition with `$type`.

Example accepting only documents where `tags` is an array:

```javascript
db.arrayCases.find({
  tags: { $type: "array" }
})
```

Results: **`a`, `b`, `c`, `f`, `g`, `i`**. Documents `d` (null), `e` (missing), and `h` (string) do not match.

## 5. Comparisons with `null`: Why Do They Often Yield Broad Results?

The query:

```javascript
db.arrayCases.find({
  tags: null
})
```

**Should not be read** as “the `tags` field exists and has BSON type Null”. An equality condition with `null` can match documents where the field is **absent**. When the field is an array, MongoDB can also match an array containing a `null` element.

On the sample data, relevant cases include:

| Document | `tags` Value | `{ tags: null }` |
| --- | --- | --- |
| `b` | `[null]` | Matches due to null element |
| `c` | `["mongo", null]` | Matches due to null element |
| `d` | `null` | Matches because whole field equals null |
| `e` | Missing field | Matches due to null equality rule |
| `a` | `[]` | Does not match |
| `f` | `["mongo"]` | Does not match |

This creates a common reasoning pitfall: a `{ tags: null }` query returns documents **without the field**, **with a null field**, and **with an array containing null**, whereas business logic may need to distinguish those three completely different states.

Writing it explicitly with `$eq` preserves the same equality semantics:

```javascript
db.arrayCases.find({
  tags: { $eq: null }
})
```

To find only **missing fields**, use `$exists: false` as in the previous section. To find only arrays containing a null element, use `$elemMatch` as in Section 7. To pinpoint the **direct type of the field itself** as Null, see the `$expr` technique in Section 6.

### Why Must `$in: [null]` Also Be Read Carefully?

```javascript
db.arrayCases.find({
  tags: { $in: [null] }
})
```

`$in` checks against the specified values, and for arrays can check each element. When the list contains `null`, it can match null or missing-field cases per the corresponding comparison rules. Hence `$in: [null]` is also not an accurate way to isolate empty arrays, null fields, and absent fields.

## 6. Distinguishing Direct Null Type from an Array Containing Null

The `$type` query operator is commonly used as follows:

```javascript
db.arrayCases.find({
  tags: { $type: "null" }
})
```

For array-valued fields, the `$type` query operator can match the **type of array elements**. Thus the filter above matches **`b`, `c`, `d`** in the sample data: the first two documents contain a null element, and the last has a direct null field. It does not match `e` because the field does not exist.

If the goal is to check the **BSON type of the field itself**, even when that field is an array, use the `$type` aggregation operator inside `$expr`:

```javascript
db.arrayCases.find({
  $expr: {
    $eq: [
      { $type: "$tags" },
      "null"
    ]
  }
})
```

This query matches **only `d`**, because:

- For `tags: null`, aggregation `$type` returns the string `"null"`.
- For `tags: [null]`, aggregation `$type` returns `"array"`, because the type of the **whole field** is array.
- When `tags` does not exist, aggregation `$type` returns `"missing"`.

You can similarly check for missing fields:

```javascript
db.arrayCases.find({
  $expr: {
    $eq: [
      { $type: "$tags" },
      "missing"
    ]
  }
})
```

This filter matches `e`. For a simple missing-field check, `{ tags: { $exists: false } }` is more concise and generally preferred.

### Remember to Distinguish the Two Contexts of `$type`

```javascript
// Query operator: can inspect array element types
{ tags: { $type: "null" } }

// Aggregation expression: inspects the type of the "$tags" expression as a single value
{
  $expr: {
    $eq: [{ $type: "$tags" }, "null"]
  }
}
```

Same `$type` name, yet **different usage positions** lead to different evaluation rules. This distinction is especially useful when separating null fields from arrays containing null.

## 7. Finding `null` Elements Inside an Array with `$elemMatch`

When the goal is “the `tags` field must be an array and **have at least one element equal to null**”, use:

```javascript
db.arrayCases.find({
  tags: {
    $elemMatch: {
      $eq: null
    }
  }
})
```

Results: **`b` and `c`**.

`$elemMatch` requires at least one element of an **array** to satisfy the inner condition. It does not treat `tags: null` as an array, nor does it treat a missing field as an array. Hence `d` and `e` do not match.

You can use a type condition inside:

```javascript
db.arrayCases.find({
  tags: {
    $elemMatch: {
      $type: "null"
    }
  }
})
```

This query likewise targets arrays containing a direct null element. With nested arrays, pay close attention to which element level is being evaluated; an element that is the **array `[null]`** is not the same as a direct **`null`** element.

### Array with Exactly One Null Element

If the requirement is that the outer array has **exactly one element and that element is null**, combine two conditions:

```javascript
db.arrayCases.find({
  $and: [
    { tags: { $size: 1 } },
    { tags: { $elemMatch: { $eq: null } } }
  ]
})
```

On the sample data, the result is **`b`**. `$size: 1` guarantees the element count, while `$elemMatch` guarantees that element is null. This combination avoids falsely matching `["mongo", null]`, which has two elements.

To find an array containing only strings and no nulls, the query must specify the exact business constraints. If you want to protect data types on write, configure schema validation for array elements instead of relying solely on a read filter.

## 8. Reference Table of Common Filters

Assuming the unmodified Section 2 sample values:

| Filter | Purpose | Matching IDs |
| --- | --- | --- |
| `{tags: {$size: 0}}` | Empty array at field level | `a` |
| `{tags: {$size: 1}}` | Array with one element | `b, f, g` |
| `{tags: {$exists: false}}` | Missing `tags` field | `e` |
| `{tags: {$exists: true}}` | Has `tags` field, regardless of value | `a, b, c, d, f, g, h, i` |
| `{tags: {$type: "array"}}` | Field has array type | `a, b, c, f, g, i` |
| `{tags: null}` | Equality with null; can include missing fields or arrays containing null | `b, c, d, e` |
| `{tags: {$type: "null"}}` | Direct null or null element in an array | `b, c, d` |
| `{tags: {$elemMatch: {$eq: null}}}` | Array containing a null element | `b, c` |
| `{$expr: {$eq: [{$type: "$tags"}, "null"]}}` | Field itself is BSON Null | `d` |
| `{$expr: {$eq: [{$type: "$tags"}, "missing"]}}` | Missing field via aggregation `$type` | `e` |

To view just IDs instead of printing long documents:

```javascript
db.arrayCases.find(
  { tags: { $size: 0 } },
  { _id: 1 }
).sort({ _id: 1 })
```

Reading filter outputs should stay grounded in **BSON types and array structure**, not how values are displayed in a UI.

## 9. Object Arrays: `null` Subfields and Missing Subfields

Arrays of objects are common in orders, forms, answer lists, or user profiles. Example:

```javascript
db.forms.insertMany([
  {
    _id: "form-1",
    answers: [
      { question: "Q1", value: null },
      { question: "Q2", value: "yes" }
    ]
  },
  {
    _id: "form-2",
    answers: [
      { question: "Q1" }
    ]
  },
  {
    _id: "form-3",
    answers: []
  },
  {
    _id: "form-4",
    answers: null
  },
  {
    _id: "form-5"
  }
])
```

Here you must distinguish whether the **`answers` field** exists, whether the **`answers` array** is empty, and whether the **`value` field inside each object** is null.

### 9.1. Has an Object Whose `value` Field Is BSON Null

```javascript
db.forms.find({
  answers: {
    $elemMatch: {
      value: { $type: "null" }
    }
  }
})
```

This query matches **`form-1`**. `$elemMatch` ensures an object element exists in the array; `$type: "null"` requires `value` to have type Null, not simply be a missing field.

### 9.2. Has an Object Missing the `value` Field

```javascript
db.forms.find({
  answers: {
    $elemMatch: {
      value: { $exists: false }
    }
  }
})
```

The result is **`form-2`**. This queries for **an object element missing a subfield**, which differs from finding documents missing the entire `answers` array.

### 9.3. Empty `answers` Array

```javascript
db.forms.find({
  answers: { $size: 0 }
})
```

The result is **`form-3`**.

### 9.4. Non-Existent `answers` Field

```javascript
db.forms.find({
  answers: { $exists: false }
})
```

The result is **`form-5`**.

### Why Is `$elemMatch` Needed in This Example?

If you write `"answers.value": null`, null equality rules and array traversal can return broader results than “there exists an object with a `value` field of type BSON Null”. When a requirement concerns **an element of an object array**, express the condition inside `$elemMatch` and check `$type` or `$exists` on the subfield.

Similarly, when multiple conditions must hold simultaneously on the **same object**:

```javascript
db.forms.find({
  answers: {
    $elemMatch: {
      question: "Q1",
      value: { $type: "null" }
    }
  }
})
```

Both `question` and `value` apply to **one answer**. If written as two separate dot paths, each condition could match across two different elements.

## 10. Aggregation: Normalizing Values for Read Purposes

Many applications want lists rendered as arrays in JSON responses. MongoDB provides aggregation to normalize null or missing fields into empty arrays **in query results**.

Example using `$ifNull`:

```javascript
db.arrayCases.aggregate([
  {
    $project: {
      name: 1,
      normalizedTags: {
        $ifNull: ["$tags", []]
      }
    }
  },
  { $sort: { _id: 1 } }
])
```

Here:

- `tags: null` is represented as `normalizedTags: []`.
- A missing `tags` field is also represented as `normalizedTags: []`.
- `tags: []` remains `[]`.
- `tags: [null]` stays `[null]`; **the null element is not removed**.
- `tags: "mongo"` stays the string `"mongo"`, because `$ifNull` only handles null/missing and does not coerce arbitrary types into arrays.

**Important point:** this is an **output transformation**, not an update to stored documents. It can fit when an API always wants `[]` for both “no list” states, though the application must consider whether merging null and missing discards important business information.

### Normalizing Only When the Field Is Actually an Array

If source data also contains strings, booleans, or objects in a field that should be an array, check type with `$isArray`:

```javascript
db.arrayCases.aggregate([
  {
    $project: {
      name: 1,
      normalizedTags: {
        $cond: {
          if: { $isArray: "$tags" },
          then: "$tags",
          else: []
        }
      }
    }
  }
])
```

This turns every non-array value into `[]` in the response, including mistyped strings. Use it only when that display policy is agreed upon; do **not** silently hide schema bugs without monitoring or a data cleanup plan.

### `$unwind` with Empty Arrays and Null

`$unwind` splits a document with an array into multiple documents, one per element. By default, empty arrays, null fields, and missing fields emit no output documents:

```javascript
db.arrayCases.aggregate([
  { $unwind: "$tags" },
  { $project: { name: 1, tags: 1 } }
])
```

An array `[null]` has **one element**, so it can emit an unwound result with `tags: null`. That differs from `[]`, which has no elements to unwind.

To retain documents with empty arrays, null, or missing fields:

```javascript
db.arrayCases.aggregate([
  {
    $unwind: {
      path: "$tags",
      preserveNullAndEmptyArrays: true
    }
  }
])
```

`preserveNullAndEmptyArrays: true` retains the input document when there are no elements to unwind, though the post-unwind field shape can vary depending on whether the source was an empty array, null, or missing field. When downstream stages need to distinguish those states, preserve or compute a status field before `$unwind`.

## 11. Safely Computing Array Size in Aggregation

The `$size: 0` query operator in Section 3 is used directly in `find()`. In aggregation, `$size` is an **expression** used to compute array length:

```javascript
db.arrayCases.aggregate([
  {
    $project: {
      name: 1,
      tagCount: {
        $cond: {
          if: { $isArray: "$tags" },
          then: { $size: "$tags" },
          else: null
        }
      }
    }
  }
])
```

In this pipeline:

- `a` has `tagCount: 0`.
- `b`, `f`, `g` have `tagCount: 1`.
- `c`, `i` have `tagCount: 2`.
- `d`, `e`, `h` have `tagCount: null` because they are not arrays.

Writing `{ $size: "$tags" }` directly when `tags` might be null, missing, or a string can cause the aggregation `$size` expression to error on a non-array value. Therefore, `$cond` combined with `$isArray` is safer on heterogeneous data.

To find documents with empty arrays via `$expr`, you can write:

```javascript
db.arrayCases.find({
  $expr: {
    $cond: {
      if: { $isArray: "$tags" },
      then: { $eq: [{ $size: "$tags" }, 0] },
      else: false
    }
  }
})
```

This filter matches only when the field is genuinely an array of length 0. For this simple requirement, **`{ tags: { $size: 0 } }`** is usually easier to read.

## 12. Updates: Setting an Empty Array vs. Removing a Field vs. Setting Null

The following three update operations produce different data states:

### 12.1. Setting an Empty Array

```javascript
db.arrayCases.updateOne(
  { _id: "f" },
  { $set: { tags: [] } }
)
```

After running, document `f` **still has the `tags` field**, and `tags` is a 0-element array. Filters `$exists: true`, `$type: "array"`, and `$size: 0` all match.

### 12.2. Setting Null

```javascript
db.arrayCases.updateOne(
  { _id: "f" },
  { $set: { tags: null } }
)
```

Afterward `tags` exists with BSON type Null. `$exists: true` still matches, while `$size: 0` and `$type: "array"` do not.

### 12.3. Unsetting the Field

```javascript
db.arrayCases.updateOne(
  { _id: "f" },
  { $unset: { tags: "" } }
)
```

Afterward the `tags` field **no longer exists**; `$exists: false` is the matching filter.

The commands above modify `f` sequentially; if all three are run, the final state is **field removed**. To inspect each state, read the document after each command with:

```javascript
db.arrayCases.findOne({ _id: "f" })
```

### Appending a Null Element with `$push`

```javascript
db.arrayCases.updateOne(
  { _id: "a" },
  { $push: { tags: null } }
)
```

Starting from `tags: []`, this produces `tags: [null]`; array length increases from 0 to 1. If the field is missing, `$push` can create a new array; however, if the field holds `null` or a non-array scalar, `$push` will fail because you cannot push onto a non-array value. This shows that “null/missing/[]” cannot be treated as interchangeable in update logic.

## 13. Equivalent Queries in the Java MongoDB Sync Driver

In a Java application, you can use `Filters` to build filters equivalent to `mongosh`. Example:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import org.bson.Document;

public class ArrayEdgeCaseQuery {

    private static void printIds(
            String title,
            MongoCollection<Document> collection,
            org.bson.conversions.Bson filter) {
        System.out.println(title);
        for (Document item : collection.find(filter)
                .projection(new Document("_id", 1))
                .sort(new Document("_id", 1))) {
            System.out.println(item.getString("_id"));
        }
    }

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Missing environment variable MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("mongo_array_lab");
            MongoCollection<Document> cases =
                db.getCollection("arrayCases");

            // tags is an array with exactly 0 elements
            printIds("Empty array", cases, Filters.size("tags", 0));

            // Document missing the tags field
            printIds("Missing tags", cases, Filters.exists("tags", false));

            // Equality with null can match both missing and arrays containing null
            printIds("Null equality", cases, Filters.eq("tags", null));

            // Direct null element inside the array
            Document arrayContainsNull = new Document(
                "tags",
                new Document("$elemMatch", new Document("$eq", null))
            );
            printIds("Array containing null", cases, arrayContainsNull);

            // BSON type of the entire tags field is Null
            Document directNull = Document.parse(
                "{ \"$expr\": { \"$eq\": [ { \"$type\": \"$tags\" }, \"null\" ] } }"
            );
            printIds("Direct null field", cases, directNull);
        }
    }
}
```

This example uses the MongoDB Java Sync Driver with a compatible `mongodb-driver-sync` dependency. It reads the `arrayCases` collection created in the lab and retrieves the URI from an environment variable to avoid hardcoding credentials in source code.

Key helpers:

| Java Driver | Equivalent Meaning in `mongosh` |
| --- | --- |
| `Filters.size("tags", 0)` | `{tags: {$size: 0}}` |
| `Filters.exists("tags", false)` | `{tags: {$exists: false}}` |
| `Filters.eq("tags", null)` | `{tags: null}` |
| `new Document("tags", new Document("$elemMatch", ...))` | Condition on a single array element |
| `Document.parse(... $expr ...)` | Direct BSON type comparison via aggregation expression |

These queries do not mutate data. When communicating over a JSON API, keep a clear boundary between a field omitted from the payload, a `null` field, and `[]`, since serializers or mapping layers can collapse them at the application layer if not configured carefully.

## 14. Schema Design to Reduce Ambiguous States

MongoDB permits flexible documents without a validator, yet a production collection can define a clear contract for `tags`. For instance, `tags` is optional; if present, it must be an **array of strings**, which may be empty:

```javascript
db.createCollection("articles", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      properties: {
        tags: {
          bsonType: "array",
          items: {
            bsonType: "string"
          }
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
})
```

With this validator:

- `{ title: "Article without tags" }` is valid because `tags` is not in `required`.
- `{ tags: [] }` is valid.
- `{ tags: ["mongodb", "java"] }` is valid.
- `{ tags: [null] }`, `{ tags: null }`, and `{ tags: "mongodb" }` are invalid because they violate the declared schema.

If business logic wants the **field to always exist**, add:

```javascript
required: ["tags"]
```

at the object schema level. Then missing fields are no longer accepted, while `[]` remains valid. If the array must have **at least one element**, add `minItems: 1` to the `tags` schema:

```javascript
tags: {
  bsonType: "array",
  minItems: 1,
  items: { bsonType: "string" }
}
```

Do not apply `minItems: 1` if an empty array is a legitimate business state, such as an article not yet tagged.

When an existing collection already holds mistyped data, adding a validator via `collMod` **does not automatically fix old documents**. Decide on a migration strategy, `validationLevel`, and `validationAction` before forcing all new writes to conform to the schema.

## 15. Performance and Indexes Related to Arrays

MongoDB can build an index on an array field, creating a **multikey index** as needed. Example:

```javascript
db.arrayCases.createIndex({
  tags: 1
})
```

An index on an array can support **element value** lookups like `{ tags: "mongo" }`. However, `$size` conditions **do not use an index to directly resolve the array-length comparison**. If the application frequently filters by element count at large scale, consider storing an additional `tagsCount` field updated consistently with `tags`, and indexing that count field.

Example:

```javascript
{
  _id: "article-01",
  tags: ["mongodb", "query"],
  tagsCount: 2
}
```

The downside of storing an extra count is ensuring `tagsCount` is updated atomically whenever `tags` changes. Otherwise, queries relying on the count can return wrong results. Only introduce derived data into the schema when performance requirements and consistency maintenance are clearly defined.

For `$exists` and `$type`, index effectiveness also depends on index type, data distribution, and the query plan. Do not assume that having an index makes every null/missing/array query fast; run:

```javascript
db.arrayCases.find({
  tags: { $size: 0 }
}).explain("executionStats")
```

to observe the execution plan on target data and environments.

## 16. Common Misconceptions

| Misconception | Consequence | Correct Understanding |
| --- | --- | --- |
| `[]` and `[null]` both mean “no elements” | Wrong element counts | `[]` has 0 elements; `[null]` has 1 element |
| `tags: null` and missing `tags` are identical | Fails to distinguish initialized vs. unset | One has a Null-typed field; the other lacks the field |
| `{tags: null}` finds only direct null fields | Also returns missing fields or arrays containing null | Use `$exists`, `$elemMatch`, or aggregation `$type` per need |
| `{tags: {$type: "null"}}` finds only direct null fields | Can match arrays containing a null element | Use `$expr` with `{$type: "$tags"}` to check whole-field type |
| `{tags: {$exists: true}}` means it has elements | Also matches `tags: []` and `tags: null` | `$exists` checks field presence, not array size |
| `{tags: {$size: 0}}` matches null/missing | Misses those documents | `$size: 0` matches only empty arrays |
| `{tags: []}` always means empty outermost array | Confusion with nested arrays | Use `$size: 0` when needing exact outer array length |
| `$all: []` finds empty arrays | Incorrect results | Use `$size: 0` |
| `$ifNull` turns `[null]` into `[]` | Misinterprets aggregation output | `$ifNull` replaces only when the expression itself is null/missing, without filtering elements |
| `$push` on `tags: null` works like an empty array | Update operation errors | Initialize an array properly or fix data first |
| Changing a validator auto-fixes legacy data | Mistyped documents remain | Schema validation is not a migration |

## 17. Practice Exercises

### Exercise 1. Classifying Five Field States

Given the documents:

```javascript
{ _id: 1, values: [] }
{ _id: 2, values: [null] }
{ _id: 3, values: null }
{ _id: 4 }
{ _id: 5, values: ["A"] }
```

State which `_id` values match `values: {$size: 0}`, `values: {$exists: false}`, and `values: null`.

**Reference answer:**

- `{ values: { $size: 0 } }` matches `1`.
- `{ values: { $exists: false } }` matches `4`.
- `{ values: null }` matches `2, 3, 4`.

### Exercise 2. Finding Arrays Containing Null Without Matching Null Fields

Using Exercise 1's data, write a query returning only documents where `values` is an array containing a `null` element.

**Reference answer:**

```javascript
db.sample.find({
  values: {
    $elemMatch: { $eq: null }
  }
})
```

The result is `_id: 2`. Collection `sample` here is a suggested name; insert the data into it first to run directly.

### Exercise 3. Distinguishing Empty Arrays from Arrays of Empty Arrays

Given:

```javascript
{ _id: "x", a: [] }
{ _id: "y", a: [[]] }
{ _id: "z", a: [[], []] }
```

Which query guarantees matching only `x` when you want **the outermost array to have 0 elements**?

**Answer:**

```javascript
db.sample.find({ a: { $size: 0 } })
```

`y` has one element and `z` has two elements; even though the inner elements are empty arrays, their outer arrays are not empty.

### Exercise 4. Null Subfield in an Object Array

Given:

```javascript
{ _id: "p1", contacts: [{ type: "email", value: null }] }
{ _id: "p2", contacts: [{ type: "email" }] }
{ _id: "p3", contacts: [] }
```

Write two filters:

1. Has an `email` contact whose `value` actually has type Null.
2. Has an `email` contact completely missing the `value` field.

**Answer:**

```javascript
// 1. Subfield value is BSON Null
db.people.find({
  contacts: {
    $elemMatch: {
      type: "email",
      value: { $type: "null" }
    }
  }
})

// 2. Subfield value does not exist
db.people.find({
  contacts: {
    $elemMatch: {
      type: "email",
      value: { $exists: false }
    }
  }
})
```

The first query matches `p1`; the second matches `p2`. `p3` has an empty array and contains no elements satisfying `$elemMatch`.

### Exercise 5. Requiring the Field to Always Be an Array

A system wants every article to have `tags`, even if no tags are assigned. This field must be an array of strings and may be `[]`. Which JSON Schema rule fits?

**Reference answer:**

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

This rule cleanly separates missing fields, null fields, arrays containing null, and valid empty arrays.

## 18. Choosing Filters by Intent

When reading business requirements, translate them into a clear BSON-level description before writing a query:

1. **“List exists, no elements yet”** → `{ tags: { $size: 0 } }`.
2. **“List field has never been stored”** → `{ tags: { $exists: false } }`.
3. **“Has `tags` field of type array”** → `{ tags: { $type: "array" } }`.
4. **“Array has at least one null element”** → `{ tags: { $elemMatch: { $eq: null } } }`.
5. **“Entire `tags` field has value BSON Null”** → `$expr` checking `{$type: "$tags"}` equals `"null"`.
6. **“An object element of the array is missing a subfield”** → use `$elemMatch` with `$exists: false` on the subfield.

Array queries in MongoDB stay accurate when you keep three concepts separate: **array element count**, **element type/value**, and **field existence**. `[]` is not `[null]`; `null` is not missing; and equality with `null` is usually broader than initial intuition suggests. Identifying the exact structure before filtering helps applications handle flexible data while preserving business meaning.
