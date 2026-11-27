# Setting, Removing, and Renaming Fields with $set, $unset, and $rename in MongoDB

## Lesson Objectives

In MongoDB, data is stored as **BSON documents** with fields that can be scalar values, nested objects, or arrays. When only a few fields of a document need to change, the application should generally avoid reading the entire document, mutating the object in memory, and overwriting everything. MongoDB provides **update operators** to modify precisely the targeted parts of the data.

Three heavily used operators are:

- **`$set`:** assigns a value to a field; if the path is valid and the field does not yet exist, MongoDB can create that field.
- **`$unset`:** removes a field from a document.
- **`$rename`:** renames a field by moving its value from the old name to the new name, subject to important constraints.

After this lesson, learners will be able to:

1. Write `updateOne()` and `updateMany()` commands using the three operators above.
2. Distinguish updating a single field using **dot notation** from replacing an entire embedded document.
3. Understand the difference between **setting `null`** and **removing a field**.
4. Use `$rename` with top-level or nested fields and identify the risk of overwriting an existing target field.
5. Update fields inside array elements with appropriate operators and syntax, while understanding `$rename` limitations regarding arrays.
6. Interpret `matchedCount` and `modifiedCount` results and handle non-matching cases.
7. Evaluate the impact of updates on schema validation, indexes, applications, and historical data.
8. Design a field-name migration workflow that is repeatable, verifiable, and avoids data loss.

> **Remember:** `$set` changes **values**, `$unset` removes **fields**, and `$rename` changes **field names**. All three operations can affect query logic, validators, and indexes; treat them as intentional data mutations, not merely editing a JavaScript object.

---

## 1. How Updating a Document Differs from Replacing a Document

Suppose the `customers` collection contains the document:

~~~javascript
{
  _id: "CUS-101",
  fullName: "Nguyễn Mai",
  contact: {
    email: "mai@example.test",
    phone: "0900000001"
  },
  profile: {
    city: "Da Nang",
    loyaltyTier: "SILVER"
  },
  status: "ACTIVE",
  tags: ["new", "newsletter"],
  createdAt: ISODate("2026-10-10T08:00:00Z")
}
~~~

Business requirement: change only the phone number.

**Updating a single field:**

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  {
    $set: {
      "contact.phone": "0900000099"
    }
  }
);
~~~

Other fields such as `contact.email`, `profile`, and `createdAt` remain intact.

**Replacing a document** is a different kind of operation:

~~~javascript
// DO NOT use this command to perform a single-field change on real data.
db.customers.replaceOne(
  { _id: "CUS-101" },
  {
    fullName: "Nguyễn Mai",
    contact: { phone: "0900000099" }
  }
);
~~~

If the replace command succeeds, fields omitted from the replacement such as `status`, `profile`, and `tags` can be lost. The document's `_id` field is preserved according to replacement rules, but other business fields are not automatically merged back.

| Operation | Meaning | Risk |
|---|---|---|
| `updateOne(filter, {$set: {...}})` | Sets only the fields listed in the operator | Wrong path or overwriting a nested object |
| `updateOne(filter, {$unset: {...}})` | Removes the fields listed in the operator | Losing field values if there is no recovery source |
| `updateOne(filter, {$rename: {...}})` | Changes field names | Overwriting the target field or breaking legacy readers |
| `replaceOne(filter, replacement)` | Replaces the entire document with replacement | Losing any fields omitted from the replacement |

**Practical rule:** A PATCH API typically maps well to update operators; an operation replacing the entire representation requires stricter safeguards to avoid data loss.

### 1.1. Update Command Structure

In **mongosh**:

~~~javascript
db.collectionName.updateOne(
  { /* condition to select document */ },
  {
    $set: {
      fieldA: "value"
    },
    $unset: {
      oldField: ""
    },
    $rename: {
      oldName: "newName"
    }
  }
);
~~~

This is an illustrative structural skeleton; in real operations, paths specified across operators **must not conflict** with one another. For example, you cannot simultaneously set and unset the same `fieldA`, or set both `profile` and `profile.city` in the same update document.

Commonly used methods:

| Method | Scope |
|---|---|
| `updateOne(filter, update, options)` | Updates at most one matching document |
| `updateMany(filter, update, options)` | Updates all matching documents; each document is updated atomically, not the whole set atomically |
| `findOneAndUpdate(filter, update, options)` | Finds one document and updates it, optionally returning the before/after version per options |
| `bulkWrite([...])` | Batches multiple operations; atomicity and per-operation errors still apply |

The following examples primarily use `updateOne()` to clearly illustrate effects on a single document.

---

## 2. Preparing the Practice Data

Use a MongoDB instance or replica set **dedicated to the lab**. These commands create and modify documents, so do not run them against a production database.

In mongosh:

~~~javascript
use update_fields_lab

db.customers.insertMany([
  {
    _id: "CUS-101",
    fullName: "Nguyễn Mai",
    legacyName: "Nguyen Mai",
    contact: {
      email: "mai@example.test",
      phone: "0900000001"
    },
    profile: {
      city: "Da Nang",
      loyaltyTier: "SILVER"
    },
    status: "ACTIVE",
    tags: ["new", "newsletter"],
    createdAt: ISODate("2026-10-10T08:00:00Z")
  },
  {
    _id: "CUS-102",
    fullName: "Trần Bình",
    legacyName: "Tran Binh",
    contact: {
      email: "binh@example.test"
    },
    profile: {
      city: "Hanoi",
      loyaltyTier: "GOLD"
    },
    status: "ACTIVE",
    tags: ["vip"],
    createdAt: ISODate("2026-10-11T08:00:00Z")
  },
  {
    _id: "CUS-103",
    fullName: "Lê Chi",
    contact: {
      email: null,
      phone: "0900000003"
    },
    status: "INACTIVE",
    tags: [],
    createdAt: ISODate("2026-10-12T08:00:00Z")
  }
]);
~~~

Inspect:

~~~javascript
db.customers.find().sort({ _id: 1 });
~~~

These cases are intentionally constructed:

- `CUS-101` has both `contact.email` and `contact.phone`.
- `CUS-102` has `contact.email` but does not yet have `contact.phone`.
- `CUS-103` has `contact.email: null`, and lacks both `profile` and `legacyName`.

The difference between a **missing field** and a **field existing with value `null`** will matter when using `$unset`.

---

## 3. `$set`: Assigning a Value or Creating a Field

### 3.1. Syntax

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  {
    $set: {
      status: "VERIFIED"
    }
  }
);
~~~

After the command, `status` on `CUS-101` becomes `"VERIFIED"`; other fields are not modified merely because they were omitted.

`$set` has two primary behaviors:

1. If the field exists and the path is valid, **replace the value**.
2. If the field does not exist and the path can be validly created, **create the field and assign the value**.

For example, `CUS-102` does not yet have `contact.phone`:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-102" },
  {
    $set: {
      "contact.phone": "0900000002"
    }
  }
);
~~~

Afterward:

~~~javascript
db.customers.findOne(
  { _id: "CUS-102" },
  { contact: 1 }
);
~~~

Illustrative result:

~~~javascript
{
  _id: "CUS-102",
  contact: {
    email: "binh@example.test",
    phone: "0900000002"
  }
}
~~~

### 3.2. Setting Multiple Fields in One Update

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  {
    $set: {
      status: "ACTIVE",
      "contact.phone": "0911111111",
      "profile.loyaltyTier": "GOLD",
      updatedAt: new Date()
    }
  }
);
~~~

MongoDB applies updates on a **single document** atomically within a single write operation. The specified fields are updated together so other applications never observe a "half-updated" state of the same document.

This does not mean an `updateMany()` command modifying thousands of documents is a single atomic transaction overall. Each individual document is updated atomically, while other documents may be observed while the batch is still running.

### 3.3. Creating Nested Objects When the Parent Does Not Exist

`CUS-103` does not yet have `profile`. The command:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-103" },
  {
    $set: {
      "profile.city": "Hue",
      "profile.loyaltyTier": "BRONZE"
    }
  }
);
~~~

can create the `profile` object and its child fields:

~~~javascript
{
  profile: {
    city: "Hue",
    loyaltyTier: "BRONZE"
  }
}
~~~

**Precondition:** The path must be constructible. If `profile` already holds an incompatible scalar value, for example:

~~~javascript
{ _id: "CUS-BAD", profile: "unknown" }
~~~

then an update targeting `"profile.city"` cannot automatically treat the string `"unknown"` as an object to attach a child field; the operation will fail due to an invalid path. Perform a data type migration before setting child fields.

### 3.4. Dot Notation vs. Replacing an Entire Embedded Document

**Updating a single child field:**

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  {
    $set: {
      "contact.email": "new.mai@example.test"
    }
  }
);
~~~

After the command, `contact.phone` remains.

**Replacing the entire nested object:**

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  {
    $set: {
      contact: {
        email: "new.mai@example.test"
      }
    }
  }
);
~~~

In the second case, **the entire `contact` value is replaced with the new object**; `contact.phone` is gone because the newly assigned object does not contain that field.

| Usage | Effect |
|---|---|
| `$set: {"contact.email": value}` | Updates the `email` field inside `contact` |
| `$set: {contact: {email: value}}` | Replaces the entire `contact` field with a new object |

This is one of the most common mistakes when updating embedded documents.

### 3.5. `$set` with a `null` Value

~~~javascript
db.customers.updateOne(
  { _id: "CUS-102" },
  {
    $set: {
      "contact.email": null
    }
  }
);
~~~

This command **does not remove** the `contact.email` field. It keeps the field present and sets its value to BSON null.

MongoDB can distinguish the two states:

~~~javascript
// Find documents where contact.email exists
db.customers.find({
  "contact.email": { $exists: true }
});

// Find documents missing contact.email
db.customers.find({
  "contact.email": { $exists: false }
});

// Find fields with an actual BSON null value
db.customers.find({
  "contact.email": { $type: "null" }
});
~~~

Notice that a plain equality query:

~~~javascript
db.customers.find({
  "contact.email": null
});
~~~

typically **matches both documents where the field is null and documents missing the field**, due to MongoDB's null-equality query semantics. If business logic must distinguish "no value yet" from "field does not exist", use `$exists` or `$type` accordingly.

### 3.6. `$set` on Arrays

You can replace an entire array:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  {
    $set: {
      tags: ["verified", "priority"]
    }
  }
);
~~~

Here the old array is replaced with the new array. If the goal is to **add elements** rather than replace the whole array, operators such as `$push` or `$addToSet` are more appropriate.

You can update by array element position when the data structure, filter, and operators support it. However, be cautious with positional indices: when an array changes concurrently, the element at index N may no longer be the business element you intended to update.

### 3.7. Setting an Update Timestamp Field

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  {
    $set: {
      status: "ACTIVE",
      updatedAt: new Date()
    }
  }
);
~~~

`new Date()` in mongosh is evaluated on the client side and sent as a BSON Date. To set the timestamp using the server's clock, MongoDB provides the `$currentDate` operator:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  {
    $set: { status: "ACTIVE" },
    $currentDate: { updatedAt: true }
  }
);
~~~

`$currentDate` is not the focus of this lesson, but it illustrates combining different update operators without conflicting on the same field.

### 3.8. `$set` Does Not Replace `$inc` and Concurrency Checks

For example, incrementing points:

~~~javascript
// Prone to race conditions if reading first and writing back the computed value
// const oldPoints = db.customers.findOne({ _id: "CUS-101" }).points;
// db.customers.updateOne(..., { $set: { points: oldPoints + 1 } });
~~~

With multiple concurrent writers, a "read then `$set`" pattern can lose updates. For arithmetic increments/decrements, `$inc` is usually the right choice:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  { $inc: { points: 1 } }
);
~~~

If the application needs to transition state only when the current state matches, place the condition in the **filter**:

~~~javascript
db.customers.updateOne(
  {
    _id: "CUS-101",
    status: "ACTIVE"
  },
  {
    $set: { status: "SUSPENDED" }
  }
);
~~~

When no document matches, `matchedCount` is 0; that can signal that the state was already changed earlier.

---

## 4. `$unset`: Removing a Field from a Document

### 4.1. Syntax and Right-Hand Value

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  {
    $unset: {
      legacyName: ""
    }
  }
);
~~~

After the command, `legacyName` is no longer present in the document.

The value paired with the key in `$unset` is purely syntactic and **does not determine any value assigned to the field**. People commonly write an empty string `""` or `1`:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-102" },
  {
    $unset: {
      legacyName: 1
    }
  }
);
~~~

Both forms mean **delete the field**, not set it to an empty string or the number 1.

### 4.2. Removing Multiple Fields at Once

~~~javascript
db.customers.updateOne(
  { _id: "CUS-102" },
  {
    $unset: {
      "contact.phone": "",
      "profile.loyaltyTier": ""
    }
  }
);
~~~

Only the listed fields are removed. The parent object remains if it contains other fields; do not assume MongoDB automatically cleans up empty parent objects according to custom business rules.

### 4.3. `$unset` Is Not the Same as `$set: {field: null}`

Before-and-after comparison:

| Before | Command | After |
|---|---|---|
| `{email:"a@example.test"}` | `$set: {email:null}` | `{email:null}` |
| `{email:"a@example.test"}` | `$unset: {email:""}` | `{}` |
| `{}` | `$unset: {email:""}` | `{}` |
| `{email:null}` | `$unset: {email:""}` | `{}` |

Impact on queries:

~~~javascript
// Returns documents when the field exists, even if its value is null
db.customers.find({
  "contact.email": { $exists: true }
});

// Returns documents when the field does not exist
db.customers.find({
  "contact.email": { $exists: false }
});
~~~

In schema design:

- **`null`** may mean "the field is defined but currently has no value".
- **A missing field** may mean "the field does not apply", "an older schema version", or "was removed".

This convention must be agreed upon between the database and the application. There is no single answer right for every domain.

### 4.4. Removing One Nested Field

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  {
    $unset: {
      "contact.phone": ""
    }
  }
);
~~~

If `contact` was previously:

~~~javascript
{
  email: "mai@example.test",
  phone: "0900000001"
}
~~~

then after the command it becomes:

~~~javascript
{
  email: "mai@example.test"
}
~~~

Do not write:

~~~javascript
// Deletes the entire contact object, not just phone
db.customers.updateOne(
  { _id: "CUS-101" },
  { $unset: { contact: "" } }
);
~~~

unless the business requirement genuinely intends to delete **the entire `contact` object**.

### 4.5. `$unset` on Arrays: Different from Removing an Element

Suppose the `orders` collection contains:

~~~javascript
{
  _id: "ORD-101",
  items: [
    { sku: "A", quantity: 1, temporaryNote: "promo" },
    { sku: "B", quantity: 2, temporaryNote: "legacy" }
  ]
}
~~~

If the goal is to **remove `temporaryNote` from an item**, you can use a filtered positional update:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $unset: {
      "items.$[line].temporaryNote": ""
    }
  },
  {
    arrayFilters: [
      { "line.sku": "B" }
    ]
  }
);
~~~

Result: the item with `sku: "B"` still exists, without the `temporaryNote` field.

Conversely, `$unset` on an **array element itself** does not pull the element out and compact the array. With the positional `$` operator, unsetting an array element sets that slot to `null` to preserve array positions.

Example illustrating this behavior:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101", "items.sku": "B" },
  {
    $unset: { "items.$": "" }
  }
);
~~~

The resulting array can contain a `null` element at that position. To **completely remove elements from an array**, use `$pull` with an appropriate condition:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $pull: {
      items: { sku: "B" }
    }
  }
);
~~~

**Remember:** `$unset` removes fields; `$pull` removes matching array elements. They are not interchangeable.

### 4.6. What If the Field Does Not Exist?

If a field named in `$unset` does not exist, the operation does not create a new field and does not raise an error merely because the field is absent.

~~~javascript
db.customers.updateOne(
  { _id: "CUS-103" },
  {
    $unset: {
      thisFieldNeverExisted: ""
    }
  }
);
~~~

If the filter locates the document, `matchedCount` can be 1 while `modifiedCount` is 0 because no actual data change occurred.

This property often makes old-field cleanup migrations safe to re-run, though you must still check other conditions such as validators, indexes, and matched document counts.

### 4.7. Do Not Delete Structural Fields Without Evaluating Constraints

You cannot use `$unset` to remove the mandatory `_id` field. In a collection with JSON Schema validation requiring `email`, removing `email` may be rejected when validation is enabled in error-blocking mode.

For example, if the collection has the rule:

~~~javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: ["email"]
  }
}
~~~

then:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  {
    $unset: { email: "" }
  }
);
~~~

can be blocked by the validator because it renders the document invalid. A schema change must be coordinated with validator and application updates, not just a single update command.

---

## 5. `$rename`: Renaming a Field

### 5.1. Syntax

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  {
    $rename: {
      legacyName: "displayNameLegacy"
    }
  }
);
~~~

If the document initially had:

~~~javascript
{
  legacyName: "Nguyen Mai"
}
~~~

after the command it has:

~~~javascript
{
  displayNameLegacy: "Nguyen Mai"
}
~~~

The value of the old field moves to the new name. The `legacyName` field is removed.

**Important distinction:** `$rename` renames a **field inside a document**, not a collection. Renaming a collection is a separate operation, such as `renameCollection`, with its own scope and constraints.

### 5.2. Renaming Nested Fields

Suppose a document has:

~~~javascript
{
  _id: "CUS-201",
  contact: {
    telephone: "0900000009",
    email: "example@example.test"
  }
}
~~~

Rename `contact.telephone` to `contact.phone`:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-201" },
  {
    $rename: {
      "contact.telephone": "contact.phone"
    }
  }
);
~~~

MongoDB supports valid nested field paths with `$rename`, provided no data type or path constraints are violated.

### 5.3. Risk of Data Loss When the Target Field Already Exists

**Critical:** If the target field name already holds a value, `$rename` can **overwrite the value at the target field**.

Suppose:

~~~javascript
{
  _id: "CUS-301",
  oldEmail: "old@example.test",
  email: "current@example.test"
}
~~~

Running:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-301" },
  {
    $rename: {
      oldEmail: "email"
    }
  }
);
~~~

moves the value from `oldEmail` to `email`; the existing `"current@example.test"` value at the target can be lost.

Therefore, **never run `$rename` in bulk before checking for documents that have both the source and target fields**.

How to count conflicts:

~~~javascript
db.customers.countDocuments({
  oldEmail: { $exists: true },
  email: { $exists: true }
});
~~~

How to inspect samples:

~~~javascript
db.customers.find(
  {
    oldEmail: { $exists: true },
    email: { $exists: true }
  },
  {
    _id: 1,
    oldEmail: 1,
    email: 1
  }
).limit(20);
~~~

If the count is non-zero, you must define a business rule: which field takes precedence, whether reconciliation or keeping both is needed, or whether the migration must pause for manual handling.

### 5.4. When the Source Field Does Not Exist

When the source field is absent, `$rename` does not create the target field and typically makes no change to that document:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-103" },
  {
    $rename: {
      legacyName: "displayNameLegacy"
    }
  }
);
~~~

In the lab dataset, `CUS-103` has no `legacyName`. This operation does not create `displayNameLegacy` just because a rename was requested.

### 5.5. `$rename` Cannot Rename Fields Inside Array Elements

Suppose the document is:

~~~javascript
{
  _id: "ORD-301",
  items: [
    { oldCode: "A", quantity: 1 },
    { oldCode: "B", quantity: 2 }
  ]
}
~~~

You cannot use `$rename` like this:

~~~javascript
// Not a supported way to rename a field inside each array element.
db.orders.updateOne(
  { _id: "ORD-301" },
  {
    $rename: {
      "items.oldCode": "items.sku"
    }
  }
);
~~~

The `$rename` operator **does not support renaming fields inside arrays**. To rename `oldCode` to `sku` in every item, use another strategy: an application-side migration, an aggregation pipeline update with `$map`/object-transformation operators supported by your version, or rewriting elements with verified logic.

With arrays, you can still use `$set` and `$unset` on **element fields** via `arrayFilters`, but that does not imply `$rename` accepts positional paths.

### 5.6. `$rename` Does Not Preserve Field Ordering in a Document

Field order within a BSON document is not a business ordering guarantee. `$rename` can change the physical position/ordering of fields inside a document. Do not design APIs, serializers, or processing logic that assumes a renamed field stays in its original position.

If display order matters, control it in query projections, the application layer, or the UI rather than relying on physical field order inside the document.

### 5.7. `$rename` and Special Field Names

Dot notation (`"contact.phone"`) normally denotes a path into an embedded document, not a top-level field whose literal name contains a dot. Some MongoDB versions allow storing fields with special characters under specific restrictions; standard update operators may not access them as expected. If a schema has field names containing `.` or starting with `$`, review operators like `$getField`, `$setField`, and version-specific limits.

For new designs, use clean field names without characters that introduce ambiguity in dot notation.

---

## 6. Comparison Table: `$set`, `$unset`, and `$rename`

| Criterion | `$set` | `$unset` | `$rename` |
|---|---|---|---|
| Purpose | Assign or replace value | Remove field | Rename field |
| Source field absent | Can create target field along valid path | No change | No change if source absent |
| Target field exists | Overwrites specified value | Removes that field | Can overwrite target field |
| Nested paths | Yes, via dot notation | Yes, via dot notation | Yes, if path is valid and not inside an array |
| Field inside array object | Can use positional/`arrayFilters` | Can use positional/`arrayFilters` | Renaming fields inside arrays is not supported |
| Remove an array element entirely | No; sets value | No; unsetting an element can leave `null` | No |
| Index impact | Indexes on the value may update | Related indexes may update | Old index does not automatically switch to new field name |
| Schema validator impact | New value must be valid | Cannot remove required field if validation blocks | Validator and field names may need updating |
| Primary caution | Overwriting nested objects | Different from setting `null` | Overwriting target fields and migrations |

Example operations on a document with:

~~~javascript
{
  oldName: "An",
  email: "an@example.test",
  profile: { city: "Hue", phone: "0900000001" }
}
~~~

| Update | Notable Outcome |
|---|---|
| `$set: {email:"new@example.test"}` | Email changes, other fields preserved |
| `$set: {"profile.city":"Da Nang"}` | Only city changes, phone preserved |
| `$set: {profile:{city:"Da Nang"}}` | Entire profile object replaced; phone lost |
| `$unset: {email:""}` | Email removed |
| `$set: {email:null}` | Email remains with null value |
| `$rename: {oldName:"displayName"}` | Field renamed and value moved |

---

## 7. Updating Multiple Documents: `updateMany()` and Safety Conditions

### 7.1. Example: Setting a Default Field for Documents Missing It

Suppose you want to add `marketingOptIn: false` **only when the field does not yet exist**:

~~~javascript
db.customers.updateMany(
  {
    marketingOptIn: { $exists: false }
  },
  {
    $set: {
      marketingOptIn: false
    }
  }
);
~~~

Filtering with `$exists: false` prevents overwriting existing opt-in/opt-out choices already stored.

A dangerous approach:

~~~javascript
// Do not use when the collection already has user-selected values.
db.customers.updateMany(
  {},
  {
    $set: {
      marketingOptIn: false
    }
  }
);
~~~

This command updates **every** document matching the empty filter, potentially overwriting valid `true` values.

### 7.2. Removing a Deprecated Field on Documents That Still Have It

~~~javascript
db.customers.updateMany(
  {
    deprecatedFlag: { $exists: true }
  },
  {
    $unset: {
      deprecatedFlag: ""
    }
  }
);
~~~

Before running in production, verify that applications, background jobs, reports, and indexes no longer reference this field.

### 7.3. Bulk Renaming When No Target Conflict Exists

For example, moving `legacyName` to `displayNameLegacy` without overwriting an existing new field:

~~~javascript
db.customers.updateMany(
  {
    legacyName: { $exists: true },
    displayNameLegacy: { $exists: false }
  },
  {
    $rename: {
      legacyName: "displayNameLegacy"
    }
  }
);
~~~

This condition protects documents containing both source and target **within the scope of the filter and per-document atomicity**. However, those conflicted documents remain unprocessed after the migration; you must count them and decide a dedicated conflict policy.

### 7.4. `updateMany()` Is Not an Atomic Transaction Across the Whole Collection

MongoDB provides atomicity at the **single-document** level for standard updates. When `updateMany()` affects multiple documents:

- Each document is updated atomically on its own.
- Other documents can be queried while the migration is still running.
- The command can stop with an error after some documents have already been modified.
- Re-runs must account for idempotency and partially migrated state.
- If cross-document atomicity is required, evaluate multi-document transactions on supported topologies and their associated overhead.

Therefore, "command returned an error" does not automatically mean "no documents were modified".

### 7.5. Accurate Filters Are the First Line of Defense

Before running `updateMany()`:

1. Scope the filter accurately: tenant, document type, schema version, status, time range.
2. Count matching documents with `countDocuments(filter)`.
3. Inspect a few samples with `find(filter).limit(...)` and an appropriate projection.
4. Check for conflicts, required fields, and validators.
5. Test in a staging environment or on a small batch when appropriate.
6. Monitor `matchedCount` and `modifiedCount`.
7. Verify postconditions after the update.

Never treat `updateMany({}, ...)` as harmless: an empty filter usually targets the entire collection.

---

## 8. Update Results: Understanding `matchedCount` and `modifiedCount`

Example:

~~~javascript
const result = db.customers.updateOne(
  { _id: "CUS-101" },
  {
    $set: {
      status: "ACTIVE"
    }
  }
);

printjson(result);
~~~

A result may look like:

~~~javascript
{
  acknowledged: true,
  matchedCount: 1,
  modifiedCount: 0,
  upsertedCount: 0
}
~~~

Interpretation:

- `acknowledged: true`: the operation received acknowledgment under the requested write concern.
- `matchedCount: 1`: the filter located one document.
- `modifiedCount: 0`: no document changed, e.g., because `status` was already `"ACTIVE"`.
- `upsertedCount: 0`: no new document was created by upsert.

Key scenarios:

| Scenario | `matchedCount` | `modifiedCount` | Explanation |
|---|---:|---:|---|
| Right document selected, different value set | 1 | 1 | Update applied |
| Right document selected, identical value set | 1 | 0 | No data change occurred |
| Filter finds no document | 0 | 0 | No update; possibly wrong ID or state changed |
| `$unset` on a field that did not exist | 1 | 0 | Nothing to remove |
| `$rename` when source does not exist | 1 | 0 | No value to move |

Actual results also depend on version, write concern, other update clauses, and system conditions. With unacknowledged writes, do not rely on result counts as if they were always populated.

### 8.1. `upsert: true` Can Create a New Document

~~~javascript
db.customers.updateOne(
  { _id: "CUS-999" },
  {
    $set: {
      status: "ACTIVE"
    }
  },
  {
    upsert: true
  }
);
~~~

If the filter matches nothing, MongoDB can **insert** a new document. This is useful, but use caution in APIs intended to "only edit existing data"; if new documents should not be created, leave upsert disabled.

During field-name migrations, an accidental upsert can create a document missing required fields or containing invalid business state. Clearly separate create vs. update scopes.

---

## 9. Combining Multiple Operators in One Update

You can combine `$set`, `$unset`, and `$rename` as long as the targeted fields do not conflict.

Suppose a document has:

~~~javascript
{
  _id: "CUS-401",
  oldDisplayName: "Phuong",
  oldPhone: "0900000001",
  accountStatus: "ACTIVE",
  legacyFlag: true
}
~~~

Requirements:

- Rename `oldDisplayName` to `displayName`.
- Remove `legacyFlag`.
- Set `accountStatus` to `VERIFIED`.
- Set `updatedAt` to the current time.

~~~javascript
db.customers.updateOne(
  { _id: "CUS-401" },
  {
    $rename: {
      oldDisplayName: "displayName"
    },
    $unset: {
      legacyFlag: ""
    },
    $set: {
      accountStatus: "VERIFIED",
      updatedAt: new Date()
    }
  }
);
~~~

The affected paths are disjoint, so they do not conflict. If `displayName` already exists, the rename can overwrite it; verify that case before running.

### 9.1. Conflicting Combinations

An example that is semantically invalid and can be rejected by MongoDB due to **conflicting update paths**:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-401" },
  {
    $set: {
      profile: { city: "Hue" },
      "profile.city": "Hanoi"
    }
  }
);
~~~

Both assignments touch the `profile` path and its child branch `profile.city`.

Similarly, do not combine:

~~~javascript
{
  $set: { status: "ACTIVE" },
  $unset: { status: "" }
}
~~~

in the same update.

**Do not rely on operator key ordering inside the object to resolve conflicts.** Split into valid operations or adopt a clear update strategy.

### 9.2. When Transformations Depend on Existing Values

Classic update operators normally accept literal values. When you need to read an existing field value, compute a new value, and assign it, you can use an **aggregation pipeline update** on supported MongoDB versions.

For example, setting `normalizedName` from an existing `fullName`:

~~~javascript
db.customers.updateMany(
  { fullName: { $type: "string" } },
  [
    {
      $set: {
        normalizedName: { $toLower: "$fullName" }
      }
    }
  ]
);
~~~

**Syntax distinction:** `$set` in the example above is an **aggregation pipeline stage** accepting expressions, distinct from the `$set` update operator in a traditional update object. Despite sharing a name, value interpretation differs.

Example moving a field via pipeline:

~~~javascript
db.customers.updateMany(
  {
    oldField: { $exists: true },
    newField: { $exists: false }
  },
  [
    {
      $set: {
        newField: "$oldField"
      }
    },
    {
      $unset: "oldField"
    }
  ]
);
~~~

In pipeline form, `"$oldField"` is evaluated as a **field path reference** in an expression, not a literal string. In an update object `{$set: {newField: "$oldField"}}`, it would be treated as the **literal string** `"$oldField"`.

Pipelines are powerful when migrations require computation, though you still need to check versions, types, validators, potentially missing fields, and pre-existing target fields.

---

## 10. Impact on Schema Validation, Indexes, and Queries

### 10.1. Schema Validation

A collection may use a validator:

~~~javascript
db.createCollection("validated_contacts", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["email"],
      properties: {
        email: { bsonType: "string" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

If a valid document has its required `email` field removed via `$unset`, MongoDB can reject the write because the resulting document violates validation.

Similarly, renaming `email` to `primaryEmail` while the validator still requires `email` causes data and validator to conflict.

When renaming fields in production, plan concurrently for:

- JSON Schema/validators in MongoDB.
- Validation in Java/Spring Boot or driver mappings.
- Queries, projections, sorts, aggregations, and reports.
- Indexes, partial index filters, TTL indexes, and unique constraints.
- API serializers/deserializers and data contract documentation.

### 10.2. Indexes Bound to Field Paths

Suppose there is an index:

~~~javascript
db.customers.createIndex(
  { legacyName: 1 },
  { name: "idx_legacy_name" }
);
~~~

After migration:

~~~javascript
db.customers.updateMany(
  {
    legacyName: { $exists: true },
    displayNameLegacy: { $exists: false }
  },
  {
    $rename: {
      legacyName: "displayNameLegacy"
    }
  }
);
~~~

**The `{legacyName:1}` index does not automatically rewrite its definition into `{displayNameLegacy:1}`.** New queries:

~~~javascript
db.customers.find({
  displayNameLegacy: "Nguyen Mai"
});
~~~

must be evaluated and may require creating an index on the new field:

~~~javascript
db.customers.createIndex(
  { displayNameLegacy: 1 },
  { name: "idx_display_name_legacy" }
);
~~~

Only after confirming no queries or constraints depend on the old index should the team consider dropping it via governance procedures.

### 10.3. Unique Indexes and Missing Fields

A unique index on a field follows specific rules when the field is missing or null; you cannot assume `$unset` on a uniquely indexed field will always succeed across all documents. With a **single-field unique index**, multiple documents lacking the field can cause a duplicate-key conflict under standard settings.

Before bulk-deleting a field referenced by a unique or partial index, check the uniqueness rules and index filter expression.

### 10.4. Queries Using Old Field Names Will Not Automatically Switch

Before migration:

~~~javascript
db.customers.find({ legacyName: "Nguyen Mai" });
~~~

Once the field is renamed to `displayNameLegacy`, queries on `legacyName` stop matching migrated documents. This affects:

- Legacy API instances not yet upgraded.
- Batch jobs and data consumers.
- Dashboards, reports, and materialized views.
- Change Streams consumers inspecting field names.
- Object mappings, projections, and repository methods.

When multiple application versions run concurrently, a bulk rename can cause outages if no compatibility phase is implemented.

---

## 11. Safe Field-Rename Migration in a Live System

### 11.1. Context

The system currently uses `phoneNumber` and wants to standardize on `contact.phone`. Three groups of documents exist:

1. Only `phoneNumber`.
2. Only `contact.phone`.
3. **Both**, potentially with different values.

Running:

~~~javascript
db.customers.updateMany(
  {},
  {
    $rename: {
      phoneNumber: "contact.phone"
    }
  }
);
~~~

puts the third group at risk of overwriting the target value. A proper migration must establish a conflict resolution policy.

### 11.2. Step 1 — Measure the Current State

~~~javascript
const hasOld = db.customers.countDocuments({
  phoneNumber: { $exists: true }
});

const hasNew = db.customers.countDocuments({
  "contact.phone": { $exists: true }
});

const hasBoth = db.customers.countDocuments({
  phoneNumber: { $exists: true },
  "contact.phone": { $exists: true }
});

printjson({ hasOld, hasNew, hasBoth });
~~~

Sample conflicting records:

~~~javascript
db.customers.find(
  {
    phoneNumber: { $exists: true },
    "contact.phone": { $exists: true }
  },
  {
    _id: 1,
    phoneNumber: 1,
    "contact.phone": 1
  }
).limit(20);
~~~

Do not merely count; inspect field type distributions, whether `contact` exists, whether `contact` is ever a scalar, whether `null` values exist, and whether mixed string/number types occur.

### 11.3. Step 2 — Design Application Compatibility

A rollout workflow can look like:

~~~text
Phase A: New application reads the new field,
         falling back to the old field if needed.
         Writes follow the agreed standardization rule.

Phase B: Create indexes/validators supporting the new field
         without breaking older running versions.

Phase C: Backfill data that has only the old field.
         Classify conflicts and resolve per business rules.

Phase D: Confirm all consumers have switched to the new field,
         stop writing the old field.

Phase E: Clean up old fields and old indexes, tighten validators,
         monitor and keep a rollback plan ready.
~~~

In multi-service or rolling-deployment environments, dual-reading during the transition window is often essential. Any dual-writing, if needed, must follow consistent rules to avoid divergence between the two fields.

### 11.4. Step 3 — Backups and Recovery Plan

Before a major migration:

- Have a verified backup or snapshot and know how to restore it.
- Record document counts and timestamps.
- Have a plan to halt conflicting writes or handle concurrent writes.
- Check impacts on throughput, replication lag, and storage capacity.
- Designate an owner for rollback decisions and prepare a runbook.

**`$rename` is not a versioning or undo mechanism.** If target data is overwritten, you cannot rely on a reverse rename to recover lost values.

### 11.5. Step 4 — Run Conditional Backfill

For example, migrating only documents that have the old field:

~~~javascript
const filter = {
  phoneNumber: { $exists: true },
  "contact.phone": { $exists: false }
};

db.customers.updateMany(
  filter,
  {
    $rename: {
      phoneNumber: "contact.phone"
    }
  }
);
~~~

In practice, verify that the `contact` path is compatible (not currently a scalar), the schema validator permits the output, and the application is ready.

**Do not run this on documents where the target already exists.** Handle those separately according to value-precedence policy and data checks.

### 11.6. Step 5 — Verify Results

~~~javascript
// Number of documents still having the source field
db.customers.countDocuments({
  phoneNumber: { $exists: true }
});

// Number of documents having the target field
db.customers.countDocuments({
  "contact.phone": { $exists: true }
});

// Documents still having both fields
db.customers.countDocuments({
  phoneNumber: { $exists: true },
  "contact.phone": { $exists: true }
});
~~~

Cross-check via application read paths, sample documents, business metrics, and queries using the new index.

Do not rely solely on `modifiedCount`. Some documents may still have the source field because they were excluded due to conflicts, even though the command succeeded on other documents.

### 11.7. Step 6 — Controlled Cleanup

Only once the entire system exclusively uses the new field and all conflicts are resolved should you consider `$unset` on the old field, updating validators, and dropping old indexes. Maintain sufficient observation time to catch stray legacy consumers.

A good **idempotent** migration script can be re-run without overwriting valid data:

- Filters based on `$exists` or schema version.
- Never overwrites an existing new field without an explicit rule.
- Logs matched and modified document counts.
- Defines explicit postconditions.
- Never marks completion while unresolved conflicts remain.

---

## 12. Notes on Concurrency, Transactions, and Write Concern

### 12.1. Single-Document Atomicity

An update modifying multiple fields within one document is atomic. Example:

~~~javascript
db.customers.updateOne(
  {
    _id: "CUS-101",
    status: "ACTIVE"
  },
  {
    $set: {
      status: "VERIFIED",
      verifiedAt: new Date()
    },
    $unset: {
      legacyFlag: ""
    }
  }
);
~~~

Other applications will not see a partially updated state on that same document.

However, do not assume the operation provides automatic history recovery. Once a field is deleted and committed, recovering its prior value requires source data, audit logs/backups, or a pre-designed history-tracking mechanism.

### 12.2. Multi-Document Updates and Transactions

An `updateMany()` does not provide batch-wide atomicity. If business logic strictly requires "all documents or none", you may need a multi-document transaction on a supported topology, with added operational overhead. For large migrations, very long transactions are often unsuitable; prefer small-batch backfills, migration state markers, and compatibility rules.

### 12.3. Concurrent Writes

During backfill, older application versions may still write `phoneNumber`, causing the old field to reappear right after backfill. Therefore, establish a deployment strategy:

- Stop writing the old field name.
- Or implement controlled dual-write.
- Or allow iterative backfill passes until no legacy writers remain.

An `$exists` filter condition protects each individual update against an existing target, but it does not solve rollout coordination while mixed application versions are writing differently.

### 12.4. Write Concern and Uncertain Outcomes

If a write concern timeout occurs, do not simply conclude the update did not execute. The operation may have already been applied without satisfying acknowledgment criteria. When retrying migrations, **idempotent** design and re-reading actual state are safer than relying solely on error messages.

---

## 13. Examples with Java Driver and Spring Data MongoDB

### 13.1. MongoDB Java Sync Driver

With the MongoDB Java Driver, build updates using helpers in `com.mongodb.client.model.Updates`.

~~~java
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.combine;
import static com.mongodb.client.model.Updates.set;
import static com.mongodb.client.model.Updates.unset;
import static com.mongodb.client.model.Updates.rename;

import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

MongoCollection<Document> customers =
    database.getCollection("customers");

UpdateResult result = customers.updateOne(
    eq("_id", "CUS-101"),
    combine(
        set("contact.phone", "0900000099"),
        unset("legacyFlag"),
        rename("legacyName", "displayNameLegacy")
    )
);

System.out.println(result.getMatchedCount());
System.out.println(result.getModifiedCount());
~~~

This snippet assumes `database` was obtained from a connected `MongoClient`; credentials, connection pooling, error handling, retries, and logging belong in the application layer.

**Caution:** This combined example is appropriate only when paths do not conflict and the target field `displayNameLegacy` holds no value that must be preserved. In production, apply proper filters/data classification before renaming.

### 13.2. Spring Data MongoDB with `MongoTemplate`

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

Query query = Query.query(
    Criteria.where("_id").is("CUS-101")
);

Update update = new Update()
    .set("contact.phone", "0900000099")
    .unset("legacyFlag")
    .rename("legacyName", "displayNameLegacy");

var result = mongoTemplate.updateFirst(
    query,
    update,
    "customers"
);
~~~

Pay attention to `@Id` mapping, Java property names, and actual BSON field names. `MongoTemplate` may apply entity-class mapping depending on which overloads you call; never assume Java field names always equal stored BSON field names if `@Field` or custom converters are configured.

### 13.3. Implementing PATCH APIs Safely

A PATCH request might carry action types such as:

~~~json
{
  "set": {
    "contact.phone": "0900000099"
  },
  "unset": [
    "legacyNote"
  ]
}
~~~

This is a **hypothetical API format**, not a MongoDB command. The server must validate the allowed field list, value types, and permissions, and prevent modifying sensitive fields such as `_id`, `tenantId`, or restricted business statuses.

**Never pass raw client input directly into a MongoDB update document.** Untrusted API callers could attempt unauthorized field writes, operator injection, or privilege-escalation modifications. Whitelist fields, validate data, and construct the update on the server.

### 13.4. Renaming Fields in Application Code Does Not Migrate the Database

Renaming a Java property:

~~~java
private String primaryEmail;
~~~

does not automatically rename existing BSON fields stored in MongoDB. Mapping annotations can maintain temporary compatibility, but long-term you must plan when to migrate data and update queries, indexes, and validators.

---

## 14. Common Mistakes and How to Fix Them

### Mistake A — Updating a Nested Object Drops Sibling Fields

**Symptom:** After `$set: {contact: {email: ...}}`, `contact.phone` disappears.

**Cause:** Replaced the entire `contact` object instead of updating only `contact.email`.

**Correct approach:**

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  { $set: { "contact.email": "new@example.test" } }
);
~~~

### Mistake B — Assuming `$set: {email: null}` Removes Email

**Symptom:** `$exists: true` still returns the document.

**Cause:** The field still exists with a null value.

**Correct approach:** Use `$unset: {email: ""}` when the domain requirement is to remove the field.

### Mistake C — Unsetting an Array Element Leaves `null`

**Symptom:** The array retains the same length, with a null element inside.

**Cause:** `$unset` is not an array element removal operator.

**Correct approach:** Use `$pull` with an appropriate business condition, or apply another array update strategy.

### Mistake D — `$rename` Overwrites the Target Field

**Symptom:** The previous value in the new field is lost.

**Cause:** Renamed without checking for documents containing both source and target.

**Correct approach:** Query for conflicts, finalize precedence policy, filter for documents having source and lacking target, and back up before migrating.

### Mistake E — Using `$rename` on Fields Inside Arrays

**Symptom:** Rename is unsupported or yields unintended errors.

**Cause:** `$rename` does not support renaming fields inside array elements.

**Correct approach:** Use a dedicated application migration or a version-appropriate aggregation pipeline with data verification.

### Mistake F — Operation Modifies Zero Documents

**Symptom:** `matchedCount: 0` or `modifiedCount: 0`.

**Possible causes:**

- Filter has wrong `_id` or wrong BSON type.
- Status condition is no longer satisfied.
- Field already holds the new value.
- Field targeted by `$unset`/`$rename` does not exist.

**Correct approach:** Inspect the filter and actual data state; never blindly broaden the filter to `{}` just to force a document to change.

### Mistake G — Invalid Nested Path

**Symptom:** `$set: {"profile.city":"Hue"}` errors.

**Possible cause:** `profile` is currently a scalar rather than an object. MongoDB cannot treat a string as an embedded document to add child fields.

**Correct approach:** Identify schema-divergent records and migrate the type before updating child fields.

### Mistake H — Forgetting to Update Indexes and Validators After Rename

**Symptom:** Queries on the new field name are slow, or updates get rejected.

**Cause:** Indexes and validators still reference the old field name.

**Correct approach:** Treat field renames as schema changes and deploy corresponding indexes, validators, and consumer updates.

### Mistake I — `updateMany()` Stops Midway

**Symptom:** Some documents are modified while others retain the old field.

**Cause:** Individual documents update atomically, but the whole batch is not necessarily atomic.

**Correct approach:** Design idempotent migrations, filter by remaining unmigrated state, verify postconditions, batch appropriately, and monitor errors.

### Mistake J — Accepting Arbitrary Field Paths from Clients

**Symptom:** Authorization, status, or metadata fields get unexpectedly modified.

**Cause:** Server constructs the update document directly from untrusted input.

**Correct approach:** Whitelist modifiable fields, validate by role and schema, and never allow clients to supply arbitrary operators or sensitive paths.

---

## 15. Decision Table: Which Operator to Choose?

| Requirement | Choice | Example |
|---|---|---|
| Change an existing email | `$set` | `{"contact.email":"new@example.test"}` |
| Add a new field where missing | `$set` with matching filter | `marketingOptIn: false` for missing docs |
| Edit city while keeping street | `$set` with dot notation | `{"address.city":"Hue"}` |
| Intentionally replace entire address | `$set` on parent object | `{address:{...}}` |
| Remove phone number | `$unset` | `{"contact.phone":""}` |
| Explicitly mark phone absent while keeping field | `$set` to `null` | `{"contact.phone":null}` |
| Remove deprecated old field | `$unset` | `{legacyFlag:""}` |
| Rename top-level field | `$rename` | `{oldName:"newName"}` |
| Rename nested object field | `$rename` with path | `{"contact.telephone":"contact.phone"}` |
| Rename field inside array elements | Do not use `$rename` directly | Array migration using appropriate logic |
| Remove array elements matching condition | `$pull` | `{items:{sku:"B"}}` |
| Atomically increment counter | `$inc` | `{points:1}` |
| Add element to array | `$push` / `$addToSet` | `{tags:"vip"}` |
| Compute new value from existing field | Aggregation pipeline update | `$set` stage with expression |

This table guides operator selection; you still need proper filters, authorization, schema validation, and business checks before execution.

---

## 16. Practice Exercises

### Exercise 1 — Updating an Embedded Field

Using the lab data:

1. Change `contact.phone` of `CUS-101` to `"0912345678"` using `$set`.
2. Verify that `contact.email` remains intact.
3. Try `$set` on the entire `contact` object in a test database and observe the difference.
4. Explain why dot notation is necessary when changing only one child field.

### Exercise 2 — Distinguishing null and Missing

With `CUS-103`:

1. Query for `"contact.email": null`.
2. Query for `"contact.email": {$exists:true}`.
3. Run `$unset` to remove `contact.email`.
4. Re-run both queries and add `$type:"null"`.
5. Explain the difference between null equality queries, field existence, and BSON null values.

### Exercise 3 — Renaming Fields with Conflicts

Create in the lab collection:

~~~javascript
db.migration_cases.insertMany([
  { _id: 1, oldLabel: "A" },
  { _id: 2, newLabel: "B" },
  { _id: 3, oldLabel: "C", newLabel: "D" },
  { _id: 4, oldLabel: null }
]);
~~~

Do the following:

1. Count documents having `oldLabel`.
2. Count documents having both `oldLabel` and `newLabel`.
3. Write a filter selecting only documents with the source field and without the target field.
4. Run `$rename` with that filter.
5. Verify document `_id: 3` did not lose `newLabel: "D"`.
6. Discuss how to resolve the conflict on document 3.

### Exercise 4 — Removing a Field from an Array Element

Create:

~~~javascript
db.orders.insertOne({
  _id: "ORD-501",
  items: [
    { sku: "A", quantity: 1, oldNote: "x" },
    { sku: "B", quantity: 2, oldNote: "y" }
  ]
});
~~~

Requirements:

- Remove `oldNote` only on the item with `sku: "B"` while keeping the item.
- Compare with running `$unset` on the whole array element.
- Explain when to use `$pull`.

### Exercise 5 — Conditional Update

Transition `status` from `ACTIVE` to `SUSPENDED` only when the current status matches. Write an `updateOne` filtering by both `_id` and `status`. Run the command a second time and explain why `matchedCount` changes.

### Exercise 6 — Production Field-Name Migration

A collection with 2 million documents currently stores `phoneNumber`; some documents already have `contact.phone`. Multiple application instances are deployed and a report still reads `phoneNumber`.

Design:

1. Inventory of old/new/conflicting data.
2. Compatible application rollout strategy.
3. Required index and validator changes.
4. Backfill command targeting only non-conflicting documents.
5. Progress tracking and mid-batch error handling.
6. Conditions permitting removal of the old field.
7. Backup/rollback plan if incorrect values are discovered.

### Exercise 7 — Safe Java PATCH API

Suppose an API allows editing `contact.phone`, `profile.city`, and deleting `legacyNote`, while forbidding edits to `_id`, `tenantId`, or `status`.

Write pseudocode or Java code to:

- Accept only valid fields.
- Validate data types and user permissions.
- Build `Updates.combine(set(...), unset(...))` from whitelisted fields.
- Inspect `matchedCount` and `modifiedCount`.
- Never let a request supply an arbitrary MongoDB update document.

---

## 17. Review Questions

1. Why does `updateOne()` with `$set` differ from `replaceOne()`?
2. When does `$set` create a new field? When does dot notation error?
3. What is the difference between `$set: {"contact.phone": "..."}` and `$set: {contact: {phone: "..."}}`?
4. Why is `$set: {email:null}` not the same as `$unset: {email:""}`?
5. When does `{email:null}` match a document missing email?
6. What does `$unset` do if the field does not exist?
7. Why can `$unset` on an array element leave `null`?
8. Which operator is appropriate for removing an element completely from an array?
9. What does `$rename` do if the target field already exists?
10. Does `$rename` support renaming fields inside array elements?
11. Why must renaming a field accompany index and validator migrations?
12. How does `matchedCount` differ from `modifiedCount`?
13. Is an `updateMany()` command atomic across all matched documents?
14. Why must `upsert: true` be used intentionally?
15. What makes a rename migration safe to re-run?
16. What is the difference between the `$set` update operator and the `$set` aggregation stage?
17. Why must an application never accept raw MongoDB update operators directly from an untrusted API request?

## 18. Summary

MongoDB provides three essential operators for modifying document structure without replacing entire records:

- **`$set`** assigns or creates fields, supporting dot notation to edit exact parts of embedded documents.
- **`$unset`** removes fields from documents; it is not equivalent to setting `null` and is not a tool for removing array elements.
- **`$rename`** moves a value to a new field name, requiring checks for existing target fields, array limitations, and impacts on queries/indexes/validators.

In a learning environment, practice with `updateOne()` and inspect results to understand their effects. In production systems, add **safe filters, access control, schema validation, repeatable migrations, backups, and post-update verification**. Especially with `$rename`, renaming a field changes the data contract between the database and every application using it.

## Official MongoDB References

- [MongoDB Manual — $set Update Operator](https://www.mongodb.com/docs/manual/reference/operator/update/set/)
- [MongoDB Manual — $unset Update Operator](https://www.mongodb.com/docs/manual/reference/operator/update/unset/)
- [MongoDB Manual — $rename Update Operator](https://www.mongodb.com/docs/manual/reference/operator/update/rename/)
- [MongoDB Manual — db.collection.updateOne()](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateOne/)
- [MongoDB Manual — db.collection.updateMany()](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateMany/)
- [MongoDB Manual — Update Documents with Aggregation Pipeline](https://www.mongodb.com/docs/manual/tutorial/update-documents-with-aggregation-pipeline/)
- [MongoDB Manual — Query for Null or Missing Fields](https://www.mongodb.com/docs/manual/tutorial/query-for-null-fields/)
- [MongoDB Manual — Update Arrays](https://www.mongodb.com/docs/manual/tutorial/use-mql-to-update-an-array/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Java Sync Driver — Update Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/update-documents/)
- [Spring Data MongoDB — Updating Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html)
