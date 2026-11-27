# Adding Elements with `$push`, `$addToSet`, and Modifiers `$each`, `$sort`, `$slice` in MongoDB

## 1. Problem Statement: Updating an Array Without Replacing the Whole Document

In MongoDB, a document field can hold an **array**. For example, an article has `tags`, a student has `scores`, an order has line `items`, or a user has `recentEvents`:

```javascript
{
  _id: "POST-01",
  title: "Learning MongoDB",
  tags: ["database", "mongodb"],
  recentEvents: [
    { eventId: "E01", action: "CREATED" }
  ]
}
```

When adding a tag or event, a naive and error-prone approach is **read the entire document → modify the array in the application → write the array back**:

```text
Client A reads tags = ["database"]
Client B reads tags = ["database"]
Client A writes ["database", "mongodb"]
Client B writes ["database", "java"]
Final result may lose one of the two new elements
```

That is a **lost update** caused by overwriting existing data without concurrency control. MongoDB provides **array update operators** to instruct the server to mutate the array field directly:

- `$push`: **appends** a value to the array, allowing duplicates.
- `$addToSet`: **adds only if an equivalent value does not already exist** in the array; does not remove pre-existing duplicates.
- `$each`: adds **multiple elements** in a single command, supported with both `$push` and `$addToSet`.
- `$sort` and `$slice`: **modifiers of `$push`** to sort and limit the number of retained elements after pushing; not valid modifiers for `$addToSet`.

These operators run inside update commands such as `updateOne()`, `updateMany()`, or equivalent write operations, and **updating a single document is atomic at the document level**. Therefore, they are far better suited than reading and rewriting the array under concurrent requests.

### Mental Model

```text
                 Document with an array field
                            |
              +-------------+-------------+
              |                           |
           $push                     $addToSet
              |                           |
      Adds even if duplicate     Adds only if not already present
              |                           |
      Can use $each               Can use $each
              |
         Can $sort
              |
         Can $slice
              |
        Updated array
```

The key is choosing the operator according to the **business meaning of the array**, not merely because you "want to add an element". An event log may permit repeated entries; a tag list may forbid duplicates; a leaderboard may require sorting and capping.

## 2. Preparing a Practice Collection

The examples below use **mongosh**. Create a dedicated test collection and insert the sample data **once**:

```javascript
db.arrayUpdateLesson.insertMany([
  {
    _id: "tags",
    title: "MongoDB Article",
    tags: ["database", "mongodb"]
  },
  {
    _id: "scores",
    student: "An",
    scores: [68, 91, 73]
  },
  {
    _id: "recent-events",
    recentEvents: [
      {
        eventId: "E02",
        occurredAt: ISODate("2026-11-10T10:00:00Z"),
        action: "LOGIN"
      },
      {
        eventId: "E01",
        occurredAt: ISODate("2026-11-09T10:00:00Z"),
        action: "REGISTER"
      }
    ]
  },
  {
    _id: "items",
    items: [{ sku: "P01", quantity: 1 }]
  },
  {
    _id: "missing-array",
    note: "Document does not yet have a tags field"
  },
  {
    _id: "invalid-array",
    tags: "mongodb"
  }
]);
```

Running examples sequentially on **the same document** will alter the starting state of later examples. Snippets below note when they assume the initial state. To reproduce exact outputs, use a fresh collection or re-seed the test data. Never run experimental write/delete commands on production data.

## 3. `$push`: Adding Elements Even If Identical Elements Already Exist

Basic syntax:

```javascript
db.collection.updateOne(
  { /* condition to match document */ },
  { $push: { arrayField: newValue } }
);
```

Example adding the `"java"` tag to the article:

```javascript
db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  { $push: { tags: "java" } }
);

db.arrayUpdateLesson.findOne(
  { _id: "tags" },
  { _id: 0, tags: 1 }
);
```

The `tags` array transitions from:

```javascript
["database", "mongodb"]
```

to:

```javascript
["database", "mongodb", "java"]
```

If you run the exact same command again, `"java"` is appended **a second time**:

```javascript
["database", "mongodb", "java", "java"]
```

This is **by design for `$push`**, not a bug: it appends an element to the array without checking for duplicates.

### 3.1. Where Is `$push` Appropriate?

- Event or processing logs where two events with identical content are still distinct records.
- Measurement history arrays where identical values at two different times are both meaningful.
- Lists of scores, items, or entries where duplicates are permitted by business rules.
- Arrays maintained in sorted order or bounded using `$sort` and `$slice`.

For critical event logs, each event should normally carry its own `eventId`; if event counts grow without bound, consider a **separate events collection** instead of embedding everything into one document.

### 3.2. Passing an Array to `$push` Inserts It as a Single Element

Consider the command:

```javascript
db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  { $push: { tags: ["spring", "java"] } }
);
```

This **does not** add two separate strings. The entire array `["spring", "java"]` is appended as **one element** of `tags`:

```javascript
[
  "database",
  "mongodb",
  "java",
  ["spring", "java"]
]
```

This example assumes the command adding `"java"` ran once and was not repeated. To append two individual strings, you must use `$each`.

**Consequence:** never assume `$push` "flattens" an input array. Appending an array as a single element creates **nested arrays**, which can break data invariants when the schema expects a flat list of strings.

## 4. `$each`: Adding Multiple Elements at Once

`$each` is a **modifier** placed inside the argument of `$push` or `$addToSet`, not a standalone top-level update operator:

```javascript
db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  {
    $push: {
      tags: { $each: ["spring", "java"] }
    }
  }
);
```

This appends **two String elements** to the end of the array, preserving existing elements and still permitting duplicates:

```text
Before: ["database", "mongodb"]
After:  ["database", "mongodb", "spring", "java"]
```

This example assumes the initial state of the `"tags"` document. If run after the commands in section 3, previously added elements remain present.

### 4.1. `$each` with Document Elements

```javascript
db.arrayUpdateLesson.updateOne(
  { _id: "items" },
  {
    $push: {
      items: {
        $each: [
          { sku: "P02", quantity: 2 },
          { sku: "P03", quantity: 1 }
        ]
      }
    }
  }
);
```

The `items` array will hold three documents: the existing `P01` and the two new elements `P02` and `P03`. MongoDB does not treat `sku` as an element-level unique key; if `P02` is pushed again, `$push` still appends it.

### 4.2. Why Use One Command Instead of Multiple Commands?

To add three elements to the same array:

```javascript
// Three separate command round-trips.
db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  { $push: { tags: "A" } }
);
db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  { $push: { tags: "B" } }
);
db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  { $push: { tags: "C" } }
);
```

A single `$push` with `$each` expresses all three additions **within one atomic document update**:

```javascript
db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  {
    $push: {
      tags: { $each: ["A", "B", "C"] }
    }
  }
);
```

Combining them reduces database round-trips and keeps the document-level atomicity boundary explicit. Still, account for array size, affected indexes, and the BSON document size limit.

## 5. `$addToSet`: Adding Only If the Element Does Not Already Exist

`$addToSet` fits when an array represents a **set of unique values**, such as tags on an article or features enabled for an account.

```javascript
db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  { $addToSet: { tags: "mongodb" } }
);
```

Starting from `tags: ["database", "mongodb"]`, `"mongodb"` is already present, so the command adds nothing.

Adding a value not yet present:

```javascript
db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  { $addToSet: { tags: "java" } }
);
```

From the initial state, MongoDB adds `"java"` once. Running the exact same command repeatedly—while nothing else modifies the array—does not add duplicates.

### 5.1. `$addToSet` Does Not Deduplicate Pre-Existing Duplicates

Suppose the data already contains:

```javascript
{ _id: "legacy-tags", tags: ["mongodb", "java", "mongodb"] }
```

Running:

```javascript
db.arrayUpdateLesson.updateOne(
  { _id: "legacy-tags" },
  { $addToSet: { tags: "mongodb" } }
);
```

**does not merge the two existing `"mongodb"` entries into one**. `$addToSet` only prevents inserting a new equivalent value; it **is not a normalization or full-array deduplication operator**. Cleaning up legacy duplicates requires a dedicated strategy to classify and rebuild the array according to business rules.

### 5.2. Element Ordering Is Not Guaranteed by `$addToSet`

`$addToSet` expresses set membership and **does not guarantee a specific array ordering** for the application. If the UI requires alphabetically sorted tags, sort on read or use another data structure. Never substitute hoping insertion order matches display order for explicit sorting requirements.

### 5.3. An Input Array Is Still Treated as a Single Value Without `$each`

```javascript
db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  {
    $addToSet: {
      tags: ["spring", "java"]
    }
  }
);
```

MongoDB treats **the entire array `["spring", "java"]` as one value**, comparing and adding it if that nested array value is not already present. It does not check `"spring"` and `"java"` individually.

To add both strings as individual elements of `tags`, combine `$each` with `$addToSet`.

## 6. `$addToSet` Combined with `$each`

```javascript
db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  {
    $addToSet: {
      tags: {
        $each: ["mongodb", "spring", "java"]
      }
    }
  }
);
```

Starting from the initial state:

```javascript
["database", "mongodb"]
```

`"mongodb"` already exists and is not added again. The two new values `"spring"` and `"java"` are added:

```javascript
["database", "mongodb", "spring", "java"]
```

**Difference from `$push + $each`:** `$push` adds all input elements (including duplicates); `$addToSet` checks each value's presence in the array.

### 6.1. Example: User Selecting Multiple Interests

```javascript
db.users.updateOne(
  { _id: "U01" },
  {
    $addToSet: {
      interests: {
        $each: ["mongodb", "backend", "java"]
      }
    }
  }
);
```

Each value is added only if absent from `interests`. However, to enforce true business uniqueness, the application must also decide whether `"MongoDB"` and `"mongodb"` represent the same tag. Under default string comparison, differing casing is treated as distinct; if case-insensitivity is required, normalize tag codes at the ingestion boundary or apply a verified collation rule.

### 6.2. `$addToSet` Compares Embedded Documents by Whole Value

For document elements, `$addToSet` **does not treat any single field as a key**:

```javascript
// Initialize in a separate test collection.
db.embeddedSetDemo.insertOne({
  _id: "cart",
  items: [{ sku: "P01", quantity: 1 }]
});

// Identical document value: not added.
db.embeddedSetDemo.updateOne(
  { _id: "cart" },
  {
    $addToSet: {
      items: { sku: "P01", quantity: 1 }
    }
  }
);

// Same sku but different quantity: this is a different document value.
db.embeddedSetDemo.updateOne(
  { _id: "cart" },
  {
    $addToSet: {
      items: { sku: "P01", quantity: 2 }
    }
  }
);
```

The result can contain both:

```javascript
[
  { sku: "P01", quantity: 1 },
  { sku: "P01", quantity: 2 }
]
```

These two elements **differ in document value**, despite sharing the same `sku`. When comparing embedded documents, MongoDB also considers **field order** inside the document: `{ sku: "P01", quantity: 1 }` and `{ quantity: 1, sku: "P01" }` are not guaranteed to be treated as equal by `$addToSet`.

If business logic requires "at most one entry per SKU in the cart", `$addToSet` on **the whole document** is insufficient. You need a different design, such as storing only a unique key in the array, a SKU-keyed map, a line-item collection with its own constraint, or conditional updates/aggregation pipelines.

## 7. `$sort`: Sorting the Array After `$push`

`$sort` is a **modifier of `$push`**; it orders the array elements during the update. Using `$sort` requires `$each`, even when `$each` contains only one element.

### 7.1. Sorting a Numeric Array Ascending

Standalone example on a document with `scores: [68, 91, 73]`:

```javascript
db.arrayUpdateLesson.updateOne(
  { _id: "scores" },
  {
    $push: {
      scores: {
        $each: [88, 97],
        $sort: 1
      }
    }
  }
);
```

MongoDB appends 88 and 97 and sorts the array in **ascending order**:

```javascript
[68, 73, 88, 91, 97]
```

In the `$sort` modifier of `$push`:

- `1`: sort ascending.
- `-1`: sort descending.

### 7.2. Sorting a Numeric Array Descending

On **another document** starting with `[68, 91, 73]`:

```javascript
db.scoreSortDemo.insertOne({
  _id: "descending",
  scores: [68, 91, 73]
});

db.scoreSortDemo.updateOne(
  { _id: "descending" },
  {
    $push: {
      scores: {
        $each: [88, 97],
        $sort: -1
      }
    }
  }
);
```

Result:

```javascript
[97, 91, 88, 73, 68]
```

Do not misread this as "MongoDB sorts only the two newly added elements". **The entire array after appending** is sorted.

### 7.3. Sorting an Array of Documents

Suppose each element has `score` and `candidateId`:

```javascript
db.leaderboardDemo.insertOne({
  _id: "weekly",
  players: [
    { candidateId: "U01", score: 80 },
    { candidateId: "U02", score: 95 }
  ]
});

db.leaderboardDemo.updateOne(
  { _id: "weekly" },
  {
    $push: {
      players: {
        $each: [
          { candidateId: "U03", score: 95 },
          { candidateId: "U04", score: 70 }
        ],
        $sort: { score: -1, candidateId: 1 }
      }
    }
  }
);
```

The array is sorted by `score` descending; when two elements tie on score, the tie-breaker `candidateId` ascending determines order deterministically:

```javascript
[
  { candidateId: "U02", score: 95 },
  { candidateId: "U03", score: 95 },
  { candidateId: "U01", score: 80 },
  { candidateId: "U04", score: 70 }
]
```

Without a tie-breaker field, do not assume tied elements preserve their previous relative order. For critical data, include a deterministic secondary sort key.

### 7.4. Distinguishing the `$sort` Modifier from the `$sort` Stage

```javascript
// $sort is a modifier OF $push, sorting elements inside the array field.
db.scoreSortDemo.updateOne(
  { _id: "descending" },
  {
    $push: {
      scores: { $each: [99], $sort: -1 }
    }
  }
);

// $sort is an aggregation STAGE, ordering output documents.
db.orders.aggregate([
  { $sort: { createdAt: -1 } }
]);
```

Both are named `$sort`, but the first sorts **elements inside one array**, while the second sorts **documents flowing through an aggregation pipeline**. Context dictates syntax and behavior.

## 8. `$slice`: Keeping at Most N Elements After `$push`

An array like `recentEvents` might only need to keep the **3 most recent events** for fast display. Appending indefinitely makes the document grow continuously, increasing read/write cost and risking the BSON document size limit.

`$slice` inside `$push` **truncates the array after appending**, and also requires `$each`.

### 8.1. Positive `$slice`: Keep the First N Elements

```javascript
db.scoreSliceDemo.insertOne({
  _id: "positive",
  scores: [10, 20, 30, 40]
});

db.scoreSliceDemo.updateOne(
  { _id: "positive" },
  {
    $push: {
      scores: {
        $each: [50, 60],
        $slice: 4
      }
    }
  }
);
```

After appending, the array is `[10, 20, 30, 40, 50, 60]`. With `$slice: 4`, MongoDB retains the **first 4 elements**:

```javascript
[10, 20, 30, 40]
```

This illustrates that if you only append to the **end of the array**, using positive `$slice` without sorting or changing insertion position immediately discards the newly pushed elements. To retain the newest elements at the end, a negative `$slice` is typically used.

### 8.2. Negative `$slice`: Keep the Last N Elements

```javascript
db.scoreSliceDemo.insertOne({
  _id: "negative",
  scores: [10, 20, 30, 40]
});

db.scoreSliceDemo.updateOne(
  { _id: "negative" },
  {
    $push: {
      scores: {
        $each: [50, 60],
        $slice: -4
      }
    }
  }
);
```

Result:

```javascript
[30, 40, 50, 60]
```

With `$slice: -4`, MongoDB retains the **last 4 elements** of the array after appending. This works when insertion order reflects chronological order, **assuming requests are processed and appended in exact order**. In systems where events can arrive late or out of timestamp order, add `$sort` on the business timestamp.

### 8.3. `$slice: 0`

```javascript
db.scoreSliceDemo.updateOne(
  { _id: "negative" },
  {
    $push: {
      scores: {
        $each: [70],
        $slice: 0
      }
    }
  }
);
```

`$slice: 0` retains **zero elements**, emptying the array to `[]`. Never pass `0` accidentally expecting "all elements". To leave length unbounded, omit the `$slice` modifier.

### 8.4. `$slice` in Updates vs. `$slice` in Projections

```javascript
// Modifier inside $push: MUTATES the stored array.
db.scoreSliceDemo.updateOne(
  { _id: "positive" },
  {
    $push: {
      scores: { $each: [70], $slice: -3 }
    }
  }
);

// Projection in find: only selects elements to RETURN, without modifying data.
db.scoreSliceDemo.find(
  { _id: "positive" },
  { scores: { $slice: -3 } }
);
```

If the UI only wants to display three elements without deleting older ones from the database, use a query projection or read-side logic. The `$slice` modifier inside `$push` **permanently removes truncated elements from the stored array**.

## 9. Combining `$push + $each + $sort + $slice`

This pattern is very useful when you need to **append new items → sort → retain only the top portion of the array**.

### 9.1. Keeping the Top Three Highest Scores

```javascript
db.topScoreDemo.insertOne({
  _id: "student-01",
  topScores: [68, 91, 73]
});

db.topScoreDemo.updateOne(
  { _id: "student-01" },
  {
    $push: {
      topScores: {
        $each: [88, 97],
        $sort: -1,
        $slice: 3
      }
    }
  }
);

db.topScoreDemo.findOne(
  { _id: "student-01" },
  { _id: 0, topScores: 1 }
);
```

Result:

```javascript
{ topScores: [97, 91, 88] }
```

Logical execution flow:

1. Initial array: `[68, 91, 73]`.
2. Append 88 and 97: `[68, 91, 73, 88, 97]`.
3. Sort descending: `[97, 91, 88, 73, 68]`.
4. Keep the first three elements: `[97, 91, 88]`.
5. Persist the resulting array in the document.

Key point: **the logical processing order is append/position → sort → slice → save**. Writing the modifier keys in a different order inside the update object does not change this standard execution order.

### 9.2. Keeping the Three Most Recent Events by Timestamp

Suppose a document already has `recentEvents` from the setup section:

```javascript
[
  {
    eventId: "E02",
    occurredAt: ISODate("2026-11-10T10:00:00Z"),
    action: "LOGIN"
  },
  {
    eventId: "E01",
    occurredAt: ISODate("2026-11-09T10:00:00Z"),
    action: "REGISTER"
  }
]
```

Add two events, one newest and one arriving late:

```javascript
db.arrayUpdateLesson.updateOne(
  { _id: "recent-events" },
  {
    $push: {
      recentEvents: {
        $each: [
          {
            eventId: "E03",
            occurredAt: ISODate("2026-11-11T10:00:00Z"),
            action: "VIEWED_PRODUCT"
          },
          {
            eventId: "E00",
            occurredAt: ISODate("2026-11-08T10:00:00Z"),
            action: "IMPORTED"
          }
        ],
        $sort: { occurredAt: -1, eventId: 1 },
        $slice: 3
      }
    }
  }
);
```

Three events are retained, ordered `E03, E02, E01`. The late-arriving `E00` is dropped because it has the oldest timestamp, even though it was pushed in the same command as `E03`.

The strength of this pattern is keeping the preview array ordered by `occurredAt` and capped at size 3. However, if you need the **complete event history** for auditing or analytics, store it in a separate collection; `recentEvents` serves purely as a **bounded preview**.

### 9.3. What Does Descending Sort Combined with Negative `$slice` Mean?

Suppose after appending numbers, we have the descending sequence:

```javascript
[97, 91, 88, 73, 68]
```

`$slice: 3` keeps `[97, 91, 88]`, the **three highest scores**. Conversely, `$slice: -3` keeps `[88, 73, 68]`, the **last three elements after descending sort**, not the three highest scores.

If the goal is the lowest scores, use ascending sort with positive slice. Always choose sort direction and slice sign together.

### 9.4. `$each: []` Is Still Useful with `$sort` or `$slice`

Sometimes you do not need to append any new elements, only sort or trim an existing array:

```javascript
db.topScoreDemo.updateOne(
  { _id: "student-01" },
  {
    $push: {
      topScores: {
        $each: [],
        $sort: -1,
        $slice: 2
      }
    }
  }
);
```

On the array `[97, 91, 88]` from section 9.1, the result is `[97, 91]`. This expresses **sorting/trimming an array without appending elements**. It differs from passing an empty argument to `$push`.

## 10. `$position`: Choosing the Insertion Index with `$push`

Although this lesson focuses on `$each`, `$sort`, and `$slice`, the `$position` modifier clarifies the step sequence inside `$push`.

By default, `$push` appends at the end of the array. To insert at the beginning or a specific index, combine `$position` with `$each`:

```javascript
db.queueDemo.insertOne({
  _id: "queue-01",
  tasks: ["B", "C"]
});

db.queueDemo.updateOne(
  { _id: "queue-01" },
  {
    $push: {
      tasks: {
        $each: ["A"],
        $position: 0
      }
    }
  }
);
```

Result:

```javascript
["A", "B", "C"]
```

`$position: 0` inserts at the start of the array. Other indices are also supported per MongoDB rules, including negative offsets counted from the end of the array; be sure you understand negative indexing before using it.

If `$sort` is also specified, the array **is sorted after insertion**, so `$position` does not necessarily determine the element's final position. For example:

```javascript
db.queueDemo.updateOne(
  { _id: "queue-01" },
  {
    $push: {
      tasks: {
        $each: ["Z"],
        $position: 0,
        $sort: 1
      }
    }
  }
);
```

After ascending sort, `"Z"` ends up at the end despite being temporarily inserted at index 0.

## 11. Data Preconditions and Errors When Updating Arrays

### 11.1. Field Does Not Yet Exist

If the document lacks the array field, `$push` or `$addToSet` can **create the new field as an array**:

```javascript
db.arrayUpdateLesson.updateOne(
  { _id: "missing-array" },
  { $push: { tags: "mongodb" } }
);
```

From:

```javascript
{ _id: "missing-array", note: "Document does not yet have a tags field" }
```

it becomes a document with:

```javascript
{ tags: ["mongodb"] }
```

Using `$addToSet` on a missing field also creates the array with the new element. There is no need to pre-initialize with `$set: { tags: [] }` just because the field is absent.

### 11.2. Field Exists but Is Not an Array

If a document contains:

```javascript
{ _id: "invalid-array", tags: "mongodb" }
```

then:

```javascript
db.arrayUpdateLesson.updateOne(
  { _id: "invalid-array" },
  { $push: { tags: "java" } }
);
```

errors because `tags` is a **String**, not an Array. `$addToSet` likewise requires an existing target field to be an array. The case `tags: null` is **also not equivalent to a missing field** and cannot be treated as an empty array for appending.

Applications should define clear schemas and, where appropriate, enforce collection validation to prevent mixing String/Null/Array in a field designed as a list.

### 11.3. `$sort` and `$slice` Cannot Be Used Directly with `$addToSet`

The following is **not valid syntax** for `$addToSet`:

```javascript
// DO NOT USE: $addToSet does not support $sort/$slice.
db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  {
    $addToSet: {
      tags: {
        $each: ["java"],
        $sort: 1,
        $slice: 3
      }
    }
  }
);
```

The two feature sets have strict boundaries:

| Modifier | `$push` | `$addToSet` |
|---|:---:|:---:|
| `$each` | Yes | Yes |
| `$sort` | Yes, with `$each` | **No** |
| `$slice` | Yes, with `$each` | **No** |
| `$position` | Yes, with `$each` | **No** |

If you need both **deduplication** and **sorting/capping to N elements**, reconsider the model: you can use an aggregation update pipeline to rebuild the array per rules, or store items in a separate collection with appropriate uniqueness constraints. Never combine `$addToSet` with unsupported modifiers.

### 11.4. BSON Document Size and Unbounded Arrays

MongoDB limits **each BSON document** to 16 MiB. An array continuously growing via `$push` enlarges the document over time, increases network/write overhead, and eventually fails writes once it hits the limit.

For large or unbounded collections (logs, comments, full view histories), it is usually better to use a **child collection** referencing the parent document. Bounded embedded arrays using `$slice` suit previews or small datasets, not permanent storage of every event.

### 11.5. Indexes on Array Elements Have Write Costs

If you index `tags`:

```javascript
db.arrayUpdateLesson.createIndex({ tags: 1 });
```

MongoDB creates a **multikey index** on the array field. This speeds up queries like `{ tags: "mongodb" }`, but every array modification must maintain the corresponding index entries. Never consider only read benefits while ignoring write amplification and index storage.

## 12. Atomicity, Concurrency, and Retry Safety

### 12.1. A Single Document Updates as One Unit

Suppose two clients concurrently add different elements to `tags` on the same document:

```javascript
// Client A
db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  { $addToSet: { tags: "spring" } }
);

// Client B
db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  { $addToSet: { tags: "docker" } }
);
```

MongoDB executes each single-document update within that operation's atomic boundary. This avoids the bug where **both read the same stale array and each overwrites the whole array**, provided the application uses these operators directly rather than rewriting the array from a stale snapshot.

When two clients concurrently `$addToSet` the exact same value, the membership check and insertion happen inside the atomic update; this is an effective way to avoid duplicate values **under `$addToSet` equality rules**.

### 12.2. `$push` Is Not Business-Idempotent on Retries

Suppose an API receives an event and runs:

```javascript
db.logs.updateOne(
  { _id: "L01" },
  { $push: { events: { eventId: "EVT-100", action: "LOGIN" } } }
);
```

If the application resends the same command after a timeout, it can append **two elements with the same `eventId`** because `$push` does not check duplicates. When the goal is storing each logical event once, you can:

- Store each event as its own document using `eventId` as a unique key.
- Use `$addToSet` if the resent document value is **byte-for-byte identical** and whole-value uniqueness satisfies business rules.
- Or enforce conditional updates / `eventId` checks and reconciliation rather than treating array pushes as idempotent.

Do not confuse retrying an HTTP request as a new command with MongoDB driver **retryable writes**: drivers track sessions and operation IDs to survive transient transport failures, which does not turn two separate business requests into the same operation.

### 12.3. `$addToSet` Is Not a Unique Constraint on a Subfield

An `items` array containing:

```javascript
[
  { sku: "P01", quantity: 1 }
]
```

will still accept `{ sku: "P01", quantity: 2 }` via `$addToSet` because the whole embedded document differs from the existing one. If business rules dictate "each SKU appears at most once", enforce that invariant in the data model and update logic. Also never assume a **unique multikey index** prevents duplicate subfields inside the same document; index uniqueness constraints follow specific rules and cannot enforce arbitrary uniqueness **within a single document's array**.

### 12.4. Multi-Document vs. Single-Document Updates

`updateMany()` can apply `$push` or `$addToSet` to each matched document. However, the batch of updates across multiple documents **is not automatically atomic as a transaction**. If business logic requires modifying multiple documents as an all-or-nothing unit, use an explicit transaction or recovery/reconciliation workflows.

## 13. Application Usage Patterns

### 13.1. Deduplicated Tag List

```javascript
db.posts.updateOne(
  { _id: "POST-01" },
  {
    $addToSet: {
      tags: {
        $each: ["mongodb", "backend", "java"]
      }
    }
  }
);
```

**Choose `$addToSet`** because whether a tag is present matters more than how many times a user clicked add. If deduplication must rely on a stable tag code while display names may change, store the stable code (String) in `tags` and keep display metadata in a tags collection.

### 13.2. Keeping the Five Most Recent Notifications

```javascript
db.users.updateOne(
  { _id: "U01" },
  {
    $push: {
      notificationPreview: {
        $each: [
          {
            notificationId: "N101",
            createdAt: ISODate("2026-11-11T10:00:00Z"),
            text: "New comment received"
          }
        ],
        $sort: { createdAt: -1, notificationId: 1 },
        $slice: 5
      }
    }
  }
);
```

**Choose `$push + $each + $sort + $slice`** because the preview needs ordering and a size cap. If duplicates by `notificationId` must be prevented, this pattern **is not enough on its own**: store full notification records under a unique key and maintain the preview with deduplication or a different array design.

### 13.3. Storing Measurements Where Values Can Repeat

```javascript
db.sensors.updateOne(
  { _id: "S01" },
  {
    $push: {
      recentReadings: {
        $each: [
          {
            at: ISODate("2026-11-11T10:00:00Z"),
            temperature: 27.5
          },
          {
            at: ISODate("2026-11-11T10:00:05Z"),
            temperature: 27.5
          }
        ],
        $sort: { at: -1 },
        $slice: 10
      }
    }
  }
);
```

Two readings with the same temperature still carry **two distinct timestamps** and both have business value; `$addToSet` on a scalar temperature would be wrong. When measurement volume is large, use dedicated collections or time-series optimizations rather than unbounded nested arrays.

### 13.4. Participant List

```javascript
db.events.updateOne(
  { _id: "EVENT-01" },
  { $addToSet: { participantIds: "USER-08" } }
);
```

If you only need to know whether a user joined, `participantIds` as a simple ID array works well with `$addToSet` to avoid duplicate IDs. However, if each participant has individual status/payment info or participant counts are very large, a separate join collection like `eventParticipants` with a unique index on `(eventId, userId)` is more suitable.

## 14. Operator Selection Comparison Table

| Requirement | Operator / Structure | Allows Duplicates? | Auto-Sorts? | Caps Element Count? |
|---|---|---|---|---|
| Add one value, allow duplicates | `$push` | Yes | No | No |
| Add multiple values, allow duplicates | `$push + $each` | Yes | No | No |
| Add one value if absent | `$addToSet` | No new equivalent copies | No | No |
| Add multiple values if absent | `$addToSet + $each` | No new equivalent copies | No | No |
| Add and sort array | `$push + $each + $sort` | Yes | Yes | No |
| Add and keep N elements | `$push + $each + $slice` | Yes | No | Yes |
| Add, sort, and keep N elements | `$push + $each + $sort + $slice` | Yes | Yes | Yes |
| Unique by subfield AND ordered/bounded | Alternative design or conditional update pipeline | Depends on design | Possible | Possible |

When encountering "add without duplicates, sort, and keep 10 elements", never blindly attach `$sort` or `$slice` to `$addToSet`. Determine **whether uniqueness is by whole value or by subfield key**, and which invariants must be atomic.

## 15. Inspecting Update Command Results

Example:

```javascript
const result = db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  { $addToSet: { tags: "mongodb" } }
);

printjson(result);
```

Typical response fields:

- `acknowledged`: whether the write was acknowledged under the write concern.
- `matchedCount`: how many documents matched the filter (at most 1 for `updateOne`).
- `modifiedCount`: how many documents were actually modified per server response.
- `upsertedId`: if upsert was enabled and created a new document, its `_id`.

When `$addToSet` sees the value is already present, a matching update reports `matchedCount: 1` and `modifiedCount: 0`. That **does not mean the query failed to find the document**; it means the write made no changes.

After updating, read back the targeted field to verify:

```javascript
db.arrayUpdateLesson.findOne(
  { _id: "tags" },
  { _id: 0, tags: 1 }
);
```

When practicing on shared collections, isolate examples or reset data to avoid misinterpreting results affected by earlier commands.

## 16. Practice Exercises

### Exercise 1 — Distinguishing `$push` and `$addToSet`

Given:

```javascript
{ _id: "P1", tags: ["mongodb", "java"] }
```

Predict the array after running **each case independently**:

```javascript
// a
{ $push: { tags: "mongodb" } }

// b
{ $addToSet: { tags: "mongodb" } }

// c
{ $push: { tags: ["spring", "java"] } }

// d
{ $addToSet: { tags: { $each: ["java", "spring"] } } }
```

Explain why case (c) creates a nested array element whereas (d) processes each String individually.

### Exercise 2 — Keeping the Top Three Scores

Given `[62, 88, 71]`. Write a single `updateOne` command to:

1. Add scores 95, 70, and 91.
2. Sort descending.
3. Keep exactly the top three scores.

Predict the result before running. Explain the roles of `$each`, `$sort: -1`, and `$slice: 3`.

### Exercise 3 — Keeping the Most Recent Events, Including Late Arrivals

Given:

```javascript
[
  { id: "A", at: ISODate("2026-11-10T10:00:00Z") },
  { id: "B", at: ISODate("2026-11-09T10:00:00Z") }
]
```

Add event `C` on 11/11 and `D` on 11/08, keeping only the three newest events by `at`. Choose the sign and value of `$sort` and `$slice` so the final order is `C, A, B`. Why is `$slice: -3` alone without sorting by timestamp insufficient here?

### Exercise 4 — Can One SKU Appear Twice?

Given:

```javascript
{
  _id: "CART-01",
  items: [{ sku: "P01", quantity: 1 }]
}
```

The application calls:

```javascript
db.carts.updateOne(
  { _id: "CART-01" },
  {
    $addToSet: {
      items: { sku: "P01", quantity: 2 }
    }
  }
);
```

Explain how the array changes and why `$addToSet` **does not guarantee one SKU is unique**. Propose a data model or update boundary enforcing "one line per SKU; adding increments quantity".

### Exercise 5 — Stored Truncation vs. Projected Truncation

You have an array of 10,000 events inside a document, and the screen only needs the three newest events. Compare:

1. Using `$slice` projection in `find()`.
2. Using `$push` with `$sort` and `$slice` modifiers on write.
3. Moving events to a separate collection and keeping only a preview in the parent document.

When does each option risk **losing history**? When does data grow toward the document size limit? When are pagination or indexes on a separate event collection needed?

### Exercise 6 — Analyzing Update Errors

Given the document:

```javascript
{ _id: "BAD", tags: null }
```

Predict the outcome of:

```javascript
db.example.updateOne(
  { _id: "BAD" },
  { $push: { tags: "mongodb" } }
);
```

Then fix the data model so `tags` is always an array when present. Explain the difference between a **missing field**, a **field with value null**, and an **empty array** when applying `$push`.

### Exercise 7 — Designing Safe Repeatable Operations

A service consumes `eventId = "EVT-100"` from a queue that can redeliver messages. Explain:

1. Why `$push`ing an event object on every delivery can create duplicates.
2. When `$addToSet` might be a sufficient solution.
3. If a redelivered event has the same `eventId` but a different `receivedAt`, why `$addToSet` on the whole object still appends it.
4. When to use a separate collection with a unique index on `eventId` or `(tenantId, eventId)`.

## 17. Key Takeaways

**Both `$push` and `$addToSet` mutate array fields in MongoDB, but express different requirements.** `$push` always appends elements as requested; `$addToSet` adds only if an equivalent value is not yet present, without cleaning up existing duplicates.

**`$each` appends multiple elements without turning the input list into a single nested array element.** It works with both `$push` and `$addToSet`.

**`$sort`, `$slice`, and `$position` are modifiers of `$push`**, paired with `$each` to sort, truncate, or position elements during an update. `$addToSet` does not accept these modifiers.

**Choose operators based on business invariants**: tag lists disallow duplicates, logs may allow repeated entries, previews need ordering and size bounds, and unbounded datasets belong in separate storage structures. Single-document atomic operations reduce write races, yet cannot automatically enforce uniqueness by subfield keys or synchronize across multiple documents.
