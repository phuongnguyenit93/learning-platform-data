# Unique Indexes: Duplicate Data, Null, and Missing Fields

In MongoDB, a **unique index** does more than accelerate data lookup: it enforces a **uniqueness constraint** on the indexed key values. As a result, the database can prevent two accounts from using the same username, prevent two records from sharing an order number, or ensure a SKU appears only once within a store scope. However, when a field can be **`null`**, **missing**, an **array**, or part of a **compound index**, the behavior often differs from assumptions carried over from SQL.

This lesson belongs to the **Specialized Indexes** chapter of the *MongoDB Document Database Engine* module, focusing on three core questions: **how duplicate values are handled, how `null` differs from missing, and how to design the right index for your business rules**. It also covers **unique sparse indexes**, **unique partial indexes**, **compound unique indexes**, **collation**, **multikey**, **sharding**, and rolling out unique indexes on collections with existing data.

After this lesson, you will be able to:

1. Create and explain the outcomes of single-field and compound unique indexes.
2. Recognize **`E11000 duplicate key`** errors across inserts, updates, replacements, and upserts.
3. Explain accurately why a **standard unique index allows only one `null`/missing key** on a single field.
4. Choose between **sparse** and **partialFilterExpression** to allow multiple documents missing a field while still rejecting duplicate values.
5. Design uniqueness scoped by **tenant**, **status**, **case-insensitivity**, or multiple fields.
6. Understand the limitations of unique multikey indexes and unique indexes on sharded collections.
7. Audit duplicate data before building an index, deploy safely, and handle race conditions properly in the application.

> **Version and environment:** Examples primarily use APIs established in MongoDB 7.0/8.0 and compatible newer releases. Some index management capabilities or sharded collection constraints depend on server version/FCV; in production, consult the **MongoDB Database Manual for your running server version**. All demos below use a dedicated database `unique_index_lab`; never run drop, index creation, or data-modification commands on a production collection without verifying ownership and impact.

## 1. What Is a Unique Index?

A regular index helps MongoDB locate documents by key value. Adding the **`unique: true`** option causes the database to **reject two distinct documents that produce the same index key value**, according to the semantics of the index type and options such as collation and partial filter.

~~~javascript
db.getSiblingDB("unique_index_lab").users.createIndex(
  { username: 1 },
  { unique: true }
)
~~~

In this example:

- `{ username: 1 }` is the index key specification; `1` denotes ascending order.
- `{ unique: true }` is the index option that enforces uniqueness.
- If a new document has a username matching an existing document within the same index scope, the write fails.
- MongoDB checks the constraint **at write time**, not merely when running queries.
- Uniqueness is evaluated based on **BSON key values** and index options; it does not necessarily match arbitrary application-level string comparisons.

### 1.1. How Does It Differ from a Regular Index?

| Characteristic | Regular Index | Unique Index |
|---|---|---|
| Supports filtering/lookup | Yes | Yes |
| Two distinct documents with the same indexed key | Allowed | Prohibited within the index scope |
| Prevents inserting duplicate business keys | No | Yes |
| Prevents updating a key to an existing value | No | Yes |
| Blocks duplicates when building index on existing data | No | Yes; index build fails if existing data violates it |
| Allows multiple missing fields in a standard single-field index | Yes | No, unless configured appropriately with sparse/partial |

**A unique index does not create a foreign key**, does not verify whether a value exists in another collection, and does not replace schema validation for enforcing required fields or types.

### 1.2. Distinguishing `_id` and Business Keys

MongoDB automatically creates a **unique index on `_id`** for standard collections. `_id` is the document identifier, whereas business logic may require additional uniqueness:

~~~javascript
// Two documents with different _id values but duplicate username.
{ _id: "U-1", username: "an" }
{ _id: "U-2", username: "an" }
~~~

If the collection only has the default index on `_id`, those two documents do not violate `_id` uniqueness. Enforcing unique usernames requires a separate index on `username`.

Conversely, putting `unique: true` on `username` does not make `username` **required**, does not force it to be a string, and does not normalize letter case or whitespace. Those rules must be handled with **schema validation**, application logic, and/or an appropriate **collation**.

## 2. Dataset and How to Run Examples

To avoid mixing data, each experiment uses a differently named collection in `unique_index_lab`. Example A creates `usersBasic`, Example B creates `usersSparse`, Example C creates `usersPartial`, and so on. Each example is designed to run the first time on a **non-existent** or **empty** collection.

~~~javascript
const lab = db.getSiblingDB("unique_index_lab")
~~~

If you re-run an experiment on the same collection, you may hit duplicate `_id` or unique index errors because data from the previous run remains. You can pick a new lab collection name or intentionally reset **only the demo collection** once you are certain it does not hold anyone else's data. Do not run `db.dropDatabase()` in a shared environment just for practice.

To inspect indexes:

~~~javascript
lab.usersBasic.getIndexes()
~~~

To observe results and error types, use `try/catch`:

~~~javascript
try {
  // Write command under test goes here.
} catch (err) {
  print("code=" + err.code)
  print("codeName=" + err.codeName)
  print(err.message)
}
~~~

Error messages, colliding key details, and exception shapes can vary by MongoDB version and driver. In many duplicate-key scenarios, the error code is **11000** and the error name is **`DuplicateKey`**.

## 3. Single-Field Unique Index and Duplicate Data

### 3.1. Creating the Index Before Inserting

~~~javascript
const lab = db.getSiblingDB("unique_index_lab")

lab.usersBasic.createIndex(
  { username: 1 },
  { unique: true, name: "ux_username" }
)

lab.usersBasic.insertOne({
  _id: "U1",
  username: "an",
  displayName: "An"
})

lab.usersBasic.insertOne({
  _id: "U2",
  username: "binh",
  displayName: "Binh"
})
~~~

Both inserts succeed because `"an"` and `"binh"` are distinct.

### 3.2. Inserting Data with the Same Key

~~~javascript
try {
  lab.usersBasic.insertOne({
    _id: "U3",
    username: "an",
    displayName: "Another An"
  })
} catch (err) {
  print(err.code)      // Typically 11000.
  print(err.codeName)  // Typically DuplicateKey.
  print(err.message)
}
~~~

`U3` has a different `_id` from U1, yet the unique index on `username` rejects it because both share the key `username = "an"`. This is distinct from a duplicate `_id`: the error code may still be 11000, but the index name and colliding key differ.

### 3.3. Updates Can Also Violate Uniqueness

~~~javascript
try {
  lab.usersBasic.updateOne(
    { _id: "U2" },
    { $set: { username: "an" } }
  )
} catch (err) {
  print(err.message)
}
~~~

MongoDB refuses to let U2 change its username to a value already owned by U1. When the write fails, it does not leave behind two documents with duplicate usernames.

Similar behavior can occur with:

- `replaceOne` whose replacement carries an existing key;
- `updateMany` causing multiple documents to change to the same value;
- `upsert` creating a new document with a colliding key due to a race condition;
- `bulkWrite` containing multiple operations competing for a unique key;
- import, restore, or migration tasks inserting data that fails uniqueness.

It is not only `insertOne` that can raise a unique constraint error.

### 3.4. Why Should You Not Rely Solely on "Find First, Insert Later"?

A common anti-pattern looks like this:

~~~javascript
const existing = lab.usersBasic.findOne({ username: "lan" })

if (!existing) {
  lab.usersBasic.insertOne({
    _id: "U4",
    username: "lan"
  })
}
~~~

This code has a **race condition**:

~~~text
Client A: find("lan") -> not found
Client B: find("lan") -> not found
Client A: insert("lan") -> succeeds
Client B: insert("lan") -> duplicate key, rejected
~~~

**The unique index is the database-level guarantee of uniqueness.** Checking before inserting only improves UX (e.g., "username is already taken"); it does not replace handling `E11000` on the write path.

The application should classify error 11000 based on the **colliding index/key**, return an appropriate business error, and never retry infinitely with the same duplicate data.

## 4. The Most Important Subtlety: `null` vs. Missing Fields

MongoDB distinguishes:

~~~javascript
// Field is present with value BSON null.
{ _id: "A", email: null }

// Field is completely absent.
{ _id: "B" }

// Field is present with type string.
{ _id: "C", email: "an@example.test" }
~~~

At the document level:

- `email: null`: the field **exists** with BSON value **null**.
- Missing: the `email` field **is absent from the document**.
- `email: ""`: the field exists with an **empty string**, which is also not null.
- `email: "null"`: a four-character string; not BSON null.

However, when MongoDB builds a **standard single-field unique index** on `email`, both a document with `email: null` and a document **missing `email`** receive an **index entry with a null key value**. Therefore, at most **one document** in this group can exist within the index scope.

### 4.1. Experiment: One Null, One Missing

~~~javascript
const lab = db.getSiblingDB("unique_index_lab")

lab.usersNull.createIndex(
  { email: 1 },
  { unique: true, name: "ux_email" }
)

lab.usersNull.insertOne({ _id: "N1", email: null })

try {
  lab.usersNull.insertOne({ _id: "N2" })
} catch (err) {
  print(err.code)    // Typically 11000.
  print(err.message) // Duplicate null key.
}
~~~

`N2` lacks `email`, yet it is rejected because `N1` already occupies the unique index key `null`. Reversing the order produces the same outcome:

~~~javascript
// Create another lab collection.
lab.usersMissingFirst.createIndex(
  { email: 1 },
  { unique: true }
)

lab.usersMissingFirst.insertOne({ _id: "M1" })

try {
  lab.usersMissingFirst.insertOne({ _id: "M2", email: null })
} catch (err) {
  print(err.message)
}
~~~

The document missing the field already created the null unique key; the subsequent insert with explicit `null` collides with it.

### 4.2. Prediction Table for a Single-Field Unique Index

Assume an initially empty collection with a unique index `{email:1}`, neither sparse nor partial:

| Operation in Order | Index Key Value | Outcome |
|---|---|---|
| Insert `{_id:1,email:"a@example.test"}` | `"a@example.test"` | Succeeds. |
| Insert `{_id:2,email:"b@example.test"}` | `"b@example.test"` | Succeeds. |
| Insert `{_id:3,email:"a@example.test"}` | `"a@example.test"` | **Duplicate key**. |
| Insert `{_id:4,email:null}` | `null` | Succeeds, if no null/missing exists yet. |
| Insert `{_id:5}` | `null` | **Duplicate key** because `_id:4` already holds the null key. |
| Insert `{_id:6,email:""}` | `""` | Succeeds, if no empty string exists yet. |
| Insert `{_id:7,email:""}` | `""` | **Duplicate key** due to duplicate empty string. |

**Key conclusion:** a single-field unique index **does not mean** "unlimited documents may omit email as long as provided emails are unique." That is a **different** requirement and needs a different index, typically **partial** or **sparse**.

### 4.3. `null` in Queries Does Not Equal Uniqueness Semantics

In the MongoDB query language, a normal equality filter `{email: null}` matches documents where `email: null` **or** where `email` is missing:

~~~javascript
lab.usersNull.find({ email: null })
~~~

To distinguish the two states in data:

~~~javascript
// Email is completely absent:
lab.usersNull.find({ email: { $exists: false } })

// Email is present and has BSON type null:
lab.usersNull.find({ email: { $type: "null" } })

// Email is present and not null:
lab.usersNull.find({
  email: { $exists: true, $ne: null }
})
~~~

Queries that distinguish missing from null help with **data analysis**, but they do not alter how a standard unique index generates keys. Filter code that appears to distinguish missing from null does not make the database distinguish them when **generating index keys**.

## 5. Unique Indexes When Existing Data Already Has Duplicates

Creating a unique index on a collection that already has two documents with the same key will fail:

~~~javascript
const lab = db.getSiblingDB("unique_index_lab")

lab.usersDirty.insertMany([
  { _id: "D1", username: "mai" },
  { _id: "D2", username: "mai" },
  { _id: "D3", username: "hung" }
])

try {
  lab.usersDirty.createIndex(
    { username: 1 },
    { unique: true }
  )
} catch (err) {
  print("Index build failed: " + err.message)
}
~~~

MongoDB **does not automatically delete or merge** duplicate documents to finish the index build. You must resolve violating data first, or adjust the business key/index definition to match business requirements.

### 5.1. Finding Duplicate Values with Aggregation

~~~javascript
lab.usersDirty.aggregate([
  {
    $group: {
      _id: "$username",
      count: { $sum: 1 },
      ids: { $push: "$_id" }
    }
  },
  { $match: { count: { $gt: 1 } } },
  { $sort: { count: -1 } }
])
// One group _id = "mai", count = 2, ids = ["D1", "D2"].
~~~

For large collections, `$push`-ing **every ID** into an array can exceed memory or result document size limits; separate the **duplicate-group counting** step from **ID sampling** or batch processing. The example below counts without accumulating all IDs:

~~~javascript
lab.usersDirty.aggregate([
  { $group: { _id: "$username", count: { $sum: 1 } } },
  { $match: { count: { $gt: 1 } } },
  { $sort: { count: -1 } },
  { $limit: 20 }
])
~~~

**You must also search for null/missing groups.** An aggregation `$group` on `"$email"` can group documents with null values and missing fields together into the corresponding group, so a data report should clearly separate **explicit null** and **missing** to decide policy.

### 5.2. When Is It Safe to Delete Duplicates?

There is no universal "keep the newest document" rule across all domains. For users/accounts or orders, two documents sharing a business key may hold different transactions, audit trails, or references. You need to:

1. Identify the **source of truth** and define what constitutes a "true duplicate".
2. Check references from other collections and related business logic.
3. Choose merge/rename/archive/reassign key/delete based on policy.
4. Record ID mappings if references need updating.
5. Block or coordinate writers still producing duplicate values while cleaning data.
6. Create the unique index only once the data satisfies the invariant.

If a job deletes documents by `username` without targeting specific IDs, it could delete the valid record too. "Cleaning duplicates before building an index" is usually a **controlled data migration**, not an unconditional `deleteMany`.

## 6. Unique Sparse Index: Allowing Multiple Documents **Missing the Field**

A **sparse index** only indexes documents that contain the indexed field appropriately; for a single-field index, a document **completely missing the field** gets no index entry. Therefore, a **unique sparse index** allows **multiple documents missing the field**, while **explicit `null` is still indexed** when the field is present.

~~~javascript
const lab = db.getSiblingDB("unique_index_lab")

lab.usersSparse.createIndex(
  { email: 1 },
  {
    unique: true,
    sparse: true,
    name: "ux_email_sparse"
  }
)
~~~

### 6.1. Testing Missing, Null, and String Inserts

~~~javascript
// Two documents without email: allowed.
lab.usersSparse.insertOne({ _id: "S1", name: "An" })
lab.usersSparse.insertOne({ _id: "S2", name: "Binh" })

// First explicit null email: allowed.
lab.usersSparse.insertOne({ _id: "S3", email: null })

// Second explicit null email: duplicate null index key.
try {
  lab.usersSparse.insertOne({ _id: "S4", email: null })
} catch (err) {
  print(err.code)      // Typically 11000.
  print(err.message)
}

// Two distinct emails: allowed.
lab.usersSparse.insertOne({
  _id: "S5",
  email: "an@example.test"
})
lab.usersSparse.insertOne({
  _id: "S6",
  email: "binh@example.test"
})

// Duplicate email matching S5: rejected.
try {
  lab.usersSparse.insertOne({
    _id: "S7",
    email: "an@example.test"
  })
} catch (err) {
  print(err.message)
}
~~~

Summary of outcomes:

| `email` Form | Unique **Non-Sparse** | Unique **Sparse** |
|---|---|---|
| Missing `email` | Generates null key; at most one document in null/missing group. | **Excluded from index**; multiple missing-field documents allowed. |
| `email: null` | Generates null key; at most one in null/missing group. | **Included in index**; at most one explicit null. |
| `email: "a@example.test"` | At most one key with this value. | At most one key with this value. |
| `email: ""` | At most one empty string. | At most one empty string. |

**Key takeaway:** `sparse: true` does not mean "ignore null". It skips documents **missing the field** in the single-field case, whereas documents containing `null` are still constrained.

### 6.2. When Is Sparse Appropriate?

Sparse can be appropriate when:

- The field is **genuinely absent** on most documents where registration is incomplete.
- Business rules allow multiple documents missing the field, but permit **at most one document with explicit null**.
- The schema and writers explicitly dictate that "no value yet" must **omit the field**, not write `null`.

If the system uses both missing and explicit null to represent "no email yet", a unique sparse index can still cause unexpected errors. In that case, a **unique partial index** is usually more flexible and expresses business rules more accurately.

### 6.3. Sparse Indexes and Query Behavior

Because a sparse index **does not contain every document**, MongoDB cannot always use it for a query where using the index would omit unindexed documents from the result. The query planner considers the query predicates; `hint` can be used in special cases, but you must understand its impact on results.

For example, counting all documents in a collection by scanning only a sparse index can **miss documents lacking `email`**. Do not treat a sparse index as a complete inventory of every `_id`.

## 7. Unique Partial Index: Specifying Exactly Which Documents Are Constrained

A **partial index** includes only documents matching a **`partialFilterExpression`**. Combining it with `unique: true` enforces uniqueness **solely within the indexed subset of documents**. This is a powerful tool for expressing rules such as "email must be unique when it is actually a string" or "username is unique only among ACTIVE accounts".

### 7.1. Constraining Only String Emails, Ignoring Missing/Null

~~~javascript
const lab = db.getSiblingDB("unique_index_lab")

lab.usersPartial.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: {
      email: { $type: "string" }
    },
    name: "ux_email_when_string"
  }
)
~~~

With this design:

- Documents **missing `email`** do not satisfy the partial filter ⇒ excluded from the index.
- Documents with `email: null` do not satisfy `$type: "string"` ⇒ excluded from the index.
- Documents with a string email, including `""`, match the filter ⇒ must be unique.
- Documents where email is a non-string type, such as a number, are **also excluded from the index** — schema validation is needed if numeric emails are invalid data.

~~~javascript
lab.usersPartial.insertMany([
  { _id: "P1", name: "An" },
  { _id: "P2", name: "Binh" },
  { _id: "P3", email: null },
  { _id: "P4", email: null },
  { _id: "P5", email: "an@example.test" },
  { _id: "P6", email: "binh@example.test" }
])

try {
  lab.usersPartial.insertOne({
    _id: "P7",
    email: "an@example.test"
  })
} catch (err) {
  print(err.code) // 11000.
}
~~~

Documents P1–P6 satisfy the index constraint despite having two missing and two explicit nulls. P7 is rejected because `"an@example.test"` already exists in the **indexed subset**.

> **Distinguishing index from schema:** A partial unique index states that **if email is a string, that string must be unique**. It does **not** state that email must be a string. Add schema validation if you want to reject emails that are numbers, objects, arrays, or empty strings.

### 7.2. Why Is `$exists: true` Not Enough to Skip Null?

Consider another partial filter:

~~~javascript
lab.usersExists.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: {
      email: { $exists: true }
    }
  }
)
~~~

It only excludes **documents missing `email`**. With `email: null`, the field still **exists**, so the document enters the index and explicit nulls still must be unique:

~~~javascript
lab.usersExists.insertOne({ _id: "E1" })
lab.usersExists.insertOne({ _id: "E2" }) // Allowed: both missing email.

lab.usersExists.insertOne({ _id: "E3", email: null })

try {
  lab.usersExists.insertOne({ _id: "E4", email: null })
} catch (err) {
  print(err.code) // 11000 because both E3/E4 have email present and null.
}
~~~

Therefore, when the requirement is **"ignore both missing and null"**, explicitly specify the valid type/value, such as `$type: "string"` paired with schema validation. Do not simply swap `sparse` for `partialFilterExpression: { email: { $exists: true } }` and expect null behavior to change.

### 7.3. Comparing Non-Sparse, Sparse, and Partial

| Index | Multiple Missing Documents | Multiple `null` Documents | Duplicate Strings |
|---|---|---|---|
| `{email:1}, unique:true` | **No** | **No** | **No** |
| `{email:1}, unique:true, sparse:true` | **Yes** | **No** | **No** |
| Unique + partial `{email:{$exists:true}}` | **Yes** | **No** | **No** |
| Unique + partial `{email:{$type:"string"}}` | **Yes** | **Yes** | **No** |

This table applies when **email is a single scalar field** with no differing collation options. With **arrays/multikey** or compound indexes, index key generation semantics are more intricate; see the sections below.

### 7.4. Partial Uniqueness by Business Status

Suppose soft-deleted accounts are allowed to keep a username that collides with an active account, while among ACTIVE accounts, usernames must be unique.

~~~javascript
lab.accountsActive.createIndex(
  { username: 1 },
  {
    unique: true,
    partialFilterExpression: {
      status: "ACTIVE"
    },
    name: "ux_username_active"
  }
)
~~~

Test:

~~~javascript
lab.accountsActive.insertMany([
  { _id: "A1", username: "lan", status: "DELETED" },
  { _id: "A2", username: "lan", status: "DELETED" },
  { _id: "A3", username: "lan", status: "ACTIVE" }
])

try {
  lab.accountsActive.insertOne({
    _id: "A4",
    username: "lan",
    status: "ACTIVE"
  })
} catch (err) {
  print(err.code) // 11000: duplicate username within ACTIVE group.
}
~~~

If A1 is updated from `DELETED` to `ACTIVE` while its username remains `"lan"`, the operation will be **blocked** because the document enters the partial unique index and collides with A3's key.

**Design implication:** A partial index is not checked only at insert time. **Updates that move a document into or out of the partial filter set** add or remove index keys and can trigger duplicate-key errors accordingly.

### 7.5. Partial Indexes and the Query Planner

For a query to use a partial index, its predicates must guarantee that the query result **does not need any documents outside the indexed set**. For example, with the partial index on `status: "ACTIVE"`:

~~~javascript
// Query with the matching filter condition:
lab.accountsActive.find({
  status: "ACTIVE",
  username: "lan"
})
~~~

This is a valid candidate to use the partial index. Conversely:

~~~javascript
// This query wants both ACTIVE and DELETED:
lab.accountsActive.find({ username: "lan" })
~~~

The server cannot safely return complete results using an index that contains only **ACTIVE**. Thus, a partial index is not merely a constraint technique; it also shapes index design for read access patterns. Use `explain()` on representative data instead of assuming every query on `username` will use the partial index.

### 7.6. `partialFilterExpression` Syntax and Limitations

MongoDB supports only a **specific subset of expressions** in `partialFilterExpression`; not every aggregation expression or query operator is allowed. Common supported forms include equality, `$exists: true`, range comparisons, `$type`, `$and`, `$or`, and `$in` in supported versions.

Do not arbitrarily place `$expr` or complex regex checks inside a partial filter without consulting the documentation. Additionally, you cannot use **`sparse: true` and `partialFilterExpression` simultaneously on the same index**. If you need conditions more expressive than sparse, use a partial index and define the logic once.

## 8. Compound Unique Indexes: Uniqueness on a **Tuple of Values**, Not Individual Fields

A **compound unique index** spans two or more indexed fields:

~~~javascript
lab.ordersPerTenant.createIndex(
  { tenantId: 1, orderNo: 1 },
  {
    unique: true,
    name: "ux_tenant_orderNo"
  }
)
~~~

MongoDB requires the **combination (`tenantId`, `orderNo`)** to be unique. That does **not** mean each `tenantId` can have only one order or that `orderNo` must be globally unique across the entire system.

~~~javascript
lab.ordersPerTenant.insertMany([
  { _id: "T1-O1", tenantId: "T1", orderNo: "001" },
  { _id: "T1-O2", tenantId: "T1", orderNo: "002" },
  { _id: "T2-O1", tenantId: "T2", orderNo: "001" }
])

try {
  lab.ordersPerTenant.insertOne({
    _id: "T1-O1-DUP",
    tenantId: "T1",
    orderNo: "001"
  })
} catch (err) {
  print(err.code) // 11000: duplicate pair T1 / 001.
}
~~~

Two tenants can have the same order number `"001"` because **`tenantId` differs**. Conversely, within T1 there cannot be two documents with `orderNo = "001"`.

### 8.1. Null/Missing in a Compound Unique Index

For a compound index, a missing or null field produces a **null component** in the index key tuple. The constraint checks the **entire tuple**, not merely how many documents lack one field.

For example:

~~~javascript
lab.compoundNull.createIndex(
  { tenantId: 1, email: 1 },
  { unique: true }
)

lab.compoundNull.insertOne({
  _id: "C1",
  tenantId: "T1"
})
// Corresponding index key: ("T1", null)

lab.compoundNull.insertOne({
  _id: "C2",
  tenantId: "T2"
})
// Corresponding index key: ("T2", null), distinct from C1.

try {
  lab.compoundNull.insertOne({
    _id: "C3",
    tenantId: "T1",
    email: null
  })
} catch (err) {
  print(err.code) // Collides on tuple ("T1", null).
}
~~~

Therefore:

- **Multiple documents across the collection can lack `email`** if **other fields in the tuple differ**.
- **Two documents cannot produce the same tuple**, such as having the same `tenantId = "T1"` and missing/null email.
- If all fields in the index are missing/null, at most one document can hold the all-null tuple.

### 8.2. Example Table for Compound Nulls

Assume a unique index `{tenantId:1,email:1}` that is neither sparse nor partial:

| Document | Key Tuple | Valid After Preceding Steps? |
|---|---|---|
| `{tenantId:"A",email:"x@test"}` | `("A","x@test")` | Yes. |
| `{tenantId:"B",email:"x@test"}` | `("B","x@test")` | Yes; different tenant. |
| `{tenantId:"A",email:"x@test"}` again | `("A","x@test")` | No; duplicate tuple. |
| `{tenantId:"A"}` | `("A",null)` | Yes if the tuple has not appeared yet. |
| `{tenantId:"B"}` | `("B",null)` | Yes; different tuple. |
| `{tenantId:"A",email:null}` | `("A",null)` | No; collides with tenant A's missing-email document. |
| `{tenantId:"C",email:null}` | `("C",null)` | Yes; different tuple. |

**This is a major difference from single-field unique indexes:** a single-field unique index on `email` allows **one null key across the entire collection**; a compound unique index allows multiple tuples containing null as long as the other components make each tuple distinct.

### 8.3. Pitfall: Compound **Sparse** Does Not Skip Missing Emails When `tenantId` Is Present

Someone wanting "email is unique within each tenant, yet optional" might try:

~~~javascript
lab.badSparseComposite.createIndex(
  { tenantId: 1, email: 1 },
  { unique: true, sparse: true }
)
~~~

This is **not** the right default solution. With a compound sparse index consisting of regular ascending/descending fields, a document can be indexed if **at least one indexed field is present**. If `tenantId` is always present, documents **missing `email`** can still be indexed with the tuple `(tenantId, null)`, causing a duplicate key on the second missing-email document within the same tenant.

When you want to enforce uniqueness only if email is actually a string, use a **compound unique partial index**:

~~~javascript
lab.accountsTenant.createIndex(
  { tenantId: 1, email: 1 },
  {
    unique: true,
    partialFilterExpression: {
      email: { $type: "string" }
    },
    name: "ux_tenant_email_when_string"
  }
)
~~~

If the application guarantees `tenantId` is required and properly typed (via schema validation), this index enforces: "**Within the same tenant, each string email belongs to at most one account**; multiple accounts without an email are allowed." If `tenantId` is missing, documents with a string email are still indexed with a null component; hence you must enforce `tenantId` via schema validation, not assume the index makes it required.

### 8.4. Field Order in a Compound Index

Both `{tenantId:1,email:1}` and `{email:1,tenantId:1}` enforce uniqueness on the pair of values, but **different field orders** affect **prefix-based query optimization**.

For instance, if you frequently query:

~~~javascript
lab.accountsTenant.find({
  tenantId: "T1",
  email: "an@example.test"
})
~~~

An index with `tenantId` first is well suited for querying by tenant and then email. If requests also frequently list all accounts for a tenant, the `tenantId` prefix is helpful. Choosing field order should be based on **access patterns**, selectivity, and index workload—not uniqueness alone.

## 9. Case-Insensitive Uniqueness with Collation

An application may treat `"An"`, `"an"`, and `"AN"` as the same username. However, if you create a unique index with the default **simple/binary collation**, those strings can produce **distinct keys** and all be stored.

### 9.1. Unique Index with Locale Rules

MongoDB supports **collation** for locale-aware string comparison and comparison strength levels. For example:

~~~javascript
const lab = db.getSiblingDB("unique_index_lab")

lab.usersCaseInsensitive.createIndex(
  { username: 1 },
  {
    unique: true,
    collation: {
      locale: "en",
      strength: 2
    },
    name: "ux_username_case_insensitive"
  }
)

lab.usersCaseInsensitive.insertOne({
  _id: "CI1",
  username: "An"
})

try {
  lab.usersCaseInsensitive.insertOne({
    _id: "CI2",
    username: "an"
  })
} catch (err) {
  print(err.code) // 11000: case-insensitive duplicate.
}
~~~

With `strength: 2`, collation is typically **case-insensitive**, while **still distinguishing diacritics/accent variants** according to locale rules. `strength: 1` reduces sensitivity even further; do not arbitrarily pick level 1 if display names or business codes need to preserve diacritical distinctions.

**Locale matters.** Character comparison differences between Vietnamese, English, and other languages must be designed and tested against product policy. MongoDB does not automatically know which variants an "application username" should consider equivalent.

### 9.2. Index Collation vs. Query Collation

When a query wants to leverage an index whose collation differs from the collection default, the query generally must specify the matching collation:

~~~javascript
lab.usersCaseInsensitive.find({
  username: "AN"
}).collation({
  locale: "en",
  strength: 2
})
~~~

Creating a unique index alone does not make all `find()` calls case-insensitive if the query uses a different collation. **The index determines uniqueness using its own collation; queries use their own collation when comparing and selecting indexes.** Choose a consistent strategy across writes, reads, and account-existence checks.

### 9.3. Normalized Values and Collation Solve Two Related Problems

Another approach is storing a `usernameCanonical` field **normalized** at the application layer according to a clearly defined rule, then placing a unique index on that field:

~~~javascript
{
  _id: "U-100",
  usernameDisplay: "An",
  usernameCanonical: "an"
}
~~~

~~~javascript
lab.usersCanonical.createIndex(
  { usernameCanonical: 1 },
  { unique: true }
)
~~~

This approach requires:

- Fixed normalization rules (trimming, case-folding, Unicode normalization if required by business logic).
- Applying **the same rules** across all writers/importers.
- Backfilling existing data and checking for collisions before creating the index.
- Protecting `usernameCanonical` with validation/controlled writes so it is never missing or out of sync.

**Do not** assume `toLowerCase()` alone resolves all multilingual Unicode differences. Collation likewise must be chosen based on locale and business requirements, rather than treated as a one-size-fits-all recipe for emails or usernames.

### 9.4. Are Emails Truly Case-Insensitive?

From a business perspective, many systems want to treat emails as case-insensitive identifiers, though email standards and provider rules have nuances. Do not blindly merge addresses using "tricks" like stripping all dots in the local-part or dropping everything after `+` across all domains. If the product wants to define a canonical email identifier, establish **explicit documented rules** and a migration policy for when two existing accounts normalize to the same key.

## 10. Unique Multikey Indexes: Arrays Are Not Like Scalar Fields

An index on a field containing an array becomes a **multikey index**. A unique multikey index has easily misunderstood semantics: MongoDB enforces uniqueness **across different documents**, and does not necessarily forbid a single document from containing **repeated elements** within its own array.

### 10.1. Unique Index on `tags` Example

~~~javascript
const lab = db.getSiblingDB("unique_index_lab")

lab.uniqueTags.createIndex(
  { tags: 1 },
  { unique: true }
)

lab.uniqueTags.insertOne({
  _id: "T1",
  tags: ["red", "blue", "red"]
})
~~~

Within **a single document T1**, `"red"` appears twice in the array, yet the unique multikey index **does not automatically reject it** solely for repeating inside the same document. Duplicate index entries originating from the same document are handled according to index semantics.

~~~javascript
try {
  lab.uniqueTags.insertOne({
    _id: "T2",
    tags: ["green", "red"]
  })
} catch (err) {
  print(err.code) // 11000 because "red" already appeared in T1.
}
~~~

T2 cannot use `"red"` because a **different document** already claims that index key. If you want "tags within the same document cannot repeat", a unique index alone **does not guarantee that invariant**; enforce it through an appropriate model/validator and update patterns, or use `$addToSet` when the business concept is truly a set of values (noting that pre-existing duplicate array elements are not automatically fixed).

### 10.2. Do Not Confuse a Unique Index with a One-Item-per-SKU-per-Order Rule

Suppose an order contains:

~~~javascript
{
  _id: "O-1",
  items: [
    { sku: "BK-01", qty: 1 },
    { sku: "BK-01", qty: 2 }
  ]
}
~~~

A unique index on `"items.sku"`:

~~~javascript
lab.ordersUniqueItems.createIndex(
  { "items.sku": 1 },
  { unique: true }
)
~~~

**Does not guarantee** a SKU appears only once **within the same order**. On the contrary, that index would inadvertently block SKU `BK-01` in **any other order**, because uniqueness applies across documents in the collection.

If you need to guarantee that no two line items share a SKU within one order:

- Use application logic or validators to ensure array consistency according to the defined schema.
- Use conditional updates appropriately, and consider `$addToSet` only when element-level equality matches your definition of "duplicate".
- If line items need independent management, model them as **an `orderLines` collection** with a unique compound index `{orderId:1,sku:1}`; uniqueness then applies across **line documents** and aligns with the business rule.

### 10.3. Compound Multikey and Parallel Arrays

MongoDB restricts compound multikey indexes when multiple indexed fields reside in **independent arrays** (parallel arrays). For example, if a document has both `colors: ["red","blue"]` and `sizes: ["S","M"]`, a compound index spanning both arrays can be invalid.

For a single array of embedded documents, paths such as `"items.sku"` and `"items.qty"` follow different indexing mechanics; you still need to check specific multikey constraints. Do not use a unique multikey index as a substitute for complex business constraints based solely on array shape.

## 11. On Sharded Collections, Unique Indexes Have Specific Constraints

In a **sharded collection**, MongoDB distributes data across multiple shards. Enforcing cross-shard uniqueness is straightforward only when the system can locate a unique key within the required routing scope.

According to MongoDB's sharding guidelines, for standard sharded collections:

- **Unique indexes** on a sharded collection must include the **shard key as a prefix** of the index key, subject to documented exceptions.
- A **hashed index** cannot normally be specified as **unique**.
- The `_id` index is unique, but if `_id` **is not the shard key**, on a sharded collection it may only be enforced **per shard**, not automatically guaranteeing global `_id` uniqueness across shards. The application must manage collision-free IDs or design an appropriate shard key.
- Changing shard keys, resharding, or creating unique indexes on already-sharded data must follow the rules and restrictions of your server version.

### 11.1. Multi-Tenant Example with a Shard Key

Suppose a collection is sharded by `tenantId` and requires usernames to be unique **within each tenant**:

~~~javascript
// Index concept (deploy only when aligned with the actual shard key):
db.getSiblingDB("unique_index_lab").tenantUsers.createIndex(
  { tenantId: 1, username: 1 },
  { unique: true }
)
~~~

The shard key `tenantId` is a **prefix** of the compound unique index, and the constraint expresses the requirement accurately: usernames may repeat across two different tenants, but not within the same tenant.

Conversely, a unique index solely on `{username:1}` without the `tenantId` shard key prefix may **not be supported** on that sharded collection. If the problem requires globally unique usernames while sharding by tenant, you need to reconsider your identity architecture or data distribution strategy rather than assuming any arbitrary global unique index can be created.

### 11.2. Questions to Ask Before Deploying

1. Is the collection already sharded? What is the current shard key, and does it have hashed components?
2. Is uniqueness required **system-wide** or **within each tenant/organization**?
3. Can the shard key serve as an index prefix while still supporting query patterns?
4. Are there duplicates across shards or during an ongoing migration?
5. Are there additional restrictions on unique + partial/sparse/collation in the running server version?

If uniqueness requirements are incompatible with the shard key, resolve them during **data modeling**, rather than discovering the restriction when building the index in production.

## 12. Unique Indexes Do Not Replace Schema Validation

An index:

~~~javascript
lab.usersPartial.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: {
      email: { $type: "string" }
    }
  }
)
~~~

only restricts **duplicate string emails**. It can still allow:

~~~javascript
{ _id: "X1", email: 123 }
{ _id: "X2", email: 123 }
{ _id: "X3", email: null }
{ _id: "X4" }
~~~

because those values **do not match** the `$type: "string"` filter. If they are invalid for your business rules, you must enforce a **validator**.

For example, email may be **absent**, but if present it must be a non-empty string (disallowing null/numbers):

~~~javascript
lab.createCollection("usersValidated", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      properties: {
        email: {
          bsonType: "string",
          minLength: 1
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
})

lab.usersValidated.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: {
      email: { $type: "string" }
    }
  }
)
~~~

Now:

- Documents missing `email` **are allowed** (`email` is not in `required`).
- Documents with `email: null` or `email: 123` are rejected by **schema validation**.
- Documents with an empty-string email are rejected by `minLength:1`.
- Documents with a valid, non-empty string email that **duplicates an existing string email** are rejected by the **unique index**.

The two layers have different responsibilities: **schema validation** decides whether a document is **structurally and type-valid**, while the **unique index** decides whether a key value is **already used by another document**. They complement each other.

### 12.1. When Is `required` Needed?

If email must be **mandatory for every user**, change the validator to:

~~~javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: ["email"],
    properties: {
      email: { bsonType: "string", minLength: 1 }
    }
  }
}
~~~

However, that change can render older documents missing `email` invalid. You must roll it out compatibly, backfill existing data, and enable strict enforcement only after writers and data comply. Creating a unique index successfully **does not prove** that all historical documents have an email.

### 12.2. Unique Only Within the ACTIVE Group

If you use a partial unique index on `status:"ACTIVE"`, documents missing `status` or having another status will **not be indexed**. Schema validation can require `status` to be an exact enum value, preventing omissions from typos like `"ACTVE"` or wrong types. Thus, a complete domain solution typically includes:

~~~text
Validator: every user has a status belonging to the recognized enum.
Index: username is unique when status = ACTIVE.
Application: handles conflicts when reactivating an account.
Migration: cleans up existing data before enabling constraints.
~~~

You cannot deploy a partial unique index alone and assume documents outside its filter are automatically business-valid.

## 13. Deploying a Unique Index on a Running Collection

Creating a unique index on a fresh, empty collection is straightforward. On a production collection with millions of documents, there may already be **duplicates**, **nulls**, **missing fields**, **wrong types**, or **writers actively inserting duplicates**. Building an index without a plan can both fail and immediately cause application flows to start returning errors once the index succeeds.

A reliable rollout methodology is **define → inventory → migrate → prevent → build → verify → observe**.

### 13.1. Step 1 — Define the Exact Unique Key

First, answer:

- Which key must be unique: `username`, `emailCanonical`, `sku`, or the tuple `(tenantId, orderNo)`?
- Does uniqueness apply across the **entire collection** or only when `status = "ACTIVE"`?
- Is a missing field valid? Is explicit null valid?
- Is an empty string considered "not entered"?
- How are case sensitivity, diacritics, and Unicode normalization handled?
- Are there multiple tenants? Does uniqueness need to be global if the collection is sharded?
- Is the field an array? Can duplicate elements appear inside one document?

Write down an explicit "key contract":

~~~text
Business key: emailCanonical
Scope: users whose emailCanonical is a string
Uniqueness: collection-wide
Missing: multiple allowed
Null: multiple allowed (though product validator may forbid explicit null)
Empty string: forbidden via schema validation
Normalization: per product canonicalization rules
Index: {emailCanonical:1}, unique + partial type string
Scaling: not yet sharded; redesign required if shard key is incompatible
~~~

With that contract, you can write the index:

~~~javascript
db.getSiblingDB("unique_index_lab").usersPolicy.createIndex(
  { emailCanonical: 1 },
  {
    unique: true,
    partialFilterExpression: {
      emailCanonical: { $type: "string" }
    },
    name: "ux_emailCanonical_string"
  }
)
~~~

This is a **policy specification**, not a guarantee that every document complies: rejecting numeric/array/empty-string emails requires validation alongside application rules.

### 13.2. Step 2 — Inventory Duplicates, Nulls, Missing Fields, and Types

Before building the index, classify existing data:

~~~javascript
const lab = db.getSiblingDB("unique_index_lab")
const collection = lab.usersDirty

const missingUsername = collection.countDocuments({
  username: { $exists: false }
})

const nullUsername = collection.countDocuments({
  username: { $type: "null" }
})

const stringUsername = collection.countDocuments({
  username: { $type: "string" }
})

printjson({
  missingUsername,
  nullUsername,
  stringUsername
})
~~~

Note: when a field can be an **array**, the query `$type` operator can match **an element inside the array** of the specified type, rather than necessarily proving the **entire field** has BSON type string. If the schema permits non-standard data, inspect whole-field types or use schema validation `bsonType` alongside appropriate auditing. Do not assume `$type:"string"` in a query forbids arrays.

To find duplicate string usernames using their exact existing values:

~~~javascript
collection.aggregate([
  { $match: { username: { $type: "string" } } },
  {
    $group: {
      _id: "$username",
      count: { $sum: 1 }
    }
  },
  { $match: { count: { $gt: 1 } } },
  { $sort: { count: -1 } },
  { $limit: 50 }
])
~~~

If the business key uses a case-insensitive collation or a canonical field, detect **collisions under the new rules**, not merely by grouping raw strings. `"AN"` and `"an"` are distinct under binary grouping but collide in a case-insensitive unique index.

### 13.3. Step 3 — Clean Up Data with Clear Provenance

When two accounts share an email:

1. Determine whether the two records belong to the same person or two different accounts that collided on data.
2. Inspect links to orders, invoices, activities, and permissions.
3. If merging, unify on a canonical ID, update references according to a plan, and preserve an audit trail.
4. If renaming/canonicalizing, notify producers and avoid introducing new collisions.
5. For missing/null values, decide between "allow missing" or "require backfill"; **never populate a shared placeholder email** if you plan to add a unique index, as the shared placeholder itself will cause duplicates.
6. Run migrations in batches with checkpoints, filter conditions, and rollback/reconciliation.

Do not delete documents merely so `createIndex` succeeds before establishing a data-retention policy.

### 13.4. Step 4 — Control Writers Before Building

While cleaning data, legacy applications may continue producing duplicates. Coordinate these safeguards:

- Deploy writer code conforming to the new policy and handling `E11000`.
- Consider a maintenance window or throttling relevant producers during the cutover.
- Audit import jobs, batch pipelines, data syncs, and admin tools.
- If using a canonical field, ensure all producers compute it using the exact same rule.
- Update schema validation if needed to forbid invalid data types, following a rollout compatible with legacy data.

Verifying "zero duplicates at time T" **does not stop** an old writer from inserting a duplicate immediately afterward. Building the index is the database enforcement boundary, and the build itself must be coordinated with live traffic and concurrent data changes per MongoDB guidance.

### 13.5. Step 5 — Create, Verify, and Monitor the Index

~~~javascript
const lab = db.getSiblingDB("unique_index_lab")

lab.usersPolicy.createIndex(
  { emailCanonical: 1 },
  {
    unique: true,
    partialFilterExpression: {
      emailCanonical: { $type: "string" }
    },
    name: "ux_emailCanonical_string"
  }
)

printjson(lab.usersPolicy.getIndexes())
~~~

During a production index build, monitor **build duration, CPU/memory/I/O resources, replication lag, duplicate-key errors, and index build commit behavior**. If the build fails due to duplicates, do not assume the index exists and is enforcing. Check the actual index list before continuing the rollout.

After it succeeds:

- Inspect `getIndexes()` to verify the **key pattern**, `unique`, `partialFilterExpression`, `collation`, `sparse`, and index name.
- Run appropriate write tests in a **test environment** to verify semantics.
- Monitor duplicate-key errors broken down by service/version/job.
- Ensure proper API responses (e.g., returning a business conflict status rather than a generic 500 error).
- If multi-tenant or sharded, confirm the uniqueness scope matches the design.

### 13.6. Does Hiding an Index Disable Uniqueness?

**No.** A hidden index is hidden from the query planner to evaluate query impact before dropping an index, yet **the unique constraint of a hidden unique index continues to be enforced**. Do not use `hideIndex()` as a temporary way to relax uniqueness.

To actually remove a unique constraint, change the index policy through a supported procedure, usually involving **dropping/recreating** the appropriate index or a conversion mechanism supported by your MongoDB version. This is a risky data/product change; do not impulsively drop a production index upon encountering a single duplicate-key error.

### 13.7. Rollback When an Index Triggers Business Errors

Rollback has two sides:

- **Code rollback:** older application code may keep trying to insert duplicate data and fail while the unique index remains in place.
- **Index rollback:** dropping the unique index allows new duplicates to be created, potentially breaking invariants assumed by newer code.

Therefore, a sound rollback plan must specify **which state remains data-safe**, rather than just saying "run `dropIndex` on error". If the business policy was wrong, you may need to revise the rule/partial filter or execute a second migration plan rather than simply turning off enforcement.

## 14. Handling `E11000` Properly in the Application

Because MongoDB enforces unique constraints on the server, the application must assume **any write modifying an indexed key can be rejected**.

### 14.1. A User Creation API

A typical flow:

~~~text
POST /users
  |
  +-- validate input and normalize fields per policy
  +-- insert user (with unique index)
          |
          +-- OK -> return new user
          +-- E11000 -> identify colliding index/key,
                         return business error "username already exists"
          +-- other error -> handle per separate error category
~~~

You can pre-check to reduce error frequency:

~~~javascript
lab.usersBasic.findOne({ username: "an" })
~~~

However, **never** rely on a pre-check as final proof due to race conditions. An insert can still return a duplicate key between two concurrent requests.

### 14.2. Never Retry Duplicate-Key Errors Infinitely

An `insertOne` failing with E11000 for username `"an"` will not magically succeed if the exact same payload is resent repeatedly. One business exception exists: a retried request carrying **the same idempotency key** where the document was already created by the initial attempt, allowing the server/app to confirm it is **the same completed operation**. Still, "same username" alone is not enough to conclude two requests are identical; verify against `requestId`/business identity.

### 14.3. Upserts Can Compete on Unique Keys

~~~javascript
lab.usersBasic.updateOne(
  { username: "newuser" },
  {
    $setOnInsert: {
      createdAt: new Date(),
      displayName: "New User"
    }
  },
  { upsert: true }
)
~~~

If two clients concurrently upsert the same non-existent username, a unique index prevents creating two duplicate documents. However, one client can still receive a duplicate-key error due to timing and filter/update structure, rather than both calls merging silently.

To handle this:

- Ensure the unique index protects the true key.
- Filter by the exact identity and design modifiers that do not conflict with the indexed key.
- When E11000 occurs, re-read state and determine whether to retry as a **conditional update**.
- Never retry unboundedly; never treat E11000 as a success if the actual state is incorrect.

### 14.4. MongoDB Java Sync Driver Example

In the Java Sync Driver, you can call `createIndex` with `IndexOptions` and catch the error code:

~~~java
import com.mongodb.MongoWriteException;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.IndexOptions;
import org.bson.Document;

import static com.mongodb.client.model.Indexes.ascending;

// Assume database is a MongoDatabase connected to the lab environment.
MongoCollection<Document> users = database.getCollection("users");

users.createIndex(
    ascending("username"),
    new IndexOptions().unique(true)
);

try {
    users.insertOne(
        new Document("_id", "U-JAVA-1")
            .append("username", "an")
    );
} catch (MongoWriteException ex) {
    if (ex.getError().getCode() == 11000) {
        // Return an appropriate business error; avoid logging sensitive data.
        System.err.println("Duplicate unique key");
    } else {
        throw ex;
    }
}
~~~

This is a **single-command** example. When `bulkWrite()` or an index build fails, the exception may be a different class (such as `MongoBulkWriteException` for bulk writes or `MongoCommandException` for commands). Do not catch one exception class and assume every write or index operation throws that same class. Verify exact API names and error structures against your project's Java driver version.

### 14.5. Unique Keys and Upserts in Multi-Tenant Java

A multi-tenant collection typically needs:

~~~java
users.createIndex(
    new Document("tenantId", 1).append("username", 1),
    new IndexOptions().unique(true)
);
~~~

When creating a user, the filter/identity must include **`tenantId`**. If the application omits `tenantId` in a pre-check query or upsert, it could read/modify another tenant's account or draw wrong conclusions about uniqueness. **The index protects the tuple constraint**, while tenant isolation in queries is the responsibility of authorization and application design.

## 15. Quick Decision Table

| Business Requirement | Index Choice | Things to Watch Out For |
|---|---|---|
| Username always present, unique across collection | `{username:1}` unique | Schema validation enforces string/non-empty username; handle case normalization. |
| Email optional; **only missing field** may repeat, at most one null | Unique **sparse** on email | Explicit null is still indexed. |
| Email optional; **missing and null** may repeat, strings must be unique | Unique **partial** `email:{$type:"string"}` | Enforce type via validator; empty string is still a string. |
| Email nullable, but want to index all **declared** fields including null | Unique partial `email:{$exists:true}` | At most one null allowed. |
| Each tenant may use the same username as another tenant | Unique compound `{tenantId:1,username:1}` | Tuple is unique; null/missing also participates in the tuple. |
| Email optional and unique **within each tenant** | Unique compound + partial on valid email | Compound sparse may fail to skip missing email if `tenantId` is always present. |
| Only ACTIVE accounts need unique usernames | Unique partial on `status:"ACTIVE"` | Transitioning status to ACTIVE is also checked. |
| Case-insensitive uniqueness | Unique index with appropriate collation or canonical key | Keep queries, writers, and migrations aligned on the rule. |
| `tags` array must be unique **across documents** | Unique multikey index | Duplicate elements **within the same document** may still be allowed. |
| SKU must not repeat **within each order** | Separate line-items model + unique `{orderId,sku}` or explicit array constraint | Unique multikey on `items.sku` does not enforce intra-document rules. |
| Unique on a sharded collection | Unique index with shard key prefix per server rules | Check `_id` and hashed shard key cases. |

## 16. Common Reasoning Mistakes

| Misconception | Accurate Understanding |
|---|---|
| "A unique index only affects inserts." | Updates, replacements, and upserts can also produce duplicate index keys and be rejected. |
| "If a field is absent, it doesn't enter a unique index." | With a **non-sparse single-field unique** index, missing creates a null key. |
| "`null` and missing are identical in every situation." | They differ in documents and `$exists` queries; only certain indexing modes map them to an equivalent null key. |
| "Unique on email allows any number of missing emails." | Non-sparse single-field unique allows only one document with a null/missing key. |
| "Sparse allows multiple explicit nulls." | **No**: single-field sparse skips missing fields, yet still indexes explicit null. |
| "Partial `$exists:true` ignores null." | **No**: a null field still exists and is indexed. |
| "Partial `$type:"string"` forbids wrong-type emails." | No: documents outside the partial filter are unchecked by the unique constraint; use a separate validator. |
| "Partial `$type:"string"` always proves the field cannot be an array." | Query `$type` has special semantics for array elements; to forbid arrays, use an appropriate BSON schema. |
| "Compound unique means each individual field must be unique." | The constraint applies to the **tuple** of multiple fields. |
| "Compound unique sparse excludes any document missing one field." | If another field in the compound index is present, the document can still be indexed. |
| "One null in a compound unique index means only one null in the collection." | Tuples containing null can still differ in the remaining field(s). |
| "A unique index checks case sensitivity per app policy." | It depends on the configured **collation or canonical key**. |
| "Unique multikey forbids duplicate tags in the same document." | It primarily constrains keys **across documents**, not ensuring an array has unique elements. |
| "A unique index on `items.sku` guarantees one SKU per order." | It blocks the SKU in other orders without forbidding duplicates in the same order. |
| "`_id` is always globally protected across shards even if not the shard key." | On sharded collections, `_id` uniqueness scope has documented exceptions to check. |
| "A hashed index can take `unique:true` like any other index." | MongoDB does not support standard unique hashed indexes. |
| "Creating a unique index automatically cleans duplicates." | Index build fails when existing data has duplicate keys; you must migrate data first. |
| "Hiding a unique index lets you write duplicate data." | Hidden indexes still enforce uniqueness. |
| "On `E11000`, just retry until it succeeds." | It is usually a persistent data conflict; change the identity or verify idempotency. |
| "Checking before insert suffices for concurrent requests." | Only a database unique index prevents race conditions at write time. |
| "A unique index replaces a validator." | Unique checks key uniqueness; validators check types, values, and required fields. |

### 16.1. Distinguishing "No Value" from "Invalid Value"

Suppose a registration UI lets users skip email. There are at least four ways a client might send it:

~~~javascript
{ _id: "A" }
{ _id: "B", email: null }
{ _id: "C", email: "" }
{ _id: "D", email: " " }
~~~

If the product treats all four as "no email yet", the database does not automatically treat them identically:

- Missing generates a null index key in **non-sparse**, yet is excluded in **sparse**.
- Explicit `null` still enters a sparse index, yet can be excluded by **partial `$type:"string"`**.
- Empty string `""` is a **string**, so it is indexed by a string-typed partial index; only one empty string is allowed under uniqueness.
- Whitespace string `" "` is a string value distinct from `""` (depending on collation), so uniqueness may not reject it even if the business wants to disallow it.

A solid solution defines **normalization + validation + indexing** together. For instance, when a client supplies an empty email, the application normalizes it to a **missing field** instead of keeping an empty string, if that is the agreed policy; or a validator forbids empty strings and asks the user to fix the input.

### 16.2. Do Not Pick a Unique Index Before Knowing History Retention Needs

A username might be reusable after a user deletes their account; however, if audit logs reference users by username, reusing it can cause identity confusion. A partial unique index on `status:"ACTIVE"` solves "only active accounts cannot collide", yet **does not** automatically resolve historical semantics.

Reference users by an **immutable ID** and store name snapshots where needed, instead of using a mutable or reusable name as a business foreign key.

### 16.3. Transactions Do Not Relax Unique Indexes

Putting two duplicate-key inserts inside a transaction does not allow them to coexist in MongoDB. A transaction can hit a duplicate key and abort; the application must classify the error and apply retries appropriately. A stronger **write concern** likewise does not replace a unique index; it controls write acknowledgment durability, not business-key duplication checks.

## 17. Practice Exercises and Suggested Answers

Each exercise starts from a **new, empty collection** and considers only the documents shown in the prompt; do not carry over data between exercises. You can run them in `unique_index_lab` using a separate collection name per exercise.

### Exercise 1 — Single-Field Unique, Null Then Missing

Given the index:

~~~javascript
db.c1.createIndex({ email: 1 }, { unique: true })
~~~

Execute:

~~~javascript
db.c1.insertOne({ _id: 1, email: null })
db.c1.insertOne({ _id: 2 })
~~~

**Question:** Which operation fails? Why?

**Answer:** The first insert succeeds; the second fails with **duplicate key** because a non-sparse single-field unique index treats missing and explicit null as having the same index key `null`.

### Exercise 2 — Reversing Insert Order

Still with the unique `{email:1}` index, insert:

~~~javascript
db.c2.insertOne({ _id: 1 })
db.c2.insertOne({ _id: 2, email: null })
~~~

**Answer:** The second insert is also blocked. It does not matter whether null comes first or missing comes first; both compete for the single null key.

### Exercise 3 — Unique Sparse

~~~javascript
db.c3.createIndex(
  { email: 1 },
  { unique: true, sparse: true }
)

db.c3.insertOne({ _id: 1 })
db.c3.insertOne({ _id: 2 })
db.c3.insertOne({ _id: 3, email: null })
db.c3.insertOne({ _id: 4, email: null })
~~~

**Answer:** The two missing-field documents are allowed; the first explicit null is allowed; the second explicit null fails with E11000. Sparse skips missing fields but **does not skip present nulls**.

### Exercise 4 — String-Typed Unique Partial

~~~javascript
db.c4.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: {
      email: { $type: "string" }
    }
  }
)

db.c4.insertOne({ _id: 1 })
db.c4.insertOne({ _id: 2, email: null })
db.c4.insertOne({ _id: 3, email: null })
db.c4.insertOne({ _id: 4, email: "a@test" })
db.c4.insertOne({ _id: 5, email: "a@test" })
~~~

**Answer:** The first four inserts satisfy the unique index; the fifth insert fails as a duplicate string. However, if business rules forbid `email:null`, the index alone is **not enough** — schema validation is needed.

### Exercise 5 — Is the Empty String Ignored?

With the partial unique index `email: {$type:"string"}`, can two documents both having `email: ""` be inserted?

**Answer:** No. `""` is of type string so it gets indexed, and the duplicate value causes a duplicate-key error. To forbid empty strings up front, use a validator such as `minLength:1` or an equivalent domain rule.

### Exercise 6 — Compound Unique per Tenant

Create the unique index `{tenantId:1,username:1}` and insert:

~~~javascript
{ _id: 1, tenantId: "A", username: "lan" }
{ _id: 2, tenantId: "B", username: "lan" }
{ _id: 3, tenantId: "A", username: "lan" }
~~~

**Answer:** The first two documents are allowed because their tuples differ; the third document is rejected for duplicating the tuple `("A","lan")`.

### Exercise 7 — Compound Index, Missing Email

With the unique index `{tenantId:1,email:1}`, consider:

~~~javascript
{ _id: 1, tenantId: "A" }
{ _id: 2, tenantId: "B" }
{ _id: 3, tenantId: "A", email: null }
~~~

**Answer:** The first two documents have tuples `("A",null)` and `("B",null)`, so both are allowed. The third document collides on tuple `("A",null)` with document 1, raising a duplicate-key error.

### Exercise 8 — Does Compound Sparse Skip Missing Emails?

A system creates a unique sparse index `{tenantId:1,email:1}`. `tenantId` is always present; users who have not registered an email lack the `email` field. Are unlimited users without an email allowed within the same tenant?

**Answer:** **Not by default.** Because `tenantId` is present, a compound sparse index can still create an entry for documents missing `email` with the tuple `(tenantId,null)`. Choose a **partial** unique compound index on valid email conditions, while validating `tenantId`.

### Exercise 9 — Case-Insensitive Uniqueness

A collection has the index:

~~~javascript
db.c9.createIndex(
  { username: 1 },
  {
    unique: true,
    collation: { locale: "en", strength: 2 }
  }
)
~~~

Can you insert username `"An"` and then `"an"`?

**Answer:** No. Under this collation, they are treated as case-equivalent in the unique key. Queries wanting to use the index with the same comparison rules generally need the matching collation.

### Exercise 10 — Unique Index and Intra-Array Duplicates

A unique multikey index exists on `{tags:1}`. Is a document with `tags:["red","red"]` automatically rejected solely because two elements are equal?

**Answer:** No. A unique multikey index enforces uniqueness across **distinct documents**; repetition within the same array is not what it prevents. A second document containing `"red"` will collide with the first document.

### Exercise 11 — Updating to a Duplicate Key

Given:

~~~javascript
{ _id: 1, username: "an" }
{ _id: 2, username: "binh" }
~~~

With a unique index on `username`, run:

~~~javascript
db.c11.updateOne(
  { _id: 2 },
  { $set: { username: "an" } }
)
~~~

**Answer:** Fails with duplicate key; the unique constraint also applies when an **update** changes an indexed field's value.

### Exercise 12 — Reactivating an Account with a Partial Index

A unique partial index on `username` has filter `{status:"ACTIVE"}`. There is an account `{username:"lan",status:"ACTIVE"}` and an account `{username:"lan",status:"DELETED"}`. What happens if the DELETED account is switched to ACTIVE without changing its username?

**Answer:** The update can fail with **duplicate key**, because the second document now enters the partial unique index set and collides with the existing ACTIVE account.

### Exercise 13 — Creating an Index on Duplicate Data

A collection contains two documents with `username:"an"`; no index exists yet. Run:

~~~javascript
db.c13.createIndex(
  { username: 1 },
  { unique: true }
)
~~~

**Answer:** The index build fails. MongoDB does not arbitrarily choose which record to keep; you must resolve the duplicate data according to business rules and recreate the index.

### Exercise 14 — Race Condition

Two requests both run `findOne({username:"mai"})` and both receive null. Both insert a user with username `"mai"`. How do you ensure two duplicate accounts are not created?

**Answer:** Create a unique index on the proper business key; one insert succeeds while the other receives E11000. Handle that error in the application. Pre-checking only improves UX; it **does not prevent race conditions**.

### Exercise 15 — Sharding and Unique Indexes

A collection is sharded by `tenantId`. The application wants usernames unique **within each tenant**. Which unique index is more appropriate: `{username:1}` or `{tenantId:1,username:1}`?

**Answer:** `{tenantId:1,username:1}` is appropriate because the tuple matches the business rule and the shard key is a prefix per sharded-collection unique index rules. You must still verify the actual shard key and MongoDB version constraints.

### Exercise 16 — Querying Null and Missing

Given:

~~~javascript
{ _id: 1, email: null }
{ _id: 2 }
{ _id: 3, email: "a@test" }
~~~

Write two separate queries: (1) missing field only, (2) explicit BSON null.

**Answer:**

~~~javascript
// Missing:
db.c16.find({ email: { $exists: false } })

// Explicit null:
db.c16.find({ email: { $type: "null" } })
~~~

`{email:null}` normally matches **both missing and explicit null**, so do not use it to tell the two groups apart.

## 18. Integrated Design Scenario: Multi-Tenant Accounts

Suppose a SaaS system has these requirements:

1. Every account belongs to **one tenant**; `tenantId` is required.
2. `username` is required; within a tenant, usernames must not collide **case-insensitively**.
3. `email` is optional. Many accounts have no email yet, and users may not have verified their address yet.
4. When `emailVerified: true`, the email must be valid and unique **within the tenant** among verified accounts.
5. When an account is disabled, history must be preserved; references must not break due to username changes.

One implementation direction (requiring consideration of actual email policies and schemas):

~~~javascript
const lab = db.getSiblingDB("unique_index_lab")

// Username unique within each tenant, compared case-insensitively.
lab.saasAccounts.createIndex(
  { tenantId: 1, username: 1 },
  {
    unique: true,
    collation: { locale: "en", strength: 2 },
    name: "ux_tenant_username_ci"
  }
)

// Email unique within each tenant ONLY when the account is verified
// and email is a string. Assumes writers/validators ensure
// tenantId and email have valid types.
lab.saasAccounts.createIndex(
  { tenantId: 1, email: 1 },
  {
    unique: true,
    partialFilterExpression: {
      emailVerified: true,
      email: { $type: "string" }
    },
    name: "ux_tenant_verified_email"
  }
)
~~~

Points to understand:

- The first index protects **username per tenant**; it does not prevent `username` from being missing or mistyped in every situation. Use a validator to require `tenantId`/`username` and validate their types.
- The second index protects only **emails of accounts matching the partial filter**; it does not force unverified accounts to have an email.
- If two unverified accounts share the same email and **both get verified**, the operation moving the second account into the indexed set can hit E11000. The application must be prepared to handle this state.
- If email is a global identifier, adjust the uniqueness scope. If the collection is sharded, account for shard key prefix restrictions.
- Trusting `emailVerified: true` sent by the client is insufficient; email verification must be a trusted server-side workflow.
- Important references to an account should use an **immutable ID**, not a username that can change or be reused.

### 18.1. Why Not Use a Single Unique Index for All Requirements?

Because there are at least **two distinct invariants**:

~~~text
Unique(username | tenantId, regardless of whether the account is verified)

Unique(email | tenantId, only when emailVerified = true
                   and email is of a recognized type)
~~~

An index has only one key pattern and one set of options/filters. Multiple independent invariants usually require **multiple indexes** combined with validators and business logic. In exchange, each index increases storage and update costs, so measure your actual workload.

### 18.2. Email Update Flow

Suppose an account wants to change from `old@example.test` to `new@example.test`:

1. The application writes the candidate email to a temporary field without marking it verified.
2. Ownership is verified through the appropriate workflow.
3. When setting `emailVerified` to true and promoting the new email into the partial index key, MongoDB checks uniqueness.
4. If E11000 is raised, do not verify a duplicate; handle the conflict according to product policy.
5. Update the related fields in a single atomic write on the account if possible, avoiding a state where "email is verified" while the new email is not properly saved.

The unique index is the final guardrail protecting the key; it does not execute the identity verification workflow itself.

## 19. Official MongoDB Documentation

The following sources belong to the **MongoDB Database Manual** and driver documentation. When applying them, select the documentation branch matching your deployment's server/FCV version; `/docs/manual/` URLs may redirect to the current release.

- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — semantics of single-field, compound, null/missing, multikey, and sharded collection unique indexes.
- [Sparse Indexes](https://www.mongodb.com/docs/manual/core/index-sparse/) — documentation on skipping missing documents and sparse index limitations.
- [Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/) — `partialFilterExpression`, combining with unique, and query usage eligibility.
- [Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/) — indexes on arrays and unique multikey constraints.
- [Case-Insensitive Indexes](https://www.mongodb.com/docs/manual/core/index-case-insensitive/) — collation and case-insensitive indexes.
- [Collation](https://www.mongodb.com/docs/manual/reference/collation/) — locale, strength, and string comparison rules.
- [`db.collection.createIndex()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.createIndex/) — index creation syntax, key patterns, and options.
- [`db.collection.getIndexes()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.getIndexes/) — inspecting actual index configurations.
- [`$exists` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/exists/) — distinguishing present fields from missing fields.
- [`$type` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/type/) — querying BSON types and array caveats.
- [Query for Null or Missing Fields](https://www.mongodb.com/docs/manual/tutorial/query-for-null-fields/) — null equality queries and locating missing fields.
- [Sharding and Unique Indexes](https://www.mongodb.com/docs/manual/core/sharding-shard-key/) — sharding/shard key requirements related to uniqueness.
- [Index Builds on Populated Collections](https://www.mongodb.com/docs/manual/core/index-creation/) — building indexes on existing data and operational impact.
- [MongoDB Java Sync Driver — Indexes](https://www.mongodb.com/docs/drivers/java/sync/current/indexes/) — `IndexOptions` and driver-based index creation.
- [MongoDB 8.0 — Unique Indexes](https://www.mongodb.com/docs/v8.0/core/index-unique/) — fixed reference for the 8.0 branch.

**Conclusion:** With unique indexes, asking "is this field unique?" is not enough. You must also ask **which values enter the index, whether null/missing may repeat, whether uniqueness applies to a single field or a tuple, and whether status/tenant/collation conditions apply**. **Non-sparse unique**, **unique sparse**, and **unique partial** indexes behave very differently when fields are missing or null. Design constraints around business invariants, inventory and migrate existing data before building the index, and always handle `E11000` as a normal outcome in concurrent systems.
