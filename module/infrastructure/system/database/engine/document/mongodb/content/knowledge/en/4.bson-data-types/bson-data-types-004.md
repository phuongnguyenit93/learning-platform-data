# Strings, Booleans, Objects, and Nested Arrays in MongoDB

MongoDB stores data as **BSON (Binary JSON) documents**. When working in `mongosh`, a document looks much like a JavaScript object or JSON, yet the underlying data is BSON-encoded with explicit types. To design and query documents accurately, you need to understand four types that frequently appear together: **strings**, **booleans**, **embedded objects/documents**, and **arrays**, especially when objects and arrays are nested multiple levels deep.

This lesson uses the `learners` collection in a practice database. All illustrative commands can be run in `mongosh` after connecting to a MongoDB instance with read/write privileges. Names, emails, and course codes are sample data only.

## 1. Looking from JSON to BSON

Consider a document describing a learner:

```javascript
{
  _id: "u101",
  name: "Linh",
  active: true,
  profile: {
    location: {
      city: "Hanoi",
      country: "VN"
    },
    notifications: {
      email: false,
      push: true
    }
  },
  interests: ["MongoDB", "Java"],
  courses: [
    {
      code: "MDB101",
      completed: false,
      results: [
        { part: "quiz", score: 9 },
        { part: "lab", score: 8 }
      ]
    },
    {
      code: "JAVA101",
      completed: true,
      results: [
        { part: "lab", score: 7 }
      ]
    }
  ]
}
```

Structural breakdown:

| Field Path | Sample Value | BSON Type | Role |
| --- | --- | --- | --- |
| `name` | `"Linh"` | String | Text |
| `active` | `true` | Boolean | True/false status |
| `profile` | `{ location: ..., notifications: ... }` | Object/document | Groups data belonging to one entity |
| `profile.location.city` | `"Hanoi"` | String | String inside a nested object |
| `profile.notifications.email` | `false` | Boolean | Flag inside a nested object |
| `interests` | `["MongoDB", "Java"]` | Array | List of strings |
| `courses` | `[{...}, {...}]` | Array | List of objects |
| `courses[0].results` | `[{part:"quiz",...},...]` | Array | Array of objects inside an object inside an array |

Document hierarchy diagram:

```text
learner (document)
├── _id: "u101"                      String
├── name: "Linh"                    String
├── active: true                    Boolean
├── profile                         Object
│   ├── location                    Object
│   │   ├── city: "Hanoi"           String
│   │   └── country: "VN"           String
│   └── notifications               Object
│       ├── email: false            Boolean
│       └── push: true              Boolean
├── interests                       Array<String>
│   ├── [0] "MongoDB"
│   └── [1] "Java"
└── courses                         Array<Object>
    ├── [0]                         Object
    │   ├── code: "MDB101"          String
    │   ├── completed: false        Boolean
    │   └── results                 Array<Object>
    │       ├── [0] {part:"quiz", score:9}
    │       └── [1] {part:"lab", score:8}
    └── [1]                         Object
        ├── code: "JAVA101"
        ├── completed: true
        └── results                 Array<Object>
            └── [0] {part:"lab", score:7}
```

MongoDB does not require every document in the same collection to share the exact same set of fields unless schema validation is enabled. However, a given field should maintain a **consistent type** across documents so queries, indexes, and application code do not encounter unexpected edge cases.

## 2. String: Character Sequences

Strings are used for names, descriptions, emails, textual identifiers, labels, and values that are inherently text. BSON stores strings in **UTF-8**, so they can hold Vietnamese characters, diacritics, and Unicode characters.

```javascript
{
  name: "Nguyễn Thị Linh",
  language: "vi",
  courseCode: "MDB101",
  notes: "Completed document reading section",
  active: "true"   // Note: this is a string, NOT a boolean
}
```

In `mongosh` JavaScript syntax, both single and double quotes create strings. When formatted as standard JSON, keys and string values use double quotes.

Example distinguishing strings from numbers:

```javascript
{ studentCode: "00125" }  // Identifier: preserves leading zeros
{ studentCode: 125 }      // Numeric type: cannot represent "00125" verbatim
```

Identifiers such as student codes or postal codes should usually be strings if they are not meant for arithmetic. Conversely, values requiring numerical comparison such as `score` or `quantity` should be stored in an appropriate numeric type, not `"9"` instead of `9`.

### Querying Strings

```javascript
db.learners.find({ name: "Linh" })
db.learners.find({ "profile.location.city": "Hanoi" })
```

Standard string comparisons follow the query's collation rules; do not assume uppercase, lowercase, or Vietnamese diacritics are ignored automatically. When language-aware or case-insensitive comparisons are needed, use a properly configured collation or an explicit query expression.

Example finding names starting with `L` using a regex:

```javascript
db.learners.find({ name: { $regex: "^L", $options: "i" } })
```

Inside JavaScript strings, special characters such as quotes, backslashes, and newlines must be escaped per string syntax rules:

```javascript
{ note: "Student said: \"I understand BSON\"" }
```

## 3. Boolean: True or False

BSON booleans have exactly two values:

- `true`: yes, enabled, on.
- `false`: no, disabled, off.

```javascript
{
  active: true,
  emailVerified: false,
  settings: {
    newsletter: true,
    pushNotification: false
  }
}
```

Distinguish clearly:

| Notation | Type | Is It Boolean? |
| --- | --- | --- |
| `true` | Boolean | Yes |
| `false` | Boolean | Yes |
| `"true"` | String | No |
| `"false"` | String | No |
| `1` | Number | No |
| `0` | Number | No |
| `null` | Null | No |
| Field does not exist | Missing field | No |

MongoDB **does not treat** the string `"true"` as equivalent to boolean `true` in equality queries:

```javascript
db.learners.find({ active: true })      // Matches boolean true
db.learners.find({ active: "true" })    // Matches string "true"
```

The states `false`, `null`, and **missing field** carry different meanings. For instance, `emailVerified: false` may mean known to be unverified, whereas an absent `emailVerified` field may mean the data has not been collected yet. Define conventions for each case when designing your application.

Check whether a field exists:

```javascript
db.learners.find({ active: { $exists: true } })
db.learners.find({ active: { $exists: false } })
```

Check for an actual boolean type:

```javascript
db.learners.find({ active: { $type: "bool" } })
```

Note that `{ someField: null }` can match both documents with value `null` and documents missing that field; therefore, do not use it as a substitute for checking boolean `false`.

## 4. Object: Embedded Documents

An object is a group of sub-fields nested under a field of a parent document. In BSON, this is an **embedded document**. For example:

```javascript
{
  name: "Linh",
  profile: {
    location: {
      city: "Hanoi",
      country: "VN"
    },
    notifications: {
      email: false,
      push: true
    }
  }
}
```

Here `profile`, `location`, and `notifications` are all objects. An object can hold strings, booleans, numbers, null, other objects, or arrays. The primary benefit is keeping related data inside a single document, which is convenient when the application typically reads or updates them together.

### Accessing Fields via Dot Notation

In MongoDB filters and update operators, **dot notation** writes nested field paths by joining segments with dots:

```javascript
db.learners.find({
  "profile.location.city": "Hanoi"
})

db.learners.find({
  "profile.notifications.email": false
})
```

Field paths containing `.` must be quoted as strings when used as keys. Querying only a nested field allows the parent object to contain additional fields.

Compare these two approaches:

```javascript
// Sub-field query: only requires city to match
db.learners.find({
  "profile.location.city": "Hanoi"
})

// Compares the entire embedded document at the location field
db.learners.find({
  "profile.location": {
    city: "Hanoi",
    country: "VN"
  }
})
```

The second predicate checks **equality against the entire object** at `profile.location`. It requires both the contents and field order of the embedded document to match the supplied value; adding a field or reordering fields can break the match. When you only need to check specific attributes, dot notation is more flexible and maintainable.

### Updating a Field Inside an Object

```javascript
db.learners.updateOne(
  { _id: "u101" },
  { $set: { "profile.location.city": "Da Nang" } }
)
```

Using `$set` with a specific path changes `city` while preserving `country` and `notifications`. By contrast:

```javascript
db.learners.updateOne(
  { _id: "u101" },
  { $set: { profile: { nickname: "L" } } }
)
```

The second command **replaces the entire value** of `profile` with a new object, removing all previous fields inside `profile`. Therefore, when modifying only one attribute, update its exact path.

## 5. Array: Ordered Lists

BSON arrays preserve element order and support **0-based index** access:

```javascript
{
  interests: ["MongoDB", "Java", "Spring"],
  flags: [true, false, true],
  scores: [7, 8, 9]
}
```

`interests[0]` is `"MongoDB"`, and `interests[1]` is `"Java"`. While BSON allows arrays to contain mixed types, practical schema design should keep elements uniform in meaning and type whenever possible:

```javascript
// Sensible: list of skill names
{ interests: ["MongoDB", "Java"] }

// Valid BSON, but hard to handle consistently in application code
{ interests: ["MongoDB", true, { name: "Java" }] }
```

### Querying an Element in an Array

```javascript
db.learners.find({ interests: "MongoDB" })
```

This condition matches documents whose `interests` array contains `"MongoDB"`; you do not need to supply the whole array.

```javascript
db.learners.find({ interests: { $all: ["MongoDB", "Java"] } })
db.learners.find({ "interests.0": "MongoDB" })
db.learners.find({ interests: { $size: 2 } })
```

- `$all`: the array must contain all listed values, in any order.
- `interests.0`: checks the element at index `0` (beginning of the array).
- `$size`: requires the array length to match exactly.

Compare with an exact array equality query:

```javascript
db.learners.find({ interests: ["MongoDB", "Java"] })
```

With full-array equality, both element count and element order must match. `["Java", "MongoDB"]` is a different array.

## 6. Objects Inside Arrays and Arrays Inside Objects

A common pattern is a learner document containing a `courses` array, where each `courses` element contains a `results` array. This is two levels of nested arrays and objects:

```javascript
{
  courses: [
    {
      code: "MDB101",
      completed: false,
      results: [
        { part: "quiz", score: 9 },
        { part: "lab", score: 8 }
      ]
    },
    {
      code: "JAVA101",
      completed: true,
      results: [
        { part: "lab", score: 7 }
      ]
    }
  ]
}
```

You can query fields inside objects within an array:

```javascript
db.learners.find({ "courses.code": "MDB101" })
db.learners.find({ "courses.completed": true })
db.learners.find({ "courses.results.part": "quiz" })
db.learners.find({ "courses.results.score": { $gte: 9 } })
```

These predicates check that **at least one element matches** along the specified path. When multiple conditions appear together, be careful about whether they must hold on the **same element** or can match different elements.

### The Same-Element Problem: Why Is `$elemMatch` Needed?

Suppose the requirement is: "Find learners who have **a course** with code `MDB101` and `completed: true`."

Writing the query like this can produce unintended matches:

```javascript
db.learners.find({
  "courses.code": "MDB101",
  "courses.completed": true
})
```

Because these are two separate conditions on the array path, `code` can match `courses[0]` while `completed` matches `courses[1]`. With the sample data, a learner could match even though `MDB101` is incomplete.

To require **the same object inside `courses`** to satisfy both predicates, use `$elemMatch`:

```javascript
db.learners.find({
  courses: {
    $elemMatch: {
      code: "MDB101",
      completed: true
    }
  }
})
```

Extending further: "Has course `MDB101` with **a quiz result scoring 9 or higher**":

```javascript
db.learners.find({
  courses: {
    $elemMatch: {
      code: "MDB101",
      results: {
        $elemMatch: {
          part: "quiz",
          score: { $gte: 9 }
        }
      }
    }
  }
})
```

The outer `$elemMatch` binds `code` and `results` to the same course object; the inner `$elemMatch` binds `part` and `score` to the same result object. Without these two layers, conditions could be satisfied across separate elements of each array.

## 7. Nested Arrays

Arrays can also contain other arrays:

```javascript
{
  board: [
    ["A1", "A2", "A3"],
    ["B1", "B2", "B3"]
  ]
}
```

Suppose `board` is a row/column grid. In JavaScript:

```javascript
const board = [
  ["A1", "A2", "A3"],
  ["B1", "B2", "B3"]
];
print(board[1][2]);  // "B3"
```

When querying a BSON path with array indices, indices also start at 0:

```javascript
db.grids.find({ "board.1.2": "B3" })
```

This queries documents in the `grids` collection whose element in the second row and third column equals `"B3"`. To test with `grids`, you can insert sample data with `db.grids.insertOne({ board: [["A1","A2","A3"],["B1","B2","B3"]] })`.

Deeply nested arrays fit data that is genuinely matrix-structured. If each element has its own business meaning, objects with clearly named fields are usually more readable than positional `[1][2]` access.

## 8. End-to-End Practice in `mongosh`

Select the practice database:

```javascript
use bson_lab
```

### Step 1: Create Data Covering All Four Types

```javascript
db.learners.insertMany([
  {
    _id: "u101",
    name: "Linh",
    active: true,
    profile: {
      location: { city: "Hanoi", country: "VN" },
      notifications: { email: false, push: true }
    },
    interests: ["MongoDB", "Java"],
    courses: [
      {
        code: "MDB101",
        completed: false,
        results: [
          { part: "quiz", score: 9 },
          { part: "lab", score: 8 }
        ]
      },
      {
        code: "JAVA101",
        completed: true,
        results: [
          { part: "lab", score: 7 }
        ]
      }
    ]
  },
  {
    _id: "u102",
    name: "Mai",
    active: false,
    profile: {
      location: { city: "Da Nang", country: "VN" },
      notifications: { email: true, push: false }
    },
    interests: ["MongoDB"],
    courses: [
      {
        code: "MDB101",
        completed: true,
        results: [
          { part: "quiz", score: 10 },
          { part: "lab", score: 9 }
        ]
      }
    ]
  }
])
```

Re-running `insertMany` on the same database will trigger a duplicate key error on existing `_id` values. When repeating the exercise, use different `_id` values or clean up the sample data in your isolated environment.

### Step 2: Query by String and Boolean

```javascript
// Active learners in Hanoi
db.learners.find({
  active: true,
  "profile.location.city": "Hanoi"
})

// Learners with email notifications disabled
db.learners.find({
  "profile.notifications.email": false
})
```

With the initial sample data, both queries find `u101`.

### Step 3: Query by Array and Objects Inside an Array

```javascript
// Interested in MongoDB
db.learners.find({ interests: "MongoDB" })

// Has at least one completed MDB101 course
db.learners.find({
  courses: {
    $elemMatch: {
      code: "MDB101",
      completed: true
    }
  }
})
```

The first query matches both `u101` and `u102`; the second matches `u102` (because in `u101`, `MDB101` has `completed: false`).

### Step 4: Select Specific Fields Using Projection

```javascript
db.learners.find(
  { active: true },
  {
    _id: 0,
    name: 1,
    "profile.location.city": 1,
    interests: 1
  }
)
```

Projection returns only the fields you need. `profile.location.city` is still returned inside its nested object structure rather than being flattened into a dotted key name.

### Step 5: Update a Boolean and an Object Field

```javascript
db.learners.updateOne(
  { _id: "u101" },
  {
    $set: {
      active: false,
      "profile.notifications.email": true
    }
  }
)
```

This update changes `u101`'s active status and email notification flag without deleting sibling fields.

### Step 6: Append an Element to an Array

```javascript
db.learners.updateOne(
  { _id: "u101" },
  { $push: { interests: "Data Modeling" } }
)
```

`$push` appends an element to the end of `interests`; if you want to avoid duplicates, consider `$addToSet` where appropriate.

### Step 7: Update an Object Inside an Array Using `arrayFilters`

For example, mark `MDB101` as completed regardless of its position in the array:

```javascript
db.learners.updateOne(
  { _id: "u101" },
  { $set: { "courses.$[course].completed": true } },
  {
    arrayFilters: [
      { "course.code": "MDB101" }
    ]
  }
)
```

`$[course]` is the filtered positional operator. MongoDB updates elements in `courses` matching `course.code`; if multiple elements match, multiple elements in the same document can be updated. This is cleaner than hardcoding `"courses.0.completed"` when course ordering may change.

With two nested array levels, you can filter both the course and the result:

```javascript
db.learners.updateOne(
  { _id: "u101" },
  { $set: { "courses.$[course].results.$[result].passed": true } },
  {
    arrayFilters: [
      { "course.code": "MDB101" },
      { "result.part": "lab" }
    ]
  }
)
```

This command adds/updates `passed: true` on result objects with `part: "lab"` inside `u101`'s `MDB101` course.

### Step 8: Inspect the Document After Updates

```javascript
db.learners.findOne({ _id: "u101" })
```

Inspect `profile`, `interests`, and `courses` after the operations; unrelated objects and arrays remain intact.

## 9. Reading These Types in the MongoDB Java Driver

In the Java Sync Driver, `org.bson.Document` represents a BSON object using a structure similar to `Map<String, Object>`. You can nest `Document`, `List`, `String`, and `Boolean`:

```java
import org.bson.Document;
import java.util.List;

public class NestedBsonExample {
    public static void main(String[] args) {
        Document learner = new Document("_id", "u201")
            .append("name", "An")
            .append("active", true)
            .append("profile", new Document("city", "Hue")
                .append("notifications",
                    new Document("email", false)))
            .append("interests", List.of("MongoDB", "Java"))
            .append("courses", List.of(
                new Document("code", "MDB101")
                    .append("completed", false)));

        String name = learner.getString("name");
        Boolean active = learner.getBoolean("active");
        Document profile = learner.get("profile", Document.class);
        String city = profile.getString("city");
        List<String> interests = learner.getList("interests", String.class);
        List<Document> courses = learner.getList("courses", Document.class);

        System.out.println(name + " - " + city + " - active=" + active);
        System.out.println(interests.get(0));
        System.out.println(courses.get(0).getString("code"));
    }
}
```

This example constructs and reads a `Document` in memory without connecting to a server. To persist it, the application needs a `MongoCollection<Document>` obtained from an appropriate client/database and calls `insertOne(learner)`.

`getBoolean` can return `null` if the field is absent; typed getters can also fail if the actual document holds an unexpected type. In applications ingesting data from multiple sources, use schema validation or a mapping/input-validation layer to avoid invalid type casts.

## 10. Designing Nested Documents: When Should You Use Them?

MongoDB handles hierarchical data naturally, yet not every relationship should be embedded into a single document.

| Scenario | Typically Appropriate Design | Reason |
| --- | --- | --- |
| A learner's name and notification preferences | `profile` object | Usually read/updated together with the learner |
| Short list of interests | `interests` string array | Small size, simple semantics |
| A handful of exam results per course | `results` object array | Each result has multiple related attributes |
| Millions of time-series events for one person | Separate collection referenced by ID | Unbounded arrays cause documents to bloat |
| Many-to-many relationships shared across entities | Consider referencing other documents | Reduces duplication and avoids multi-document sync updates |

MongoDB enforces a BSON document size limit (typically **16 MiB**) and a nesting depth limit (typically **100 levels**). Therefore, do not treat a single document as a container for unbounded child records. For continuously growing arrays, consider splitting into a linked collection, bucketing/pagination, or an alternative data model.

Practical guidelines:

1. **Type consistency:** `active` should always be boolean; `interests` should always be an array of strings if that is the application's data contract.
2. **Update boundaries:** When a group of fields is routinely read and written together, an embedded document keeps operations natural and single-document writes atomic.
3. **Bounded arrays:** Arrays like interests or a finite set of results work well; large, ever-growing history arrays should be reconsidered.
4. **Avoid index dependency:** When elements carry business identifiers, use `$elemMatch` and `arrayFilters` rather than assuming an item is always at position `0`.
5. **Match queries to semantics:** When multiple conditions must hold on the same array object, use `$elemMatch`; when checking a sub-field, use dot notation.
6. **Schema validation:** BSON is typed, but a collection does not automatically enforce a uniform schema across all documents. For long-lived systems, apply `$jsonSchema` validators and validate data at the application boundary.

## 11. Common Misconceptions

| Misconception | Consequence | Correct Understanding |
| --- | --- | --- |
| `"false"` is equivalent to `false` | Boolean queries miss documents storing strings | Strings and booleans are different types |
| Missing field is equivalent to `false` | Misinterprets state and ignores uncollected data | Distinguish missing, `null`, and boolean values |
| `{ profile: { city: "Hue" } }` always finds any object with `city: "Hue"` | Fails to match if `profile` has extra fields or different field order | Use `"profile.city": "Hue"` to match a sub-field |
| `"courses.code"` and `"courses.completed"` matching means the same course | Can match across two different array elements | Use `$elemMatch` |
| Arrays are unordered sets | Whole-array equality and index lookups break | Arrays preserve order; indices are 0-based |
| `$set: { profile: {...} }` updates only a few fields inside `profile` | Overwrites and erases existing sub-fields | Use `$set` with dot notation |
| Seeing `{...}` in the shell means pure JSON | Overlooks BSON types like `ObjectId` and `Date` | JSON is a familiar display syntax; MongoDB stores BSON |

## 12. Practice Exercises

### Exercise 1: Distinguish Types

Consider the document:

```javascript
{
  title: "MongoDB",
  published: "false",
  details: {
    reviewed: false,
    tags: ["document", "BSON"]
  }
}
```

Question: Is `published` a boolean? Write a query to find documents where `details.reviewed` equals boolean `false`.

**Suggested answer:** `published` is a string. Filter:

```javascript
db.articles.find({ "details.reviewed": false })
```

### Exercise 2: Query the Same Array Element

Consider:

```javascript
{
  name: "Minh",
  tasks: [
    { code: "A", done: false },
    { code: "B", done: true }
  ]
}
```

Question: Why can the filter `{ "tasks.code": "A", "tasks.done": true }` still match this document? Rewrite it to require that task `A` is completed.

**Suggested answer:** The two conditions can match two different elements. Write:

```javascript
db.users.find({
  tasks: {
    $elemMatch: { code: "A", done: true }
  }
})
```

The sample document does not match this `$elemMatch` filter because task `A` has `done: false`.

### Exercise 3: Update an Object Without Erasing Other Fields

Document:

```javascript
{
  _id: "u301",
  settings: { theme: "light", newsletter: false }
}
```

Question: How do you change only `newsletter` to `true` while keeping `theme`?

**Suggested answer:**

```javascript
db.learners.updateOne(
  { _id: "u301" },
  { $set: { "settings.newsletter": true } }
)
```

### Exercise 4: Query Nested Arrays

Given:

```javascript
{
  groups: [
    { name: "G1", members: ["An", "Binh"] },
    { name: "G2", members: ["Chi", "Dung"] }
  ]
}
```

Question: Write a query to find documents containing **a single group** named `G2` that includes member `"Chi"`.

**Suggested answer:**

```javascript
db.teams.find({
  groups: {
    $elemMatch: {
      name: "G2",
      members: "Chi"
    }
  }
})
```

Here `members: "Chi"` matches an element of the string array inside the group object selected by `$elemMatch`.

## Conclusion

When reading a MongoDB document, identify the **data type at every level**. Strings hold text; booleans are strictly `true`/`false`; objects group related fields; arrays store ordered lists and can hold nested objects or arrays. **Dot notation** reaches nested fields, while **`$elemMatch`** ensures multiple predicates apply to the same array element. For updates, path-based `$set` and `arrayFilters` modify the intended elements without accidentally replacing an entire object or array.
