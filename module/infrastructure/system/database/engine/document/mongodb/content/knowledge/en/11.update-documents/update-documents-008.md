# Removing Elements with $pull, $pullAll, and $pop in MongoDB

## 1. Problem Statement: Removing Elements Inside a Document

A MongoDB document can contain arrays such as `tags`, `roles`, `cartItems`, `comments`, or `recentEvents`. When a tag no longer applies, a role is revoked, or a task is finished, the application typically wants to **remove elements from the array** while keeping the parent document intact.

MongoDB provides three update operators for common cases:

| Operator | How elements are selected for removal | Business Example |
| --- | --- | --- |
| **`$pull`** | Removes **all elements** equal to a given value or matching a query condition. | Remove every `"archived"` tag, every task with `status = "DONE"`, or every score below a threshold. |
| **`$pullAll`** | Removes **all occurrences** of every value in a specified list. | Revoke both `"EDITOR"` and `"REVIEWER"` roles at once. |
| **`$pop`** | Removes **one element from the beginning or end of the array**. | Drop the head of an ordered list or the tail of a simple stack. |

These operations differ in **selection criteria**, not merely syntax. When deleting a line item by `itemId`, use a condition identifying the line item—typically `$pull`. When removing **whatever element is currently last**, `$pop: 1` fits better. When removing several exact values from a string array, `$pullAll` expresses the intent directly.

In all three cases, MongoDB updates **the array stored inside the document**. It does not delete the parent document from the collection, nor does it automatically clean up related data in other collections.

### 1.1. General Command Skeleton

~~~javascript
db.collection.updateOne(
  { /* condition to match document */ },
  {
    $pull: {
      arrayField: /* value or element-matching condition */
    }
  }
);
~~~

An update command has two filtering scopes:

1. **The outer filter** selects which document(s) to update, e.g., `_id: "ORDER-1"`.
2. **The inner condition inside `$pull`** selects which elements to remove from the matched document's array.

These two scopes do not substitute for each other. A document may match the outer filter while its array contains no element to remove; in that case you can see `matchedCount = 1` and `modifiedCount = 0`.

---

## 2. Preparing Sample Data

The examples use `mongosh` and an illustrative collection `arrayRemovalLab`. Assume this collection does not yet contain the example IDs. Create the data:

~~~javascript
db.arrayRemovalLab.insertMany([
  {
    _id: "TAGS-PULL",
    tags: ["vip", "archived", "vip", "featured"],
    scores: [55, 78, 82, 99]
  },
  {
    _id: "TAGS-ALL",
    tags: ["red", "blue", "red", "green", "blue"]
  },
  {
    _id: "QUEUE-POP",
    queue: ["created", "validated", "processed", "sent"]
  },
  {
    _id: "TASKS-PULL",
    tasks: [
      { taskId: "T1", status: "DONE", points: 4 },
      { taskId: "T2", status: "OPEN", points: 8 },
      { taskId: "T3", status: "DONE", points: 9 },
      { taskId: "T4", status: "OPEN", points: 2 }
    ]
  },
  {
    _id: "NESTED",
    groups: [
      { code: "ENG", members: ["U1", "U2"] },
      { code: "OPS", members: ["U2", "U3"] }
    ]
  },
  {
    _id: "EMPTY",
    tags: []
  },
  {
    _id: "MISSING",
    label: "document without tags"
  },
  {
    _id: "SCALAR",
    tags: "vip"
  }
]);
~~~

Examples operate on **separate IDs** for clear observation. A few sections present alternatives or distinct scenarios: treat those as standalone examples against the described initial state rather than expecting identical outcomes if every variant is executed back-to-back.

To inspect an array after updating:

~~~javascript
db.arrayRemovalLab.findOne(
  { _id: "TAGS-PULL" },
  { tags: 1, scores: 1 }
);
~~~

Never run practice commands against collections holding production data without a proper plan and tight update bounds.

---

## 3. `$pull`: Removing Every Element Matching a Value

Syntax:

~~~javascript
{
  $pull: {
    <arrayField>: <value>
  }
}
~~~

When the supplied value is a simple scalar, MongoDB removes **all occurrences** of that value from the array.

### 3.1. Removing a String from an Array

Initial array:

~~~javascript
{
  _id: "TAGS-PULL",
  tags: ["vip", "archived", "vip", "featured"]
}
~~~

Command:

~~~javascript
db.arrayRemovalLab.updateOne(
  { _id: "TAGS-PULL" },
  { $pull: { tags: "vip" } }
);
~~~

After updating:

~~~javascript
{
  _id: "TAGS-PULL",
  tags: ["archived", "featured"]
}
~~~

Both occurrences of `"vip"` are removed. `$pull` does **not** mean "remove only the first match found". If `"vip"` appeared 100 times, all 100 occurrences would be removed.

Remaining elements preserve their relative order. `$pull` does not sort the array.

### 3.2. Removing a Numeric Value

~~~javascript
db.arrayRemovalLab.updateOne(
  { _id: "TAGS-PULL" },
  { $pull: { scores: 82 } }
);
~~~

From `scores: [55, 78, 82, 99]`, the result is `[55, 78, 99]`.

MongoDB compares according to BSON type semantics. Do not assume the string `"82"` matches the number `82`. When a field is designed as a numeric array, enforce its type so mixed strings/numbers never produce surprising removal results.

### 3.3. Removing All Occurrences vs. Removing Exactly One Element

If business logic states "revoke the `EDITOR` role from the roles list", removing all occurrences of `EDITOR` makes sense because a role list should not hold duplicates anyway.

However, if business logic states "cancel **one** ticket booking out of two with the same label", using `$pull: { bookings: "VIP" }` deletes **both** bookings. A sounder design gives each booking a unique `bookingId` and removes by that identifier.

An operator cannot know "the second occurrence means something different from the first" unless the data distinguishes them.

## 4. `$pull` with Comparison Conditions

`$pull` accepts **query condition expressions**, not just exact values. On numeric arrays, you can remove all scores below a threshold, within a range, or inside a set of values.

### 4.1. Removing All Scores Below a Threshold

On the initial `scores: [55, 78, 82, 99]`:

~~~javascript
db.arrayRemovalLab.updateOne(
  { _id: "TAGS-PULL" },
  {
    $pull: {
      scores: { $lt: 80 }
    }
  }
);
~~~

The result is `scores: [82, 99]`. Both 55 and 78 are less than 80 and are removed.

Common comparison operators include:

| Operator | Meaning per element |
| --- | --- |
| `$eq` | Equals the specified value. |
| `$ne` | Does not equal the specified value. |
| `$gt` / `$gte` | Greater than / greater than or equal to. |
| `$lt` / `$lte` | Less than / less than or equal to. |
| `$in` | Belongs to a set of values. |
| `$nin` | Does not belong to a set of values. |
| `$regex` | String matches a regular expression under applied options. |

For the requirement "remove scores in the interval **[80, 90)**":

~~~javascript
db.examRecords.updateOne(
  { _id: "EXAM-1" },
  {
    $pull: {
      scores: {
        $gte: 80,
        $lt: 90
      }
    }
  }
);
~~~

An element is removed when that single element's value is both **greater than or equal to 80** and **less than 90**. For instance, `[75, 80, 85, 90, 92]` becomes `[75, 90, 92]`. For user-submitted data, **rejecting out-of-range scores at write time** is usually safer than storing them and cleaning them up later. These examples illustrate `$pull` capabilities, not a replacement for schema validation.

### 4.2. Removing Multiple Values with `$in`

~~~javascript
db.users.updateOne(
  { _id: "U100" },
  {
    $pull: {
      roles: { $in: ["GUEST", "OBSOLETE"] }
    }
  }
);
~~~

Every `"GUEST"` or `"OBSOLETE"` element is removed. Here `$pull` expresses a goal very similar to `$pullAll`. Choose whichever reads more clearly to maintainers and stay consistent across your codebase.

### 4.3. Removing Strings by Pattern

~~~javascript
db.documents.updateOne(
  { _id: "DOC-1" },
  {
    $pull: {
      tags: { $regex: "^tmp-" }
    }
  }
);
~~~

On `tags: ["published", "tmp-draft", "tmp-legacy"]`, this removes tags starting with `"tmp-"`. Construct regular expressions carefully, especially when user input is involved. Unconstrained regexes risk removing unintended elements or incurring unnecessary processing cost.

### 4.4. `$pull` Is an Update, Not a Read Query

~~~javascript
// Query: find documents having an element in the forbidden set
db.documents.find({
  tags: { $in: ["tmp-draft", "tmp-legacy"] }
});

// Update: remove elements in the forbidden set from the selected document
db.documents.updateOne(
  { _id: "DOC-1" },
  {
    $pull: {
      tags: { $in: ["tmp-draft", "tmp-legacy"] }
    }
  }
);
~~~

In the read query, `$in` determines **which documents** are returned. In the update, the condition inside `$pull` determines **which array elements** are removed. The same operator in a different position acts at a different scope.

---

## 5. `$pull` on Arrays of Embedded Documents

Real-world schemas frequently store arrays of objects rather than arrays of strings. Example:

~~~javascript
{
  _id: "TASKS-PULL",
  tasks: [
    { taskId: "T1", status: "DONE", points: 4 },
    { taskId: "T2", status: "OPEN", points: 8 },
    { taskId: "T3", status: "DONE", points: 9 },
    { taskId: "T4", status: "OPEN", points: 2 }
  ]
}
~~~

### 5.1. Removing All Tasks with Status DONE

~~~javascript
db.arrayRemovalLab.updateOne(
  { _id: "TASKS-PULL" },
  {
    $pull: {
      tasks: { status: "DONE" }
    }
  }
);
~~~

Result:

~~~javascript
{
  _id: "TASKS-PULL",
  tasks: [
    { taskId: "T2", status: "OPEN", points: 8 },
    { taskId: "T4", status: "OPEN", points: 2 }
  ]
}
~~~

The condition `{ status: "DONE" }` is evaluated against **each element document** of the `tasks` array. It matches elements whose `status` equals `"DONE"`, even when elements also carry other fields like `taskId` and `points`.

### 5.2. Multiple Conditions on the Same Embedded Document

Suppose the requirement is **remove only completed tasks with at least 8 points**:

~~~javascript
db.arrayRemovalLab.updateOne(
  { _id: "TASKS-PULL" },
  {
    $pull: {
      tasks: {
        status: "DONE",
        points: { $gte: 8 }
      }
    }
  }
);
~~~

Applied to the **initial** data from section 2, only `T3` (DONE, 9 points) is removed. `T1` is DONE but has only 4 points; `T2` has 8 points but is OPEN. Both are preserved.

Key point: **the `$pull` condition on an array of embedded documents is evaluated as a query against each individual element**. You do not need to wrap it in an outer `$elemMatch` just to bind `status` and `points` to the same object under evaluation.

Compare the intent:

~~~javascript
// Read: one task simultaneously satisfies both conditions.
db.arrayRemovalLab.find({
  tasks: {
    $elemMatch: {
      status: "DONE",
      points: { $gte: 8 }
    }
  }
});

// Write: remove every task simultaneously satisfying both conditions.
db.arrayRemovalLab.updateOne(
  { _id: "TASKS-PULL" },
  {
    $pull: {
      tasks: {
        status: "DONE",
        points: { $gte: 8 }
      }
    }
  }
);
~~~

`$elemMatch` in a **read query** binds multiple conditions to the same array element. Inside `$pull`, the target being tested is already **each individual array element**, so place the element field conditions directly as shown.

### 5.3. Removing by Stable Identifier

In order systems, a more reliable condition is the line-item identifier:

~~~javascript
db.orders.updateOne(
  { _id: "ORDER-1007" },
  {
    $pull: {
      items: { lineId: "LINE-02" }
    }
  }
);
~~~

This removes every line with `lineId: "LINE-02"` from the order document. If the schema guarantees `lineId` is unique within an order, the business outcome is deleting that exact single line.

If `lineId` appears twice due to bad input data, **both** matching elements are removed. `$pull` has no "remove only the first match" flag. Therefore, when business rules require uniqueness per element, enforce that invariant in your data model and write logic.

### 5.4. Conditions on Nested Fields Inside Embedded Documents

~~~javascript
db.shipments.updateOne(
  { _id: "SHIP-1" },
  {
    $pull: {
      packages: {
        "warehouse.city": "HCM",
        state: "CANCELLED"
      }
    }
  }
);
~~~

Each `packages` element must simultaneously have `warehouse.city = "HCM"` and `state = "CANCELLED"` to be removed. The path `warehouse.city` is resolved relative to **each element document**.

### 5.5. When an Element Itself Contains an Array

A document in `reports` may contain a `checks` array:

~~~javascript
{
  _id: "RUN-1",
  reports: [
    {
      reportId: "R1",
      checks: [
        { code: "ACCESS", passed: true },
        { code: "SECURITY", passed: false }
      ]
    },
    {
      reportId: "R2",
      checks: [
        { code: "ACCESS", passed: true }
      ]
    }
  ]
}
~~~

To remove any report containing **a failed SECURITY check**, use `$elemMatch` on the **inner `checks` array**:

~~~javascript
db.testRuns.updateOne(
  { _id: "RUN-1" },
  {
    $pull: {
      reports: {
        checks: {
          $elemMatch: {
            code: "SECURITY",
            passed: false
          }
        }
      }
    }
  }
);
~~~

Here `$pull` still evaluates **each report**, while `$elemMatch` is necessary to require both conditions on **the same element of the inner `checks` array**. Never confuse the two array nesting levels when designing predicates.

---

## 6. `$pullAll`: Removing All Values Belonging to a List

Syntax:

~~~javascript
{
  $pullAll: {
    <arrayField>: [<value1>, <value2>, ...]
  }
}
~~~

`$pullAll` takes an **array of values to remove**, deleting every occurrence of each listed value from the target array.

### 6.1. Removing Multiple Labels Including Duplicates

Initial data:

~~~javascript
{
  _id: "TAGS-ALL",
  tags: ["red", "blue", "red", "green", "blue"]
}
~~~

Command:

~~~javascript
db.arrayRemovalLab.updateOne(
  { _id: "TAGS-ALL" },
  {
    $pullAll: {
      tags: ["red", "blue"]
    }
  }
);
~~~

Result:

~~~javascript
{
  _id: "TAGS-ALL",
  tags: ["green"]
}
~~~

`"red"` appeared twice and `"blue"` appeared twice; **all four elements** are removed. The list `["red", "blue"]` specifies **which values to remove**, not "remove two elements".

### 6.2. Comparing `$pullAll` and `$pull` + `$in`

These two commands share **the same goal** on a regular array of strings:

~~~javascript
// Approach 1: list of values to remove
db.users.updateOne(
  { _id: "U1" },
  { $pullAll: { roles: ["OBSOLETE", "GUEST"] } }
);

// Approach 2: membership condition
db.users.updateOne(
  { _id: "U1" },
  { $pull: { roles: { $in: ["OBSOLETE", "GUEST"] } } }
);
~~~

These two examples are **not meant to run sequentially** for a cumulative effect; they illustrate two equivalent alternatives.

Differences in capability:

| Requirement | `$pullAll` | `$pull` |
| --- | --- | --- |
| Remove exact value `"old"` | Yes. | Yes. |
| Remove both `"old"` and `"deprecated"` | Yes, via list. | Yes, via `$in`. |
| Remove all numbers less than 0 | Does not accept comparison conditions. | Yes, via `$lt`. |
| Remove all objects with `status = "DONE"` | Not suited for field-level filtering. | Yes, via embedded-document condition. |
| Remove strings matching a regex | Does not support query predicates. | Yes, via `$regex`. |
| Remove all duplicates of targeted values | Yes. | Yes. |

`$pullAll` is best suited for **an explicit set of values, usually scalars**. If an array contains objects with multiple fields that evolve over time, prefer `$pull` with an identifying key like `itemId` or a business predicate. Never force clients to reconstruct an entire multi-field object merely to delete one element.

### 6.3. Values to Remove Must Have the Exact Type

~~~javascript
db.metrics.updateOne(
  { _id: "M1" },
  { $pullAll: { codes: [2, 3] } }
);
~~~

If `codes` is `[1, 2, 3, "2"]`, numeric matching should not be expected to coerce strings into numbers. Keeping stored types consistent and supplying exact matching types is far better than trial-and-error across operators.

### 6.4. Be Careful with Arrays of Documents

Example:

~~~javascript
{
  _id: "A1",
  participants: [
    { userId: "U1", role: "EDITOR" },
    { userId: "U2", role: "REVIEWER" }
  ]
}
~~~

If the goal is to remove every participant with `userId = "U1"`, use:

~~~javascript
db.sessions.updateOne(
  { _id: "A1" },
  {
    $pull: {
      participants: { userId: "U1" }
    }
  }
);
~~~

This does not depend on the `role` field, which might change later. Trying to use `$pullAll` with whole objects makes the match overly brittle and unable to express flexible rules.

---

## 7. `$pop`: Removing the First or Last Array Element

Syntax:

~~~javascript
{
  $pop: {
    <arrayField>: -1 // first element
  }
}
~~~

or:

~~~javascript
{
  $pop: {
    <arrayField>: 1 // last element
  }
}
~~~

The value selects **position**, not the count of elements to delete:

- **`-1`:** removes the **first** element.
- **`1`:** removes the **last** element.

### 7.1. Removing the Last Element

Initially:

~~~javascript
{
  _id: "QUEUE-POP",
  queue: ["created", "validated", "processed", "sent"]
}
~~~

Command:

~~~javascript
db.arrayRemovalLab.updateOne(
  { _id: "QUEUE-POP" },
  {
    $pop: { queue: 1 }
  }
);
~~~

After command:

~~~javascript
{
  _id: "QUEUE-POP",
  queue: ["created", "validated", "processed"]
}
~~~

### 7.2. Removing the First Element

Continuing **from the newly updated state**:

~~~javascript
db.arrayRemovalLab.updateOne(
  { _id: "QUEUE-POP" },
  {
    $pop: { queue: -1 }
  }
);
~~~

Result:

~~~javascript
{
  _id: "QUEUE-POP",
  queue: ["validated", "processed"]
}
~~~

`$pop` does not filter by value. On `["A", "B", "A"]`, `$pop: 1` removes the trailing `"A"`, and `$pop: -1` removes the leading `"A"`. To remove **all** `"A"` regardless of position, use `$pull`.

### 7.3. `$pop: 1` Does Not Mean Removing an Arbitrary Specific Element

If the item to delete is identified by `notificationId`, use `$pull`:

~~~javascript
db.notifications.updateOne(
  { _id: "USER-1" },
  {
    $pull: {
      messages: { notificationId: "N-42" }
    }
  }
);
~~~

Using `$pop: 1` here simply drops whatever happens to be last at update time—which could be a completely different notification.

### 7.4. When Is `$pop` Appropriate?

- An array has **meaningful ordering** and the requirement is strictly to trim the head or tail.
- The list is short, bounded, and owned by a single document.
- The application explicitly accepts removing whichever element occupies that end slot at execution time.

`$pop` **does not return the popped element** like a queue-dequeue API that guarantees exclusive worker ownership of a job. For multi-consumer queues needing ack/retry and duplicate-delivery prevention, use a dedicated jobs collection or a specialized message queue.

---

## 8. Visual Comparison of the Three Operators

Consider the same starting array:

~~~javascript
{
  labels: ["A", "B", "A", "C", "B"]
}
~~~

Each command below is assumed to run **independently on the initial array**:

| Command | Result |
| --- | --- |
| `{ $pull: { labels: "A" } }` | `["B", "C", "B"]` |
| `{ $pull: { labels: { $in: ["A", "B"] } } }` | `["C"]` |
| `{ $pullAll: { labels: ["A", "B"] } }` | `["C"]` |
| `{ $pop: { labels: -1 } }` | `["B", "A", "C", "B"]` |
| `{ $pop: { labels: 1 } }` | `["A", "B", "A", "C"]` |

Easy way to remember:

- `$pull` answers **"which elements match the condition?"**.
- `$pullAll` answers **"which elements are in the value list?"**.
- `$pop` answers **"which element is at the head/tail?"**.

Arrays with repeated values are an especially clear test case to distinguish the first two from `$pop`.

---

## 9. Missing Fields, Empty Arrays, and Invalid Data Types

Consider three documents:

~~~javascript
{ _id: "EMPTY", tags: [] }
{ _id: "MISSING", label: "document without tags" }
{ _id: "SCALAR", tags: "vip" }
~~~

### 9.1. Empty Array

When `tags: []`, there are no elements to remove. For example:

~~~javascript
db.arrayRemovalLab.updateOne(
  { _id: "EMPTY" },
  { $pull: { tags: "vip" } }
);
~~~

The document remains `tags: []`. Likewise, `$pullAll` or `$pop` cannot remove anything from an empty array.

### 9.2. Missing Field

~~~javascript
db.arrayRemovalLab.updateOne(
  { _id: "MISSING" },
  { $pull: { tags: "vip" } }
);
~~~

Because the document lacks the `tags` field, the operation does not materialize a new array just to remove from it. Update operators do not turn a missing field into `[]`. If business rules require the array to always exist, initialize the schema or backfill data in a separate step.

### 9.3. Field Exists but Is Not an Array

~~~javascript
db.arrayRemovalLab.updateOne(
  { _id: "SCALAR" },
  { $pull: { tags: "vip" } }
);
~~~

Here `tags` is the string `"vip"`, not an array. MongoDB does not treat a string as a single-element array for removal operators. The operation is rejected because array updates cannot apply to non-array values. `$pullAll` and `$pop` likewise require a valid array field.

When schemas are inconsistent, do not work around errors by treating scalar fields like arrays. Decide on a migration: convert scalars to arrays, update the API, or drop obsolete values per business rules.

### 9.4. Update Result When No Element Matches

~~~javascript
const result = db.arrayRemovalLab.updateOne(
  { _id: "EMPTY" },
  { $pull: { tags: "not-found" } }
);

printjson(result);
~~~

For standard acknowledged writes, the result looks like:

~~~javascript
{
  acknowledged: true,
  matchedCount: 1,
  modifiedCount: 0,
  upsertedId: null
}
~~~

- **`matchedCount = 1`**: the outer filter matched one document.
- **`modifiedCount = 0`**: the document was not modified.
- **`upsertedId = null`**: no new document was created.

Do not assume `modifiedCount = 0` is always an error. For an action meaning **"ensure the legacy role is absent"**, modifying nothing because the role was already removed is a valid, idempotent outcome. If business logic requires **"must remove an actually present element"**, enforce an explicit precondition and report status accordingly.

---

## 10. Removing Elements from Nested Arrays Using Filtered Positional Operators

Sometimes a document contains an **array of groups**, where each group has its own `members` array:

~~~javascript
{
  _id: "NESTED",
  groups: [
    { code: "ENG", members: ["U1", "U2"] },
    { code: "OPS", members: ["U2", "U3"] }
  ]
}
~~~

Requirement: remove `U2` **only from the ENG group**, keeping OPS membership untouched. Updating the entire `groups` array or pulling from the wrong path risks wiping another group's data.

Use the **filtered positional operator `$[g]`** together with `arrayFilters`:

~~~javascript
db.arrayRemovalLab.updateOne(
  { _id: "NESTED" },
  {
    $pull: {
      "groups.$[g].members": "U2"
    }
  },
  {
    arrayFilters: [
      { "g.code": "ENG" }
    ]
  }
);
~~~

Result:

~~~javascript
{
  _id: "NESTED",
  groups: [
    { code: "ENG", members: ["U1"] },
    { code: "OPS", members: ["U2", "U3"] }
  ]
}
~~~

In this example:

1. `groups` is the outer array.
2. `$[g]` selects `groups` elements matching `g.code = "ENG"`.
3. `members` is the inner array inside each selected group.
4. `$pull` removes all occurrences of `"U2"` from just those `members` arrays.

`arrayFilters` filters **elements of the outer array**; `$pull`'s condition filters **elements of the inner array**. The two condition layers serve distinct targets.

If duplicate `code` values were permitted across groups, all groups matching `arrayFilters` would be affected. When business rules target a single group, ensure group identifiers remain stable and unique within the document.

### 10.1. Do Not Confuse with `$unset` on an Array Index

In many situations, `$unset` applied to an array index (such as `"tags.1"`) **sets that element to `null`**, rather than shrinking the array and shifting subsequent elements left. When the goal is to **remove an element and compact the array**, use `$pull` by value/identifier or `$pop` for the ends.

For example, deleting an item with a specific ID via `$pull: { items: { itemId: "I2" } }` is far clearer than finding its index and calling `$unset`.

---

## 11. Atomicity and Concurrent Updates

An update command on a **single document** in MongoDB is atomic. This applies when using `$pull`, `$pullAll`, or `$pop` inside `updateOne`: readers never observe a document halfway through removing elements.

Even so, **document-level atomicity does not solve every business concurrency rule**.

### 11.1. Two Clients Concurrently Removing the Same Value

Suppose an array contains `"EDITOR"`. Two requests run simultaneously:

~~~javascript
db.users.updateOne(
  { _id: "U100" },
  { $pull: { roles: "EDITOR" } }
);
~~~

Once both finish, `"EDITOR"` is gone. One request modifies the document, while the other makes no further change. That is typically ideal for **target-state role revocation** (*ensure absent*).

If the API defines "revoke an existing role and send a notification exactly once", add explicit rules to determine which request actually performed the change so side effects do not fire twice.

### 11.2. `$pop` on an Array Receiving Concurrent Appends

Suppose Client A reads the array and sees `"JOB-1"` at the end, then Client B pushes `"JOB-2"` before Client A's `$pop: 1` arrives. When A's command runs, the **current** last element is `"JOB-2"`.

Therefore, if the intent is to remove `"JOB-1"`, never rely on a prior read followed by `$pop`. Match by identifier:

~~~javascript
db.jobs.updateOne(
  { _id: "QUEUE-1" },
  { $pull: { pending: { jobId: "JOB-1" } } }
);
~~~

If it is genuinely a multi-worker queue, you must also handle **job claiming, completion acknowledgment, crash retries, and duplicate-execution guards**. An array removal operator alone does not provide full queue guarantees.

### 11.3. Updating Multiple Documents

~~~javascript
db.users.updateMany(
  { tenantId: "T1" },
  { $pull: { roles: "LEGACY_USER" } }
);
~~~

The command applies the removal to **each matched document**. Each document updates atomically, **but the set of multiple documents does not automatically form an atomic transaction**. On mid-run errors or interruptions, the application must distinguish partial progress and support controlled re-runs.

If business logic requires multiple documents to commit or roll back together, evaluate multi-document transactions on supported deployments. For sweeping role-cleanup campaigns across millions of users, a checkpointed idempotent batch process is often more practical than a massive transaction.

### 11.4. Recognizing Duplicate Updates and Idempotency

`$pull` on a value already absent makes no further change, making it naturally friendly to repeated runs. The same holds for `$pullAll` once all targeted values are gone.

By contrast, **`$pop` is not idempotent for "remove one intended element"**: the first call drops the last element; a second call drops the **new last element**, causing unintended data loss. When APIs retry on timeouts, blindly re-sending `$pop` is especially dangerous.

With retryable writes enabled, drivers may safely retry transport-level failures under supported conditions, yet that does not replace business-level idempotency or state verification when a client is unsure whether an operation succeeded.

---

## 12. Removing an Element While Preserving Business Invariants

Suppose a shopping cart contains:

~~~javascript
{
  _id: "CART-1",
  status: "OPEN",
  items: [
    { lineId: "L1", sku: "P1", quantity: 2, unitPriceMinor: 100000 },
    { lineId: "L2", sku: "P2", quantity: 1, unitPriceMinor: 300000 }
  ],
  totalMinor: 500000
}
~~~

If you only run:

~~~javascript
db.carts.updateOne(
  { _id: "CART-1" },
  { $pull: { items: { lineId: "L2" } } }
);
~~~

after the update, `L2` is gone from the array, yet **`totalMinor` may still remain `500000`**. The invariant "total equals sum of line items" is broken if the application treats the total field as authoritative.

Options:

1. Store only `items` and compute totals on read when arrays are small and access frequency permits.
2. Update the same document with a **pipeline update** that recalculates the total from the filtered array, when logic can be expressed via aggregation expressions.
3. Use versioned updates or transactions when multiple related records are involved.

Example pipeline update removing `L2` and recomputing the total from remaining items:

~~~javascript
db.carts.updateOne(
  { _id: "CART-1", status: "OPEN" },
  [
    {
      $set: {
        items: {
          $filter: {
            input: "$items",
            as: "item",
            cond: { $ne: ["$$item.lineId", "L2"] }
          }
        }
      }
    },
    {
      $set: {
        totalMinor: {
          $sum: {
            $map: {
              input: "$items",
              as: "item",
              in: {
                $multiply: [
                  "$$item.quantity",
                  "$$item.unitPriceMinor"
                ]
              }
            }
          }
        }
      }
    }
  ]
);
~~~

This is an **alternative** when both an array and derived fields must stay consistent within one document operation. It does not use `$pull`, yet highlights a critical limitation of bare element removal: a business update often needs to maintain aggregate fields alongside the array.

For high-precision monetary values, use integers in the smallest currency unit or an appropriate decimal type, guarding against overflow and rounding issues.

### 12.1. Why Not Simply Pair `$inc` with `$pull`?

One might consider reading the line price and running:

~~~javascript
db.carts.updateOne(
  { _id: "CART-1" },
  {
    $pull: { items: { lineId: "L2" } },
    $inc: { totalMinor: -300000 }
  }
);
~~~

Updates on **the same document** are atomic, yet this command can still **decrement the total even if `L2` was already deleted earlier**, because the outer filter checks only `_id`. Retries can subtract the amount twice. If choosing this pattern, include a filter condition verifying the line item still exists along with concurrency/idempotency controls, or use a pipeline that recomputes the total from current state.

The core takeaway: **removing an element does not automatically complete the business invariant**; always consider dependent invariants.

---

## 13. Size Limits, Indexes, and Performance

### 13.1. MongoDB Still Caps Each Document at 16 MiB

Large arrays can push a document toward the **16 MiB** BSON limit. Removal operators reduce element counts, yet they do not make unbounded arrays a sound model. If a history list can reach millions of records, splitting into a separate collection with a reference key is much more sustainable.

For example, avoid storing an entire order history inside:

~~~javascript
{
  _id: "CUSTOMER-1",
  orders: [ /* years of order history */ ]
}
~~~

When orders have independent lifecycles, use an `orders` collection with `customerId` and proper indexes. Deleting an order from history then follows dedicated business and retention policies rather than simply pulling an element from a customer document.

### 13.2. Removing Elements Can Affect Multikey Indexes

If an array field participates in a **multikey index**, adding or removing elements requires updating index entries. Example:

~~~javascript
db.products.createIndex({ tags: 1 });
~~~

Followed by:

~~~javascript
db.products.updateOne(
  { _id: "P1" },
  { $pull: { tags: "obsolete" } }
);
~~~

Mutating the array must maintain matching index entries. With very large arrays, frequent updates, and many indexes, write overhead can become significant. Never assume removing one short string from an array always carries negligible fixed cost.

### 13.3. Selecting the Target Document Using Indexes

`$pull` operates on the array **of an already-selected document**. How MongoDB locates that document beforehand still matters greatly:

~~~javascript
db.carts.updateOne(
  { _id: "CART-1" },
  { $pull: { items: { lineId: "L2" } } }
);
~~~

Filtering by `_id` uses the default index to locate the cart quickly. Conversely, an `updateMany` with an unindexed filter on a huge collection may scan millions of documents before executing updates.

Running `explain` on a read query with the same filter helps inspect the document lookup plan; evaluate query indexing and array update costs together.

### 13.4. Bulk-Removing Elements Across Many Documents

Suppose 500,000 users have a `roles` array and an old role must be revoked. You can run:

~~~javascript
db.users.updateMany(
  { roles: "LEGACY" },
  { $pull: { roles: "LEGACY" } }
);
~~~

The outer filter skips users lacking that role (and can leverage a multikey index if present). Still, large datasets require planning for write load, replication lag, monitoring, and per-batch outcomes. An `updateMany` failing midway does not automatically roll back already-modified documents.

### 13.5. For Lists Keeping the "N Most Recent Elements"

If the requirement is retaining the **last N recent values**, you do not need to call `$pop: -1` in a loop after every append. MongoDB supports `$push` with `$each` and `$slice` to bound array size:

~~~javascript
db.userActivity.updateOne(
  { _id: "U1" },
  {
    $push: {
      recentActions: {
        $each: [
          { actionId: "A100", happenedAt: new Date() }
        ],
        $slice: -20
      }
    }
  }
);
~~~

This appends one element and retains the **last 20 elements in array order** within a single update. If timestamp order can differ from insertion order, add sorting rules to handle late-arriving events. Never treat `$slice` as full-history retention; truncated elements are discarded from the current array.

---

## 14. Usage in the Java MongoDB Sync Driver

The MongoDB Java Sync Driver accepts updates as `Bson`, such as `org.bson.Document`. This shows the direct mapping between `mongosh` commands and Java code.

### 14.1. `$pull` with a Scalar Value

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

public class ArrayRemovalExamples {
    public static void removeVip(MongoCollection<Document> collection) {
        UpdateResult result = collection.updateOne(
            Filters.eq("_id", "TAGS-PULL"),
            new Document(
                "$pull",
                new Document("tags", "vip")
            )
        );

        System.out.printf(
            "matched=%d modified=%d%n",
            result.getMatchedCount(),
            result.getModifiedCount()
        );
    }
}
~~~

From Java, the expression mirrors `mongosh`:

~~~javascript
{
  $pull: {
    tags: "vip"
  }
}
~~~

Under an unacknowledged write concern, result count methods do not behave like acknowledged writes; configure an appropriate acknowledged write concern.

### 14.2. `$pull` with Conditions on Embedded Documents

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;

public class RemoveCompletedTasks {
    public static void run(MongoCollection<Document> collection) {
        Document condition = new Document("status", "DONE")
            .append("points", new Document("$gte", 8));

        Document update = new Document(
            "$pull",
            new Document("tasks", condition)
        );

        collection.updateOne(
            Filters.eq("_id", "TASKS-PULL"),
            update
        );
    }
}
~~~

This applies the condition to **each document inside `tasks`**. It does not delete the `TASKS-PULL` document itself.

### 14.3. `$pullAll`

~~~java
import java.util.List;
import org.bson.Document;
import com.mongodb.client.model.Filters;

collection.updateOne(
    Filters.eq("_id", "TAGS-ALL"),
    new Document(
        "$pullAll",
        new Document("tags", List.of("red", "blue"))
    )
);
~~~

When removing exact specified strings, a Java `List` maps directly to a BSON array.

### 14.4. `$pop`

~~~java
// Remove the last element:
collection.updateOne(
    Filters.eq("_id", "QUEUE-POP"),
    new Document("$pop", new Document("queue", 1))
);

// Remove the first element:
collection.updateOne(
    Filters.eq("_id", "QUEUE-POP"),
    new Document("$pop", new Document("queue", -1))
);
~~~

Running these two commands back-to-back removes **two elements**, one from each end at the moment each command executes. Do not call both if the requirement is to drop a single item.

### 14.5. Using Java Driver Builders

For common operations, the Java Driver offers builders in `Updates`:

~~~java
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.pull;

collection.updateOne(
    eq("_id", "TAGS-PULL"),
    pull("tags", "vip")
);
~~~

Builders avoid repeating operator strings throughout code. For complex updates or pipelines, you can construct BSON with builders or `Document` according to your deployed driver API and version.

### 14.6. Spring Data MongoDB

With Spring Data MongoDB, express the same operation using `Query` and `Update`:

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public class RemoveUserRole {
    private final MongoTemplate mongoTemplate;

    public RemoveUserRole(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public void revoke(String userId, String role) {
        Query query = new Query(
            Criteria.where("_id").is(userId)
        );

        Update update = new Update().pull("roles", role);

        mongoTemplate.updateFirst(
            query,
            update,
            "users"
        );
    }
}
~~~

This reflects the same `$pull` semantics in MongoDB. If roles and permissions span multiple documents/collections, enforce related invariants and permission invalidation at the business layer.

---

## 15. Distinguishing `$pull` from Other Update/Delete Methods

MongoDB offers many array and document operators. They are not arbitrarily interchangeable:

| Goal | Appropriate Tool | Key Reminder |
| --- | --- | --- |
| Delete entire document from collection | `deleteOne` / `deleteMany` | Affects the whole document, not just an array element. |
| Remove the `tags` field from a document | `$unset: { tags: "" }` | Removes **the entire field**, not a single array value. |
| Remove all elements matching a condition | `$pull` | Can remove multiple elements. |
| Remove all occurrences of specific values | `$pullAll` | Takes an explicit list of values. |
| Remove first/last array element | `$pop` | By position, not by value. |
| Modify an existing element's value | `$set` with index or `arrayFilters` | Modifies rather than removes. |
| Append values to an array | `$push` | Allows duplicates. |
| Append if equivalent value is absent | `$addToSet` | Prevents new matching duplicates; does not clean pre-existing ones. |
| Keep matching elements by rebuilding array | Pipeline update + `$filter` | Useful when derived fields in the same document must be recalculated. |
| Clear one index via `$unset` | Usually unsuitable | Leaves `null` at that slot. |

For example, to **clear all roles for a user**, there is no need to `$pull` each role individually:

~~~javascript
db.users.updateOne(
  { _id: "U1" },
  { $set: { roles: [] } }
);
~~~

However, that clears valid roles too. When revoking only `"LEGACY"`, `$pull` expresses the narrower, safer intent.

To **remove the `roles` field completely** (distinguishing missing field from empty array):

~~~javascript
db.users.updateOne(
  { _id: "U1" },
  { $unset: { roles: "" } }
);
~~~

Choosing `[]` vs. a missing field depends on your schema contract and domain semantics.

---

## 16. Errors, Results, and API Handling

### 16.1. Distinguishing Found Document from Actual Modification

~~~javascript
const result = db.users.updateOne(
  { _id: "U1" },
  { $pull: { roles: "LEGACY" } }
);

printjson({
  matchedCount: result.matchedCount,
  modifiedCount: result.modifiedCount,
  acknowledged: result.acknowledged
});
~~~

Three common outcomes:

| State | `matchedCount` | `modifiedCount` | Interpretation |
| --- | --- | --- | --- |
| User not found | 0 | 0 | Outer filter matched no document. |
| User found, role already absent | 1 | 0 | No matching element to remove. |
| User found and role removed | 1 | 1 | **Document changed**; `modifiedCount` counts documents, not removed elements. |

Even if `$pull` removes 10 elements from **one** document, `modifiedCount` for `updateOne` is still **1**, not 10. Counting removed elements requires separate logic (such as controlled before/after length comparison or pipeline calculation), keeping concurrency in mind.

### 16.2. Errors When Field Is Not an Array

Running `$pull` on a scalar string or object field raises a write error. Do not infinitely retry the same payload; fix the data or schema. In Java applications, catch the appropriate driver/Spring Data exception and return a domain response without leaking sensitive document contents.

### 16.3. Permissions and Validation

Array updates remain subject to **write privileges**, **schema validators**, and other collection constraints. For instance, if a validator requires `roles` to have at least one item, a `$pull` emptying the array will be rejected.

~~~javascript
{
  $jsonSchema: {
    bsonType: "object",
    properties: {
      roles: {
        bsonType: "array",
        minItems: 1
      }
    }
  }
}
~~~

This is a partial validator snippet, not a standalone collection definition. It demonstrates that update validity is checked against the **post-update state**, not merely the syntax of the `$pull` condition.

### 16.4. Securing ID-Based Removal Operations

Consider an API endpoint like:

~~~text
DELETE /carts/CART-1/items/L2
~~~

Never rely solely on `_id: "CART-1"` taken from the URL. Authenticate and authorize the caller to modify that cart. You can embed ownership into the update filter:

~~~javascript
db.carts.updateOne(
  {
    _id: "CART-1",
    ownerId: "AUTHENTICATED-USER-ID",
    status: "OPEN"
  },
  {
    $pull: {
      items: { lineId: "L2" }
    }
  }
);
~~~

Source `ownerId` from a trusted authentication context, never a client-supplied parameter. When `matchedCount = 0`, the cart may not exist, belong to another user, or no longer be open; choose the response according to your API security policy.

---

## 17. Real-World Scenarios

### 17.1. Revoking Multiple Legacy Roles

**Requirement:** User has `roles: ["USER", "EDITOR", "GUEST", "EDITOR"]`. Remove `EDITOR` and `GUEST`, keeping `USER`.

~~~javascript
db.users.updateOne(
  { _id: "U1" },
  {
    $pullAll: {
      roles: ["EDITOR", "GUEST"]
    }
  }
);
~~~

**Result:** `roles: ["USER"]`. All duplicate EDITOR entries are removed.

**Why not `$pop`?** The roles to remove are not tied to the head or tail position.

### 17.2. Cleaning Up Moderated Comments

**Requirement:** Remove all comments inside a post document with `status = "REJECTED"`.

~~~javascript
db.posts.updateOne(
  { _id: "POST-1" },
  {
    $pull: {
      comments: { status: "REJECTED" }
    }
  }
);
~~~

**Note:** If rejected comments must be retained for auditing or appeals, deleting them permanently may violate business rules. In that case, keep the records and change display status or move them to an archive.

### 17.3. Removing Expired Time-Based Events

**Requirement:** Keep only unexpired events in the array; drop older ones.

~~~javascript
const cutoff = ISODate("2026-11-01T00:00:00Z");

db.sessions.updateOne(
  { _id: "SESSION-1" },
  {
    $pull: {
      events: {
        occurredAt: { $lt: cutoff }
      }
    }
  }
);
~~~

All event documents with `occurredAt < cutoff` are removed. Standardize timezones and retention cutoffs. When event volume is large or bulk expiration is needed, storing events in a dedicated collection with retention/TTL policies is often easier to operate.

### 17.4. Dropping the Last Step of a Short Action History

**Requirement:** A document stores `recentSteps` in order, and the UI offers an action to discard **the current last step**.

~~~javascript
db.editorSessions.updateOne(
  { _id: "EDIT-1" },
  { $pop: { recentSteps: 1 } }
);
~~~

If the UI defines "undo step X just displayed", verify no other client appended step Y beforehand; under concurrent editing, use versioning/checkpoints or a dedicated undo model. `$pop` strictly removes whatever is last **at update time**.

### 17.5. Deleting an Item When Product Codes Can Repeat

**Requirement:** A cart has two lines sharing the same `sku` but with different shipping options. The user asks to delete **one line**.

~~~javascript
{
  items: [
    { lineId: "L1", sku: "P42", shipping: "STANDARD" },
    { lineId: "L2", sku: "P42", shipping: "EXPRESS" }
  ]
}
~~~

Do not use:

~~~javascript
{ $pull: { items: { sku: "P42" } } }
~~~

because it deletes **both** lines. Use the `lineId` key:

~~~javascript
{ $pull: { items: { lineId: "L2" } } }
~~~

This difference stems from the domain model, not from one operator being "more powerful".

---

## 18. Practice Exercises with Answers

The exercises below use separate illustrative data. Predict the array state before running them in a test collection.

### Exercise 1 — Removing All Occurrences

Initially:

~~~javascript
{ _id: 1, tags: ["A", "B", "A", "C"] }
~~~

Command:

~~~javascript
db.samples.updateOne(
  { _id: 1 },
  { $pull: { tags: "A" } }
);
~~~

**Answer:** `tags: ["B", "C"]`. No `"A"` remains anywhere.

### Exercise 2 — Removing Multiple Values

Initially:

~~~javascript
{ _id: 2, roles: ["ADMIN", "EDITOR", "READER", "EDITOR"] }
~~~

Command:

~~~javascript
db.samples.updateOne(
  { _id: 2 },
  { $pullAll: { roles: ["EDITOR", "READER"] } }
);
~~~

**Answer:** `roles: ["ADMIN"]`. Every occurrence of all listed values is removed.

### Exercise 3 — Distinguishing Head and Tail

Initially:

~~~javascript
{ _id: 3, values: [10, 20, 30] }
~~~

- `$pop: { values: -1 }` -> `[20, 30]`.
- `$pop: { values: 1 }` -> `[10, 20]`.

Both results are evaluated **independently from the initial array**. Running them sequentially on the same document yields a different result.

### Exercise 4 — Removing Child Documents by Condition

Initially:

~~~javascript
{
  _id: 4,
  attempts: [
    { id: "A1", passed: false, score: 40 },
    { id: "A2", passed: true, score: 90 },
    { id: "A3", passed: false, score: 85 }
  ]
}
~~~

Requirement: remove all attempts that **failed** and scored **below 50**.

~~~javascript
db.samples.updateOne(
  { _id: 4 },
  {
    $pull: {
      attempts: {
        passed: false,
        score: { $lt: 50 }
      }
    }
  }
);
~~~

**Answer:** only `A1` is removed; `A2` and `A3` remain.

### Exercise 5 — Inner Array Only in the ENG Group

Initially:

~~~javascript
{
  _id: 5,
  groups: [
    { code: "ENG", users: ["A", "B"] },
    { code: "OPS", users: ["B", "C"] }
  ]
}
~~~

Requirement: remove user B **only in the ENG group**.

~~~javascript
db.samples.updateOne(
  { _id: 5 },
  {
    $pull: {
      "groups.$[g].users": "B"
    }
  },
  {
    arrayFilters: [{ "g.code": "ENG" }]
  }
);
~~~

**Answer:** ENG becomes `["A"]`, OPS remains `["B", "C"]`.

### Exercise 6 — The `$pop` and Retry Trap

Initially `queue: ["J1", "J2", "J3"]`. Client sends `$pop: { queue: 1 }`, loses connection before getting a response, and **resends the same operation as a new command**.

**Answer:** If the first operation actually committed and the second also executes independently, the result can become `["J1"]`, because `"J3"` and then `"J2"` are removed sequentially. Never blindly retry positional operations. Use idempotency, state checks, or identifier-based operations.

### Exercise 7 — `modifiedCount` vs. Number of Removed Elements

Initially `tags: ["x", "x", "x", "y"]`. Run `$pull: { tags: "x" }`.

**Answer:** three elements are removed and the document becomes `tags: ["y"]`; however, `modifiedCount` for an acknowledged `updateOne` is **1**, because it counts **modified documents**, not removed array elements.

### Exercise 8 — Shopping Cart Design

A cart contains `items` and `totalMinor`. An API needs to delete line `L5` without leaving the total wrong. Explain:

1. How to identify the exact line to remove.
2. How to block the operation when the cart is already `CHECKED_OUT`.
3. Why `$pull` alone may be insufficient.
4. How to avoid subtracting the total twice on API retries.
5. When to use a pipeline update recomputing the total from remaining items.

**Hint:** match outer filter by `_id`, owner, and `status: "OPEN"`; match `lineId` in the removal condition; update totals atomically in the same write or recompute from the array; avoid pairing unconditional `$inc` with repeatable removals.

---

## 19. Misconceptions to Avoid

| Misconception | Accurate Understanding |
| --- | --- |
| "`$pull` removes only the first matching element." | It removes **all elements** matching the value or condition. |
| "`$pullAll` removes at most one occurrence per listed value." | It removes **every occurrence** of each listed value. |
| "`$pullAll` works with conditions like `$gte` and `$regex`." | It takes a list of **values**, not general query predicates; use `$pull` for predicates. |
| "`$pop: 3` removes the last three elements." | `$pop` accepts `1` or `-1` for tail/head, removing one element per operation. |
| "`$pop` removes the exact item the client just saw at the end." | It removes whichever item is at the end **when the update runs**; another client may have changed it. |
| "`$pull`ing an item deletes the whole document." | It modifies only the document's array field, not the parent document. |
| "Removing by `sku` always deletes one line item." | If multiple lines share a `sku`, all matching lines are deleted; use a line identifier. |
| "You must wrap two object fields in `$elemMatch` inside `$pull`." | On object arrays, `$pull` applies its condition directly to **each object**; `$elemMatch` is only needed for a **nested inner array**. |
| "Missing fields are initialized to `[]` before removal." | No change occurs when the field does not exist. |
| "Scalar field `"a"` is treated as `["a"]`." | Array removal operators require an actual array field. |
| "`modifiedCount = 1` means one element was removed." | It counts **documents**; one document may have lost multiple elements. |
| "`updateMany` is an atomic transaction across all documents." | Atomicity is per document; multiple documents do not commit/roll back together automatically. |
| "`$pull` automatically keeps `totalMinor` updated." | Derived fields require explicit update rules. |
| "Repeating `$pop` after a timeout is always safe." | Repeating it can drop another element at the head/tail. |
| "`$unset` on an array index removes the element like `$pull`." | `$unset` can leave `null` at that slot. |

## 20. Official MongoDB Documentation

- [`$pull` — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/operator/update/pull/): removes all array elements matching a value or condition.
- [`$pullAll` — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/operator/update/pullAll/): removes all instances of listed values.
- [`$pop` — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/operator/update/pop/): removes the first or last element.
- [Filtered Positional Operator `$[identifier]`](https://www.mongodb.com/docs/manual/reference/operator/update/positional-filtered/): targets outer array elements using `arrayFilters`.
- [`$push` — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/operator/update/push/): appends elements and supports modifiers such as `$slice`.
- [`$filter` — Aggregation](https://www.mongodb.com/docs/manual/reference/operator/aggregation/filter/): produces an array containing only matching elements in pipeline updates.
- [`updateOne()` and `updateMany()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateOne/): update results and operation scope.
- [Java Sync Driver — Update Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/update-documents/): updating fields and using update operators in Java.

When choosing among these three operators, ask precisely: **"am I targeting elements by value, by condition, or by position?"** `$pull` fits values/conditions, `$pullAll` fits explicit value lists, and `$pop` fits trimming the head or tail. In production applications, pair that choice with **stable element identifiers, consistent data types, concurrency controls, and document invariant maintenance** so removing an element never inadvertently corrupts business state.
