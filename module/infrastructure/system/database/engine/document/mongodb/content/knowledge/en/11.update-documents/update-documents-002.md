# replaceOne, Document Replacement Limits, and the _id Field in MongoDB

## 1. Lesson Objectives

MongoDB lets you modify data using update operators such as `$set`, `$inc`, and `$unset`, or replace **an entire document** using `replaceOne()`. These two approaches have very different effects: updating individual fields preserves unmentioned fields, whereas replacing a document removes old fields that do not appear in the replacement data.

This is a lesson in the **Update Documents** chapter of **Database Engine Document MongoDB**, focusing on the `replaceOne()` method and the limits of replacement, especially the immutable identifier field `_id`.

After completing this lesson, you will be able to:

- Distinguish `replaceOne` from `updateOne`, `updateMany`, and `findOneAndReplace`.
- Write filters, replacement documents, and `upsert` options appropriately.
- Predict which fields are preserved and which fields are removed when replacing a document.
- Explain why `_id` cannot be changed during replacement; properly handle replacements with or without `_id`.
- Interpret `matchedCount`, `modifiedCount`, and `upsertedId` results.
- Avoid accidental overwrites when filters are too broad or a document is updated by multiple processes.
- Use `replaceOne` with nested data, arrays, schema validation, and Java Driver examples.

The write commands below use the **`replace_lab`** database dedicated to practice. Do not run them directly against production collections.

## 2. What Is replaceOne?

Syntax in `mongosh`:

~~~javascript
db.collection.replaceOne(
  filter,
  replacement,
  options
);
~~~

Where:

| Parameter | Meaning | Example |
|---|---|---|
| `filter` | Condition to find the document to replace | `{ _id: "sku-100" }` |
| `replacement` | New BSON document containing all fields to keep after replacement | `{ name: "Backpack", price: NumberDecimal("20.00") }` |
| `options` | Additional configuration; commonly `upsert` | `{ upsert: true }` |

By default, `replaceOne` targets **one document matching the filter**. If multiple documents match, you must not rely on natural order to guess which document will be replaced. Use a unique filter, typically `_id`, or an appropriate unique key.

Replacement operates at the **document** level. It does not update individual properties, merge nested objects, append two arrays, or automatically preserve fields missing from the replacement.

Example:

~~~javascript
// Document before replacement
{
  _id: "sku-100",
  name: "T-shirt",
  price: NumberDecimal("15.50"),
  stock: NumberInt(12),
  tags: ["new", "summer"],
  supplier: { code: "SUP-A", city: "Hanoi" }
}
~~~

Command:

~~~javascript
db.products.replaceOne(
  { _id: "sku-100" },
  {
    name: "Basic T-shirt",
    price: NumberDecimal("16.00")
  }
);
~~~

Document after replacement:

~~~javascript
{
  _id: "sku-100",
  name: "Basic T-shirt",
  price: NumberDecimal("16.00")
}
~~~

The `stock`, `tags`, and `supplier` fields **are gone** because they were not included in the replacement. Only `_id` is preserved even though the replacement did not declare it, because the `_id` of an existing document is an immutable identifier.

## 3. Preparing the Practice Dataset

Connect to MongoDB with `mongosh` and select the practice database:

~~~javascript
use replace_lab
~~~

Create sample data:

~~~javascript
const seedProducts = [
  {
    _id: "sku-100",
    name: "T-shirt",
    category: "fashion",
    price: NumberDecimal("15.50"),
    stock: NumberInt(12),
    tags: ["new", "summer"],
    supplier: {
      code: "SUP-A",
      city: "Hanoi"
    },
    createdAt: ISODate("2026-11-01T08:00:00Z"),
    version: NumberInt(1)
  },
  {
    _id: "sku-200",
    name: "Backpack",
    category: "accessories",
    price: NumberDecimal("32.00"),
    stock: NumberInt(5),
    tags: ["school"],
    supplier: {
      code: "SUP-B",
      city: "Da Nang"
    },
    createdAt: ISODate("2026-11-02T09:00:00Z"),
    version: NumberInt(1)
  },
  {
    _id: "sku-300",
    name: "Notebook",
    category: "stationery",
    price: NumberDecimal("4.50"),
    stock: NumberInt(40),
    tags: ["office"],
    supplier: {
      code: "SUP-C",
      city: "Hue"
    },
    createdAt: ISODate("2026-11-03T10:00:00Z"),
    version: NumberInt(1)
  }
];

seedProducts.forEach(product => {
  db.products.replaceOne(
    { _id: product._id },
    product,
    { upsert: true }
  );
});

db.products.find().sort({ _id: 1 });
~~~

If the collection starts empty, three products will be created. The seed snippet uses `replaceOne` with `upsert: true` so it can be re-run idempotently by `_id`, though it **resets the sample products** back to their initial state. Only re-run it when you want to reset the practice lab.

The dataset uses **string** `_id` values for readability. MongoDB also commonly uses `ObjectId` as the default `_id` type when the client does not supply an identifier. The data type of `_id` is part of the data contract: the string `"sku-100"` and `ObjectId("...")` are distinct types.

## 4. Replacing a Document by _id

### 4.1. Replacing with All Fields to Keep

Suppose you need to update `sku-100` while **preserving** metadata and unchanged fields. The explicit way is to provide the full replacement:

~~~javascript
const result = db.products.replaceOne(
  { _id: "sku-100" },
  {
    _id: "sku-100",
    name: "Basic T-shirt",
    category: "fashion",
    price: NumberDecimal("16.00"),
    stock: NumberInt(12),
    tags: ["new", "summer"],
    supplier: {
      code: "SUP-A",
      city: "Hanoi"
    },
    createdAt: ISODate("2026-11-01T08:00:00Z"),
    version: NumberInt(2)
  }
);

printjson(result);
db.products.findOne({ _id: "sku-100" });
~~~

The data is replaced as a whole document. There is no automatic mechanism to "keep unknown fields" added by another client unless you read them first and include them in the replacement.

If you only want to change the price, `updateOne` is usually simpler and safer:

~~~javascript
db.products.updateOne(
  { _id: "sku-100" },
  {
    $set: { price: NumberDecimal("16.00") }
  }
);
~~~

### 4.2. Replacing When the Replacement Omits _id

MongoDB allows a replacement **without specifying `_id`** when replacing an existing document. In that case, the existing `_id` is retained:

~~~javascript
db.products.replaceOne(
  { _id: "sku-200" },
  {
    name: "Waterproof Backpack",
    category: "accessories",
    price: NumberDecimal("39.00"),
    stock: NumberInt(8)
  }
);

db.products.findOne({ _id: "sku-200" });
~~~

The result retains `_id: "sku-200"`, while `tags`, `supplier`, `createdAt`, and `version` from the old document are removed because they are absent from the replacement.

**Do not misunderstand:** the server preserving `_id` does not mean it preserves all unmentioned fields. `_id` is an exception due to the immutability of the primary identifier key.

### 4.3. Replacing with _id Matching the Existing Identifier

A replacement can explicitly specify `_id`, provided it equals the identifier of the document being replaced:

~~~javascript
db.products.replaceOne(
  { _id: "sku-300" },
  {
    _id: "sku-300",
    name: "Hardcover Notebook",
    category: "stationery",
    price: NumberDecimal("5.00"),
    stock: NumberInt(25)
  }
);
~~~

Here `_id` does not change. Declaring `_id` in the replacement makes it clear to code readers that the identifier is preserved, though the application must still ensure a different identifier is never supplied.

## 5. Core Limitation: The _id Field Is Immutable

### 5.1. Cannot Change _id with replaceOne

MongoDB requires a document's `_id` to remain **unchanged** across update or replacement operations. The following example is designed to be **rejected**:

~~~javascript
db.products.replaceOne(
  { _id: "sku-100" },
  {
    _id: "sku-999", // Wrong: _id differs from existing document
    name: "Change product code",
    price: NumberDecimal("16.00")
  }
);
~~~

Because the filter selects the document with `_id: "sku-100"`, the replacement attempts to change the key to `"sku-999"`. The server typically returns an error like:

~~~text
Performing an update on the path '_id' would modify the immutable field '_id'
~~~

Error codes, wording, and response structure can vary by version and driver, but the rule stays the same: **you cannot modify the `_id` of an existing document**.

Similarly, you cannot modify `_id` using:

~~~javascript
// Also invalid
db.products.updateOne(
  { _id: "sku-100" },
  { $set: { _id: "sku-999" } }
);
~~~

Nor can you use `$unset` to remove `_id` from an existing document.

### 5.2. Same Display Representation with Different Type Is Not the Same _id

Consider a collection using BSON ObjectId:

~~~javascript
const oid = ObjectId("64a000000000000000000001");
~~~

The value `oid` (BSON ObjectId) **is different from** the string:

~~~javascript
"64a000000000000000000001"
~~~

A replacement attempting to switch from an ObjectId to a string with the same hex representation does not preserve identity. Both filters and replacements must maintain the **exact BSON `_id` value and type**.

If a Java/REST application receives an ID as a string and looks up a document whose `_id` is an ObjectId, it must parse and validate the type at the API layer rather than assuming MongoDB automatically coerces strings to ObjectId.

### 5.3. Changing a Business Code vs. Changing _id

If the system needs to change a product's display code, consider using a separate business field:

~~~javascript
{
  _id: ObjectId("64a000000000000000000001"),
  sku: "SKU-OLD",
  name: "T-shirt"
}
~~~

To change the SKU code:

~~~javascript
db.products.updateOne(
  { _id: ObjectId("64a000000000000000000001") },
  { $set: { sku: "SKU-NEW" } }
);
~~~

This example illustrates a document with an ObjectId `_id`; the `replace_lab.products` dataset in section 3 uses string `_id` values, so it will not match this query.

If `sku` must be unique, create an appropriate unique index and coordinate reference updates across related systems. For new designs, choose a stable `_id` and separate mutable business codes.

### 5.4. What If You Truly Must "Change _id"?

There is no single `replaceOne` operation to alter an existing `_id`. At the data level, doing so requires **creating a new document with the new `_id`**, updating related references, and handling the old document through a migration workflow. This is an identity change that can impact unique indexes, application links, events, caches, and external integrations.

Do not propose deleting the old document and re-inserting as if it were a routine field edit: there is risk of data loss if failure occurs between steps, broken references, or business rule violations. When identity migration is genuinely necessary, design a proper migration and consistency mechanism.

## 6. How replaceOne Differs from updateOne

Consider the existing document:

~~~javascript
{
  _id: "sku-100",
  name: "T-shirt",
  price: NumberDecimal("15.50"),
  stock: NumberInt(12),
  tags: ["new", "summer"],
  supplier: { code: "SUP-A", city: "Hanoi" }
}
~~~

### 6.1. updateOne with $set

~~~javascript
db.products.updateOne(
  { _id: "sku-100" },
  { $set: { price: NumberDecimal("16.00") } }
);
~~~

Result: only `price` changes; `name`, `stock`, `tags`, and `supplier` remain intact. You can also use `$inc` to increment/decrement counters without reading and rewriting the whole document:

~~~javascript
db.products.updateOne(
  { _id: "sku-100" },
  { $inc: { stock: NumberInt(1) } }
);
~~~

### 6.2. replaceOne with a Replacement Document

~~~javascript
db.products.replaceOne(
  { _id: "sku-100" },
  {
    name: "T-shirt",
    price: NumberDecimal("16.00")
  }
);
~~~

Result: `stock`, `tags`, and `supplier` are gone. The core difference lies in the **semantics of the payload**, not just the method name.

| Criterion | `updateOne` with update operators | `replaceOne` |
|---|---|---|
| Unit of change | Specified fields/paths | Entire document body (except immutable `_id`) |
| Unmentioned fields | Typically preserved | Removed |
| Nested objects | Can update paths like `"supplier.city"` | Must include the entire object to keep in the replacement |
| Arrays | Has `$push`, `$pull`, `$addToSet`, etc. | Replaces the entire array value if present |
| `_id` | Cannot be modified | Cannot be modified |
| Upsert | Supported | Supported |
| Use when | Partial edits, counters, array operations | Writing a complete document snapshot per contract |

### 6.3. Do Not Pass $set to replaceOne

The following syntax is invalid:

~~~javascript
// Wrong: replaceOne does not accept an update operator document
db.products.replaceOne(
  { _id: "sku-100" },
  { $set: { price: NumberDecimal("16.00") } }
);
~~~

The second argument of `replaceOne` is a **replacement document**, not an update document containing operators like `$set`. The server/driver will reject a replacement structured with update operators.

Use:

~~~javascript
// Correct when modifying only one field
db.products.updateOne(
  { _id: "sku-100" },
  { $set: { price: NumberDecimal("16.00") } }
);
~~~

Conversely, an operator-less update (legacy syntax) should not be used to replace documents in modern mongosh/drivers; `replaceOne` is the explicit API for that purpose.

## 7. Replace Does Not Merge Nested Data or Arrays

### 7.1. Nested Objects

Suppose initially:

~~~javascript
{
  _id: "sku-100",
  supplier: {
    code: "SUP-A",
    city: "Hanoi",
    contact: {
      phone: "0900000000",
      email: "supa@example.test"
    }
  }
}
~~~

If you call:

~~~javascript
db.products.replaceOne(
  { _id: "sku-100" },
  {
    supplier: {
      city: "Da Nang"
    }
  }
);
~~~

After replacement, the document contains only `_id` and `supplier.city`. The fields `supplier.code`, `supplier.contact`, and any other top-level fields vanish. `replaceOne` **does not merge recursively**.

To change only the city while keeping other fields:

~~~javascript
db.products.updateOne(
  { _id: "sku-100" },
  { $set: { "supplier.city": "Da Nang" } }
);
~~~

### 7.2. Arrays

For a document with:

~~~javascript
{
  _id: "sku-100",
  tags: ["new", "summer"],
  stock: 12
}
~~~

If the replacement only contains:

~~~javascript
{
  tags: ["featured"]
}
~~~

then after replacement, `tags` becomes `["featured"]` and the `stock` field is removed. There is no implicit concatenation onto the old array.

If the goal is to add a tag without duplicates:

~~~javascript
db.products.updateOne(
  { _id: "sku-100" },
  { $addToSet: { tags: "featured" } }
);
~~~

If the goal is to remove a tag:

~~~javascript
db.products.updateOne(
  { _id: "sku-100" },
  { $pull: { tags: "summer" } }
);
~~~

Depending on the case, replacing the entire array can be appropriate (when the user submits a complete new list), whereas incremental add/remove actions should use the corresponding update operators.

## 8. Return Result of replaceOne

`replaceOne` does not return the replaced document. It returns metadata about the write operation, typically containing:

~~~javascript
{
  acknowledged: true,
  matchedCount: 1,
  modifiedCount: 1,
  upsertedId: null,
  upsertedCount: 0
}
~~~

Fields and display format may vary by driver/version, but the core meanings are:

| Field | Meaning |
|---|---|
| `acknowledged` | Server confirms the operation was received/processed under the applied write concern |
| `matchedCount` | Number of documents matching the replacement filter; typically 0 or 1 |
| `modifiedCount` | Number of documents actually modified according to server results; typically 0 or 1 |
| `upsertedCount` | Number of new documents inserted by upsert, typically 0 or 1 |
| `upsertedId` | The `_id` of the newly inserted document when an upsert occurs |

When the write concern does not require acknowledgment, some result details are unavailable; examples in this lesson use acknowledged writes by default.

### 8.1. Document Matches and Content Changes

~~~javascript
db.products.replaceOne(
  { _id: "sku-300" },
  {
    name: "New Notebook",
    price: NumberDecimal("5.50")
  }
);
~~~

Typically `matchedCount: 1` and `modifiedCount: 1`.

### 8.2. No Document Matches, upsert Defaults to false

~~~javascript
db.products.replaceOne(
  { _id: "sku-does-not-exist" },
  {
    name: "Not inserted",
    price: NumberDecimal("10.00")
  }
);
~~~

The result is typically `matchedCount: 0`, `modifiedCount: 0`, `upsertedCount: 0`. Replacement does nothing if no document matches and upsert is not enabled.

### 8.3. Document Matches but Data Is Equivalent

If the replacement yields a document with identical content to the existing one, the server may return `matchedCount: 1`, `modifiedCount: 0`. Therefore:

- `matchedCount` answers "did any document match the filter?"
- `modifiedCount` answers "how many documents had their content modified?"

Do not always treat `modifiedCount: 0` as an error. Inspect `matchedCount`, `upsertedCount`, and the data state to interpret it accurately.

## 9. Upsert with replaceOne

### 9.1. How Does Upsert Work?

`upsert` stands for *update or insert*. With `replaceOne`:

- If the filter matches a document, replace that document.
- If the filter does not match and `upsert: true`, insert a new document constructed from the replacement and `_id` resolution rules.
- If no match and `upsert` is disabled, insert nothing.

Example:

~~~javascript
const result = db.products.replaceOne(
  { _id: "sku-400" },
  {
    _id: "sku-400",
    name: "Water Bottle",
    category: "accessories",
    price: NumberDecimal("12.90"),
    stock: NumberInt(15)
  },
  { upsert: true }
);

printjson(result);
db.products.findOne({ _id: "sku-400" });
~~~

If `sku-400` did not exist yet, the result typically shows `matchedCount: 0`, `upsertedCount: 1`, and `upsertedId: "sku-400"`. Running it again with the same filter finds `sku-400` already present and performs a replacement instead of creating a second document.

### 9.2. Replacement Missing _id During Upsert

When the replacement omits `_id` and an upsert needs to insert a new document, MongoDB must assign an `_id` to the new document. If the filter contains a direct equality condition on `_id`, the identifier can be derived from that condition:

~~~javascript
db.products.replaceOne(
  { _id: "sku-500" },
  {
    name: "Pencil Case",
    price: NumberDecimal("7.20")
  },
  { upsert: true }
);

db.products.findOne({ _id: "sku-500" });
~~~

A clearer, easier-to-verify, and unambiguous practice is to **put the desired `_id` in both the filter and the replacement** as shown in the `sku-400` example.

If an upsert inserts a document without an explicit `_id`, the server generates an identifier according to MongoDB rules. Do not assume arbitrary fields in the filter are automatically copied into the replacement. When using replacement, include all required business fields inside the replacement itself.

### 9.3. Imprecise Filter During Upsert

Suppose an application executes:

~~~javascript
db.products.replaceOne(
  { category: "fashion" },
  {
    name: "New Product",
    category: "fashion",
    price: NumberDecimal("10.00")
  },
  { upsert: true }
);
~~~

If any product with `category: "fashion"` already exists, the command can **replace an existing product** instead of inserting a new one. If none exists, it can insert one. An overly broad filter leads to two drastically different outcomes.

For an upsert meaning "save product by unique code", use `_id` or a unique business key, backed by an appropriate unique index.

### 9.4. Concurrent Upserts Across Multiple Processes

If two flows concurrently execute an upsert on a non-existent key, both may observe that no document exists yet. To prevent duplicate records, enforce a unique index on the appropriate business key, handle duplicate key errors, and design controlled retries.

`upsert: true` does not automatically turn arbitrary business filters into a unique key. By default, MongoDB maintains a unique index on `_id` in standard collections; for other keys, design appropriate indexes.

## 10. Constraints and Requirements on Replacement Documents

### 10.1. Replacement Must Be a Complete Valid Document

A replacement is not a set of operators like `$set`/`$inc`. It must be a valid BSON structure conforming to the application schema.

If a collection has a validator requiring `name`, `price`, and `stock`, a replacement missing `stock` may be rejected when `validationAction: "error"`. This is beneficial because it prevents replacement from accidentally dropping required fields, though a validator only enforces rules that are declared.

### 10.2. Document Size Limit

MongoDB imposes a maximum BSON document size limit of **16 MiB** for standard documents. An oversized replacement, such as one containing a massive array, will be rejected for exceeding this limit.

If a document grows unboundedly with history entries or array elements, consider modeling a child collection linked by key rather than forcing everything into a single document.

### 10.3. Other Immutable Field Rules in Special Configurations

Beyond `_id`, replacement behavior also depends on collection configuration, such as sharding and shard keys, time series collections, or collections with specific constraints/mechanisms. Exact rules regarding modifying shard keys, routing, and collection types depend on the MongoDB version and topology.

Therefore, do not overgeneralize that "`_id` is the only restriction". When operating on sharded collections or specialized collections, review the constraints applicable to your environment.

### 10.4. Validation and Access Privileges

An account needs appropriate write privileges for replacement operations; upserts may also require insert privileges when creating a new document. If the server rejects with `not authorized`, do not mistake it for a filter or `_id` error.

When a collection enforces JSON Schema validation, replacements must satisfy the validator. Depending on privileges and tools, administrative mechanisms may exist to bypass document validation, but these should not be used casually as a default way to "work around" schema errors.

### 10.5. Indexes and Uniqueness

Replacements are checked against relevant index constraints. Keeping `_id` unchanged does not guarantee the entire replacement is valid: for instance, changing an email field to an email already used elsewhere can violate a unique index on email.

Thus, duplicate key errors, document validation errors, and immutable `_id` errors are distinct error categories that should be handled separately at the application layer.

## 11. Filters and the Question of "Which Document Gets Replaced?"

### 11.1. Avoid Broad Filters When Targeting a Specific Record

~~~javascript
// May match multiple products in the same category
db.products.replaceOne(
  { category: "fashion" },
  { name: "Replacement record" }
);
~~~

Even though `replaceOne` replaces only **one** document, that does not mean the selected document is deterministic or aligns with business intent. On frequently changing data, broad filters are even more error-prone.

Use explicit identifying criteria:

~~~javascript
db.products.replaceOne(
  { _id: "sku-100" },
  {
    _id: "sku-100",
    name: "Basic T-shirt",
    category: "fashion",
    price: NumberDecimal("16.00"),
    stock: NumberInt(12)
  }
);
~~~

### 11.2. Filters Can Combine _id and Business Conditions

~~~javascript
db.products.replaceOne(
  {
    _id: "sku-100",
    category: "fashion"
  },
  {
    _id: "sku-100",
    name: "New T-shirt",
    category: "fashion",
    price: NumberDecimal("17.00"),
    stock: NumberInt(9)
  }
);
~~~

If `_id` matches but `category` on the server has changed, the command matches no document. A `matchedCount: 0` result can indicate the record was deleted, changed state, or the filter is no longer valid.

Filter fields are **not automatically preserved** after replacement: if the replacement omits `category`, that field disappears even though the filter used `category` to match.

### 11.3. Inspecting Scope Before Writing

~~~javascript
const filter = { _id: "sku-100" };

db.products.findOne(filter);
db.products.countDocuments(filter);
~~~

When filtering by unique `_id`, at most one document is selected. For more complex filters, use a unique index or well-defined business keys.

In environments with concurrent writers, pre-reading only aids observation; it does not "lock" the document between the read and the replacement.

## 12. Avoiding Lost Updates from Read-Then-Replace

### 12.1. What Is a Lost Update?

Suppose initially:

~~~javascript
{
  _id: "sku-100",
  name: "T-shirt",
  stock: 12,
  price: 15.50
}
~~~

Sequence of events:

~~~text
T0: Client A reads the document (stock = 12)
T1: Client B increments stock to 13 using $inc
T2: Client A runs replaceOne with stale snapshot (stock = 12)
T3: Result: stock reverts to 12, Client B's change is overwritten
~~~

A `replaceOne` command is **atomic at the single-document level**, but it does not guarantee that every field in the client's snapshot is still fresh. Atomicity does not prevent lost updates across two consecutive valid writes.

### 12.2. Update Only Necessary Fields with updateOne

If Client A only wants to change the name:

~~~javascript
db.products.updateOne(
  { _id: "sku-100" },
  { $set: { name: "Basic T-shirt" } }
);
~~~

This operation does not overwrite `stock` being updated by Client B. For counters, use `$inc` instead of reading the value and writing back a new number.

### 12.3. Optimistic Concurrency Using version

When full-document replacement is unavoidable, use **version** to detect stale snapshots. All write paths must consistently update the version.

The following example assumes the document has an integer `version` field:

~~~javascript
const current = db.products.findOne({ _id: "sku-100" });

if (current) {
  const next = {
    ...current,
    name: "New Basic T-shirt version",
    version: NumberInt(Number(current.version) + 1)
  };

  const result = db.products.replaceOne(
    {
      _id: current._id,
      version: current.version
    },
    next
  );

  if (result.matchedCount === 0) {
    print("Document has changed or no longer exists. Reload required.");
  } else {
    print("Replacement succeeded.");
  }
}
~~~

If another client updated `version` from 1 to 2 before the replacement ran, the filter with `version: 1` no longer matches, and the client receives `matchedCount: 0` instead of silently overwriting.

Condition for this mechanism to work: **every relevant write path must increment the version**. If one flow modifies `stock` without incrementing `version`, a stale snapshot can still overwrite that flow's change.

### 12.4. Do Not Automatically Retry on Version Mismatch

A replacement rejected due to a version conflict must not be blindly retried with the same snapshot. Reload the latest data, reconcile user intent, and decide whether to merge or retry according to business rules.

## 13. replaceOne and Schema Validation

A JSON Schema validator helps mitigate the risk of accidentally dropping required fields during document replacement.

Example creating a separate collection:

~~~javascript
use replace_lab

if (db.getCollectionInfos({ name: "validatedProducts" }).length === 0) {
  db.createCollection("validatedProducts", {
    validator: {
      $jsonSchema: {
        bsonType: "object",
        required: ["name", "price", "stock"],
        properties: {
          _id: { bsonType: ["string", "objectId"] },
          name: { bsonType: "string", minLength: 1 },
          price: {
            bsonType: "decimal",
            minimum: NumberDecimal("0")
          },
          stock: {
            bsonType: "int",
            minimum: 0
          }
        }
      }
    },
    validationLevel: "strict",
    validationAction: "error"
  });
}
~~~

Insert a valid document:

~~~javascript
db.validatedProducts.replaceOne(
  { _id: "valid-001" },
  {
    _id: "valid-001",
    name: "Ballpoint Pen",
    price: NumberDecimal("1.50"),
    stock: NumberInt(20)
  },
  { upsert: true }
);
~~~

Attempt a replacement missing `stock`:

~~~javascript
// Expected to be rejected due to missing required field
db.validatedProducts.replaceOne(
  { _id: "valid-001" },
  {
    name: "Blue Ballpoint Pen",
    price: NumberDecimal("1.80")
  }
);
~~~

With `validationAction: "error"` active, the server rejects the invalid replacement. The old document is not replaced with a version missing `stock`.

Schema validation can also constrain fields, BSON types, arrays, and nested objects. However, it only checks rules that are explicitly defined. If the schema does not require `tags`, a replacement that drops `tags` can still pass schema validation.

### 13.1. Why Decimal128 Matters Here

When a replacement originates from an API JSON payload, `price` might arrive as a Double, whereas the validator expects BSON `decimal`. When writing via `mongosh`, use:

~~~javascript
NumberDecimal("19.90")
~~~

In Java, you can use `BigDecimal` and `Decimal128`. Do not assume representing `19.90` as a JSON number automatically converts it to Decimal128.

## 14. replaceOne in MongoDB Compass

MongoDB Compass primarily provides a UI to **view and edit documents**. Depending on the version, Edit Document may allow editing the full JSON/Tree and saving, but the exact underlying write command issued by the UI should not be assumed to always be `replaceOne`.

To learn the exact semantics of `replaceOne`, run the examples in `mongosh` and observe the changes in Compass:

1. Connect Compass to the same server used in `mongosh` and open `replace_lab.products`.
2. Filter with `{"_id":"sku-100"}`; observe the `name`, `price`, `stock`, `tags`, and `supplier` fields.
3. Run the `replaceOne` command from section 4.2 or an intentional replacement on a sample document.
4. Return to Compass, click Refresh/Find to verify that fields omitted from the replacement have disappeared.
5. Run the command attempting to change `_id` from section 5.1 in mongosh. Observe the error, then Refresh Compass to confirm the original identifier remains intact.
6. Try upserting `sku-400` in section 9; Refresh the document list to verify the newly inserted record.
7. If Compass displays BSON types, verify that `price` appears as Decimal128 when using `NumberDecimal`.

When entering a filter expression in Compass, use valid JSON:

~~~json
{"_id":"sku-100"}
~~~

If editing a document directly in Compass, distinguish between **editing a field**, **deleting a field**, and **replacing the entire document** according to your Compass version's UI. Always verify the final effect against server data.

## 15. Using replaceOne with the MongoDB Java Driver

The Java Driver provides `replaceOne(filter, replacement)` and options via `ReplaceOptions`. Example using `Document`:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import com.mongodb.client.model.ReplaceOptions;
import org.bson.Document;
import org.bson.types.Decimal128;

import java.math.BigDecimal;

MongoCollection<Document> products = database.getCollection("products");

Document replacement = new Document("_id", "sku-100")
    .append("name", "Basic T-shirt")
    .append("category", "fashion")
    .append("price", new Decimal128(new BigDecimal("16.00")))
    .append("stock", 12);

UpdateResult result = products.replaceOne(
    new Document("_id", "sku-100"),
    replacement,
    new ReplaceOptions().upsert(false)
);

System.out.println("Matched: " + result.getMatchedCount());
System.out.println("Modified: " + result.getModifiedCount());
~~~

This snippet assumes the `database` variable is a connected `MongoDatabase` with write privileges; it illustrates the API rather than a complete standalone Java program.

The `replacement` parameter can be a POJO managed by a codec/ODM instead of `Document`. When using POJOs, watch out for mappers that omit `null`/unloaded fields or define `_id` inconsistently, as replacement can drop fields not represented in the Java object.

Upsert example using the driver:

~~~java
UpdateResult result = products.replaceOne(
    new Document("_id", "sku-600"),
    new Document("_id", "sku-600")
        .append("name", "Document Organizer Box")
        .append("price", new Decimal128(new BigDecimal("9.90")))
        .append("stock", 3),
    new ReplaceOptions().upsert(true)
);

if (result.getUpsertedId() != null) {
    System.out.println("Created: " + result.getUpsertedId());
}
~~~

The application should handle non-matching documents, version conflicts, validation errors, unique key duplicates, and network/timeout errors separately. For business fields that change independently, `updateOne` with update operators usually reduces overwrite risk.

## 16. When Should You Use findOneAndReplace?

`replaceOne` returns **write metadata**, not the before/after document. If the application needs the document returned, MongoDB provides the `findOneAndReplace` API with options to return either the pre- or post-replacement document.

Example in `mongosh`:

~~~javascript
const updated = db.products.findOneAndReplace(
  { _id: "sku-300" },
  {
    _id: "sku-300",
    name: "Leather-cover Notebook",
    price: NumberDecimal("6.50"),
    stock: NumberInt(10)
  },
  {
    returnDocument: "after"
  }
);

printjson(updated);
~~~

If both old and new data are needed for auditing, design an appropriate audit/event workflow rather than assuming every API returns both. `findOneAndReplace` does not alter the immutable `_id` rule or whole-document replacement behavior.

| Method | Purpose | Typical Result |
|---|---|---|
| `updateOne` | Update one document using valid operators/pipeline | Write operation metadata |
| `replaceOne` | Replace the content of one document | Write operation metadata |
| `findOneAndReplace` | Replace one document and return the document per options | Before or after document, or null if no match |
| `updateMany` | Update multiple documents | Matched/modified counts |
| `insertOne` | Insert one new document | Inserted document ID |

There is no `replaceMany` equivalent to replace multiple documents with one replacement document. When performing bulk data migrations, define targets, choose an update/`bulkWrite` strategy, and control impact separately.

## 17. Common Pitfalls

| Scenario | Cause | Resolution |
|---|---|---|
| Different `_id` in replacement | Attempted to change immutable key | Keep exact existing `_id` or omit `_id` in a matched replacement |
| `_id` string matches hex but fails to match ObjectId | BSON type mismatch | Parse and preserve exact identifier BSON type |
| Document loses many fields after replace | Replacement omits those fields | Supply full snapshot or use `updateOne` |
| Nested fields lost after replace | Replacement does not merge objects | Use `$set` with dot notation to edit one branch |
| Entire array replaced | Replacement overwrites whole array value | Use `$push`/`$pull`/`$addToSet` for partial edits |
| Passing `{$set:{...}}` to `replaceOne` | Invalid replacement format | Use `updateOne` or a valid replacement document |
| `matchedCount = 0` | Filter did not match or document changed | Check ID, BSON type, version, and data state |
| `modifiedCount = 0` despite matched = 1 | Replacement may equal existing document | Inspect both result and actual document |
| Unintended document inserted | `upsert: true` enabled and filter did not match | Control filter, unique key, and upsert option |
| Wrong product replaced | Filter too broad, matching multiple records | Use identifier or unique key |
| Duplicate key error | Concurrent upsert or replacement violates unique index | Verify unique keys, handle errors, and retry conditionally |
| Schema validation error | Replacement missing fields or wrong BSON type | Provide all valid fields; do not casually bypass validator |
| Record loses concurrent changes | Client replaced using stale snapshot | Use update operators or optimistic version |
| Document too large error | BSON exceeds size limit | Redesign data/arrays or split into separate collections |

## 18. Practice Exercises

Run these sequentially in the `replace_lab` database. To ensure independent results, you can reload `seedProducts` from section 3 whenever you want to reset the sample dataset.

### Exercise 1. Observing Full-Document Replacement

Before replacement:

~~~javascript
db.products.findOne({ _id: "sku-100" });
~~~

Replace:

~~~javascript
db.products.replaceOne(
  { _id: "sku-100" },
  {
    name: "Minimalist T-shirt",
    price: NumberDecimal("18.00")
  }
);
~~~

Read back:

~~~javascript
db.products.findOne({ _id: "sku-100" });
~~~

**Explain:** Why does `_id` remain, while `stock`, `tags`, `supplier`, and `createdAt` are lost?

### Exercise 2. Invalid _id Modification

~~~javascript
db.products.replaceOne(
  { _id: "sku-100" },
  {
    _id: "sku-100-new",
    name: "Attempt ID change"
  }
);
~~~

**Expected:** An error due to immutable `_id`. Inspect `sku-100` before and after to confirm the identifier did not change.

### Exercise 3. Matched and Modified

Run a replacement with the same data twice:

~~~javascript
const p = {
  _id: "sku-300",
  name: "Notebook",
  price: NumberDecimal("5.50"),
  stock: NumberInt(25)
};

printjson(db.products.replaceOne({ _id: "sku-300" }, p));
printjson(db.products.replaceOne({ _id: "sku-300" }, p));
~~~

**Observe:** The first run can report `modifiedCount: 1` (if content changed), while the second reports `modifiedCount: 0` when the replacement matches the current state; `matchedCount` remains 1.

### Exercise 4. No Match and Upsert

~~~javascript
db.products.replaceOne(
  { _id: "sku-700" },
  {
    _id: "sku-700",
    name: "Document Folder",
    price: NumberDecimal("3.00")
  }
);
~~~

When `sku-700` does not exist yet, the command inserts nothing. Continue:

~~~javascript
db.products.replaceOne(
  { _id: "sku-700" },
  {
    _id: "sku-700",
    name: "Document Folder",
    price: NumberDecimal("3.00")
  },
  { upsert: true }
);
~~~

**Expected:** The second run produces `upsertedCount: 1` if the record did not exist. Running it again performs a replacement.

### Exercise 5. Comparing replaceOne and updateOne

Reload the sample data and try:

~~~javascript
db.products.updateOne(
  { _id: "sku-200" },
  { $set: { "supplier.city": "Ho Chi Minh City" } }
);
~~~

Read back `supplier.code`. Then reload the sample data and try:

~~~javascript
db.products.replaceOne(
  { _id: "sku-200" },
  {
    supplier: { city: "Ho Chi Minh City" }
  }
);
~~~

**Explain:** Why do only `_id` and `supplier.city` remain in the second run?

### Exercise 6. Optimistic Concurrency

Reload the sample data, read `sku-100` into `current`, then simulate another process updating the version:

~~~javascript
const current = db.products.findOne({ _id: "sku-100" });

db.products.updateOne(
  { _id: "sku-100" },
  { $inc: { version: NumberInt(1) } }
);

const result = db.products.replaceOne(
  { _id: "sku-100", version: current.version },
  {
    ...current,
    name: "Stale snapshot",
    version: NumberInt(Number(current.version) + 1)
  }
);

printjson(result);
~~~

**Expected:** `matchedCount: 0` because the server version changed. Do not blindly retry; re-read before deciding to replace.

### Exercise 7. Validator Blocking Replacement Missing Fields

Create `validatedProducts` as in section 13, insert `valid-001`, then try a replacement without `stock`.

**Expected:** Under strict/error validation, the command is rejected. Compare this error with the immutable `_id` error and duplicate key error to distinguish the mechanisms.

### Exercise 8. Choosing the Right Method for the Requirement

| Requirement | Appropriate Choice |
|---|---|
| Modify only the selling price | `updateOne` + `$set` |
| Increment inventory upon receiving stock | `updateOne` + `$inc` |
| Add a tag to an array without duplicates | `updateOne` + `$addToSet` |
| Persist a fully controlled product snapshot | `replaceOne` |
| Save a snapshot by ID, creating if absent | `replaceOne` + `upsert: true` |
| Retrieve the new document immediately after replacement | `findOneAndReplace` with return-after |
| Change the `_id` of an existing document | Not supported via `replaceOne` |
| Replace a document while avoiding stale snapshot overwrites | `replaceOne` with a version filter and version-increment protocol |

## 19. Practical Rules When Using replaceOne

Before sending a replacement, verify **which document is selected**, **whether the payload contains every field that must be kept**, and **whether `_id` matches the exact BSON identifier of the current document**. Also confirm that the operation truly requires replacing the whole document rather than updating individual fields.

When enabling upsert, carefully check the filter and unique keys. When a system has multiple concurrent writers, prefer field-level update operators; if replacing a snapshot is mandatory, use conflict detection mechanisms such as a version field. Combine schema validation to block replacements missing required data, while monitoring `matchedCount`, `modifiedCount`, and `upsertedId`.

`replaceOne()` is a useful tool when the business intent is genuinely to **redefine the entire content of a document**. Understanding its whole-document scope and the immutability of `_id` lets you use it without losing fields or accidentally altering data identity.
