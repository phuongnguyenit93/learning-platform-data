# Sparse Indexes and Partial Indexes with Filter Expressions in MongoDB

## Lesson Objectives

Indexes in MongoDB help queries locate documents faster by storing an organized data structure based on the fields that need to be searched or sorted. However, not every document in a collection needs to contribute an index entry for a given business use case. When a collection has many documents missing a field, or when the application predominantly queries a subset of documents matching a specific condition, you can use a **sparse index** or a **partial index** to restrict the data included in the index.

These two index types are frequently confused:

- A **sparse index** primarily relies on whether the indexed field **exists**.
- A **partial index** uses **`partialFilterExpression`** to define the indexed subset of documents via a filter condition; this condition can reference the indexed field or other fields.

The difference affects many aspects: index size, write overhead, uniqueness, query planner index selection, and query correctness when fields are missing or `null`.

After this lesson, learners will be able to:

1. Create sparse and partial indexes with `createIndex()`.
2. Explain accurately which documents receive index entries, especially for **missing** and **`null`**.
3. Choose `partialFilterExpression` for data segmented by status, document type, or value range.
4. Understand when a partial/sparse index **cannot be chosen by the query planner** to avoid omitting documents.
5. Combine `unique: true` with sparse/partial and recognize duplicate-key risks.
6. Read index definitions and inspect query plans with `getIndexes()` and `explain("executionStats")`.
7. Analyze the costs of building, maintaining, altering, dropping, and migrating indexes.
8. Select indexes based on workload, correctness, and data characteristics rather than assuming "a smaller index is always faster".

> **Key takeaway:** A sparse index is a relatively simple tool for **optional** fields. A partial index expresses a **conditional document subset** much more explicitly. Both require queries aligned with the index's data scope so results are never wrong or incomplete.

---

## 1. Reviewing the Role of Indexes in MongoDB

Suppose the `customers` collection has millions of documents. When looking up an email:

~~~javascript
db.customers.findOne({
  email: "an@example.test"
});
~~~

Without an appropriate index, MongoDB may have to scan many documents in the collection. A standard index:

~~~javascript
db.customers.createIndex({
  email: 1
});
~~~

stores `email` values in order inside the index structure. When many documents lack an email, a standard single-field index still creates entries corresponding to those missing/null documents according to MongoDB rules, resulting in storage and scan work that brings little benefit to queries only looking for customers with real emails.

For an index on a single field, three situations must be kept distinct:

~~~javascript
// Document A: has a string email value
{ _id: "A", email: "an@example.test" }

// Document B: email field exists, but value is null
{ _id: "B", email: null }

// Document C: email field is completely absent
{ _id: "C", fullName: "Binh" }
~~~

**Missing** and **`null`** are not the same data state:

- Missing: the field does not exist in the document.
- `null`: the field exists and holds the BSON value null.

A query:

~~~javascript
db.customers.find({
  email: null
});
~~~

normally matches both documents with `email: null` and documents **missing `email`**. Conversely:

~~~javascript
db.customers.find({
  email: { $exists: true }
});
~~~

selects documents where the `email` field exists, **including** null values.

The query:

~~~javascript
db.customers.find({
  email: { $type: "string" }
});
~~~

restricts to documents whose email value satisfies the string type. This distinction is the foundation for designing sparse and partial indexes.

### 1.1. An Index Impacts Both Reads and Writes

Indexes benefit many read patterns, at a cost:

- Consumes storage space for the index structure.
- Consumes memory/cache when the index is used.
- Inserts must add an index entry if the document falls within the index scope.
- Updates may add, remove, or modify keys in the index.
- Deletes must update the corresponding index.
- Building an index on a large collection can consume significant resources.
- Unique indexes enforce constraints and can cause writes to fail on duplicate keys.

Sparse and partial indexes help reduce some of these costs when the scope is chosen wisely. However, an overly narrow index may **fail to serve queries that need all documents**.

### 1.2. Design Questions to Ask Up Front

Before using sparse/partial indexes:

1. Can the field be missing, or can it only be null?
2. Which predicates do queries typically filter on?
3. Which documents **must be found**, and which lie outside the query scope?
4. Is uniqueness required only for a subset of documents?
5. Does that subset change frequently?
6. Do sort, pagination, or aggregation queries need documents outside that subset?
7. Do existing indexes already serve other endpoints?

**Do not choose an index merely because it is smaller.** You must demonstrate that the index serves the actual workload correctly.

---

## 2. What Is a Sparse Index?

A sparse index includes only documents where the indexed field **exists**, even if that field's value is `null`. For a **single-field sparse index** on `email`:

~~~javascript
db.customers.createIndex(
  { email: 1 },
  { sparse: true }
);
~~~

MongoDB skips documents that do not contain the `email` field when building this index.

For example:

| Document | `email` | Has entry in sparse index `{email:1}`? |
|---|---|---|
| A | `"an@example.test"` | **Yes** |
| B | `null` | **Yes** |
| C | Missing | **No** |
| D | `""` (empty string) | **Yes** |
| E | `123` (number, if schema permits) | **Yes** |

**Key point:** Sparse does **not** mean "only index non-null values". It checks field **presence**, and does not automatically exclude null or empty-string values.

### 2.1. Practical Example

The `profiles` collection stores accounts that may or may not have a phone number:

~~~javascript
db.profiles.insertMany([
  {
    _id: "U-101",
    displayName: "An",
    phone: "0901000001"
  },
  {
    _id: "U-102",
    displayName: "Binh"
  },
  {
    _id: "U-103",
    displayName: "Chi",
    phone: null
  },
  {
    _id: "U-104",
    displayName: "Dung",
    phone: "0901000004"
  }
]);
~~~

Create a sparse index:

~~~javascript
db.profiles.createIndex(
  { phone: 1 },
  {
    sparse: true,
    name: "idx_profiles_phone_sparse"
  }
);
~~~

The index contains entries for U-101, U-103, and U-104, while skipping U-102 because U-102 lacks `phone`.

A typical lookup query:

~~~javascript
db.profiles.find({
  phone: "0901000001"
});
~~~

can leverage the index because any matching document is guaranteed to have the `phone` field.

However, a query retrieving all profiles:

~~~javascript
db.profiles.find({}).sort({
  phone: 1
});
~~~

**cannot rely solely on the sparse index and still guarantee complete results**, because U-102 is not in the index at all. In such a case, the query planner may choose another execution path so documents are not omitted.

### 2.2. Inspecting the Index Definition

~~~javascript
db.profiles.getIndexes();
~~~

A definition looks similar to:

~~~javascript
{
  v: 2,
  key: { phone: 1 },
  name: "idx_profiles_phone_sparse",
  sparse: true
}
~~~

Metadata fields such as `v` may vary by version. What to verify are `key` and the `sparse: true` option.

### 2.3. Do Not Assume a Sparse Index Guarantees Index Usage

The MongoDB query planner must ensure queries do not return incomplete results. It will normally avoid choosing a sparse index when using that index would omit documents matching the filter.

For example:

~~~javascript
db.profiles.find({
  phone: null
});
~~~

This query can match **documents missing `phone` as well**. The sparse index omits U-102, so using it as the sole source could return incomplete data. Do not expect the planner to choose this index here.

Conversely:

~~~javascript
db.profiles.find({
  phone: { $exists: true }
});
~~~

only needs documents where `phone` exists, so its scope aligns with the sparse index. Still, which index the planner actually picks depends on filters, sorts, data size, and estimated cost.

---

## 3. Sparse Indexes with Multiple Fields and Limitations

### 3.1. A Compound Sparse Index Is Not Simply "All Fields Exist"

For a compound sparse index consisting solely of ascending/descending keys, MongoDB can create an entry for a document if **at least one of the indexed fields exists**.

For example:

~~~javascript
db.contacts.createIndex(
  {
    email: 1,
    phone: 1
  },
  {
    sparse: true,
    name: "idx_contacts_email_phone_sparse"
  }
);
~~~

Documents:

~~~javascript
{ _id: 1, email: "a@example.test" }
{ _id: 2, phone: "0900000002" }
{ _id: 3, email: "c@example.test", phone: "0900000003" }
{ _id: 4, displayName: "No contact info" }
~~~

For a standard compound index on `email` and `phone`:

- Document 1 gets an entry because `email` exists.
- Document 2 gets an entry because `phone` exists.
- Document 3 gets an entry because both exist.
- Document 4 gets no entry because both are absent.

Do not assume a compound sparse index only includes documents that have **both `email` and `phone`**.

**Special note:** Compound indexes containing text or 2dsphere keys have separate sparse rules depending on key type. When using those index types, consult the compound sparse indexes documentation for your specific version. The "at least one field exists" rule above applies to regular ascending/descending key combinations.

### 3.2. Why Can Compound Sparse Be Surprising?

Suppose the system wants uniqueness on the email–phone pair, yet some documents only have an email. A compound sparse index may still index them. When combined with `unique: true`, missing components of the compound key follow MongoDB uniqueness rules, which can trigger duplicate-key errors in unexpected cases.

If the business rule is "index only documents where both email and phone exist", `sparse` does not express that requirement accurately. A partial index requiring existence on both fields is much clearer:

~~~javascript
db.contacts.createIndex(
  { email: 1, phone: 1 },
  {
    partialFilterExpression: {
      email: { $exists: true },
      phone: { $exists: true }
    },
    name: "idx_contacts_both_fields"
  }
);
~~~

Note that `$exists: true` still includes null values. If business rules require actual strings, use an appropriate BSON type filter rather than just an existence check.

### 3.3. Sparse and Specialized Index Types

You cannot extrapolate every behavior of a regular single-field sparse index to text, wildcard, geospatial, or other specialized indexes. For instance, some index types have inherent sparse behavior, while others have specific entry-creation rules.

When your task is actually full-text search, coordinate queries, or wildcard fields, design around the characteristics of that index type rather than assuming `sparse: true` behaves just like a single-field B-tree index.

---

## 4. Unique Sparse Indexes and Optional Fields

### 4.1. Multiple Documents Missing the Field Can Coexist

Suppose the application lets accounts **omit an email**, while requiring provided emails not to duplicate.

~~~javascript
db.members.createIndex(
  { email: 1 },
  {
    sparse: true,
    unique: true,
    name: "uk_members_email_sparse"
  }
);
~~~

Example:

~~~javascript
db.members.insertMany([
  { _id: "M-001", name: "An" },
  { _id: "M-002", name: "Binh" },
  {
    _id: "M-003",
    name: "Chi",
    email: "chi@example.test"
  }
]);
~~~

Documents M-001 and M-002 both lack `email`; neither has an `email` entry in the sparse index, so omitting `email` in both does not violate this index's uniqueness.

However, inserting:

~~~javascript
db.members.insertOne({
  _id: "M-004",
  name: "Dung",
  email: "chi@example.test"
});
~~~

is rejected because it duplicates M-003's email, typically with duplicate key error code **11000**.

### 4.2. Multiple Null Values Remain a Problem

A sparse index **does index** documents where `email: null`. With a **single-field unique sparse index**, at most one document can hold the corresponding null key under standard uniqueness rules.

For example:

~~~javascript
db.members.insertOne({
  _id: "M-005",
  name: "Ha",
  email: null
});
~~~

Then:

~~~javascript
db.members.insertOne({
  _id: "M-006",
  name: "Lan",
  email: null
});
~~~

The second command can fail with a duplicate-key error because both documents have the `email` field with the value null.

This is a critical distinction:

| Email State | `unique: true, sparse: true` |
|---|---|
| Missing email | No index entry; multiple documents can omit it |
| Distinct string email | Valid |
| Two identical string emails | Duplicate key |
| Email is null | **Indexed**, so multiple nulls collide |
| Email is empty string | Indexed, so multiple empty strings collide |

If the system stores "no email provided" as `null`, unique sparse usually **fails the requirement** "allow multiple users without an email".

### 4.3. When Is Unique Sparse Appropriate?

Unique sparse is a straightforward option when the application consistently follows:

- Users without an email **do not store the `email` field**.
- Users with an email store a valid value.
- Data does not contain many null emails.
- Uniqueness is desired across all present email values.

If existing data contains many nulls, do not just turn on unique sparse and expect the index build to succeed. Either migrate the data or choose a partial index with an appropriate filter.

---

## 5. Partial Indexes: Indexing Only Documents Matching a Filter

### 5.1. Concept

A **partial index** defines its indexed document subset via the `partialFilterExpression` option.

For example, indexing only active customers:

~~~javascript
db.customers.createIndex(
  { lastLoginAt: -1 },
  {
    partialFilterExpression: {
      status: "ACTIVE"
    },
    name: "idx_active_customers_last_login"
  }
);
~~~

This definition has two parts:

1. **Index key:** `{ lastLoginAt: -1 }` — the data used for searching/sorting.
2. **Filter expression:** `{ status: "ACTIVE" }` — **only ACTIVE documents** are placed into the index.

**Key advantage:** The filter field **does not have to match** the index key field. This is a major difference from single-field sparse indexes: a partial index can be keyed on `lastLoginAt` while storing only documents with `status: "ACTIVE"`.

### 5.2. Status-Based Example

~~~javascript
db.customers.insertMany([
  {
    _id: "C-101",
    status: "ACTIVE",
    lastLoginAt: ISODate("2026-11-10T08:00:00Z")
  },
  {
    _id: "C-102",
    status: "INACTIVE",
    lastLoginAt: ISODate("2026-11-12T08:00:00Z")
  },
  {
    _id: "C-103",
    status: "ACTIVE",
    lastLoginAt: ISODate("2026-11-13T08:00:00Z")
  },
  {
    _id: "C-104",
    status: "DELETED",
    lastLoginAt: ISODate("2026-11-14T08:00:00Z")
  }
]);
~~~

Index:

~~~javascript
db.customers.createIndex(
  { lastLoginAt: -1 },
  {
    partialFilterExpression: {
      status: "ACTIVE"
    },
    name: "idx_active_last_login"
  }
);
~~~

This index includes documents C-101 and C-103, and excludes C-102 and C-104.

Eligible query:

~~~javascript
db.customers.find({
  status: "ACTIVE"
}).sort({
  lastLoginAt: -1
});
~~~

Because the query **only asks for ACTIVE documents**, its scope falls within the indexed subset. The planner can consider the partial index to avoid scanning the remaining documents.

### 5.3. The Filter Is Not Automatically Injected into Queries

A partial index does not mean MongoDB "automatically adds `status: 'ACTIVE'`" to every query using `lastLoginAt`.

For example:

~~~javascript
db.customers.find({}).sort({
  lastLoginAt: -1
});
~~~

This query asks for **ACTIVE, INACTIVE, and DELETED**, whereas the partial index only contains ACTIVE. If the planner used the partial index as the sole data source, documents would be missing. Therefore, the planner normally **does not select a partial index for queries that may require documents outside the filter**.

Always distinguish:

~~~text
partialFilterExpression = condition for a document to belong to the index.

query filter = condition the caller wants to find.

For a query to use the index safely:
  The query's result scope must be covered
  by the set of indexed documents.
~~~

---

## 6. Supported Conditions in `partialFilterExpression`

MongoDB supports a specific set of operators inside `partialFilterExpression`. Common ones include:

| Expression | Meaning | Example |
|---|---|---|
| Equality | Field equals a specific value | `{ status: "ACTIVE" }` |
| `$exists: true` | Field exists | `{ email: { $exists: true } }` |
| Range | Comparisons `$gt`, `$gte`, `$lt`, `$lte` | `{ score: { $gte: 80 } }` |
| `$type` | Checks BSON type | `{ email: { $type: "string" } }` |
| `$in` | Field belongs to a set of values | `{ status: { $in: ["NEW", "ACTIVE"] } }` |
| `$and` / `$or` | Combines supported conditions | See example below |

Expression support evolves across versions, so check the documentation for your server version before deploying. Not every query operator is valid inside `partialFilterExpression`. In particular, do not assume `$ne`, `$regex`, `$expr`, or `$exists: false` are supported options for creating partial indexes.

### 6.1. Multi-Condition Filter

For example, indexing only open, high-priority tickets:

~~~javascript
db.tickets.createIndex(
  { updatedAt: -1, _id: -1 },
  {
    partialFilterExpression: {
      status: "OPEN",
      priority: { $gte: 4 }
    },
    name: "idx_open_high_priority_recent"
  }
);
~~~

A document enters the index only if **both** conditions hold:

~~~text
status = OPEN
AND
priority >= 4
~~~

Eligible query:

~~~javascript
db.tickets.find({
  status: "OPEN",
  priority: { $gte: 4 }
}).sort({
  updatedAt: -1,
  _id: -1
}).limit(20);
~~~

A narrower query can also qualify:

~~~javascript
db.tickets.find({
  status: "OPEN",
  priority: { $gte: 5 }
}).sort({
  updatedAt: -1,
  _id: -1
}).limit(20);
~~~

Because `priority >= 5` is a subset of `priority >= 4`, every document the query needs satisfies the partial filter. The planner can choose the index if its cost is favorable.

Conversely:

~~~javascript
db.tickets.find({
  status: "OPEN",
  priority: { $gte: 2 }
});
~~~

may require tickets with priority 2 or 3 that **are not indexed**, so the partial index cannot return the complete query result.

### 6.2. Filtering by Document Type

A collection holding multiple document types:

~~~javascript
{
  _id: "DOC-001",
  docType: "INVOICE",
  invoiceNo: "INV-101"
}

{
  _id: "DOC-002",
  docType: "RECEIPT",
  receiptNo: "RCPT-301"
}
~~~

If only invoices have `invoiceNo`, you can create:

~~~javascript
db.documents.createIndex(
  { invoiceNo: 1 },
  {
    partialFilterExpression: {
      docType: "INVOICE"
    },
    name: "idx_invoice_no_for_invoices"
  }
);
~~~

Query:

~~~javascript
db.documents.find({
  docType: "INVOICE",
  invoiceNo: "INV-101"
});
~~~

If a query specifies only `invoiceNo` **without** asserting `docType`, the planner does not automatically assume non-invoices never contain that field unless it can prove so from the predicate and supported rules. Therefore, when designing APIs, include the appropriate discriminator predicate in the query.

### 6.3. Filtering by Existence and Data Type

To index every document that has the `email` field:

~~~javascript
db.accounts.createIndex(
  { email: 1 },
  {
    partialFilterExpression: {
      email: { $exists: true }
    },
    name: "idx_accounts_existing_email"
  }
);
~~~

This index serves a goal similar to a single-field sparse index, **still including null**.

If you want only emails that are actual strings:

~~~javascript
db.accounts.createIndex(
  { email: 1 },
  {
    partialFilterExpression: {
      email: { $type: "string" }
    },
    name: "idx_accounts_string_email"
  }
);
~~~

The `$type: "string"` filter is useful when data contains mixed field types. However, MongoDB queries and aggregations have special rules for arrays and `$type`; for a system requiring `email` to always be a scalar string, **schema validation** is an essential safeguard. Do not rely solely on a partial filter to block invalid data types.

---

## 7. Partial Unique Indexes: Uniqueness Only Within a Subset

### 7.1. Uniqueness by Status

Suppose an application allows multiple historical records with the same `username`, but only one **ACTIVE** record per username.

~~~javascript
db.user_records.createIndex(
  { username: 1 },
  {
    unique: true,
    partialFilterExpression: {
      status: "ACTIVE"
    },
    name: "uk_active_username"
  }
);
~~~

Meaning:

- Two documents with `username: "an"` and status INACTIVE can coexist.
- One document with username `"an"` and status ACTIVE can exist.
- Inserting or updating another document to also be ACTIVE with username `"an"` will violate the unique index.

Example:

~~~javascript
db.user_records.insertMany([
  {
    _id: "U-001",
    username: "an",
    status: "INACTIVE"
  },
  {
    _id: "U-002",
    username: "an",
    status: "DELETED"
  },
  {
    _id: "U-003",
    username: "an",
    status: "ACTIVE"
  }
]);
~~~

However:

~~~javascript
db.user_records.insertOne({
  _id: "U-004",
  username: "an",
  status: "ACTIVE"
});
~~~

can fail with duplicate key error 11000.

Key point: uniqueness **applies only to documents matching `partialFilterExpression`**, not the entire collection.

### 7.2. Status Transitions Can Cause Duplicate Keys

Suppose an INACTIVE document shares a username with an ACTIVE document. If you run:

~~~javascript
db.user_records.updateOne(
  { _id: "U-001" },
  {
    $set: {
      status: "ACTIVE"
    }
  }
);
~~~

this operation can fail because U-001 now enters the index scope and collides with U-003's unique key.

A partial unique index governs not only **inserts**, but also updates that cause a document to:

- Move from **outside** to **inside** the subset.
- Change the indexed field's value while remaining **inside** the subset.
- Move from **inside** to **outside** the subset.

Status changes can add or remove index entries, so account for them in write overhead.

### 7.3. Unique Email Only When Email Is a String

If you want multiple accounts without an email **or with a null email**, while forbidding duplicate string emails:

~~~javascript
db.accounts.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: {
      email: { $type: "string" }
    },
    name: "uk_accounts_string_email"
  }
);
~~~

Under typical requirements and scalar field types:

| Email | Has entry in partial unique index? |
|---|---|
| Missing | No |
| `null` | No |
| `"an@example.test"` | Yes |
| `"binh@example.test"` | Yes |
| `""` | Yes, because empty string is still a string |
| `123` | No, if it does not match string type under query semantics |

Notes:

- This is an **index rule**, not a complete email validator.
- `""` is still a string; if the application disallows empty emails, enforce that in the application or schema validator.
- If `email` can be an array or unusual type, check `$type` and multikey index semantics rather than mechanically applying the scalar table above.
- If emails are case-insensitive, consider **collation**, data normalization, and uniqueness semantics. Creating a partial index alone does not create case-insensitive uniqueness.

### 7.4. Partial Uniqueness Does Not Mean All Documents Are Unique

For instance, with a unique index filtered by:

~~~javascript
partialFilterExpression: {
  status: "ACTIVE"
}
~~~

INACTIVE documents can share duplicate usernames. This matches the index definition, yet is wrong if business rules require usernames to be unique **permanently**, even after an account is disabled. Choose the filter based on the **data contract**, not merely storage savings.

---

## 8. Comparing Sparse Indexes and Partial Indexes

| Criterion | Sparse Index | Partial Index |
|---|---|---|
| Option | `sparse: true` | `partialFilterExpression: {...}` |
| Core idea | Excludes documents missing the indexed field | Indexes only documents matching a predicate |
| Null handling in single-field index | `null` is still indexed if field exists | Depends on filter; can exclude null with `$type` |
| Filter on another field | Not sparse's strength | **Yes**, e.g., index `lastLoginAt` only when `status=ACTIVE` |
| Range conditions | Cannot express directly | Can use supported range operators |
| Subset uniqueness | Multiple missing allowed; nulls still collide | Unique only among documents matching filter |
| Compound keys | Has specific sparse rules | Scope determined by predicate |
| Query planner usability | Needs enough data for complete query results | Query must satisfy/imply the index condition |
| Index cost | Fewer entries if many docs omit the field | Fewer entries if predicate selects a small subset |
| New designs | Reasonable for simple optional fields | Usually more flexible for explicit filtering rules |

### 8.1. Sparse Can Be Viewed as Close to a Special Case of Partial

For a typical scalar field, these two indexes:

~~~javascript
db.users.createIndex(
  { email: 1 },
  {
    sparse: true,
    name: "idx_sparse_email"
  }
);
~~~

and:

~~~javascript
db.users.createIndex(
  { email: 1 },
  {
    partialFilterExpression: {
      email: { $exists: true }
    },
    name: "idx_partial_existing_email"
  }
);
~~~

have similar document-selection goals. However, do not infer that they behave identically across all compound indexes or specialized index types.

**MongoDB does not allow specifying both `sparse` and `partialFilterExpression` in the same index definition.** When you need to express richer conditions, choose a partial index instead of trying to combine both options.

### 8.2. Why Is Partial More Flexible?

Suppose the application only reads open orders:

~~~javascript
db.orders.find({
  status: "OPEN",
  customerId: "C-101"
}).sort({
  createdAt: -1
});
~~~

You can create:

~~~javascript
db.orders.createIndex(
  {
    customerId: 1,
    createdAt: -1
  },
  {
    partialFilterExpression: {
      status: "OPEN"
    },
    name: "idx_open_orders_customer_created"
  }
);
~~~

The index key does not need to store `status` merely to narrow the document set; the index predicate already excludes all CLOSED/CANCELED orders. This can reduce index size and write work for workloads focused on OPEN orders.

In return, if the application also queries CLOSED history per customer, this index **is insufficient to serve it**. Another index may be needed for the historical read path.

---

## 9. The Query Planner Can Only Choose an Index When Results Remain Complete

This is the most critical aspect of using partial and sparse indexes.

### 9.1. The Subset Rule

Suppose we have a partial index:

~~~javascript
db.orders.createIndex(
  { createdAt: -1 },
  {
    partialFilterExpression: {
      total: { $gte: 1000000 }
    },
    name: "idx_large_orders_created"
  }
);
~~~

The index holds orders with `total >= 1000000`.

A query:

~~~javascript
db.orders.find({
  total: { $gte: 2000000 }
}).sort({
  createdAt: -1
});
~~~

only needs orders totaling at least 2 million; all of them are in the index since `2 million >= 1 million`. The planner can use the index.

A query:

~~~javascript
db.orders.find({
  total: { $gte: 500000 }
});
~~~

needs orders between 500 thousand and under 1 million that **are missing from the partial index**. The planner cannot use this index as the sole source if it must return complete results.

Mental model:

~~~text
Index predicate:
  P(document) = total >= 1000000

Query predicate:
  Q(document) = total >= 2000000

If every Q satisfies P:
  The query can use the index without missing results.

If there exists a Q that does not satisfy P:
  The index is insufficient to return complete query results.
~~~

This is a rule about **result-set correctness**, before even considering performance.

### 9.2. The Query Must Express a Compatible Condition

Partial index:

~~~javascript
db.orders.createIndex(
  { createdAt: -1 },
  {
    partialFilterExpression: {
      status: "OPEN"
    },
    name: "idx_open_created"
  }
);
~~~

Compatible query:

~~~javascript
db.orders.find({
  status: "OPEN"
}).sort({
  createdAt: -1
});
~~~

Incompatible query:

~~~javascript
db.orders.find({}).sort({
  createdAt: -1
});
~~~

The second query needs all statuses. The planner normally refuses to select an index containing only OPEN.

For queries with complex filters, `$or`, `$in`, type coercion, or collation, whether the planner can **prove compatibility** is an important detail. Do not write vague business filters and expect the optimizer to infer every application invariant on its own.

### 9.3. Use `hint()` with Extreme Caution

You can force a query to use an index with `hint()`, for example:

~~~javascript
db.orders.find({}).hint(
  "idx_open_created"
);
~~~

Using a partial index containing only OPEN to answer a query asking for **all documents** can produce **incomplete results**. Similarly, forcing a sparse index on a query needing documents missing the field can omit data.

Never use `hint` to "force a query to run fast" before proving the result set remains correct. The query planner tries to avoid indexes that omit results; forcing an index can bypass that safeguard in certain cases.

### 9.4. Sorting Also Requires Complete Data

For example:

~~~javascript
db.customers.find({}).sort({
  lastLoginAt: -1
});
~~~

If the partial index only holds status ACTIVE, reading entries in index order will fail to return INACTIVE customers who have `lastLoginAt`. The planner must pick another strategy or use an index that covers the query.

Do not conclude an index works just because `sort` matches the index key direction; the **data scope** must match as well.

---

## 10. Verifying Indexes with Explain

### 10.1. Preparing the Index

~~~javascript
db.orders.createIndex(
  {
    customerId: 1,
    createdAt: -1,
    _id: -1
  },
  {
    partialFilterExpression: {
      status: "OPEN"
    },
    name: "idx_open_by_customer"
  }
);
~~~

### 10.2. Compatible Query

~~~javascript
const plan = db.orders
  .find({
    customerId: "C-101",
    status: "OPEN"
  })
  .sort({
    createdAt: -1,
    _id: -1
  })
  .limit(20)
  .explain("executionStats");

printjson(plan.queryPlanner.winningPlan);
printjson(plan.executionStats);
~~~

Fields worth checking:

| Field | Meaning |
|---|---|
| `winningPlan` | Selected query execution plan |
| `IXSCAN` / equivalent index scan stage | Index scan |
| `COLLSCAN` | Collection scan |
| `SORT` or equivalent sort stage | Explicit in-memory sort stage |
| `nReturned` | Number of returned documents |
| `totalKeysExamined` | Number of index entries examined |
| `totalDocsExamined` | Number of documents read/examined |
| `executionTimeMillis` | Reported execution time in explain |

Plan shapes can vary across MongoDB versions and query engines; you may need to inspect nested stages inside `winningPlan`. On small collections, the planner may pick `COLLSCAN` because it is cheaper even when a valid index exists; do not conclude an index is useless from a tiny dataset of a few documents.

### 10.3. Query Without the Partial Filter

~~~javascript
db.orders
  .find({ customerId: "C-101" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");
~~~

This query requires both OPEN and CLOSED. A partial index containing only OPEN **is insufficient**. Compare the plans and explain why the planner picks a different index or a collection scan.

### 10.4. Explain Results Do Not Replace Benchmarking

`explain("executionStats")` shows the execution strategy and index/document scan volume. However, API latency also includes connection pooling, network overhead, BSON decoding, Java object mapping, serialization, caching, concurrency, and write load.

Benchmarks require:

- Representative real or synthetic datasets.
- Both selective and low-selectivity queries.
- Identical hardware and MongoDB version.
- Comparable indexes and write concerns when comparing options.
- Warm-up, multiple runs, and p95/p99 latency measurements.
- Realistic cache state and data distribution.

---

## 11. Evaluating Index Size and Maintenance Cost

### 11.1. Sparse/Partial Can Shrink an Index

Suppose a collection has 2 million users:

- 1.6 million users do not have a phone number yet.
- 400 thousand users have a phone number.
- Most phone queries look up a specific value.

A sparse index on `phone` may store entries for only around 400 thousand documents that have `phone`, instead of creating entries for all documents missing the field. However, if many documents store `phone: null`, they **still belong to the sparse index** and that count will be larger.

If the business only uses string phones, a partial index with `$type: "string"` can additionally exclude null values from the index scope.

**Do not equate index entry count with bytes on disk.** Actual size also depends on key sizes, record identifiers, storage engine behavior, and compression.

### 11.2. Measuring Storage Size

~~~javascript
db.users.stats();
~~~

Statistics output may include `indexSizes` and `totalIndexSize`, for example:

~~~javascript
{
  indexSizes: {
    "_id_": 123456,
    "idx_phone_sparse": 654321
  },
  totalIndexSize: 777777
}
~~~

Numbers shown here are illustrative only. Actual server data determines real sizes.

To inspect index definitions:

~~~javascript
db.users.getIndexes();
~~~

To inspect access statistics:

~~~javascript
db.users.aggregate([
  { $indexStats: {} }
]);
~~~

`$indexStats` is not the sole proof of whether an index is needed. Access counters can reset on restarts or maintenance operations, and a rarely queried unique index still provides essential data-integrity enforcement.

### 11.3. A Partial Index Can Increase Write Work When Document Status Changes

A partial index `status: "OPEN"` stores only OPEN orders:

~~~text
Create OPEN order:
  -> add index entry.

Change OPEN -> CLOSED:
  -> remove entry from partial index.

Change CLOSED -> OPEN:
  -> add entry to partial index.

Update createdAt while still OPEN:
  -> update related key.
~~~

If statuses flip very frequently, index maintenance overhead can be significant even though the index only holds part of the dataset. Evaluate the **read/write mix**, not just current index size.

### 11.4. Partial Filters Should Be Neither Too Broad Nor Too Narrow

If a partial filter matches 99.9% of the collection, the index may save very little compared to a regular index.

If a partial filter matches 0.1% of the collection while the API mostly queries documents outside it, the index is tiny yet useless for the main read path.

Answer:

- What percentage of documents currently match the filter?
- How does that percentage evolve over time?
- What percentage of read queries target that subset?
- Which operations cause documents to enter or leave the subset?
- Do other queries still require a full index?

---

## 12. Unique Indexes, Collation, and Data Normalization

### 12.1. Case-Insensitive Emails

Suppose an application treats `An@Example.Test` and `an@example.test` as the same email. A unique partial index using only:

~~~javascript
db.accounts.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: {
      email: { $type: "string" }
    }
  }
);
~~~

does not automatically enforce case-insensitive comparison per business rules if the default collation is simple.

You can consider a unique partial index with an appropriate collation:

~~~javascript
db.accounts.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: {
      email: { $type: "string" }
    },
    collation: {
      locale: "en",
      strength: 2
    },
    name: "uk_accounts_email_case_insensitive"
  }
);
~~~

Note that collation affects string comparison and whether queries can use the index. Verify Unicode handling, email normalization, and system-specific rules; do not assume every email worldwide is properly handled by lowercasing the entire string.

### 12.2. Null, Empty String, and Missing Are Three Distinct States

| Data | Possible Business Meaning | Included by Partial Filter `$type:"string"`? |
|---|---|---|
| Missing | Not provided yet | No |
| `null` | No value | No |
| `""` | Empty string | Yes |
| `"abc"` | String value | Yes |

If the system rejects empty strings, use schema validation or normalize them to missing/null under a consistent policy. Do not use a unique index in place of a validator.

### 12.3. An Index Can Fail to Build Due to Duplicate Data

Before creating a unique partial index, check for duplicate keys **within the subset matching the filter**.

For example, checking only ACTIVE users:

~~~javascript
db.user_records.aggregate([
  {
    $match: {
      status: "ACTIVE"
    }
  },
  {
    $group: {
      _id: "$username",
      count: { $sum: 1 },
      ids: { $push: "$_id" }
    }
  },
  {
    $match: {
      count: { $gt: 1 }
    }
  }
]);
~~~

If duplicate usernames exist in the ACTIVE subset, the unique index build can fail. On large datasets, the aggregation above can be resource-heavy and `ids` can grow large; in production, use an appropriate batched verification approach.

Before enforcing uniqueness, finalize a policy for handling duplicates rather than deleting or renaming records arbitrarily.

---

## 13. Sparse/Partial Indexes Do Not Replace Schema Validation

A partial index with:

~~~javascript
partialFilterExpression: {
  email: { $type: "string" }
}
~~~

only determines which documents are indexed. It **does not reject** documents where `email` is a number, null, or array if the collection has no other constraints.

For example:

~~~javascript
db.accounts.insertOne({
  _id: "A-100",
  email: 12345
});
~~~

Without a validator or application rule blocking it, MongoDB can still accept this document. It is simply omitted from the partial index per the chosen predicate.

If the business rule is "email, when present, must be a valid string", use:

- API/application-level validation.
- MongoDB schema validation where appropriate.
- Unique/partial indexes to enforce uniqueness within the defined scope.
- Legacy data normalization workflows.

Indexes and validators handle **two separate responsibilities**:

~~~text
Schema validation:
  Does the document have the right structure and types?

Unique index:
  Are keys within the index scope duplicated?

Partial/sparse index:
  Which documents contribute keys to the index?

Query planner:
  Which index can be used without missing results?
~~~

---

## 14. Important Scope and Restrictions

### 14.1. Do Not Combine `sparse` and `partial` on the Same Index

Do not declare:

~~~javascript
// Invalid configuration: choose one mechanism.
db.users.createIndex(
  { email: 1 },
  {
    sparse: true,
    partialFilterExpression: {
      email: { $type: "string" }
    }
  }
);
~~~

If you need to index only string emails, use partial. If you only need field presence, single-field sparse may suffice.

### 14.2. Do Not Arbitrarily Apply Partial to Every Index Type

MongoDB enforces restrictions by index type. For example, the `_id` index cannot arbitrarily be turned into a partial index; shard key indexes also have restrictions with partial indexes. Some specialized indexes have their own limitations.

If the system uses sharded collections, cluster keys, text/geospatial indexes, or advanced features, check the official documentation for your **exact MongoDB version and topology** before creating the index. Do not assume every option from a standard B-tree index works on every index type.

### 14.3. Partial Indexes Only Support Specified Filter Operators

Do not rely on MQL intuition to assume every `find()` expression is valid inside `partialFilterExpression`.

For example, if you want to index documents **missing** a field with `$exists: false`, that is not a generally supported partial index option like `$exists: true`. You must redesign the predicate or materialize a meaningful business flag such as `hasEmail: false` if indexing that group is truly necessary.

### 14.4. Do Not Use Unique Partial as a Collection-Wide Constraint

A partial unique index on `username` when `status` is ACTIVE **allows** duplicate usernames across non-ACTIVE documents. If the business team does not want that, the index definition is wrong even though every MongoDB command succeeds.

### 14.5. Index Predicates Can Interact with Collation

When a partial filter contains string comparisons, the configured collation can affect how scope is evaluated and how queries match the index. When using an index with a custom collation, supply the matching collation on queries when needed and verify with `explain()`.

---

## 15. Hands-On Lab: Building Sparse and Partial Indexes

This section uses the `special_index_lab` database. Run only in a test environment.

### 15.1. Creating Sample Data

~~~javascript
use special_index_lab

db.users.insertMany([
  {
    _id: "U-001",
    name: "An",
    status: "ACTIVE",
    email: "an@example.test",
    score: 92
  },
  {
    _id: "U-002",
    name: "Binh",
    status: "ACTIVE",
    score: 85
  },
  {
    _id: "U-003",
    name: "Chi",
    status: "INACTIVE",
    email: null,
    score: 73
  },
  {
    _id: "U-004",
    name: "Dung",
    status: "ACTIVE",
    email: "dung@example.test",
    score: 95
  },
  {
    _id: "U-005",
    name: "Ha",
    status: "INACTIVE",
    score: 81
  },
  {
    _id: "U-006",
    name: "Lan",
    status: "ACTIVE",
    email: null,
    score: 88
  },
  {
    _id: "U-007",
    name: "Mai",
    status: "DELETED",
    email: "mai@example.test",
    score: 90
  }
]);
~~~

Inspect:

~~~javascript
db.users.find().sort({ _id: 1 });
~~~

Cases:

| Document | Status | Email |
|---|---|---|
| U-001 | ACTIVE | string |
| U-002 | ACTIVE | Missing |
| U-003 | INACTIVE | null |
| U-004 | ACTIVE | string |
| U-005 | INACTIVE | Missing |
| U-006 | ACTIVE | null |
| U-007 | DELETED | string |

### 15.2. Creating a Sparse Index

~~~javascript
db.users.createIndex(
  { email: 1 },
  {
    sparse: true,
    name: "idx_email_sparse"
  }
);
~~~

The index has entries for U-001, U-003, U-004, U-006, and U-007. It skips U-002/U-005 because they lack the `email` field.

Try queries:

~~~javascript
db.users.find({
  email: "an@example.test"
});

db.users.find({
  email: { $exists: true }
});

db.users.find({
  email: null
});
~~~

For the last query, remember that documents missing `email` also match the equality `null` condition, so the sparse index does not hold all matching results.

### 15.3. Creating a Status-Based Partial Index

~~~javascript
db.users.createIndex(
  { score: -1, _id: 1 },
  {
    partialFilterExpression: {
      status: "ACTIVE"
    },
    name: "idx_active_score"
  }
);
~~~

Querying the ACTIVE list:

~~~javascript
db.users.find({
  status: "ACTIVE"
}).sort({
  score: -1,
  _id: 1
});
~~~

Documents U-001, U-002, U-004, and U-006 fall inside this index scope; U-003, U-005, and U-007 do not.

Querying scores across all statuses:

~~~javascript
db.users.find({}).sort({
  score: -1,
  _id: 1
});
~~~

should not be resolved solely with the ACTIVE partial index, because that would omit non-ACTIVE documents.

### 15.4. Inspecting Query Plans

~~~javascript
db.users
  .find({ status: "ACTIVE" })
  .sort({ score: -1, _id: 1 })
  .explain("executionStats");

db.users
  .find({})
  .sort({ score: -1, _id: 1 })
  .explain("executionStats");
~~~

Record the index used, `nReturned`, `totalKeysExamined`, and `totalDocsExamined`. With only seven documents, the planner may choose a scan because the dataset is tiny; do not treat timings from this lab as production benchmarks.

### 15.5. Testing Unique Partial with String Emails

Because U-003 and U-006 have null emails, creating a **unique sparse** index directly on `email` would hit a duplicate-key conflict. Use a string partial filter:

~~~javascript
db.users.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: {
      email: { $type: "string" }
    },
    name: "uk_email_string"
  }
);
~~~

If your MongoDB version or existing index set imposes restrictions on identical key patterns, use a different lab collection or intentionally drop the older index before creating this one. The goal is to observe uniqueness within the string scope, not force two conflicting index definitions to coexist.

Try inserting a duplicate email:

~~~javascript
db.users.insertOne({
  _id: "U-008",
  name: "Ngoc",
  status: "ACTIVE",
  email: "an@example.test",
  score: 80
});
~~~

A duplicate-key error can occur because `"an@example.test"` already exists and satisfies the filter.

Try creating a user without an email:

~~~javascript
db.users.insertOne({
  _id: "U-009",
  name: "Quan",
  status: "ACTIVE",
  score: 77
});
~~~

Omitting `email` does not violate this unique partial index.

### 15.6. Inspecting Metadata

~~~javascript
db.users.getIndexes();
db.users.stats();

db.users.aggregate([
  { $indexStats: {} }
]);
~~~

Verify `sparse` and `partialFilterExpression` in the metadata rather than relying solely on the index name.

---

## 16. Business Case 1: Indexing Only Open Orders

### 16.1. Problem Statement

The `orders` collection holds 5 million orders spanning several years, yet only about 100 thousand are in the OPEN state. An operations dashboard continually queries each customer's OPEN orders sorted by newest first:

~~~javascript
db.orders.find({
  customerId: "C-101",
  status: "OPEN"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

### 16.2. Standard Index

~~~javascript
db.orders.createIndex(
  {
    customerId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "idx_orders_customer_status_recent"
  }
);
~~~

This index covers all statuses; it is useful if endpoints also query PAID/CANCELED/CLOSED orders per customer.

### 16.3. Partial Index Dedicated to OPEN

~~~javascript
db.orders.createIndex(
  {
    customerId: 1,
    createdAt: -1,
    _id: -1
  },
  {
    partialFilterExpression: {
      status: "OPEN"
    },
    name: "idx_open_customer_recent"
  }
);
~~~

Why can this be beneficial?

- Stores only the 100 thousand OPEN orders instead of all 5 million.
- The query always specifies `status: "OPEN"`, so it can use the index safely.
- The index key does not need to carry `status` because the scope is fixed at the predicate level.

Trade-offs:

- When an order transitions OPEN → PAID, the index entry must be deleted.
- Endpoints viewing PAID history cannot rely on this index alone.
- If the count of OPEN orders grows dramatically, size savings shrink.
- If the application forgets the `status` predicate in a query, the planner may not select the index.

You cannot claim a partial index is always faster than a regular index without measuring key counts, sizes, cache behavior, and read/write latencies.

---

## 17. Business Case 2: Optional Yet Unique Email

### 17.1. Two Different Data Shapes Lead to Different Indexes

**Design A:** When there is no email, **omit the field completely**.

~~~javascript
{ _id: "A", name: "An" }
{ _id: "B", name: "Binh" }
{ _id: "C", name: "Chi", email: "chi@example.test" }
~~~

Unique sparse can be suitable:

~~~javascript
db.accounts.createIndex(
  { email: 1 },
  {
    unique: true,
    sparse: true,
    name: "uk_email_sparse"
  }
);
~~~

**Design B:** When there is no email, `null` may be stored.

~~~javascript
{ _id: "A", name: "An", email: null }
{ _id: "B", name: "Binh", email: null }
{ _id: "C", name: "Chi", email: "chi@example.test" }
~~~

Unique sparse does not allow multiple indexed nulls under standard single-field unique rules. A string-typed partial unique index may be a better fit:

~~~javascript
db.accounts.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: {
      email: { $type: "string" }
    },
    name: "uk_email_string"
  }
);
~~~

### 17.2. Adding Validation

If `email`, when present, must be a string:

~~~javascript
db.createCollection("validated_accounts", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      properties: {
        email: {
          bsonType: ["string", "null"]
        }
      }
    }
  }
});
~~~

The validator example above permits null or string, though it does not check valid email syntax yet. The application still needs validation for empty strings, whitespace, and specific email format rules.

The unique partial index guarantees uniqueness **within the set of string emails**. It does not guarantee valid email formatting or that a field will never hold a number if a validator is missing.

---

## 18. Business Case 3: Indexing Currently Valid Data

A `coupons` collection contains many expired vouchers, while the API frequently queries vouchers that are ACTIVE and not yet expired.

If you consider creating a partial index with a dynamic condition based on **the current time**, be cautious. `partialFilterExpression` is not a filter that automatically shifts every second with the application clock. Do not assume you can put a dynamic "now" value in the index definition and have the server automatically prune the scope simply as time passes.

A more common design:

~~~javascript
db.coupons.createIndex(
  {
    customerId: 1,
    expiresAt: 1
  },
  {
    partialFilterExpression: {
      status: "ACTIVE"
    },
    name: "idx_active_coupons_expiry"
  }
);
~~~

Query:

~~~javascript
db.coupons.find({
  customerId: "C-101",
  status: "ACTIVE",
  expiresAt: { $gt: new Date() }
}).sort({
  expiresAt: 1
});
~~~

Meaning:

- The partial index filters on **status ACTIVE**.
- The range predicate on `expiresAt` is evaluated in the query at execution time.
- The application or a background job manages the voucher's ACTIVE status per business logic.
- A past-due voucher still marked ACTIVE may retain an index entry; the range query filters it out at read time.

This separates the stable index predicate from the continuously changing time condition in the query.

---

## 19. Managing Index Lifecycle in Production

### 19.1. You Cannot Arbitrarily Edit an Existing Index's Filter

If an existing index is:

~~~javascript
{
  key: { createdAt: -1 },
  partialFilterExpression: {
    status: "OPEN"
  }
}
~~~

and you want to expand it to OPEN or PENDING, do not assume calling `createIndex` again with the same name will update the predicate in place. Index definitions must be managed by creating a new index or replacing it through a procedure supported by your server version.

A migration plan might include:

1. Finalizing the workload and new filter.
2. Auditing existing data, including uniqueness if applicable.
3. Creating the new index under a different name when configuration permits.
4. Running `explain()` and benchmarks on representative data.
5. Switching the application to queries compatible with the new index.
6. Verifying no remaining dependency on the old index.
7. Only then dropping the old index under change management procedures.

When replacing a unique index, pay attention to the overlap or gap in constraint enforcement, concurrent writes, and key collision risks.

### 19.2. Index Builds on Large Collections

Before creating:

~~~javascript
db.orders.createIndex(
  { customerId: 1, createdAt: -1 },
  {
    partialFilterExpression: {
      status: "OPEN"
    },
    name: "idx_open_customer"
  }
);
~~~

evaluate:

- CPU, disk I/O, cache, and storage headroom.
- Resulting index size after the build.
- Number of documents scanned during the build.
- Risk of a unique index build failing due to duplicate data.
- Production load, deployment window, and monitoring.
- Replica set and sharded deployment considerations if applicable.

A partial index holds only a subset of documents after completion, yet building the index still requires determining which documents match the filter—so building is not automatically cheap.

### 19.3. When Dropping an Index

~~~javascript
db.orders.dropIndex(
  "idx_open_customer"
);
~~~

This command alters query performance and/or uniqueness guarantees if the index enforced a constraint. Execute it only after verifying the old index is no longer needed or a replacement index meets all requirements.

Do not drop a production index merely because `$indexStats` shows 0 accesses over a short window. A rarely scanned unique index can still be a vital guardrail against duplicate data.

### 19.4. Naming Indexes to Convey Intent

Clear names aid operations:

~~~text
idx_users_phone_sparse
uk_accounts_email_string
idx_open_orders_customer_recent
idx_active_tickets_priority
idx_coupons_active_expiry
~~~

Avoid naming indexes `index_1` or `idx_test` in production when a system has many indexes and migrations. Index names are part of operations, logs, explain plans, and change management.

---

## 20. Common Mistakes and Misconceptions

### "A sparse index skips null"

**False.** A single-field sparse index skips documents **missing the field**, whereas documents containing the field with `null` are still indexed.

### "Unique sparse allows unlimited null values"

**False** for a standard single-field unique sparse index. Multiple documents missing the field are allowed, but documents containing `null` collide on the null key.

### "A partial index can only filter on the indexed field"

**False.** A partial index can build its keys on `createdAt` while filtering by `status`.

### "Any query matching the index's sort order can use a partial index"

**False.** The index must cover all documents the query needs. If the query needs CLOSED while the partial index holds only OPEN, using the index as the sole source would produce incomplete results.

### "Forcing `hint` is a good way to make an index get chosen"

**Risky.** Hinting a sparse/partial index that does not cover all results can cause the query to drop matching documents. Prove correctness first.

### "Partial unique guarantees collection-wide uniqueness"

**False.** It constrains only documents matching the filter.

### "A smaller index is always faster"

Not necessarily. The planner might not choose the index, transitions into/out of the subset add write overhead, and read speed also depends on cache, index keys, selectivity, and returned data volume.

### "With an index, you don't need a validator"

**False.** Indexes control index entries and key constraints; validators control document structure and types. A partial filter may simply skip mistyped documents rather than rejecting them.

### "Compound sparse only indexes documents having all fields"

Incorrect for compound sparse indexes composed of standard ascending/descending keys: a document with at least one indexed field can contribute an entry. Always verify the rules for the specific compound index type.

### "You can set `sparse: true` and `partialFilterExpression` together"

**No.** Those two options cannot be combined in the same index definition.

### "You can change a partial filter by recreating the index with the same name"

Do not assume this. Index definitions must be updated through an appropriate migration/replacement workflow.

### "Time-expired data disappears from a partial index automatically"

Not simply because the application clock advances. An index predicate is not a live clock. If using an ACTIVE status, documents must have their status updated or be deleted per business policy; queries can still filter `expiresAt` at read time.

---

## 21. Practice Exercises

### Exercise 1 — Sparse and Null

In `special_index_lab`, create six documents:

1. Two documents with distinct string `phone` values.
2. Two documents **missing** `phone`.
3. Two documents with `phone: null`.

Create a non-unique sparse `{phone:1}` index. Identify which documents are indexed. Then try a unique sparse index on a different collection with the same data; explain why the index build can fail on the two nulls.

### Exercise 2 — Partial Unique for String Emails

Design an account collection that allows:

- Multiple users without an `email` field.
- Multiple users with a null `email`.
- No duplicate string emails.
- No numeric emails in new data.

Choose the partial unique index and add an appropriate validator. Explain why the index alone does not enforce valid data types.

### Exercise 3 — Choosing an Index for a Dashboard

An `orders` collection has 5 million documents, with only 2% still OPEN. A dashboard runs:

~~~javascript
db.orders.find({
  customerId: "C-101",
  status: "OPEN"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

Propose a compound partial index and explain its keys and filter. List two queries that this index **does not** cover completely.

### Exercise 4 — Query Planner Eligibility

Partial index:

~~~javascript
db.tickets.createIndex(
  { updatedAt: -1 },
  {
    partialFilterExpression: {
      priority: { $gte: 4 }
    }
  }
);
~~~

For each query below, determine whether its result set is contained within the indexed set:

~~~javascript
// A
db.tickets.find({
  priority: { $gte: 5 }
});

// B
db.tickets.find({
  priority: { $gte: 2 }
});

// C
db.tickets.find({
  priority: 4
});

// D
db.tickets.find({});
~~~

Explain why eligibility does not guarantee the planner will choose the index.

### Exercise 5 — Status and Unique Partial

Create a unique partial index on `username` when `status: "ACTIVE"`. Insert two INACTIVE documents with the same username and one ACTIVE document with that username. Then try switching one INACTIVE document to ACTIVE. Predict the error and explain the index entry created during the status change.

### Exercise 6 — Measuring and Comparing Indexes

Generate lab data with the distribution:

- 80% of documents missing the `phone` field.
- 10% with `phone: null`.
- 10% with a string `phone`.

Compare index sizes across regular, sparse, and partial `$type:"string"` indexes on separate collections to avoid same-key-pattern index restrictions. Run `explain()` for a string-phone query and a `phone: null` query. Analyze correctness, index sizes, keys/docs examined, and write cost.

### Exercise 7 — Compound Sparse

Suppose documents exist with only `email`, only `phone`, both, and neither. Create a sparse compound index `{email:1,phone:1}`. Explain which entries are created. Then design a partial index that includes only documents **where both `email` and `phone` are strings**.

### Exercise 8 — Production Index Migration

A collection has a regular index `{customerId:1,createdAt:-1}`. The team wants to replace it with a partial index only for status OPEN:

1. Collect all query shapes currently using the old index.
2. Identify which endpoints still need CLOSED/PAID orders.
3. Create the new index and inspect `explain()`.
4. Evaluate storage size and write maintenance.
5. Determine when it is safe to drop the old index.
6. Design a rollback plan if a historical endpoint slows down after the change.

---

## 22. Review Questions

1. Which documents does a single-field sparse index exclude from the index?
2. Why is `null` not equivalent to missing?
3. Can a unique sparse index allow multiple documents missing `email`?
4. Why can two documents with `email: null` collide under a unique sparse index?
5. How does a partial index differ from a sparse index in expressing conditions?
6. Can `partialFilterExpression` reference a field other than the index key?
7. Why might a query filtering only on `customerId` not use a partial index with `status: "OPEN"`?
8. What makes a query a subset of a partial filter?
9. How can `hint()` cause incomplete results?
10. Does a unique partial index prevent duplicate keys outside the filter?
11. Why can changing status INACTIVE → ACTIVE trigger a duplicate-key error?
12. What is the entry-creation rule for a compound sparse index with ascending keys?
13. Why should you not assume `$exists: false` is supported in a partial filter?
14. `$type: "string"` excludes null, but does it exclude empty strings?
15. Does a partial index automatically update by the clock for a "not yet expired" condition?
16. Which metrics demonstrate that an index is useful for a query?
17. Why might a smaller index fail to improve performance?
18. When changing an index definition in production, which workloads must you investigate first?
19. Why might a rarely queried unique index still need to be kept?
20. Why do indexes not replace schema validation?

## 23. Summary

Both sparse indexes and partial indexes help avoid storing index entries for documents that do not serve a set of queries, yet they have different semantics:

- **Sparse indexes:** suited for optional fields, primarily skipping documents **that lack the indexed field**. In a single-field index, fields holding `null` **are still indexed**.
- **Partial indexes:** restrict the document set using `partialFilterExpression`, which can filter by status, BSON type, range, or conditions on a different field.
- **Unique sparse/partial:** enforce uniqueness only across documents that have an entry. When handling optional emails, the distinction between missing and null is crucial.
- **Query planner:** must ensure an index cannot cause incomplete query results. With sparse/partial indexes, query filters must align with the index scope; never force `hint` merely to see an index used.
- **Operations:** measure execution plans, index sizes, write costs, and data consistency; during index migrations, account for both historical queries and unique constraints.

The practical workflow should be: **define the document subset to query → express the condition precisely → create the index → inspect `getIndexes()` and `explain()` → benchmark on representative data → check write impact and production change plans**.

## Official MongoDB References

- [MongoDB Manual — Sparse Indexes](https://www.mongodb.com/docs/manual/core/index-sparse/)
- [MongoDB Manual — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Manual — Create Index](https://www.mongodb.com/docs/manual/reference/method/db.collection.createIndex/)
- [MongoDB Manual — Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Manual — Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [MongoDB Manual — Query for Null or Missing Fields](https://www.mongodb.com/docs/manual/tutorial/query-for-null-fields/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — Collation](https://www.mongodb.com/docs/manual/reference/collation/)
- [MongoDB Manual — Query Optimization](https://www.mongodb.com/docs/manual/core/query-optimization/)
- [MongoDB Manual — $indexStats Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexStats/)
