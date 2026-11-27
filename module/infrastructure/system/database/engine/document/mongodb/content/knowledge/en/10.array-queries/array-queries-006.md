# Array Projection with $elemMatch, $slice, and the Positional Operator in MongoDB

A MongoDB document can hold long arrays: student grades, activity history, image lists, comments, or product variants. Many APIs only need **one element**, **the first/last few elements**, or **the first element satisfying a condition**. Returning the entire array on every request forces the application to transfer and process unnecessary data.

**Array projection** is the technique of selecting a subset of an array field's data **in query results**. The three primary tools in this lesson are:

- **`$elemMatch` in projection**: retrieves the **first element** of the array satisfying the condition specified right inside the projection.
- **`$slice` in projection**: retrieves a slice of the array by **position and count**, without filtering by element values.
- **Positional operator `$` in projection**: retrieves the **first element matching the query condition** on the array.

Distinguish projection from filtering: **the filter decides which documents are returned**, whereas **the projection decides which fields and array elements those returned documents contain**. Original contents in the collection are never altered by a read operation using projection.

## 1. General Syntax

The two typical arguments to `find()`:

~~~javascript
db.collection.find(
  { /* filter: select documents */ },
  { /* projection: select returned fields and array elements */ }
);
~~~

Example:

~~~javascript
// Select published courses, returning at most the first 2 lessons.
db.courses.find(
  { status: "published" },
  { title: 1, lessons: { $slice: 2 } }
);
~~~

Inside the projection:

- `title: 1` means include the `title` field.
- `lessons: { $slice: 2 }` means return the first two elements of `lessons`.
- `_id` is still returned by default unless `_id: 0` is specified.
- No documents are added, deleted, or modified by `find()`.

Quick comparison table:

| Goal | Projection | Array Result |
| --- | --- | --- |
| Return the whole array | `{ lessons: 1 }` | All elements |
| Get the first element meeting a condition | `{ grades: { $elemMatch: { score: { $gte: 90 } } } }` | Array containing the **first matching element**, if any |
| Get the first two elements | `{ lessons: { $slice: 2 } }` | Array of at most two elements |
| Get the last two elements | `{ lessons: { $slice: -2 } }` | Array of at most two elements |
| Get two elements after skipping the first one | `{ lessons: { $slice: [1, 2] } }` | Array starting from the specified position |
| Return the element matching the filter condition | `{ "grades.$": 1 }` | Array containing the **first element** matching the filter |
| Get **all** elements meeting a condition | `$filter` in aggregation | Array with zero, one, or many elements |

**Naming note:** MongoDB also has the `$elemMatch` operator used **in filters**, the `$slice` expression used **in aggregation**, the `$slice` modifier used **in updates with `$push`**, and the positional `$` operator used **in updates**. They share similar names yet have different syntax and purposes.

## 2. Preparing the Practice Dataset

Examples use **mongosh** and a dedicated collection without affecting production data.

~~~javascript
const lab = db.getSiblingDB("array_projection_lab");

lab.courses.drop();

lab.courses.insertMany([
  {
    _id: 101,
    title: "MongoDB Fundamentals",
    status: "published",
    lessons: ["BSON", "CRUD", "Query", "Indexes", "Aggregation"],
    grades: [
      { student: "An", score: 66, passed: false },
      { student: "Binh", score: 89, passed: true },
      { student: "Chi", score: 92, passed: true }
    ],
    ratings: [3, 5, 4, 5],
    details: {
      category: "database",
      topics: ["documents", "arrays", "indexes"],
      language: "vi"
    }
  },
  {
    _id: 102,
    title: "MongoDB Advanced",
    status: "published",
    lessons: ["Aggregation", "Transactions", "Change streams", "Performance"],
    grades: [
      { student: "Dung", score: 77, passed: true },
      { student: "Hoa", score: 95, passed: true },
      { student: "Minh", score: 95, passed: true }
    ],
    ratings: [4, 5],
    details: {
      category: "database",
      topics: ["replica set", "transactions"],
      language: "vi"
    }
  },
  {
    _id: 103,
    title: "Java Fundamentals",
    status: "draft",
    lessons: ["Syntax", "OOP"],
    grades: [
      { student: "Lan", score: 45, passed: false },
      { student: "Nam", score: 58, passed: false }
    ],
    ratings: [2, 3],
    details: {
      category: "programming",
      topics: ["classes", "interfaces"],
      language: "en"
    }
  },
  {
    _id: 104,
    title: "Query Practice",
    status: "published",
    lessons: [],
    grades: [],
    ratings: [],
    details: {
      category: "database",
      topics: [],
      language: "vi"
    }
  },
  {
    _id: 105,
    title: "Mongo Express",
    status: "published",
    lessons: ["Find", "Projection"]
    // Intentionally omits grades, ratings, and details.
  }
]);
~~~

To keep results easy to compare, you can run:

~~~javascript
lab.courses.find({}, { title: 1, lessons: 1, grades: 1 })
  .sort({ _id: 1 });
~~~

Documents `101` and `102` have multiple elements satisfying various conditions; document `103` has elements that do not meet high-score conditions; `104` has empty arrays; `105` **completely lacks** several array fields. This dataset makes edge-case results clear to observe.

## 3. Standard Projection: Including or Excluding Entire Array Fields

Before using specialized operators, understand basic projection:

~~~javascript
// Return only title and lessons; _id is included by default.
lab.courses.find(
  { _id: 101 },
  { title: 1, lessons: 1 }
);
~~~

Sample output:

~~~javascript
{
  _id: 101,
  title: "MongoDB Fundamentals",
  lessons: ["BSON", "CRUD", "Query", "Indexes", "Aggregation"]
}
~~~

To hide arrays while keeping other fields:

~~~javascript
lab.courses.find(
  { _id: 101 },
  { grades: 0, ratings: 0 }
);
~~~

Normally, in one projection you **do not mix** inclusion (`1`) and exclusion (`0`) specifications, except for the special rule on `_id`. Array projection operators have additional rules on how they combine; see the `$slice` section.

Projection **does not paginate the document list**. The command:

~~~javascript
lab.courses.find({}, { lessons: 1 }).limit(2);
~~~

only limits the number of **documents** returned, not the number of **elements in each lessons array**. To trim arrays, use `$slice` or another appropriate operator.

## 4. $elemMatch in Projection: First Element Matching an Independent Condition

### 4.1. Syntax

~~~javascript
db.collection.find(
  { /* condition selecting documents */ },
  {
    arrayField: {
      $elemMatch: { /* element condition */ }
    }
  }
);
~~~

MongoDB scans the array elements and includes in the result the **first element matching** the `$elemMatch` condition. If no element matches, **that array field is omitted** from the returned document.

Important: the `$elemMatch` condition is **in the projection**, so it determines which element **is displayed**, without automatically excluding the entire document when no array element matches.

### 4.2. Example with an Object Array

Retrieve all published courses, but display only the **first student scoring at least 90**:

~~~javascript
lab.courses.find(
  { status: "published" },
  {
    title: 1,
    grades: {
      $elemMatch: { score: { $gte: 90 } }
    }
  }
).sort({ _id: 1 });
~~~

Relevant output:

~~~javascript
{ _id: 101, title: "MongoDB Fundamentals",
  grades: [{ student: "Chi", score: 92, passed: true }] }

{ _id: 102, title: "MongoDB Advanced",
  grades: [{ student: "Hoa", score: 95, passed: true }] }

{ _id: 104, title: "Query Practice" }

{ _id: 105, title: "Mongo Express" }
~~~

Explanation:

- Course `101` has one element scoring 90 or higher: `Chi`.
- Course `102` has **two** elements scoring 95: `Hoa` and `Minh`. The projection returns only the one appearing **first in the array**, which is `Hoa`.
- Course `104` has `grades: []` and no matching element. The result **omits the grades field**.
- Course `105` has no `grades`, so the result also **has no grades field**.
- Course `103` is `draft` and is excluded **by the filter** `{ status: "published" }`; that is a different reason from `grades` being omitted.

Easy mistake: a document with no element matching projection `$elemMatch` **can still be returned** if it satisfies the filter.

### 4.3. Combining Multiple Conditions on the Same Element

Requirement: display the **first student who both scored at least 80 and has `passed: true`**.

~~~javascript
lab.courses.find(
  { _id: 101 },
  {
    title: 1,
    grades: {
      $elemMatch: {
        score: { $gte: 80 },
        passed: true
      }
    }
  }
);
~~~

Result:

~~~javascript
{
  _id: 101,
  title: "MongoDB Fundamentals",
  grades: [{ student: "Binh", score: 89, passed: true }]
}
~~~

The `score` and `passed` conditions apply to the **same object** inside the `grades` array. Without knowing which element qualifies, you cannot rely on one element having a high score and another having `passed: true` to conclude an element satisfies both.

### 4.4. Query $elemMatch and Projection $elemMatch Occupy Two Different Positions

**Query `$elemMatch`** sits in the filter to **select documents**:

~~~javascript
lab.courses.find(
  {
    grades: {
      $elemMatch: {
        score: { $gte: 90 },
        passed: true
      }
    }
  },
  { title: 1 }
);
// Returns documents 101 and 102; does not extract a specific array element.
~~~

**Projection `$elemMatch`** sits in the second argument to **select the returned array element**:

~~~javascript
lab.courses.find(
  { status: "published" },
  {
    title: 1,
    grades: {
      $elemMatch: { passed: true }
    }
  }
);
// Still returns published documents, even without any grade where passed:true.
~~~

You can place both in one query, with **different purposes**:

~~~javascript
lab.courses.find(
  { "grades.score": { $gte: 90 } },
  {
    title: 1,
    grades: {
      $elemMatch: { passed: true }
    }
  }
);
~~~

The query selects courses `101` and `102` because they **have a score of 90 or higher**, yet the projection picks the **first grade with `passed: true`**. Consequently:

- `101` returns `Binh`, score **89**.
- `102` returns `Dung`, score **77**.

The output faithfully matches the two conditions placed in **two different positions**, though it may surprise an author who assumed projection always returns the element that caused the document to match the filter.

### 4.5. $elemMatch with Arrays of Simple Values

Beyond objects, arrays can hold numbers or strings. For instance, `ratings` on course `101` is:

~~~javascript
[3, 5, 4, 5]
~~~

Get the **first rating of 4 or higher**:

~~~javascript
lab.courses.find(
  { _id: 101 },
  {
    ratings: {
      $elemMatch: { $gte: 4 }
    }
  }
);
~~~

Result:

~~~javascript
{ _id: 101, ratings: [5] }
~~~

Because `5` is the first element satisfying `$gte: 4`, the `4` and the trailing `5` are **not** returned.

Avoid writing `{ ratings: { $elemMatch: { value: 4 } } }` when the array only holds **numbers**, since a `value` condition only makes sense for an array of **objects having a `value` field**.

## 5. $slice in Projection: Slicing Arrays by Position

### 5.1. Two Syntax Forms

`$slice` does not inspect element values; it limits an array slice by position:

~~~javascript
// Form 1: get the first or last n elements.
db.collection.find(
  { /* filter */ },
  { arrayField: { $slice: n } }
);

// Form 2: skip `skip` elements, return at most `limit` elements.
db.collection.find(
  { /* filter */ },
  { arrayField: { $slice: [skip, limit] } }
);
~~~

In the second form, **limit must be a positive integer**. `skip` can be positive, 0, or negative.

| Expression | Meaning for Array |
| --- | --- |
| `{ $slice: 2 }` | First two elements |
| `{ $slice: -2 }` | Last two elements |
| `{ $slice: [0, 2] }` | Starting from index 0, take two elements |
| `{ $slice: [1, 2] }` | Skip the first element, then take two elements |
| `{ $slice: [-3, 2] }` | Start at the third position from the end, take two elements |
| `{ $slice: [100, 2] }` | Returns an empty array if skip exceeds array length |

Element indices start at **0**. The array `["BSON", "CRUD", "Query", "Indexes", "Aggregation"]` has index 0 as `"BSON"` and index 4 as `"Aggregation"`.

### 5.2. Taking Leading Elements

~~~javascript
lab.courses.find(
  { _id: 101 },
  { title: 1, lessons: { $slice: 2 } }
);
~~~

Result:

~~~javascript
{
  _id: 101,
  title: "MongoDB Fundamentals",
  lessons: ["BSON", "CRUD"]
}
~~~

If the array has fewer than two elements, MongoDB returns all existing elements; `$slice` does not pad dummy values to meet the count.

### 5.3. Taking Trailing Elements

~~~javascript
lab.courses.find(
  { _id: 101 },
  { title: 1, lessons: { $slice: -2 } }
);
~~~

Result:

~~~javascript
{
  _id: 101,
  title: "MongoDB Fundamentals",
  lessons: ["Indexes", "Aggregation"]
}
~~~

**`$slice: -2` preserves the natural order of the last two elements**; it does not reverse the array.

### 5.4. Slicing from a Specific Position

~~~javascript
lab.courses.find(
  { _id: 101 },
  { title: 1, lessons: { $slice: [1, 2] } }
);
~~~

Result:

~~~javascript
{
  _id: 101,
  title: "MongoDB Fundamentals",
  lessons: ["CRUD", "Query"]
}
~~~

Here `skip = 1` skips `"BSON"`, and `limit = 2` returns `"CRUD"` and `"Query"`. This slices **a subarray within each document**, unlike `cursor.skip()` which skips **documents in the result set**.

### 5.5. Negative Index in [skip, limit]

~~~javascript
lab.courses.find(
  { _id: 101 },
  { lessons: { $slice: [-3, 2] } }
);
~~~

The array has five elements; position `-3` from the end corresponds to index 2, so the result is:

~~~javascript
{ _id: 101, lessons: ["Query", "Indexes"] }
~~~

If the absolute value of a negative skip exceeds the array length, the starting point clamps to the **beginning of the array**. With a positive skip beyond array length, the result is an **empty array**.

### 5.6. Empty Arrays and Missing Fields

~~~javascript
lab.courses.find(
  { _id: { $in: [104, 105] } },
  { title: 1, lessons: { $slice: 3 }, grades: { $slice: 2 } }
).sort({ _id: 1 });
~~~

Relevant output:

~~~javascript
{ _id: 104, title: "Query Practice", lessons: [], grades: [] }
{ _id: 105, title: "Mongo Express", lessons: ["Find", "Projection"] }
~~~

The difference:

- `104` **has** `grades: []`; `$slice` returns an **empty array**.
- `105` **does not have** `grades`; projection does not fabricate a `grades` field.
- `105` has two lessons, fewer than limit 3; both are returned.

This contrasts with **projection `$elemMatch`**: when the array exists but has no matching element, the array field is **omitted from the result** rather than returned as `[]`.

### 5.7. $slice and Inclusion/Exclusion Projection

An easily overlooked detail: **`$slice` on its own is treated as an exclusion projection**. Therefore, the query:

~~~javascript
lab.courses.find(
  { _id: 101 },
  { lessons: { $slice: 2 } }
);
~~~

can **still return all other fields** of the document, merely shortening `lessons`. If an API should only return `title` and the first two lessons, explicitly declare the fields to include:

~~~javascript
lab.courses.find(
  { _id: 101 },
  {
    _id: 0,
    title: 1,
    lessons: { $slice: 2 }
  }
);
~~~

When using an inclusion projection with nested fields, `$slice` on a nested array can cause **sibling fields inside the object** to be omitted. Example:

~~~javascript
lab.courses.find(
  { _id: 101 },
  {
    title: 1,
    "details.topics": { $slice: 2 }
  }
);
~~~

The result keeps the sliced `details.topics`, yet **does not automatically keep `details.language` or `details.category`**. If you need those fields, declare them in the inclusion projection:

~~~javascript
lab.courses.find(
  { _id: 101 },
  {
    title: 1,
    "details.language": 1,
    "details.category": 1,
    "details.topics": { $slice: 2 }
  }
);
~~~

To avoid **path collision** errors, do not simultaneously apply `$slice` to an array and project a child path of that same array in the same projection argument; split into multiple `$project` stages in aggregation instead.

### 5.8. $slice Does Not Perform Sorting

If `grades` is `[66, 89, 92]`, then:

~~~javascript
lab.courses.find(
  { _id: 101 },
  { grades: { $slice: 1 } }
);
~~~

takes the **first element in array order**, which is score 66, **not the highest score**. `find().sort({ "grades.score": -1 })` sorts the **documents**, rather than sorting elements inside each array before `$slice`.

To retrieve the best element by an attribute, use another approach: store the array in the desired order or use aggregation with an appropriate array sorting operation (such as `$sortArray` in supported MongoDB versions) before limiting elements.

## 6. Positional Operator $ in Projection

### 6.1. Syntax and Semantics

The positional operator `$` in **projection** has the syntax:

~~~javascript
db.collection.find(
  { arrayField: { /* condition */ } },
  { "arrayField.$": 1 }
);
~~~

The `$` sits at the **end of the field path**, retrieving the **first element of the array matching the query condition**.

Example with the grades array:

~~~javascript
lab.courses.find(
  { _id: 101, "grades.score": { $gte: 80 } },
  {
    title: 1,
    "grades.$": 1
  }
);
~~~

Result:

~~~javascript
{
  _id: 101,
  title: "MongoDB Fundamentals",
  grades: [{ student: "Binh", score: 89, passed: true }]
}
~~~

In document 101, `Binh` is the first element with score 80 or above; `Chi` also qualifies but appears later, so she is not returned.

### 6.2. The Array Condition Lives in the Filter

This is the major difference from projection `$elemMatch`: the `$` operator typically takes the element satisfying the **condition written in the filter**, whereas `$elemMatch` in projection accepts a condition **directly inside the projection**.

Example finding all courses with a student scoring 90 or higher and returning the first matching element:

~~~javascript
lab.courses.find(
  { "grades.score": { $gte: 90 } },
  {
    title: 1,
    "grades.$": 1
  }
).sort({ _id: 1 });
~~~

Result:

~~~javascript
{ _id: 101, title: "MongoDB Fundamentals",
  grades: [{ student: "Chi", score: 92, passed: true }] }

{ _id: 102, title: "MongoDB Advanced",
  grades: [{ student: "Hoa", score: 95, passed: true }] }
~~~

Both documents are selected due to the condition on `grades.score`, and only the **first matching grade** is returned in each document.

### 6.3. Multiple Conditions on the Same Element: $elemMatch in the Filter

Suppose you need a student who has both `score >= 80` and `passed: true`. Use **query `$elemMatch`** to ensure both conditions apply to **one element**:

~~~javascript
lab.courses.find(
  {
    grades: {
      $elemMatch: {
        score: { $gte: 80 },
        passed: true
      }
    }
  },
  {
    title: 1,
    "grades.$": 1
  }
).sort({ _id: 1 });
~~~

Result:

~~~javascript
{ _id: 101, title: "MongoDB Fundamentals",
  grades: [{ student: "Binh", score: 89, passed: true }] }

{ _id: 102, title: "MongoDB Advanced",
  grades: [{ student: "Hoa", score: 95, passed: true }] }
~~~

Using a condition like:

~~~javascript
{
  "grades.score": { $gte: 80 },
  "grades.passed": true
}
~~~

can let **two different elements** satisfy the two conditions individually, when no single element satisfies both. That form does not substitute for `$elemMatch` when same-element matching is required, and also produces unpredictable results when paired with positional projection.

### 6.4. Important Limitations of Positional $

When using projection `"grades.$": 1`, keep in mind:

1. **Only one positional `$` per projection.** Do not use both `"grades.$"` and `"ratings.$"` in the same projection.
2. **There should be only one array field acting as the element-selection condition** in the filter; putting multiple distinct arrays in the filter can lead to undefined positional projection behavior.
3. **There should be only one condition applied to the projected array**; if you need multiple conditions on the same element, wrap them inside **query `$elemMatch`**.
4. **`$` must appear at the end of the field path**, e.g. `"grades.$"`, not `"grades.$.score"`.
5. **Do not combine `$slice` inside the positional `$` expression itself**, such as `{ "grades.$": { $slice: 1 } }`.
6. **Do not confuse it with `$` in update commands.** Projection `$` only trims read output, while positional update `$` modifies the matching array element in the database.
7. **Use caution with `sort()` on a repeated array field**: document sorting does not guarantee the projected element is “first/highest” in the way a reader might assume.

Modern MongoDB versions may allow specifying positional projection on an array field **different from the one in the query**, though results require careful attention to array conditions and array sizes. For clarity, the practice examples here use the **same `grades` array referenced in the filter**.

## 7. Comparing $elemMatch and Positional $ on the Same Requirement

Requirement: find published courses, displaying the **first student with `passed: true`**.

Approach 1 — Projection `$elemMatch` accepts the condition right in the projection:

~~~javascript
lab.courses.find(
  { status: "published" },
  {
    title: 1,
    grades: { $elemMatch: { passed: true } }
  }
);
~~~

- Returns published courses **even if they have no passed students**, though the `grades` field may be omitted in the output.
- From course 101, picks `Binh`.
- From course 102, picks `Dung`.

Approach 2 — Positional `$` uses the condition in the filter:

~~~javascript
lab.courses.find(
  {
    status: "published",
    "grades.passed": true
  },
  {
    title: 1,
    "grades.$": 1
  }
);
~~~

- Returns only published courses **that have at least one passed student**.
- From course 101, picks `Binh`.
- From course 102, picks `Dung`.
- Courses 104 and 105 are not returned because they **fail the filter**.

When you need to **filter documents** and **specify an independent display condition**, use projection `$elemMatch`. When you want the element **that caused the document to match the filter**, positional `$` usually expresses intent more directly, provided you respect the limits on array fields in the filter.

## 8. When You Need Multiple Elements: Switch to Aggregation $filter

Both `$elemMatch` projection and `$` positional projection are limited to **the first matching element**. If the requirement is to display **all students with score >= 85**, use `$filter` in an **aggregation pipeline**:

~~~javascript
lab.courses.aggregate([
  { $match: { status: "published" } },
  {
    $project: {
      title: 1,
      highScores: {
        $filter: {
          input: { $ifNull: ["$grades", []] },
          as: "grade",
          cond: { $gte: ["$$grade.score", 85] }
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Results for the two courses with scores from 85:

~~~javascript
{
  _id: 101,
  title: "MongoDB Fundamentals",
  highScores: [
    { student: "Binh", score: 89, passed: true },
    { student: "Chi", score: 92, passed: true }
  ]
}
{
  _id: 102,
  title: "MongoDB Advanced",
  highScores: [
    { student: "Hoa", score: 95, passed: true },
    { student: "Minh", score: 95, passed: true }
  ]
}
~~~

Courses 104 and 105 are also `published`, yet `highScores` is `[]` because `$ifNull` turns missing/null fields into empty arrays before filtering.

`$filter` has three main parts:

- `input`: input array, which can be an expression.
- `as`: variable name representing a single element.
- `cond`: logical expression evaluated per element (e.g., `$$grade.score`).

`$filter` output **preserves the original order** of matching elements. If you want to cap the count, you can use `$filter`'s `limit` parameter in supported MongoDB versions, or apply the **aggregation `$slice` expression** after filtering.

### 8.1. $slice in find() vs. $slice in Aggregation

Same name, two contexts:

~~~javascript
// Projection operator in find():
lab.courses.find(
  { _id: 101 },
  { lessons: { $slice: 2 } }
);

// Expression operator in aggregation:
lab.courses.aggregate([
  { $match: { _id: 101 } },
  {
    $project: {
      firstTwoLessons: { $slice: ["$lessons", 2] }
    }
  }
]);
~~~

Key differences:

| Context | Syntax | Effect |
| --- | --- | --- |
| `find()` projection | `{ lessons: { $slice: 2 } }` | Slices the `lessons` field array when returning the document |
| `$project` aggregation | `{ firstTwoLessons: { $slice: ["$lessons", 2] } }` | Evaluates an **array expression** and assigns it to an output field |
| `$push` update modifier | `{ $push: { lessons: { $each: [...], $slice: 5 } } }` | **Mutates the stored array** in the database to enforce a cap |

In aggregation, operations combine flexibly. For instance, keep only the **first two students scoring >= 85**:

~~~javascript
lab.courses.aggregate([
  { $match: { _id: 101 } },
  {
    $project: {
      title: 1,
      firstTwoHighScores: {
        $slice: [
          {
            $filter: {
              input: "$grades",
              as: "g",
              cond: { $gte: ["$$g.score", 85] }
            }
          },
          2
        ]
      }
    }
  }
]);
~~~

The `firstTwoHighScores` result on course 101 is `Binh` and `Chi`. These are the **first two elements in original array order satisfying the condition**, not necessarily the top two scores if the array is unsorted.

### 8.2. Getting an Element at a Specific Index

If the task requires the exact element at **index 2**, rather than the first element matching a condition, use `$arrayElemAt` in aggregation:

~~~javascript
lab.courses.aggregate([
  { $match: { _id: 101 } },
  {
    $project: {
      title: 1,
      lessonAtIndex2: { $arrayElemAt: ["$lessons", 2] }
    }
  }
]);
~~~

The `lessonAtIndex2` result is the string `"Query"`. This returns the **element value itself**, rather than wrapping it in a single-element array like positional projection.

## 9. Rules When an Array Sits Inside a Nested Object

In the sample data, `details` is an object, and `details.topics` is an array:

~~~javascript
{
  details: {
    category: "database",
    topics: ["documents", "arrays", "indexes"],
    language: "vi"
  }
}
~~~

Using `$slice` with a dotted path:

~~~javascript
lab.courses.find(
  { _id: 101 },
  {
    _id: 0,
    title: 1,
    "details.topics": { $slice: 2 }
  }
);
~~~

Result:

~~~javascript
{
  title: "MongoDB Fundamentals",
  details: {
    topics: ["documents", "arrays"]
  }
}
~~~

To also retain category and language, request them explicitly:

~~~javascript
lab.courses.find(
  { _id: 101 },
  {
    _id: 0,
    title: 1,
    "details.category": 1,
    "details.language": 1,
    "details.topics": { $slice: 2 }
  }
);
~~~

Avoid projection path collisions:

~~~javascript
// Can trigger a path collision error:
// projecting the grades array with $slice while also
// projecting a child field grades.student in the same projection.
lab.courses.find(
  { _id: 101 },
  {
    grades: { $slice: 2 },
    "grades.student": 1
  }
);
~~~

If you need to **slice an array and then keep only certain fields of each object**, move to aggregation with `$slice` and `$map` (or consecutive `$project` stages), rather than forcing two conflicting projections on the same path.

Example slicing the first two elements and returning only student names:

~~~javascript
lab.courses.aggregate([
  { $match: { _id: 101 } },
  {
    $project: {
      _id: 1,
      studentNames: {
        $map: {
          input: { $slice: ["$grades", 2] },
          as: "g",
          in: "$$g.student"
        }
      }
    }
  }
]);
~~~

`studentNames` returns `["An", "Binh"]`, because the `grades` array was sliced to its first two elements before mapping to `student`.

## 10. Limitations and Gotchas to Watch Out For

### 10.1. Querying MongoDB Views

For a MongoDB **standard view**, `find()` **does not support** the array projection operators `$elemMatch`, `$slice`, and positional `$` per official documentation rules.

If querying a view instead of a physical collection, check using an **aggregation pipeline** with `$project`, `$filter`, or the `$slice` expression to produce equivalent results where your server version and deployment support it.

### 10.2. $elemMatch Projection Does Not Support $text Inside

Do not embed a `$text` query inside a `$elemMatch` projection condition; it is not an element-level array matcher. If you need full-text search followed by element display, separate document selection and array transformation per the appropriate APIs/features.

### 10.3. Projection Does Not Modify Source Data

A `find()` command with `$slice: 2` **does not truncate the stored array** to two elements. A `find()` with `$elemMatch` also **does not delete non-matching elements**.

If you need to modify array elements in the database, that is a separate update task using operators like `$set`, `$push`, `$pull`, `$[]`, or `$[identifier]` with proper write controls.

### 10.4. Do Not Assume Projection Turns a Query into a Covered Query

Projection can shrink the payload **returned to the client**, yet the server still has to locate documents and determine matching array elements. Returning fewer elements does not automatically guarantee an index can satisfy the whole query without reading documents.

Particularly for arrays, MongoDB can create a **multikey index**; however, projecting array fields typically still requires reading document contents to decide which elements to return. To understand real performance, run:

~~~javascript
lab.courses.find(
  { "grades.score": { $gte: 90 } },
  { title: 1, "grades.$": 1 }
).explain("executionStats");
~~~

Inspect `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, `nReturned`, and I/O on a realistic dataset. A sample collection of five documents does not reflect index effectiveness in a large environment.

### 10.5. Projection Is Not an Authorization Mechanism

An API using `{ title: 1, grades: { $slice: 1 } }` only trims fields returned **in that specific call**. If the same account has direct read privileges on the collection, a client can still send another query to retrieve the entire array. Protecting sensitive data must rely on access permissions, API boundaries, and system security controls, not solely on a projection.

### 10.6. Large Array Lengths and Document Design

If an array such as activity history grows endlessly, `$slice` helps limit the returned portion, yet the **underlying document still contains the entire array**. BSON document size limits and document update costs do not disappear.

For unbounded histories, consider splitting into a separate collection with document-level pagination and appropriate indexes. If business logic always needs only the most recent few elements, consider capping the array at write time, though that is a separate data-modeling decision.

## 11. Common Mistakes

| Error or Unexpected Result | Cause | How to Handle |
| --- | --- | --- |
| `$elemMatch` returns just one grade even though many match | Projection `$elemMatch` returns only the **first element** | Use aggregation `$filter` when all are needed |
| Document still appears even when `$elemMatch` does not match | Condition is in projection, not filter | Add the condition to the filter to exclude documents |
| Array field is omitted from output | No element matches `$elemMatch` or field is absent | Check conditions and distinguish missing from `[]` |
| `$slice: -2` does not return a reversed array | Negative count takes trailing elements in original order | Use an array transformation if reversal is needed |
| `$slice: [1, 2]` does not skip a document | `$slice` slices **elements inside the array** | Use `cursor.skip()` for documents |
| `$slice` output has more fields than expected | Standalone `$slice` acts as an exclusion projection | Declare explicit inclusion: `{ title: 1, lessons: { $slice: 2 } }` |
| Positional `$` returns an unexpected element | Filter spans multiple array fields or conditions across different elements | Use one clear array condition, or query `$elemMatch` when needed |
| `"grades.$.score": 1` is invalid | `$` must be at the end of the field path | Use `"grades.$": 1` and read the field from the returned object |
| Path collision error | Projecting `grades` with `$slice` and `grades.student` simultaneously | Use multi-stage aggregation |
| Trying to use `$slice` projection inside `$project` aggregation | Different contexts have different syntax | Use `{ $slice: ["$grades", 2] }` |
| Trying to mutate data with `find()` projection | Projection affects only read output | Use update operators to modify stored data |
| Using specialized array projections on a view | These array projections have restrictions on `find()` over views | Switch to an appropriate aggregation pipeline |
| Expecting the “highest score” element but getting the first | `$elemMatch`, `$`, and `$slice` do not sort arrays | Sort the array first before selecting elements |

## 12. Practice Exercises

The exercises below use `lab.courses` from Section 2; no collection updates are needed.

### Exercise 1 — Fetching First and Last Lessons

Write two queries for course `101`:

1. Return `_id`, `title`, and the first three lessons.
2. Return `_id`, `title`, and the last two lessons.

Hint:

~~~javascript
lab.courses.find(
  { _id: 101 },
  { title: 1, lessons: { $slice: 3 } }
);

lab.courses.find(
  { _id: 101 },
  { title: 1, lessons: { $slice: -2 } }
);
~~~

The `lessons` outputs are respectively:

~~~javascript
["BSON", "CRUD", "Query"]
["Indexes", "Aggregation"]
~~~

### Exercise 2 — Slicing by Position

From course `101`, skip the first two lessons and take the next two.

~~~javascript
lab.courses.find(
  { _id: 101 },
  { lessons: { $slice: [2, 2] }, _id: 1 }
);
~~~

`lessons` returns `["Query", "Indexes"]`. Because the projection has `$slice` and `_id: 1` without another inclusion field such as `title: 1`, other fields may still be returned; to return strictly `_id` and `lessons`, use explicit non-`_id` inclusion where appropriate or aggregation `$project`.

### Exercise 3 — Displaying the First High-Scoring Student

Use projection `$elemMatch` to find the **first grade with `score >= 90`** for all `published` courses.

~~~javascript
lab.courses.find(
  { status: "published" },
  {
    title: 1,
    grades: { $elemMatch: { score: { $gte: 90 } } }
  }
);
~~~

Identify why courses 104 and 105 still appear without a `grades` field in the result.

### Exercise 4 — Filtering Documents and Retrieving the Same Qualifying Element

Select only courses that have a student with both `passed: true` and `score >= 90`. Return the first grade satisfying both conditions using positional `$`.

~~~javascript
lab.courses.find(
  {
    grades: {
      $elemMatch: {
        passed: true,
        score: { $gte: 90 }
      }
    }
  },
  { title: 1, "grades.$": 1 }
);
~~~

Results must include course `101` with `Chi` and `102` with `Hoa`.

### Exercise 5 — $elemMatch on a Numeric Array

On `ratings` of course `101`, retrieve the first number satisfying `$gte: 4`.

~~~javascript
lab.courses.find(
  { _id: 101 },
  { ratings: { $elemMatch: { $gte: 4 } } }
);
~~~

Explain why the result is `[5]` instead of `[5, 4, 5]`.

### Exercise 6 — Retrieving All Matching Elements

Write an aggregation returning every grade with `score >= 85` for each course, preserving array order. Contrast with `$elemMatch` projection to explain the difference between “all elements” and “first element”.

~~~javascript
lab.courses.aggregate([
  {
    $project: {
      title: 1,
      gradesAtLeast85: {
        $filter: {
          input: { $ifNull: ["$grades", []] },
          as: "g",
          cond: { $gte: ["$$g.score", 85] }
        }
      }
    }
  }
]);
~~~

### Exercise 7 — Real-World API Scenario

A course-listing endpoint needs to:

- Select only `published` documents.
- Return `title`.
- Return the first two lessons.
- Return the first student with a score of 90 or higher.
- Omit `_id` from the JSON response.

Write a projection combining `$slice` and `$elemMatch` on **two different array fields**:

~~~javascript
lab.courses.find(
  { status: "published" },
  {
    _id: 0,
    title: 1,
    lessons: { $slice: 2 },
    grades: {
      $elemMatch: { score: { $gte: 90 } }
    }
  }
);
~~~

Observe courses with no score >= 90: the `grades` field may be omitted. If the API contract requires every response to include `grades: []`, use aggregation to normalize results to the contract.

## 13. Key Takeaways

- **`$elemMatch` projection** retrieves the **first element matching a condition placed inside the projection**. If none match, the array field may be omitted from the output, while the document is still returned if it matches the filter.
- **`$slice` projection** slices **by position**, not by value; positive counts take from the start, negative counts take from the end, and `[skip, limit]` selects a range.
- **Positional `$` projection** retrieves the **first element matching the array condition in the filter**, often paired with query `$elemMatch` when multiple conditions must apply to the same element.
- **`$filter` in aggregation** is appropriate when you need **all matching elements** or complex array processing; the `$slice` expression and `$arrayElemAt` handle positional slicing/selection in pipelines.
- Projection only formats **read results**; it does not mutate stored data and does not substitute for indexing, security, or data-model design.

### Official References

- [Projection — MongoDB Manual](https://www.mongodb.com/docs/manual/tutorial/project-fields-from-query-results/) — inclusion/exclusion rules when reading documents.
- [$elemMatch — Projection Operator](https://www.mongodb.com/docs/manual/reference/operator/projection/elemMatch/) — first element matching a projection condition.
- [$slice — Projection Operator](https://www.mongodb.com/docs/manual/reference/operator/projection/slice/) — retrieving leading, trailing, and sliced array segments.
- [$ — Positional Projection Operator](https://www.mongodb.com/docs/manual/reference/operator/projection/positional/) — retrieving the element matched by the filter and its limitations.
- [$elemMatch — Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/elemMatch/) — multiple conditions on the same array element.
- [$filter — Aggregation Expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/filter/) — retaining multiple array elements matching a condition.
- [$slice — Aggregation Expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/slice/) — slicing arrays inside an aggregation pipeline.
