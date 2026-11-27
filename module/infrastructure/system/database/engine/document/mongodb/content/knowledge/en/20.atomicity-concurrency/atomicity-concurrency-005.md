# Unique Indexes Protecting Constraints Under Concurrent Requests in MongoDB

## 1. Real-world problem and goals

A website allows creating accounts by email, reserving a time slot, or registering a transaction code. With a single request, the program can read the database, verify the data does not yet exist, and then insert it. However, in a multi-user system, multiple requests can **read simultaneously** and all conclude that the key is available.

To enforce the rule **"no two distinct documents may share the same business key"**, MongoDB provides **unique indexes**. This constraint is enforced at the database layer when data is written, independent of any single application instance, process, or backend pod.

This lesson in the **Atomicity and Concurrency** chapter explains:

- The **time-of-check to time-of-use (TOCTOU)** race condition of the `findOne()` then `insertOne()` pattern.
- Creating single-field unique indexes and compound unique indexes with the exact business scope.
- How concurrent operations are blocked with duplicate key error `E11000`.
- Distinguishing single-document atomicity, unique indexes, and multi-document transactions.
- Concurrent upserts, `$setOnInsert`, retry handling, and idempotency keys.
- Partial unique indexes for active records, sparse/partial indexes, null/missing fields, collation, and multikeys.
- Limitations with sharding, migrations, and multi-writer testing.

**Core principle:** Application-layer checks can help surface early user messages, but **never replace a unique index** when uniqueness must hold under concurrent load.

## 2. Race condition: why is "check then write" unsafe?

Consider an account-creation endpoint:

~~~javascript
async function registerUser(users, emailKey) {
  const found = await users.findOne({ emailKey });

  if (found) {
    throw new Error("Email already exists");
  }

  return users.insertOne({
    emailKey,
    createdAt: new Date()
  });
}
~~~

The two commands `findOne()` and `insertOne()` **are not a single atomic operation**. They can interleave with operations from another client.

~~~text
Time             Request A                       Request B
-----------------------------------------------------------------
T1               findOne(email = x)
T2               No document found
T3                                               findOne(email = x)
T4                                               No document found
T5               insertOne(email = x)
T6               Write succeeded
T7                                               insertOne(email = x)
T8                                               Can also succeed
                                                 if there is no
                                                 unique index
-----------------------------------------------------------------
Result: two accounts share the same email.
~~~

Even though A and B both called `findOne()` in steps T1–T4, the database has no constraint tying the subsequent writes together. That is a TOCTOU bug: data was **true at check time** yet may have **changed by use time**.

The measures below are **insufficient** when a system has multiple writers:

- Adding `sleep()` or random delays.
- Re-checking with `countDocuments()` right before inserting.
- Disabling a button in the frontend.
- A JavaScript mutex living only inside **one process** when running multiple pods.
- Assuming requests "never collide within the same millisecond."
- Starting a transaction and still relying only on not having seen a document on read.

MongoDB needs a mechanism that **evaluates the key on the write path**, not just a query observing prior state.

## 3. What does a unique index do at write time?

Basic syntax:

~~~javascript
db.users.createIndex(
  { emailKey: 1 },
  { unique: true }
);
~~~

MongoDB does not allow two distinct documents within the index scope to store the same `emailKey` value. If two nearly simultaneous requests insert the same key, **both cannot be accepted with duplicate keys** once the unique index is built and enforced.

One request succeeds, while the other receives an error:

~~~text
E11000 duplicate key error ... index: ...
~~~

The standard error code is **11000**. Which specific request succeeds or fails depends on execution order; do not assume a particular request will win.

Comparison:

| Scenario | Without a unique index | With an appropriate unique index |
| --- | --- | --- |
| Two inserts with the same key | Both can succeed | At most one duplicate key is accepted |
| Two upserts with the same key | Can create two documents | Cannot create two duplicate documents; one may update or error |
| Update giving two documents the same email | Can create duplicate data | Update violating uniqueness is rejected |
| Script importing duplicate data | Can import duplicates | Index blocks violating documents |
| Two different services writing concurrently | Application logic may be unsynchronized | Constraint remains enforced at the database |
| Whether `find` uses the index | No effect on duplicate prevention | Unique constraint is still enforced on write |

A **regular index** on `{emailKey:1}` speeds up lookups; only with `unique: true` does it define a uniqueness constraint.

## 4. Preparing the practice database and first index

Open `mongosh`; the following commands are for a dedicated database only. Never run `drop()` on production collections.

~~~javascript
const lab = db.getSiblingDB("mongo_unique_concurrency_lab");

lab.accounts.drop();
lab.claims.drop();
lab.optionalCodes.drop();
lab.partialCodes.drop();
lab.reservations.drop();
lab.caseInsensitive.drop();
lab.aliases.drop();
lab.legacyUsers.drop();

lab.accounts.createIndex(
  { tenantId: 1, emailKey: 1 },
  {
    unique: true,
    name: "uq_tenant_email"
  }
);

lab.accounts.getIndexes();
~~~

The definition above protects **the key pair `(tenantId, emailKey)`**. Insert the first account:

~~~javascript
lab.accounts.insertOne({
  _id: "account-a",
  tenantId: "tenant-1",
  email: "An@Example.com",
  emailKey: "an@example.com",
  displayName: "An",
  createdAt: new Date()
});
~~~

Try inserting the same emailKey, same tenant, but a different `_id`:

~~~javascript
try {
  lab.accounts.insertOne({
    _id: "account-b",
    tenantId: "tenant-1",
    email: "AN@example.com",
    emailKey: "an@example.com",
    displayName: "Another An",
    createdAt: new Date()
  });
} catch (err) {
  print("errorCode = " + err.code);
  print(err.message);
}
~~~

MongoDB returns a duplicate key error with `code: 11000`. `account-b` is not inserted.

Yet the same email in a different tenant remains valid:

~~~javascript
lab.accounts.insertOne({
  _id: "account-c",
  tenantId: "tenant-2",
  email: "an@example.com",
  emailKey: "an@example.com",
  displayName: "An from tenant 2",
  createdAt: new Date()
});

lab.accounts.find(
  { emailKey: "an@example.com" },
  { _id: 1, tenantId: 1, emailKey: 1 }
).sort({ tenantId: 1 });
~~~

Two accounts are stored successfully: one in `tenant-1` and one in `tenant-2`. This is the **expected behavior** of a compound unique index, not a bug.

## 5. Simulating two competing writers with mongosh

Create an independent unique key:

~~~javascript
lab.claims.createIndex(
  { claimKey: 1 },
  { unique: true, name: "uq_claim_key" }
);
~~~

Open two `mongosh` windows connected to the same lab database. Both read:

~~~javascript
const lab = db.getSiblingDB("mongo_unique_concurrency_lab");

lab.claims.findOne({ claimKey: "seat-101" });
// null when not yet present.
~~~

Suppose both windows see null. Next:

**Session A:**

~~~javascript
lab.claims.insertOne({
  _id: "claim-A",
  claimKey: "seat-101",
  requestedBy: "A"
});
~~~

**Session B:**

~~~javascript
lab.claims.insertOne({
  _id: "claim-B",
  claimKey: "seat-101",
  requestedBy: "B"
});
~~~

When the inserts have distinct `_id` values yet the same `claimKey`, **only one insert can be accepted** and the other receives a duplicate key error. There is no guarantee whether A or B wins.

Verify:

~~~javascript
lab.claims.countDocuments({ claimKey: "seat-101" });
// 1 when one write succeeded and still exists.
~~~

The experiment demonstrates that **both sessions reading null is not a problem** as long as all writes pass through an appropriate unique constraint.

### 5.1. Concurrency test with the MongoDB Node.js Driver

This code runs in a Node.js application, **not `mongosh`**. It requires the `mongodb` package and a valid connection URI:

~~~javascript
const { MongoClient } = require("mongodb");

async function main() {
  const client = new MongoClient(
    process.env.MONGODB_URI ?? "mongodb://127.0.0.1:27017"
  );

  try {
    await client.connect();

    const c = client
      .db("mongo_unique_concurrency_lab")
      .collection("concurrentTrials");

    // Delete only data for this experiment.
    await c.deleteMany({ claimKey: "race-217" });

    await c.createIndex(
      { claimKey: 1 },
      { unique: true, name: "uq_trial_claim" }
    );

    const requests = Array.from(
      { length: 20 },
      (_, i) => c.insertOne({
        _id: "trial-" + i,
        claimKey: "race-217",
        requester: i
      })
    );

    const results = await Promise.allSettled(requests);

    const ok = results.filter(
      r => r.status === "fulfilled"
    ).length;

    const duplicates = results.filter(
      r => r.status === "rejected" && r.reason?.code === 11000
    ).length;

    const others = results.filter(
      r => r.status === "rejected" && r.reason?.code !== 11000
    ).length;

    console.log({
      ok,
      duplicates,
      others,
      stored: await c.countDocuments({ claimKey: "race-217" })
    });
  } finally {
    await client.close();
  }
}

main().catch(err => {
  console.error(err);
  process.exitCode = 1;
});
~~~

When the experiment runs standalone, the index exists, and there are no network/permission errors, the expected output is:

~~~text
ok:         1
duplicates: 19
others:     0
stored:     1
~~~

Using `Promise.allSettled()` collects **all 20 outcomes**, rather than short-circuiting on the first rejection like `Promise.all()`. Because the documents have distinct `_id` values, this test specifically targets the uniqueness of `claimKey`. Running multiple copies of **the same test** concurrently can introduce `_id` collisions and muddle the numbers; isolate each test run.

## 6. Which operations are checked by a unique index?

Unique constraints are not checked only on `insertOne()`:

| Operation | What is checked |
| --- | --- |
| `insertOne()` | Does the new document create a duplicate index key? |
| `insertMany()` / `bulkWrite()` | Does each write violate the index? |
| `updateOne()` | Does the new key value collide with another document? |
| `updateMany()` | Do the updated documents still satisfy uniqueness? |
| `replaceOne()` | Does the replacement document create a duplicate key? |
| `findOneAndUpdate()` | Does the update/upsert violate the constraint? |
| `updateOne(..., {upsert:true})` | Does the inserted or updated document create a duplicate key? |
| Writes inside a transaction | Constraints are still enforced; transactions do not bypass unique indexes |

Try updating `account-c` from tenant-2 to tenant-1 while keeping emailKey:

~~~javascript
try {
  lab.accounts.updateOne(
    { _id: "account-c" },
    { $set: { tenantId: "tenant-1" } }
  );
} catch (err) {
  print(err.code); // 11000.
}
~~~

The update is rejected because after changing tenant, the key pair would collide with `account-a`.

**Document-level atomicity** ensures changes to a single document execute atomically; it **does not enforce invariants involving two distinct documents**. A unique index complements it by enforcing constraints **across documents**.

## 7. E11000: recognizing and responding properly

The error message typically looks like:

~~~text
E11000 duplicate key error collection: ...
index: uq_tenant_email dup key: ...
~~~

This is illustrative; exact formatting varies by driver, server, and index.

Keep in mind:

1. `code: 11000` is commonly used to detect duplicate key errors.
2. The error can come from **any unique index**, including `_id_`, not necessarily the email index.
3. Some drivers expose `keyPattern`, `keyValue`, or the index name, but do not assume every environment provides the exact same structure.
4. `E11000` is not an error to retry endlessly with the same data when the key still conflicts.
5. `E11000` **does not prove** that an earlier business request succeeded completely.

### 7.1. Catching the error in code

~~~javascript
try {
  lab.accounts.insertOne({
    _id: "another-account",
    tenantId: "tenant-1",
    emailKey: "an@example.com"
  });
} catch (err) {
  if (err.code === 11000) {
    print("Unique key conflict");
  } else {
    throw err; // Do not swallow network/validation/authorization errors.
  }
}
~~~

**Never forward raw errors or stack traces verbatim** to API clients, as they can leak collection names, index names, personal keys, or implementation details.

### 7.2. Creation REST APIs typically return 409

~~~javascript
async function createAccount(accounts, request) {
  const emailKey = request.email.trim().toLowerCase();

  try {
    const result = await accounts.insertOne({
      tenantId: request.tenantId,
      email: request.email,
      emailKey,
      displayName: request.displayName,
      createdAt: new Date()
    });

    return {
      status: 201,
      body: { id: String(result.insertedId) }
    };
  } catch (err) {
    if (err?.code === 11000) {
      return {
        status: 409,
        body: { code: "ACCOUNT_ALREADY_EXISTS" }
      };
    }
    throw err;
  }
}
~~~

In production APIs, inspect **which index caused the conflict** if a collection has multiple unique indexes. The snippet above illustrates a concise business response, not full middleware classifying every duplicate case.

### 7.3. Do not treat E11000 as automatic idempotent success

If a new request reuses the same key with a **different payload**, `E11000` does not mean the caller got the same outcome. Especially for payments, bookings, and orders, check the key, request contents, persisted state, and retry/idempotency rules before returning a response.

## 8. Compound unique indexes: defining the exact scope

Single-field index:

~~~javascript
db.users.createIndex(
  { emailKey: 1 },
  { unique: true }
);
~~~

Enforces unique emailKey across the entire collection.

Multi-field index:

~~~javascript
db.users.createIndex(
  { tenantId: 1, emailKey: 1 },
  { unique: true }
);
~~~

Enforces a unique **pair**.

| tenantId | emailKey | Outcome with compound unique |
| --- | --- | --- |
| t1 | an@example.com | Valid if not yet present |
| t1 | an@example.com | **Rejected** if pair already exists |
| t2 | an@example.com | Valid because tenant differs |
| t1 | binh@example.com | Valid because email differs |

A three-field index such as:

~~~javascript
db.inventory.createIndex(
  { tenantId: 1, warehouseId: 1, serialKey: 1 },
  { unique: true }
);
~~~

only protects **the triple**. It does not enforce that serialKey is unique across all warehouses.

Key questions before choosing an index:

- Does a user register an email unique **across the whole app** or **within a tenant**?
- Is an order code unique **within a shop** or **across the whole platform**?
- Is a seat held **per show** or regardless of show?
- Should cancelled or soft-deleted records continue occupying a slot in the unique index?
- Are the fields forming the key always present and of the right BSON type?

A compound index can also support matching query filters, though **query performance** and **write-time uniqueness constraints** are separate concerns.

## 9. Key normalization and collation

### 9.1. A unique index does not know your application's email rules

If an index uses the simple collation, these two strings are **two distinct keys**:

~~~text
An@Example.com
an@example.com
~~~

If the application considers them the same logical email, define that equivalence before creating the index.

### 9.2. Storing a normalized field

Recommended design:

~~~javascript
{
  email: "An@Example.com",
  emailKey: "an@example.com"
}
~~~

All write paths must apply the same rule to compute `emailKey`. `trim().toLowerCase()` illustrates typical ASCII email handling, while internationalized emails require a complete normalization policy. Do not strip dots or `+` suffixes based on one provider's rules and apply that blindly to every email address.

Index on `emailKey`:

~~~javascript
db.users.createIndex(
  { tenantId: 1, emailKey: 1 },
  { unique: true }
);
~~~

### 9.3. Using a unique index with collation

If you want to preserve the original string while comparing **case-insensitively**:

~~~javascript
lab.caseInsensitive.createIndex(
  { email: 1 },
  {
    unique: true,
    name: "uq_email_case_insensitive",
    collation: {
      locale: "en",
      strength: 2
    }
  }
);

lab.caseInsensitive.insertOne({
  _id: 1,
  email: "An@Example.com"
});

try {
  lab.caseInsensitive.insertOne({
    _id: 2,
    email: "an@example.com"
  });
} catch (err) {
  print(err.code); // 11000.
}
~~~

With the chosen collation, strings differing only in case compare equal. For queries to use this collated index properly, specify a compatible collation:

~~~javascript
lab.caseInsensitive.find({
  email: "AN@example.com"
}).collation({
  locale: "en",
  strength: 2
});
~~~

Having a collated unique index does **not** mean queries omitting collation automatically match under those rules unless the collection itself is configured with that default collation. Sharded collections also impose additional collation restrictions on unique indexes.

## 10. Null and missing fields in unique indexes

MongoDB indexes `null` values and **missing** fields according to specific rules. For a **single-field** unique index, MongoDB allows at most **one document** with a null index entry (including missing fields or explicit null).

~~~javascript
lab.optionalCodes.createIndex(
  { externalCode: 1 },
  { unique: true, name: "uq_external_code" }
);

lab.optionalCodes.insertOne({
  _id: "missing-first"
});

try {
  lab.optionalCodes.insertOne({
    _id: "explicit-null",
    externalCode: null
  });
} catch (err) {
  print(err.code); // 11000.
}
~~~

The second document collides on the null index key with the first document.

With a compound unique index `{tenantId:1,emailKey:1}`:

~~~javascript
{ tenantId: "t1" } // indexed combination ("t1", null)
{ tenantId: "t2" } // indexed combination ("t2", null)
~~~

Two **distinct** pairs can coexist. However, two documents missing emailKey **within the same tenant** generate the same compound key and violate the constraint.

**Do not assume** that "compound unique always allows multiple missing fields" or "missing is always distinct from null." The constraint operates on **the entire indexed key combination**.

### 10.1. Required fields need validation

If `tenantId` and `emailKey` are mandatory, a unique index **is not enough** to enforce format/type:

~~~javascript
lab.runCommand({
  collMod: "accounts",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["tenantId", "emailKey"],
      properties: {
        tenantId: { bsonType: "string", minLength: 1 },
        emailKey: { bsonType: "string", minLength: 1 }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

This is an example for the lab. On real collections, inspect existing validators and legacy data before running `collMod`, so you do not inadvertently overwrite active schema rules.

## 11. Sparse unique and partial unique for optional fields

### 11.1. Sparse unique

~~~javascript
db.users.createIndex(
  { externalCode: 1 },
  {
    unique: true,
    sparse: true
  }
);
~~~

With a single-field sparse index:

- Documents **missing** `externalCode` are not indexed.
- Multiple documents missing the field can coexist.
- Documents **containing the field with value null** are still indexed.
- Two documents with the same string value are still blocked.

Thus sparse **does not mean** "ignore null."

### 11.2. Partial unique on strings

~~~javascript
lab.partialCodes.createIndex(
  { externalCode: 1 },
  {
    unique: true,
    name: "uq_external_string",
    partialFilterExpression: {
      externalCode: { $type: "string" }
    }
  }
);

lab.partialCodes.insertMany([
  { _id: "a" },
  { _id: "b", externalCode: null },
  { _id: "c", externalCode: null }
]);

lab.partialCodes.insertOne({
  _id: "d",
  externalCode: "CODE-01"
});

try {
  lab.partialCodes.insertOne({
    _id: "e",
    externalCode: "CODE-01"
  });
} catch (err) {
  print(err.code); // 11000.
}
~~~

A partial unique constraint applies only to documents matching `partialFilterExpression`. In this example, missing/null values fall outside the indexed set; two `"CODE-01"` strings compete for the same unique key.

**Note:** the empty string `""` still has type string; if business rules disallow empty strings, add checks/validation. A partial unique index only protects the subset selected by its filter.

## 12. Partial unique index for active bookings and soft deletes

A room-booking system wants:

- No two **active** bookings for the same room and time slot.
- Retain cancelled booking history.
- Allow re-booking the slot once an old booking is no longer active.

An unconditional unique index on `(roomId, startAt)` would hold keys even for cancelled bookings. Use a **partial unique index**:

~~~javascript
lab.reservations.createIndex(
  { roomId: 1, startAt: 1 },
  {
    unique: true,
    name: "uq_active_room_start",
    partialFilterExpression: { active: true }
  }
);
~~~

Insert the first booking:

~~~javascript
const slot = ISODate("2026-11-16T09:00:00Z");

lab.reservations.insertOne({
  _id: "booking-A",
  roomId: "R-01",
  startAt: slot,
  active: true,
  reservedBy: "An"
});
~~~

A second **active** booking for the same slot is blocked:

~~~javascript
try {
  lab.reservations.insertOne({
    _id: "booking-B",
    roomId: "R-01",
    startAt: slot,
    active: true,
    reservedBy: "Binh"
  });
} catch (err) {
  print(err.code); // 11000.
}
~~~

Cancelled bookings can be stored as history:

~~~javascript
lab.reservations.insertOne({
  _id: "booking-C",
  roomId: "R-01",
  startAt: slot,
  active: false,
  reservedBy: "Chi",
  cancelledAt: new Date()
});
~~~

Attempting to reactivate `booking-C` while `booking-A` is still active:

~~~javascript
try {
  lab.reservations.updateOne(
    { _id: "booking-C" },
    { $set: { active: true } }
  );
} catch (err) {
  print(err.code); // 11000.
}
~~~

**Updates that bring a document into the partial index subset are also checked for uniqueness.**

If booking A is cancelled:

~~~javascript
lab.reservations.updateOne(
  { _id: "booking-A", active: true },
  { $set: { active: false, cancelledAt: new Date() } }
);
~~~

then a new active booking for the same room/start can be added, provided no other writer claims the slot first.

### 12.1. Limitations of partial unique

- A writer that omits `active` or writes `active: "true"` instead of a boolean can **fall outside the filter**, unless blocked by schema validation.
- If states include `pending`, `confirmed`, and `cancelled`, define clearly which states hold the slot.
- A partial unique index only blocks **identical keys**, not **two overlapping time intervals**.

For instance, appointments `09:00–10:00` and `09:30–10:30` have different `startAt` timestamps. A unique index on `(roomId,startAt)` **does not enforce non-overlapping intervals**. You need discrete time-slot documents or appropriate coordination/transaction mechanisms.

### 12.2. Cancelling and re-allocating is a multi-step workflow

The index preserves the invariant "at most one active booking per slot," yet **does not guarantee** that cancelling, recording payments, updating schedules, and sending notifications all succeed as a single transaction. Separate **key constraints** from **business workflows**.

## 13. Multikey unique indexes: across documents, not within one array

Indexing an array field creates a **multikey index**. With `unique: true`, MongoDB prevents **different** documents from producing duplicate index keys. However, a single document may still contain duplicate elements **within its own array**.

~~~javascript
lab.aliases.createIndex(
  { aliases: 1 },
  { unique: true, name: "uq_aliases" }
);

lab.aliases.insertOne({
  _id: "doc-A",
  aliases: ["alpha", "alpha", "beta"]
});
~~~

The array repeats `"alpha"`, yet a multikey unique index does not consider that a cross-document violation.

~~~javascript
try {
  lab.aliases.insertOne({
    _id: "doc-B",
    aliases: ["beta", "gamma"]
  });
} catch (err) {
  print(err.code); // 11000: beta in doc-A.
}
~~~

To ensure **elements within the same array do not duplicate**, use validation or other logic, such as JSON Schema with `uniqueItems: true`:

~~~javascript
{
  $jsonSchema: {
    bsonType: "object",
    properties: {
      aliases: {
        bsonType: "array",
        items: { bsonType: "string" },
        uniqueItems: true
      }
    }
  }
}
~~~

`$addToSet` also helps prevent duplicates during certain array updates, though it does not replace a cross-document unique index or clean up arrays that already contain duplicates.

With **compound multikey** indexes, additional restrictions apply regarding multiple array fields in the same document; you cannot arbitrarily combine multiple arrays into an index and expect MongoDB to guard every combination.

## 14. Concurrent upserts: errors still need handling even with an index

`upsert: true` means: if the filter matches a document, update it; otherwise, attempt to insert a new document.

~~~javascript
const result = lab.accounts.updateOne(
  {
    tenantId: "tenant-1",
    emailKey: "binh@example.com"
  },
  {
    $setOnInsert: {
      email: "Binh@Example.com",
      displayName: "Binh",
      createdAt: new Date()
    }
  },
  { upsert: true }
);

printjson(result);
~~~

### 14.1. Without a unique index

Two upserts can both finish their lookup phase before any document exists and then both insert. `upsert: true` **does not enforce key uniqueness on its own**.

### 14.2. With an appropriate unique index

With `{tenantId:1,emailKey:1}, unique: true`, **two duplicate documents cannot both be accepted**. Under contention, another concurrent operation may:

- Update the document just inserted by another request.
- Receive `E11000`.
- Receive another error related to network/transaction conditions.

MongoDB documents specific conditions under which a racing upsert can update the newly inserted document: the filter uses one or more **equality predicates**, filter fields match the unique index key pattern, the operation is not a multi-update, and the update does not modify fields forming the unique key.

**Never promise that every concurrent upsert succeeds.** When additional state predicates are added to the filter, updating the newly inserted document may no longer apply.

### 14.3. Example filter prone to duplicate errors

~~~javascript
lab.accounts.updateOne(
  {
    tenantId: "tenant-1",
    emailKey: "binh@example.com",
    status: "pending"
  },
  {
    $setOnInsert: {
      displayName: "Binh",
      createdAt: new Date()
    }
  },
  { upsert: true }
);
~~~

If a document with the same tenant/email **already exists with a status other than pending**, the filter fails to match, so upsert tries to insert a new document with the same unique key and fails with `E11000`.

Good design separates:

1. **Identity key** protected by a unique index.
2. **State transition conditions** to update a specific document.
3. **Policy** when the document already exists in an unexpected state.

### 14.4. Interpreting upsert results

Common fields:

| Field | Meaning |
| --- | --- |
| `matchedCount` | Number of documents matched for update |
| `modifiedCount` | Number of documents whose data changed |
| `upsertedId` | Identifier of the newly inserted document |
| `acknowledged` | Whether the write was acknowledged per write concern |

`modifiedCount: 0` does not mean "no document": it may have matched without modifying any values. In application code, interpret fields per your driver API specification.

## 15. Unique indexes and idempotency keys

Systems frequently receive **the same request again** due to network failures, gateway retries, double clicks, or message queue redelivery. For payments and order creation, the requirement is not merely "no duplicate emails," but also that **one idempotency key must never spawn two independent workflows**.

### 15.1. Creating a unique claim

~~~javascript
lab.idempotencyClaims.drop();

lab.idempotencyClaims.createIndex(
  { tenantId: 1, operationKey: 1 },
  {
    unique: true,
    name: "uq_tenant_operation"
  }
);
~~~

When receiving a request:

~~~javascript
lab.idempotencyClaims.insertOne({
  tenantId: "tenant-1",
  operationKey: "checkout-001",
  payloadHash: "canonical-request-hash",
  state: "processing",
  createdAt: new Date()
});
~~~

If two workers both insert `(tenant-1,checkout-001)`, the unique index guarantees that two claims with the same key cannot both be accepted.

### 15.2. Handling an already-existing claim

~~~text
Receive request (tenantId, operationKey, payload)
           |
           v
Compute payloadHash from canonicalized request
           |
           v
Try INSERT claim with unique key
           |
           +-- Insert succeeds
           |     -> start business processing
           |     -> persist recoverable state/result
           |
           +-- E11000
                 -> read stored claim
                 |
                 +-- payloadHash differs
                 |     -> 409: same key, different request
                 |
                 +-- payloadHash matches, completed
                 |     -> return stored result (per contract)
                 |
                 +-- payloadHash matches, processing
                       -> report in-progress/pending or bounded retry
~~~

**Do not treat `E11000` as proof that the payment already finished**. The prior request may have only created the claim without calling the payment provider yet, or may be recovering from a crash.

### 15.3. Idempotency does not mean exactly-once for external systems

Suppose the workflow is:

1. Insert claim in MongoDB.
2. Send charge request to payment provider.
3. Update claim to `completed`.

If the process dies between steps 2 and 3, the claim stays `processing` even though the provider already charged. The unique index prevents creating **duplicate claims**, yet does not turn step 2 (an external system) into an atomic transaction with MongoDB.

Combine idempotency keys at the payment provider, outbox/inbox patterns, reconciliation, recoverable states, timeouts, and carefully designed retries. Do not expire claims too early: an old request resent after the claim is deleted would be treated as brand new.

TTL indexes can support retention per contract, but TTL deletion runs asynchronously; it is not a millisecond-accurate mechanism for releasing a "transaction lock."

## 16. Unique indexes, atomicity, and transactions are separate layers

MongoDB provides **single-document** atomicity for write operations. However, a rule like "no two documents share the same code" is a **cross-document constraint**. A unique index enforces that constraint via index keys.

| Mechanism | Primary guarantee | What it does not guarantee alone |
| --- | --- | --- |
| Atomic single-document update | No half-updated state on one document | Uniqueness across multiple documents without an index |
| Unique index | No duplicate keys within index scope | Arbitrary business invariants, multi-doc transactions |
| Multi-document transaction | Atomicity of the committed group of operations | Which business keys count as duplicates unless defined |
| Application pre-check | Early UX/validation | Race prevention under concurrent requests |
| Write concern | Write acknowledgment/replication level | Creating uniqueness constraints |
| Retryable writes | Driver/server retry support | Exactly-once external side effects outside DB |

### 16.1. Transactions do not replace unique indexes

Two transactions can both read "account for email x does not exist yet." Transaction/snapshot reads **must not be used as a substitute** for a unique constraint. When both try to write the same unique key, duplicate key or write conflict/transaction errors occur depending on scenario and execution order. The application must handle errors and abort/retry appropriately.

### 16.2. When is a transaction also needed?

For example, reserving a seat requires:

- Inserting a reservation into `reservations`.
- Decrementing available seats in `events`.
- Recording a payment record in `payments`.

A unique index on `(showId,seatCode)` blocks two reservations for the same seat, but does not ensure **all three writes across three documents/collections** commit or roll back together. If business rules require all-or-nothing, use a multi-document transaction on a supported topology, factoring in cost/limits and proper retry handling.

### 16.3. Constraints that unique indexes do not solve

| Requirement | Is a unique index enough? | Mechanism to consider |
| --- | --- | --- |
| One email per tenant | Yes, with the right key | Validation/normalization |
| One seat per show | Yes, with key and active condition | State/audit |
| Non-negative inventory | No | Conditional atomic update |
| Total bookings not exceeding capacity | Not sufficient alone | Counter/conditional write/transaction |
| No two bookings overlapping in time | Not via startAt alone | Slot model/serialization |
| All-or-nothing money transfer between two wallets | No | Transaction |
| At most one webhook claim per key | Yes for the claim step | Complete idempotency workflow |

Example of a proper single-document atomic stock deduction:

~~~javascript
db.inventory.updateOne(
  { _id: "SKU-101", stock: { $gte: 2 } },
  { $inc: { stock: -2 } }
);
~~~

The `stock >= 2` condition is attached to the write operation, avoiding read-stock-then-unconditional-overwrite. This is a **different problem** from duplicate keys, though part of the same concurrency domain.

## 17. Bulk writes and updateMany are not automatically atomic overall

For `insertMany()` with a unique index:

~~~javascript
// Illustrative: individual items can fail with duplicate errors.
db.users.insertMany(
  [
    { tenantId: "t1", emailKey: "a@example.com" },
    { tenantId: "t1", emailKey: "a@example.com" },
    { tenantId: "t1", emailKey: "b@example.com" }
  ],
  { ordered: false }
);
~~~

- `ordered: true` stops processing subsequent writes after the first error in order.
- `ordered: false` continues processing other items and reports a list of errors.
- Neither rolls back the entire batch by default when one document duplicates.

For `updateMany()`:

~~~javascript
// DO NOT RUN on data you want to keep.
// May alter some documents' keys before hitting a duplicate.
db.users.updateMany(
  { tenantId: "t1" },
  { $set: { emailKey: "shared@example.com" } }
);
~~~

Each updated document must still satisfy the unique constraint, yet `updateMany` **is not by default an atomic transaction across all documents**. If one document updates before the next hits a duplicate, partial changes may persist.

When all operations must succeed or fail together, design a dedicated transaction or migration. Never assume an `E11000` error guarantees earlier operations in the bulk call modified nothing.

## 18. Replica sets, failover, write concern, and retries

### 18.1. Write concern is not uniqueness

On a replica set, `w: "majority"` requests write acknowledgment from a majority of members per deployment rules:

~~~javascript
lab.accounts.insertOne(
  {
    tenantId: "tenant-1",
    emailKey: "majority@example.com",
    displayName: "Majority Test"
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
~~~

This command illustrates write acknowledgment level; it **does not replace a unique index**. If `emailKey` duplicates, whether majority is used or not, the constraint must still be enforced.

### 18.2. Timeouts can leave the client unsure of write state

~~~text
Client sends insert
       |
       v
Server performs write
       |
       v
Network timeout before acknowledgment reaches client
       |
       v
Client is unsure whether the operation was persisted
~~~

If the application resends the same request itself:

- If the earlier document persisted, the retry hits `E11000`.
- If the earlier write did not execute or rolled back during failover, the retry can insert anew.
- Driver **retryable writes** have their own mechanism and eligibility conditions. Do not equate the driver mechanism with arbitrary business-level re-invocation.

Never treat `E11000` after a timeout as proof that **all side effects finished**; use idempotency keys, state reads, and reconciliation.

### 18.3. Building unique indexes on a replica set

Index builds follow synchronization/commit quorum rules. For certain rolling procedures creating a **unique index**, MongoDB requires stopping writes to the collection during the process. If writes cannot be stopped, use the supported index build method via the primary (replica set) or `mongos` (sharded cluster) per your version's documentation.

Never check a single node for an index and assume **the entire topology** is enforcing uniqueness as intended.

## 19. Sharded clusters: uniqueness tied to the shard key

On a sharded collection, MongoDB restricts unique indexes so constraints can be enforced across shards.

With **ranged sharding**, a unique index must either be the shard key index or have **the entire shard key as a prefix**. For example, a collection sharded by:

~~~javascript
{ tenantId: 1 }
~~~

Valid index for email uniqueness within a tenant:

~~~javascript
db.accounts.createIndex(
  { tenantId: 1, emailKey: 1 },
  { unique: true }
);
~~~

By contrast:

~~~javascript
// Lacks shard-key prefix; invalid for a collection
// sharded by { tenantId: 1 }.
db.accounts.createIndex(
  { emailKey: 1 },
  { unique: true }
);
~~~

An email can appear in multiple tenants. If an email must be **globally unique across the platform** despite multiple shards, design an appropriate shard key or a global unique registry/collection. You cannot simply drop `tenantId` from the index and expect the sharded cluster to allow it.

### 19.1. _id is not always cluster-wide unique

In a sharded collection where `_id` is not the shard key, `_id` uniqueness may only be enforced per shard. The application must ensure IDs are globally unique across the cluster in that setup.

### 19.2. Hashed indexes cannot be unique

~~~javascript
// Invalid: hashed indexes do not support unique.
db.accounts.createIndex(
  { tenantId: "hashed" },
  { unique: true }
);
~~~

When sharding on a hashed key, consult unique index rules for that topology; do not try adding `unique` to a hashed index.

### 19.3. Collation in sharded uniqueness

Sharded uniqueness also imposes collation restrictions; MongoDB guarantees uniqueness only under supported rules, notably **simple collation**. For case-insensitive emails, a more controllable approach is storing a normalized `emailKey` and using a unique index with a shard-key prefix and simple comparison, rather than assuming an arbitrary collated unique index works globally.

## 20. Rolling out a unique index on an existing collection

A unique index build cannot succeed if the collection **currently holds documents with duplicate index keys**. This is a migration problem, not just running a DDL statement.

### 20.1. Finding duplicates before creating the index

~~~javascript
db.accounts.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        emailKey: "$emailKey"
      },
      count: { $sum: 1 },
      exampleId: { $first: "$_id" }
    }
  },
  { $match: { count: { $gt: 1 } } },
  { $sort: { count: -1 } },
  { $limit: 20 }
]);
~~~

This pipeline groups by **the exact compound key** intended for uniqueness. Without a normalized field, emails differing in case will not group together automatically. Standardize the normalization policy and backfill first.

Do not default to `$push: "$_id"` to collect **every ID** in duplicate groups on huge collections: arrays can grow too large and trigger memory/BSON errors. Start with counts and a sample ID to scope the cleanup.

### 20.2. Controlled rollout plan

1. Define uniqueness scope: global, per-tenant, or active-only.
2. Normalize keys, verify BSON types, and handle null/missing fields.
3. Detect and resolve historical duplicates per merge/retire/audit policy.
4. Ensure **no writer continues introducing duplicates** during the transition window. You may need to pause affected writes or route traffic through a controlled path.
5. Create the unique index using the topology-appropriate command/procedure and wait for the build to complete.
6. Verify `getIndexes()`, build status, and test duplicate-write rejections in staging.
7. Add schema validation if key fields must always be present.
8. Update all services, background jobs, and import scripts to produce the exact same normalized keys.
9. Monitor `E11000`, write latency, index size, and post-rollout errors.

**Rollout-window race:** Checking for duplicates at 10:00 and creating the index at 10:05 is not enough if writers can still insert duplicates during those five minutes. Until the unique index finishes building, the constraint is not yet fully enforced.

### 20.3. Do not attempt to convert a regular index to unique in-place

If a non-unique compound index already exists, calling `createIndex()` again with different options **should not be relied upon to turn it into unique across versions**. MongoDB has specific procedures for converting an existing index to unique or creating the right index after resolving duplicates.

In particular, **never drop an active unique index enforcing a rule while writes continue** without a replacement mechanism in place. That opens a window allowing duplicate data.

## 21. Performance, operations, and monitoring

A unique index adds maintenance cost whenever insert/update/delete alters key values: additional index entries, disk/cache footprint, and index build work. However, if uniqueness is a mandatory invariant, do not drop the constraint just to boost throughput.

A compound unique index can also speed up lookups:

~~~javascript
lab.accounts.find({
  tenantId: "tenant-1",
  emailKey: "an@example.com"
}).explain("executionStats");
~~~

Still, **whether the query planner uses `IXSCAN` does not determine whether MongoDB enforces the unique constraint on writes**. `explain()` inspects read paths; index definitions and duplicate-write tests verify the constraint.

Inspect metadata:

~~~javascript
lab.accounts.getIndexes().filter(
  idx => idx.name === "uq_tenant_email"
);
~~~

Metrics to observe in production:

- `E11000` error count by index/operation/tenant (mask sensitive data).
- Retry rate after timeouts.
- Requests sharing the same idempotency key.
- Index build duration, write overhead, and index storage size.
- Key collision rates in imports/batches.
- Unexpected `E11000` errors due to null/missing fields or mismatched normalization across services.

A small number of duplicate errors when users resubmit the same request can be normal. A sudden spike can signal **a retry bug**, integration error, normalization mismatch, or incomplete migration.

## 22. Common mistakes and misconceptions

| Misconception | Consequence | Fix |
| --- | --- | --- |
| `findOne` then `insertOne` prevents duplicates | TOCTOU when two writers run concurrently | Database-level unique index |
| An in-memory lock on one pod suffices | Multiple pods do not share the mutex | Shared constraint in the database |
| A standard unique index compares emails case-insensitively | Can store mixed-case duplicates | Normalized emailKey or proper collation |
| Global unique email when only per-tenant is needed | Incorrectly blocks other tenants | Compound unique scoped by tenant |
| Per-tenant compound unique when global email is needed | Allows duplicates across tenants | Global key/registry design |
| Nullable field with a single-field unique index | Duplicate null/missing collision | Validation or proper sparse/partial filter |
| Sparse unique automatically ignores null | Null values can still be indexed | Use partial type filter |
| Partial unique blocks all documents | Documents outside partialFilterExpression can duplicate | Define active filter accurately |
| Unique index on startAt prevents interval overlap | Two intervals with different starts can overlap | Slot model or coordination |
| Returning success on E11000 | May be a request with a different payload | Compare key, payloadHash, and state |
| Catching all errors as duplicates | Masks network/permission/validation errors | Handle only code 11000 specifically |
| Concurrent upserts always auto-update | Can still receive E11000 | Exact unique key, proper error path |
| updateMany rolls back the whole batch on error | Partial updates may persist | Transaction if all-or-nothing needed |
| Unique multikey forbids duplicates inside one array | Does not prevent intra-array duplicates | uniqueItems validator or app logic |
| Transaction replaces unique index | Does not define which keys must be unique | Keep the unique constraint |
| Majority write concern creates uniqueness | Confuses durability with constraints | Use both for their respective goals |
| Sharded collections always enforce global _id uniqueness | Limited when _id is not the shard key | Generate globally unique IDs by design |
| Building index already protects writes | Build may not have finished | Control writers and verify rollout |
| Retrying E11000 forever will eventually succeed | Key still collides, increases load | Return conflict/idempotency-aware response |

## 23. Practice exercises

### Exercise 1 — Reproducing TOCTOU

Two requests call `findOne({emailKey:"x"})`, both observe null, and then both call `insertOne`. Draw their interleaved timeline. Without a unique index, what can happen? With the index present, what error does the losing writer receive?

**Answer:** Without an index, two duplicate documents can be created; with a unique index, duplicate writes cannot both be accepted and the racing operation hits `E11000`.

### Exercise 2 — Tenant-scoped index

An application requires username to be unique **within each tenant**, while different tenants may share the same username. Write the index:

~~~javascript
db.users.createIndex(
  { tenantId: 1, usernameKey: 1 },
  { unique: true, name: "uq_tenant_username" }
);
~~~

Explain why an index on `usernameKey` alone violates the business scope.

### Exercise 3 — Rejected update changing a key

In `lab.accounts`, create a new account in tenant-1 with a different emailKey, then try updating it to `an@example.com`. Explain why this fails even though `_id` differs.

### Exercise 4 — Null and missing

Create a single-field unique index on `externalCode`. Insert a document missing the field, a document with `externalCode: null`, and a document with `externalCode: "A"`. Which document is rejected? If multiple documents should omit the code, what index design fits?

**Guided answer:** missing and null both produce colliding null keys; sparse unique skips missing fields, while partial with `$type:"string"` excludes both missing and null from scope.

### Exercise 5 — Active bookings

Create a partial unique index `{roomId:1,startAt:1}` with `partialFilterExpression:{active:true}`. Test two colliding active bookings, one colliding inactive booking, and then updating the inactive one to active. Describe which steps trigger `E11000`.

### Exercise 6 — Overlapping booking intervals

Two schedules `09:00–10:00` and `09:30–10:30` have different start times. Does a unique index on `startAt` detect the overlap? Propose a slot model or suitable coordination solution.

### Exercise 7 — Competing upserts

Two workers concurrently invoke:

~~~javascript
db.users.updateOne(
  { tenantId: "t1", usernameKey: "an" },
  { $setOnInsert: { displayName: "An" } },
  { upsert: true }
);
~~~

Which unique index is required? Is it guaranteed that both writers succeed?

**Answer:** A unique index on the tenantId/usernameKey pair; at most one document per key. Another writer may update or receive E11000 depending on conditions; both are not guaranteed to succeed.

### Exercise 8 — Idempotency key with differing payloads

A client sends two requests with the same key but different payloadHashes. The second request hits a duplicate. Should you return "already paid" or `409 Conflict`? Why?

**Answer:** Read the stored claim and compare payloads; if they differ, return a conflict rather than treating the duplicate as success.

### Exercise 9 — Multi-document update

An `updateMany()` sets emailKey across multiple documents to the same string. If a unique error occurs midway, does the entire operation automatically roll back?

**Answer:** Not by default; multiple documents do not form a transaction. To get all-or-nothing, design an appropriate transaction.

### Exercise 10 — Unique on arrays

Create a unique index `{aliases:1}`. Why is `["a","a"]` accepted within one document, while a second document with `["a","b"]` is rejected?

**Answer:** Multikey unique checks duplicate keys **across documents**; it does not enforce uniqueness among elements of the same document's array.

### Exercise 11 — Sharding

Collection `accounts` is sharded by `tenantId`. Among these three indexes, which satisfies the shard-key prefix rule and can be unique accordingly?

~~~javascript
{ emailKey: 1 }
{ tenantId: 1, emailKey: 1 }
{ tenantId: "hashed" }
~~~

**Answer:** The compound index with tenantId prefix; an index on emailKey alone is invalid for uniqueness on a tenant-sharded ranged collection; hashed indexes do not support unique.

### Exercise 12 — Rolling out on existing data

A collection contains:

~~~javascript
{ _id: 1, tenantId: "t1", email: "An@Example.com" }
{ _id: 2, tenantId: "t1", email: "an@example.com" }
~~~

Outline the order of normalizing emailKey, finding duplicates, cleaning data, controlling writers, creating the unique index, and load-testing concurrency. Why does scanning for duplicates at 10:00 not guarantee an index build at 10:05 succeeds if writers are still active?

### Exercise 13 — Concurrency test

Run the Node.js experiment with 20 `insertOne` calls having distinct `_id`s but the same claimKey. Record successful requests, `E11000` count, and actual stored count. Why is `Promise.allSettled()` more convenient than `Promise.all()` for this test?

### Exercise 14 — Distinguishing constraints from replication

Explain the independent roles of `unique: true` and `writeConcern: { w: "majority" }`. Which defines "no two documents may share an email," and which defines write acknowledgment level?

### Exercise 15 — Designing a production endpoint

Design `POST /reservations` with requirements: one active booking per room/slot, cancellation history preserved, multiple pods receiving concurrent requests, idempotency key support, and no raw MongoDB error leaks. Specify:

- Compound partial unique index protecting the slot.
- Validation ensuring key fields and active have proper types.
- Claim/idempotency flow and E11000 handling.
- Handling payment side effects and timeouts.
- When a multi-document transaction is needed.
- Concurrent writers test scenario.

## 24. Summary

**A unique index is a write-time constraint**, making it essential whenever concurrent requests try to create or update the same business key.

Ten things to remember:

1. **Pre-checks do not prevent TOCTOU**; define a real unique index in the database.
2. **Keys must match the exact scope:** single-field, compound, per-tenant, or active-only.
3. **E11000 is a duplicate key conflict**, not automatic proof that an earlier business request finished.
4. **Upserts still race without an index**; even with an index, racing requests can still error.
5. **Null/missing, sparse, partial, multikey, and collation** each have distinct rules to specify clearly.
6. **Schema validation and key normalization** complement a unique index rather than replacing it.
7. **Document-level atomicity differs from cross-document uniqueness**, and multi-document transactions are a separate guarantee layer.
8. **Idempotency is an entire workflow**: unique claim, payloadHash, state tracking, and crash/timeout recovery.
9. **Sharded clusters have limits**: unique indexes must respect shard keys, and hashed indexes cannot be unique.
10. **Migrations must control writers during index builds**; prior duplicate checks do not guarantee data stays clean until the build finishes.

### Official MongoDB documentation

- [Unique Indexes and Duplicate Values](https://www.mongodb.com/docs/manual/core/index-unique/) — unique, compound, null/missing, and multikey rules.
- [db.collection.createIndex()](https://www.mongodb.com/docs/manual/reference/method/db.collection.createIndex/) — syntax and unique option.
- [Upsert with Duplicate Values](https://www.mongodb.com/docs/manual/reference/method/db.collection.update/#upsert-with-duplicate-values) — possible outcomes under racing upserts.
- [db.collection.updateOne()](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateOne/) — update, upsert, and write concern.
- [Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/) — partialFilterExpression scope and unique partial indexes.
- [Sparse Indexes](https://www.mongodb.com/docs/manual/core/index-sparse/) — handling missing fields.
- [Collation](https://www.mongodb.com/docs/manual/reference/collation/) — string and case-sensitivity comparisons.
- [Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/) — uniqueness on array fields.
- [Maintain Uniqueness in Sharded Clusters](https://www.mongodb.com/docs/manual/tutorial/maintain-uniqueness-in-sharded-clusters/) — shard-key prefix and restrictions.
- [Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/) — document-level atomicity.
- [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — multi-document transactions.
- [Schema Validation with JSON Schema](https://www.mongodb.com/docs/manual/core/schema-validation/specify-json-schema/) — enforcing proper field types.
- [Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — driver-level retries.
