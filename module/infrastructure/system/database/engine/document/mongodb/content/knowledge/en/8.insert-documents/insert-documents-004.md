# Duplicate Key Errors, Validation Errors, and Partial Success Results

## 1. Context: Writing Multiple Documents Is Not Equivalent to a Transaction

When inserting documents into MongoDB, an operation can fail because data violates a **unique index** constraint, fails **schema validation**, or because the system cannot acknowledge the write result as requested. If an application is importing multiple documents via `insertMany()` or `bulkWrite()`, **some documents may have been successfully written before or concurrently with other errors**.

For example, an import batch of five customers contains three valid profiles, one existing email, and one age violating a rule. What matters is not only recognizing "the batch had an error," but determining:

- Which documents were definitely written, and which were rejected?
- Did MongoDB stop immediately at the first error or continue attempting other items?
- Was the error due to data constraint violations or the system failing to acknowledge the operation?
- Can the entire batch be resent or must reconciliation happen first?
- When the business requires all items to succeed together, what mechanism is needed?

This lesson uses `mongosh` to illustrate server-side rules and the **MongoDB Java Sync Driver** to illustrate application-side Java error handling. Exact exception/response structure details can vary by driver and version; do not write logic by parsing verbatim error message strings.

### 1.1. Common Operations

| Operation | Purpose | On Error |
| --- | --- | --- |
| `insertOne(document)` | Insert a single document. | That document may be rejected; if acknowledged as successful, this operation wrote one document. |
| `insertMany(documents)` | Insert multiple documents into the same collection. | Outside a transaction, successful elements **do not automatically roll back** when another element fails. |
| `bulkWrite(operations)` | Combine insert, update, replace, and delete in bulk mode. | Can partially succeed; must distinguish operation types and corresponding results. |
| Multi-document transaction | Create a transaction boundary for multiple operations. | If the transaction aborts, transaction changes are not committed; successful/ambiguous commits must be handled per transaction semantics. |

**Atomicity of a single write on a single document** does not make a multi-document `insertMany()` batch atomic as a whole. The `ordered` option controls how processing continues after an error, not turning the batch into a transaction.

## 2. Duplicate Key Error: Duplicate Key (E11000)

MongoDB uses a **unique index** to prevent duplicate key values across documents. Every regular collection has a unique index on the `_id` field. Applications can also create unique indexes for business keys such as customer codes, order codes, or emails per tenant.

When an operation violates a unique index, MongoDB typically returns **error code 11000**, accompanied by a message containing `E11000 duplicate key error`.

### 2.1. Duplicate `_id`

~~~javascript
db.accounts.insertOne({
  _id: "ACC-100",
  owner: "Lan",
  status: "ACTIVE"
});

// Attempt to add another document with the same _id:
db.accounts.insertOne({
  _id: "ACC-100",
  owner: "Minh",
  status: "ACTIVE"
});
~~~

The second command is rejected because `_id: "ACC-100"` already exists. The original document remains intact. A duplicate error does not mean MongoDB automatically overwrites the old record; `insert` has **create new** semantics, whereas modifying an existing document requires an appropriate update operation.

The message may look similar to:

~~~text
E11000 duplicate key error collection: demo.accounts
index: _id_ dup key: { _id: "ACC-100" }
~~~

Do not depend on the exact wording/formatting of the message. When handling automatically, prioritize **error code 11000**, index metadata, and pre-assigned business identifiers.

### 2.2. Duplicate on a Non-`_id` Unique Index

~~~javascript
db.accounts.createIndex(
  { externalCode: 1 },
  { unique: true, name: "uk_external_code" }
);

db.accounts.insertOne({
  _id: "A-01",
  externalCode: "EXT-778",
  owner: "Lan"
});

db.accounts.insertOne({
  _id: "A-02",
  externalCode: "EXT-778",
  owner: "Minh"
});
// E11000 on uk_external_code
~~~

Two documents have different `_id`s yet share the same `externalCode`. The error is caught by the unique index on the business field. **Having distinct `_id` values does not guarantee the entire document is valid against other indexes**.

### 2.3. Multi-Field Uniqueness

In a multi-tenant system, emails might only need to be unique **within the same tenant**:

~~~javascript
db.customers.createIndex(
  { tenantId: 1, emailNormalized: 1 },
  { unique: true, name: "uk_tenant_email" }
);

db.customers.insertOne({
  _id: "C-1",
  tenantId: "T1",
  emailNormalized: "an@example.com"
});

db.customers.insertOne({
  _id: "C-2",
  tenantId: "T2",
  emailNormalized: "an@example.com"
}); // Valid: different tenant

db.customers.insertOne({
  _id: "C-3",
  tenantId: "T1",
  emailNormalized: "an@example.com"
}); // E11000: duplicate tenant + email pair
~~~

This index enforces uniqueness of the **key combination**, without requiring every tenant to have different emails. Email normalization needs explicit business rules. Without normalization, default indexes are typically case-sensitive unless an appropriate collation is configured.

### 2.4. Missing or `null` Fields Also Need Attention

A standard unique index on **a single field** allows at most one document with an index entry of `null`; documents missing the field can also be indexed as `null`. Therefore:

~~~javascript
db.members.createIndex({ memberCode: 1 }, { unique: true });

db.members.insertOne({ _id: 1, displayName: "Lan" });
db.members.insertOne({ _id: 2, displayName: "Minh" });
// The second document can hit E11000:
// both are missing memberCode
~~~

If `memberCode` is optional and only string values need to be unique, you can design a **partial unique index**:

~~~javascript
db.members.createIndex(
  { memberCode: 1 },
  {
    unique: true,
    partialFilterExpression: {
      memberCode: { $type: "string" }
    }
  }
);
~~~

This example should be applied on an appropriate collection or after handling the old index, rather than arbitrarily creating overlapping indexes and expecting the new index to alter the old index's effect. A partial index only enforces the unique constraint within the subset of documents matching the filter. Check the schema if multiple types other than string exist.

**Note:** `sparse`, `partial`, unique compound indexes, and unique indexes on arrays each have their own rules. Do not generalize that "missing fields never cause collisions" or "every array element must be unique within a single document." The rules of a **unique multikey index** primarily handle key conflicts across documents and do not automatically replace validation disallowing duplicate elements within the same array.

### 2.5. Creating a Unique Index on Existing Data

If a collection already has two documents with the same code before creating a unique index, the index creation command can **fail during the build phase**. The proper workflow is to audit existing data, identify the canonical record, resolve duplicate data per business rules, and only then create the index.

Never "fix the error" by randomly deleting one of the two documents, especially if they involve transactions, ownership, or audit history.

## 3. Validation Error: Document Fails Collection Rules

Besides unique indexes, MongoDB has **collection schema validation**. Applications can use `$jsonSchema` to specify required fields, BSON types, minimum/maximum values, or other structural constraints.

When `validationAction: "error"` and a document is invalid, MongoDB typically rejects the write with **error code 121 — DocumentValidationFailure**.

### 3.1. Creating a Collection with a Validator

For example, a registrations collection requiring `email` to be a string and `age` to be a BSON integer of at least 18:

~~~javascript
db.createCollection("registrations", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["email", "age"],
      properties: {
        email: {
          bsonType: "string",
          minLength: 3,
          description: "email must be a non-empty string"
        },
        age: {
          bsonType: "int",
          minimum: 18,
          description: "age must be an integer >= 18"
        }
      }
    }
  },
  validationAction: "error",
  validationLevel: "strict"
});

db.registrations.createIndex(
  { email: 1 },
  { unique: true, name: "uk_registration_email" }
);
~~~

In this example there are **two independent constraint layers**:

- `$jsonSchema` validates structure and value domains (type `int`, minimum age 18).
- The unique index ensures no two documents share the same `email`.

The validator above only checks that email is a string of at least three characters; it does **not** validate full email syntax or case normalization. If those are business requirements, add appropriate validation in the application and/or collection.

### 3.2. Valid and Invalid Write Examples

~~~javascript
db.registrations.insertOne({
  _id: "R-001",
  email: "an@example.com",
  age: NumberInt(22)
}); // Success

db.registrations.insertOne({
  _id: "R-002",
  email: "binh@example.com",
  age: NumberInt(16)
}); // Error 121: age is less than 18

db.registrations.insertOne({
  _id: "R-003",
  email: "chi@example.com",
  age: "22"
}); // Error 121: age is a string, not a BSON int

db.registrations.insertOne({
  _id: "R-004",
  email: "an@example.com",
  age: NumberInt(23)
}); // Error 11000: duplicate email
~~~

The fact that a document carries a value appearing to a user as "22" **does not mean its BSON type is right**. With a validator requiring `bsonType: "int"`, the string value `"22"` will fail. In Java, `Integer` is typically encoded as BSON Int32; `Long` as Int64. If the business accepts both, the schema must accurately list the permitted types.

### 3.3. Validation on Insert and on Update

Validation does not happen only during creation. With `validationLevel: "strict"` and `validationAction: "error"`, an update that turns a valid document into an invalid one is also rejected:

~~~javascript
db.registrations.updateOne(
  { _id: "R-001" },
  { $set: { age: NumberInt(17) } }
);
// Error 121; original document unchanged because update failed
~~~

When using replace, be careful because replacing the entire document can accidentally omit required fields, causing a validation error even if the remaining values are valid.

### 3.4. `validationAction` and `validationLevel`

| Setting | Meaning |
| --- | --- |
| `validationAction: "error"` | Rejects writes if the document violates the validator; this is the default behavior. |
| `validationAction: "warn"` | Allows writing invalid documents while logging a warning; does not produce validator write error 121. |
| `validationAction: "errorAndLog"` | Rejects and logs the error; available starting in MongoDB 8.1. |
| `validationLevel: "strict"` | Validates all inserts/updates against the validator; this is the default level. |
| `validationLevel: "moderate"` | Validates inserts and updates on currently valid documents; does not enforce rules for updates on legacy documents that were already invalid. |
| `validationLevel: "off"` | Disables collection validation. |

Additional options can vary by MongoDB version. When operating a specific version, read that version's documentation, especially before using newer values.

A collection with `warn` can contain schema-violating documents **while inserts still report success**. When investigating data quality bugs, inspect the validator configuration rather than assuming "having a schema means MongoDB blocked all bad data."

### 3.5. Permission-Restricted Validation Bypass

Some APIs allow `bypassDocumentValidation` in appropriately authorized scenarios, such as controlled migrations. This option can bypass the **collection validator**, but **does not disable unique indexes** or BSON structural limits.

Do not use bypass as a default workaround for error 121. Doing so lets invalid data enter the system while other applications still assume every document matches the schema.

## 4. Reading the Result of a Successful Insert Command

In `mongosh`:

~~~javascript
const result = db.registrations.insertOne({
  _id: "R-010",
  email: "dung@example.com",
  age: NumberInt(28)
});

printjson(result);
~~~

When acknowledged according to the applied write concern, the result typically looks like:

~~~javascript
{
  acknowledged: true,
  insertedId: "R-010"
}
~~~

Meaning:

- `acknowledged` indicates whether write acknowledgement was used.
- `insertedId` is the identifier of the successfully inserted document.
- This result does not imply the application has completed all side-effect steps such as sending emails, publishing events, or updating external systems.

With `insertMany()`, full success typically returns `acknowledged` and the `insertedIds` collection. However, on error, the API may **throw an exception instead of returning a normal success object**; partial success details must be read from the result and error fields inside the exception per the driver's API.

## 5. Ordered Insert: The First Error Blocks Subsequent Items

By default, `insertMany()` uses `ordered: true`. Documents are processed in array order; when one document encounters a **write error**, subsequent documents are not attempted. Documents before the error that succeeded **are retained** if not inside an aborted transaction.

### 5.1. Illustrative Dataset

Assuming the collection and unique index were created as in Section 3; before running the batch, a single seed document is pre-inserted:

~~~javascript
db.registrations.insertOne({
  _id: "SEED",
  email: "existing@example.com",
  age: NumberInt(30)
});

const batch = [
  { _id: "B-1", email: "one@example.com", age: NumberInt(20) },
  { _id: "B-2", email: "existing@example.com", age: NumberInt(21) },
  { _id: "B-3", email: "three@example.com", age: NumberInt(16) },
  { _id: "B-4", email: "four@example.com", age: NumberInt(27) }
];
~~~

Among the four documents:

- `B-1` is valid.
- `B-2` violates the unique index because the email already exists in `SEED`.
- `B-3` violates the validator because 16 is less than 18.
- `B-4` is valid.

### 5.2. Executing in Order

~~~javascript
try {
  const result = db.registrations.insertMany(
    batch,
    { ordered: true }
  );
  printjson(result);
} catch (error) {
  print("Batch had an error:");
  print(error.message);
}
~~~

Starting from the exact state described above:

| Item | Behavior | Outcome |
| --- | --- | --- |
| `B-1` | Processed first; valid. | **Inserted**. |
| `B-2` | Duplicates `existing@example.com`. | **Rejected**, code 11000. |
| `B-3` | Positioned after the error. | **Not attempted**; no 121 error is reported for this item in that ordered run. |
| `B-4` | Positioned after the error. | **Not attempted** even though valid. |

This example highlights the difference between **attempted and failed** versus **not attempted**. You cannot treat every absent item as "invalid."

Verify saved state:

~~~javascript
db.registrations.find({
  _id: { $in: ["B-1", "B-2", "B-3", "B-4"] }
}).sort({ _id: 1 });
~~~

If no other errors occurred, only `B-1` appears. An exception occurred, yet one new document was written successfully.

### 5.3. Do Not Run the Unordered Example Directly on the Modified Data

If you reuse the exact same collection after the ordered run above, `B-1` **already exists**; resending the batch creates an additional duplicate `_id` error. To compare fairly with the next section, reset the test collection to a state containing only `SEED`, or use another collection with the same validator/index and seed data. Do not perform such cleanup operations on a production database.

## 6. Unordered Insert: Still Attempting Other Items

When passing `ordered: false`, MongoDB continues processing other documents after a write error. This is often the right choice for imports with **independent** records, as long as the application reports per-record errors.

~~~javascript
try {
  const result = db.registrations.insertMany(
    batch,
    { ordered: false }
  );
  printjson(result);
} catch (error) {
  print("Batch had one or more errors:");
  print(error.message);
}
~~~

**Assuming the collection was recreated from the initial state containing only `SEED`**:

| Item | Condition | Expected Outcome |
| --- | --- | --- |
| `B-1` | Valid. | Inserted. |
| `B-2` | Duplicates seed email. | Write error 11000. |
| `B-3` | Fails validator. | Write error 121. |
| `B-4` | Valid. | Inserted. |

If no other issues arise, documents `B-1` and `B-4` are inserted, while the remaining two fail. The API can still throw an **aggregate bulk error**, even though some data was saved.

MongoDB may **reorder execution** of unordered operations to improve performance. Therefore, do not build business rules assuming `B-1` always executes before `B-4` in this mode. For independent documents, order generally does not matter; for dependent operations, it can matter greatly.

### 6.1. Comparing `ordered` and `unordered`

| Property | `ordered: true` | `ordered: false` |
| --- | --- | --- |
| Default for `insertMany()` | Yes. | Must be specified. |
| When an item hits a write error | Stops subsequent items. | Continues attempting remaining items. |
| Ordering | Preserves order semantics within the batch. | Must not depend on execution order. |
| Number of errors reported | Usually the first write error for the ordered chain. | Can be multiple write errors. |
| Auto-rolls back inserted items? | No, when outside a transaction. | No, when outside a transaction. |
| Suitable example | Workflow stopping on the first bad row. | Independent import wanting to collect multiple errors in one pass. |
| Risk to manage | Skips valid rows after an error. | Must tally successes and errors accurately without relying on order. |

**Ordered does not mean atomic.** An ordered batch can still partially succeed. **Unordered does not mean ignoring errors.** The API reports errors for failed operations while other items may still be written.

## 7. Error and Result Structure During Bulk Writes

MongoDB distinguishes error categories, of which the following are especially important:

- **`writeErrors`:** errors while processing individual write operations, such as unique key collisions or documents violating a validator.
- **`writeConcernErrors`:** errors failing to meet write acknowledgement requirements within the requested timeout, such as waiting too long for replica acknowledgements.
- **Partial write result:** information about operations that were processed successfully, such as the number of accepted inserts.

Example **illustrating the logical structure** of an unordered error:

~~~javascript
{
  writeErrors: [
    {
      index: 1,
      code: 11000,
      errmsg: "E11000 duplicate key error ..."
    },
    {
      index: 2,
      code: 121,
      errmsg: "Document failed validation"
    }
  ],
  writeConcernErrors: [],
  nInserted: 2
}
~~~

This is not a guarantee of the exact outer wrapper property names across every driver version. In `mongosh`, bulk errors include related fields such as `writeErrors`, `writeConcernErrors`, and inserted counts; the Java driver exposes methods on its exception/result classes.

The `index` field in a write error typically indicates **the zero-based position of the operation in the original list**. For example, `index: 1` is the second element. Attach a **stable input identifier** to each element so you can map from the index back to the record without depending on printed error text.

### 7.1. Errors 11000 and 121 Require Different Corrective Actions

| Code | Common Name/Message | Common Cause | Appropriate Action |
| --- | --- | --- | --- |
| **11000** | `DuplicateKey` / `E11000 duplicate key` | `_id` or another unique index collided. | Identify the index, duplicate value, and policy to merge, skip, or update. |
| **121** | `DocumentValidationFailure` | Document violated the collection validator. | Fix payload/schema mapping or business rules; check the active validator. |
| **64** in many scenarios | `WriteConcernTimeout` | Operation was not acknowledged per write concern within the expected window. | Check replica health, existing results, and retry/reconciliation policy. |

**Do not blindly fix all errors with retries.** Error 11000 from duplicate values and error 121 from wrong data types usually will not disappear by resending the exact same payload. Conversely, a write concern error or network interruption requires determining **whether the write may already have occurred**, rather than assuming guaranteed failure.

### 7.2. A `writeConcernError` Is Not Confirmation of a "Rollback"

Suppose a command requests `writeConcern: { w: "majority", wtimeout: 100 }` in a replica set. The primary may have accepted the write, yet acknowledgements from the required number of replicas did not arrive within 100 ms. The driver/server may report a write concern error.

That is an **acknowledgement/durability level** issue, distinct from a document rejected by a validator. Never interpret every `writeConcernError` as "no documents were written." Before retrying, you need idempotency keys and a result verification strategy.

### 7.3. Partial Results Must Be Persisted as Per-Record Statuses

An ingestion system should distinguish:

~~~text
SUCCESS_CONFIRMED   Confirmed written successfully
REJECTED_DUPLICATE  Rejected due to unique key collision
REJECTED_VALIDATION Rejected due to schema validation
NOT_ATTEMPTED       Ordered stopped before processing this row
UNKNOWN             Cannot determine with certainty after network/acknowledgement error
~~~

These statuses are **application design examples**, not enums defined by MongoDB. For uncertain outcomes, avoid inferring `FAILED` or `SUCCESS` solely from a timeout message.

## 8. Exception Handling in `mongosh`

One way to learn and inspect behavior is to catch the exception, print technical details, and verify existing data:

~~~javascript
try {
  const result = db.registrations.insertMany(
    batch,
    { ordered: false }
  );
  printjson({ status: "ALL_INSERTED", result });
} catch (error) {
  print("BULK_ERROR");
  print("message: " + error.message);
  printjson(error.writeErrors);
  printjson(error.writeConcernErrors);
  printjson(error.result);
}
~~~

Depending on the `mongosh` version, fields on the exception may differ or be absent; print relevant exception properties while learning and cross-check with your running version's documentation. Do not log full documents or sensitive payloads in production logs just for error debugging.

Next, **read back using known application IDs**:

~~~javascript
db.registrations.find(
  { _id: { $in: ["B-1", "B-2", "B-3", "B-4"] } },
  { _id: 1, email: 1, age: 1 }
).sort({ _id: 1 });
~~~

Reading back reveals the current state, but remember that other processes may be concurrently writing or modifying data. In systems with concurrency or retries, check an additional import ID, version, or idempotency marker rather than seeing an `_id` exist and concluding it was definitely created by the current batch run.

## 9. Java Sync Driver: Catching Errors and Extracting Partial Success Info

In Java applications, `MongoCollection<Document>` provides `insertOne`, `insertMany`, and `bulkWrite`.

Common result/error classes:

| Java API | Success | Errors to Handle |
| --- | --- | --- |
| `insertOne` | `InsertOneResult` | `MongoWriteException` for single write errors, plus corresponding connection/write concern exceptions. |
| `insertMany` | `InsertManyResult` | `MongoBulkWriteException` for bulk errors. |
| `bulkWrite` (collection-level) | `BulkWriteResult` | `MongoBulkWriteException` and other connection/acknowledgement errors depending on the scenario. |

### 9.1. Java Example with Unordered `insertMany`

~~~java
import com.mongodb.MongoBulkWriteException;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.InsertManyOptions;
import org.bson.Document;

import java.util.List;

public class RegistrationImporter {
    public static void importBatch(MongoCollection<Document> registrations) {
        List<Document> documents = List.of(
            new Document("_id", "B-1")
                .append("email", "one@example.com")
                .append("age", 20),
            new Document("_id", "B-2")
                .append("email", "existing@example.com")
                .append("age", 21),
            new Document("_id", "B-3")
                .append("email", "three@example.com")
                .append("age", 16),
            new Document("_id", "B-4")
                .append("email", "four@example.com")
                .append("age", 27)
        );

        try {
            var result = registrations.insertMany(
                documents,
                new InsertManyOptions().ordered(false)
            );
            System.out.println(
                "All documents inserted: "
                + result.getInsertedIds().size()
            );
        } catch (MongoBulkWriteException e) {
            System.err.println(
                "Acknowledged successful inserts: "
                + e.getWriteResult().getInsertedCount()
            );

            e.getWriteErrors().forEach(writeError -> {
                int inputIndex = writeError.getIndex();
                int code = writeError.getCode();

                System.err.printf(
                    "Input index %d, code %d, id %s%n",
                    inputIndex,
                    code,
                    documents.get(inputIndex).getString("_id")
                );
            });

            if (e.getWriteConcernError() != null) {
                System.err.println(
                    "Write concern error also occurred"
                );
            }
        }
    }
}
~~~

In the Java Sync Driver, `MongoBulkWriteException` lets you read the write errors and the successful write result portion. `e.getWriteResult().getInsertedCount()` is useful for knowing how many inserts were acknowledged by the server when the bulk result contains write errors.

This snippet assumes the error is of the bulk type and only illustrates **how to inspect it**. When building a real importer, you must:

- Also handle connection/timeout errors or cases where the result is not fully acknowledged.
- Not merely count successes, but map statuses back to each input ID.
- Avoid logging raw emails, personal documents, or validator details containing sensitive data.
- Not assume every error shares the same API or every driver version uses identical classes.
- Never mutate the order of `documents` after sending the command; `writeError.getIndex()` must map back to the original input list.

In the example, `append("age", 20)` with a normal `Integer` is encoded by the driver as BSON Int32, matching the validator requiring `bsonType: "int"`. If replaced with `20L`, the field may be encoded as BSON Int64 and fail the active validator.

### 9.2. With `insertOne`

~~~java
import com.mongodb.MongoWriteException;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

public class SingleInsertExample {
    public static void insert(MongoCollection<Document> collection) {
        try {
            collection.insertOne(
                new Document("_id", "B-2")
                    .append("email", "existing@example.com")
                    .append("age", 21)
            );
        } catch (MongoWriteException e) {
            int code = e.getError().getCode();

            if (code == 11000) {
                System.err.println("Duplicate unique key");
            } else if (code == 121) {
                System.err.println("Schema validation rejected document");
            } else {
                throw e;
            }
        }
    }
}
~~~

Error codes help classify errors to return business messages or decide the next action. However, do not turn `11000` into "success" by default: it could be a **different** record that collided on the same key, so identifier and content must be compared per business policy.

### 9.3. Spring Data MongoDB

With `MongoTemplate`, Spring Data can **translate driver exceptions** into Spring's data-access exception hierarchy, such as `DuplicateKeyException` for unique errors. Spring Data's bulk APIs also have different exception/result types and wrapping behaviors across versions.

If an application needs *per-item* details in a batch, inspect the exact abstraction in use, root causes, and version contract. Do not simply catch a broad exception class and return HTTP 500 while ignoring already-written items.

Java-side validation like `@NotNull`, `@Email`, or `@Min` can be helpful at the API layer, but does not replace unique indexes or collection validators: another process might write directly via the driver, and application-level pre-checks are vulnerable to race conditions.

## 10. `bulkWrite()` and Partial Success Results

`bulkWrite()` lets you send multiple operations: insert, update, replace, and delete. The bulk result includes corresponding counters such as `insertedCount`, `matchedCount`, `modifiedCount`, `deletedCount`, or `upsertedCount`, depending on the API.

~~~javascript
db.inventory.bulkWrite(
  [
    {
      insertOne: {
        document: { _id: "P1", stock: 10 }
      }
    },
    {
      updateOne: {
        filter: { _id: "P2" },
        update: { $inc: { stock: 5 } }
      }
    },
    {
      insertOne: {
        document: { _id: "P3", stock: 7 }
      }
    }
  ],
  { ordered: false }
);
~~~

An `updateOne` result can have **matched = 0** without any write error, for example if product `P2` does not exist. That differs from an insert failing due to a duplicate. A bulk result reporting "command succeeded" at the operation level does not prove every business objective was achieved.

Do not use unordered bulk when operations **depend on order**, such as creating a document first and immediately updating that same document in the same batch. MongoDB may execute unordered operations in a different order; separate dependent stages or use transactions and appropriate orchestration.

### 10.1. Error Index in Bulk Operations

If the third operation fails, `writeErrors.index = 2` refers to the position of the third operation in the bulk list, regardless of whether the operation is an insert or an update. Therefore, the reconciliation table must record:

~~~text
index 0 -> insert product P1
index 1 -> increment stock P2
index 2 -> insert product P3
~~~

You cannot treat `index` as an index into a separate insert-only sublist if the bulk request also contains updates/deletes.

### 10.2. Large Batches

In high-level APIs, the driver can split a very long list into multiple batches according to protocol limits, such as `maxWriteBatchSize`. Thus, one application call can correspond to multiple write requests to the server. Outside a transaction, an error in a later batch **does not automatically undo** documents already written in an earlier batch.

Ingestion systems should mark each processed range or identifier rather than treating an entire file as having only a single "DONE/FAILED" flag.

## 11. Transactions: When Must All Operations Succeed Together?

If business rules dictate **partial insertion is unacceptable**, consider a multi-document transaction on a supported MongoDB deployment.

For example, a business operation creating an order and recording payment history must belong to the same transaction:

~~~text
start transaction
    insert order
    insert payment record
    update reserved inventory
commit transaction
~~~

If an operation inside the transaction triggers an error forcing the transaction to abort, the transaction's changes are not committed. The application must properly implement abort/retry/commit flows and transaction *error labels* per driver documentation.

Key distinctions:

- **`ordered: true` outside a transaction:** an error after an insert still leaves prior inserts in place.
- **`ordered: false` outside a transaction:** can leave multiple successful inserts interspersed with rejected ones.
- **Aborted transaction:** there is no "partial commit" state for changes inside the transaction.
- **Commit returns an uncertain result:** the application needs handling for *unknown transaction commit result* per the driver; do not treat a timeout as proof of rollback.

Transactions also carry costs: resources, snapshot retention duration, conflict likelihood, and operational limits. Do not wrap millions of independent documents in one gigantic transaction merely to avoid tracking per-row statuses. For imports where partial success is acceptable, unordered + accurate reporting is usually the more pragmatic choice.

## 12. Retries: The Hardest Problem After Partial Success

Suppose an unordered batch has four rows:

~~~text
B-1: inserted
B-2: E11000
B-3: E121
B-4: inserted
~~~

If you resend all four rows **unchanged**:

- `B-1` and `B-4` may now trigger E11000 because they already exist.
- `B-2` still collides on the key.
- `B-3` still violates the validator.
- Reported error counts increase while data remains unchanged.

New errors do not mean the previous run inserted nothing. This is a common cause of blind retries cluttering import logs.

### 12.1. Assigning Stable Identifiers Before Sending

For example, each record arriving from an external system has a unique `sourceSystem` and `externalId`. You can create a unique index on this pair or derive a durable `_id` from the external identifier:

~~~javascript
{
  _id: "CRM|customer-481",
  sourceSystem: "CRM",
  externalId: "customer-481",
  fullName: "Customer A"
}
~~~

If the write loses connection, the application has a stable key to **query and reconcile** before deciding to re-insert, update, or report a conflict.

Do not generate a new `ObjectId()` on every retry when business logic requires the same event to be applied only once: having a different `_id` each time makes it hard to detect logical duplicates.

### 12.2. Upsert Can Support Idempotency

If the rule is "create if absent, do not modify if already present," you can use `$setOnInsert`:

~~~javascript
db.importedCustomers.updateOne(
  { _id: "CRM|customer-481" },
  {
    $setOnInsert: {
      sourceSystem: "CRM",
      externalId: "customer-481",
      fullName: "Customer A",
      importedAt: new Date()
    }
  },
  { upsert: true }
);
~~~

When the document already exists, the update leaves fields in `$setOnInsert` untouched; when absent, MongoDB inserts a new document. However, this only fits **"keep the existing record" semantics**. If new data differs from the old record, the application must still know whether it is a valid update, conflicting data, or a true duplicate.

With concurrent upserts, unique indexes and error handling for race conditions are still required; do not assume `upsert: true` eliminates every possibility of E11000.

### 12.3. Grouping Retryability

| Result Type | Should Auto-Retry Identical Payload? | How to Handle |
| --- | --- | --- |
| E11000 with same code and existing business content | Usually no need to re-insert. | Reconcile with existing record; confirm whether duplicate is accepted or a conflict. |
| E11000 due to same code but different content | No. | Return conflict or follow business merge workflow. |
| E121 due to missing/mismatched field type | No, if data is unchanged. | Fix validation/mapping or route to a data-repair queue. |
| Ordered stopped: unattempted items | Can send these items after resolving the root cause, using stable IDs. | Do not mix with already-inserted items; separate statuses. |
| Network/timeout error, write outcome unknown | Only controlled retries. | Use driver retryable writes when appropriate; read/reconcile via stable keys. |
| Write concern timeout | Do not treat as "not written." | Check acknowledgement state and data, then decide per durability requirements. |

MongoDB drivers can support **retryable writes** when topology, operation type, and configuration permit. That does not replace *business* idempotency; for instance, replaying a payment event or incrementing a counter from the application still requires duplicate-handling rules.

## 13. Designing an API Response for Partial Success

An API importing 100 customers should not merely return:

~~~json
{ "success": false, "message": "Import failed" }
~~~

That message hides the possibility that 98 profiles were already written. The API can return a per-row report, such as:

~~~json
{
  "importId": "IMP-2026-11-14-001",
  "received": 4,
  "inserted": 2,
  "rejected": 2,
  "unknown": 0,
  "items": [
    { "sourceId": "B-1", "status": "INSERTED" },
    { "sourceId": "B-2", "status": "DUPLICATE", "errorCode": 11000 },
    { "sourceId": "B-3", "status": "INVALID", "errorCode": 121 },
    { "sourceId": "B-4", "status": "INSERTED" }
  ]
}
~~~

This is an **example application contract**, not a standard response from MongoDB. You can use an HTTP status code fitting your API conventions (such as a success response containing a per-row error report, or a designated code for partial results), but more importantly, the client knows accurately which data was inserted and which portion needs fixing.

The API should also clearly record:

- `importId` and data source version.
- Stable ID of each row or idempotency key.
- `NOT_ATTEMPTED` status if ordered stopped before that row.
- `UNKNOWN` status when confirmation details are insufficient.
- Machine-readable technical error codes, and business messages free of sensitive secrets.
- Processing timestamp, total attempted/inserted/rejected counts, and retry policy.

When error details are large or contain personal data, separate access-controlled technical logs from messages returned to end users.

## 14. Multi-Layer Validation and Race Conditions

A Java service can validate data before calling MongoDB:

~~~text
HTTP request
   |
   v
Bean Validation / DTO validation
   |
   v
Business rules / normalization
   |
   v
MongoDB driver
   |
   v
Collection validator + unique indexes
~~~

The layers serve different purposes:

1. **DTO/Bean Validation:** returns friendly errors early, such as missing email or negative age.
2. **Business validation:** business-dependent rules, such as allowing only one account type per tenant.
3. **Collection validator:** helps keep data structurally sound even when accessed by other processes.
4. **Unique index:** serves as the final safeguard against concurrent conflicts on unique keys.

Code following the pattern "check if email doesn't exist, then insert" does not replace a unique index:

~~~javascript
const exists = db.registrations.findOne({
  email: "an@example.com"
});

if (!exists) {
  db.registrations.insertOne({
    email: "an@example.com",
    age: NumberInt(24)
  });
}
~~~

Two concurrent requests can both observe `exists == null` before either inserts. Only a unique index or an appropriate consistency mechanism prevents both from creating duplicates. The application must catch error E11000 and translate it into the appropriate business decision.

Similarly, a collection validator should not be "fixed" by altering the schema in production to accommodate a bad payload if the actual issue is DTO mapping, BSON typing, or user data. Changing a validator requires a migration workflow and impact assessment.

## 15. Observing and Reconciling a Real-World Import Batch

Suppose a file has 50,000 rows, processed in batches of 1,000. A resilient design might use:

~~~text
Source file + importId + checksum
                 |
                 v
      Normalize and validate in app
                 |
                 v
      Assign stable ID per row
                 |
                 v
      Send ordered/unordered batch
                 |
                 v
      Collect acknowledged results and writeErrors
                 |
                 v
      Write status table keyed by sourceId
                 |
        +--------+--------+
        |                 |
     Success         Error/unknown
        |                 |
        v                 v
    Mark DONE     Fix data or reconcile
                          |
                          v
                    Controlled retry
~~~

### 15.1. Metrics to Track

| Metric | Meaning |
| --- | --- |
| `receivedCount` | Total number of input rows. |
| `attemptedCount` | Number of rows sent/attempted, distinguishing unknown states. |
| `insertedCount` | Number of inserts acknowledged as successful. |
| `duplicateCount` | Number of rows hitting E11000, split by index if needed. |
| `validationFailureCount` | Number of rows hitting E121, grouped by failing rule. |
| `notAttemptedCount` | Rows not processed because ordered halted or the job stopped. |
| `unknownCount` | Rows lacking sufficient confirmation due to network/acknowledgement errors. |
| `reconciledCount` | Previously unknown rows reconciled via stable keys. |
| `retryCount` | Number of retry attempts, categorized by cause. |

Do not expect `received = inserted + duplicate + invalid` if there are still unattempted items or unknown results. The system must ensure **each row has exactly one current status**, with a status transition history for investigation.

### 15.2. When Data Already Existed Before the Import

The same external ID might exist in the database because an earlier import succeeded. When hitting E11000, you must compare:

- Is it truly the **same source** and **same business identifier**?
- Does the payload have the same version/content?
- Is this a retry of the same import or two different sources contending?
- Is the policy to skip, update, merge, or return a conflict?
- Does audit logging or event emission depend on whether it was "newly inserted" versus "already existed"?

Thus, E11000 is a **uniqueness constraint signal**, not yet a business determination that the existing record is "identical" to the new one.

## 16. Common Misleading Scenarios

### Scenario A: A Batch Has an Invalid Age Row in the Middle

~~~text
Input: A valid, B age 16, C valid
Validator: age >= 18
~~~

- With `ordered: true`: A is inserted, B fails with 121, C is not attempted.
- With `ordered: false`: A and C can be inserted, B fails with 121.
- Outside a transaction, there is no automatic rollback of A when B fails.

### Scenario B: Two Records Share the Same `_id` Within the Same Batch

~~~javascript
[
  { _id: "X1", email: "a@example.com", age: NumberInt(20) },
  { _id: "X1", email: "b@example.com", age: NumberInt(21) }
]
~~~

The unique index on `_id` prevents both from coexisting in the same collection. With ordered, the first element may be inserted and the second fails; with unordered, **do not depend on which record executes first**. If the two payloads have different meanings, this is a source-data identity bug that must be fixed rather than accepting "whichever wins."

### Scenario C: Batch Throws an Exception Yet the Last Document Appears in the Database

This can be completely normal with `ordered: false`: a middle item failed while the last item was inserted. When network errors or concurrent writers are also involved, reconcile IDs to verify the record's origin.

### Scenario D: `validationAction: "warn"`

A document failing the validator can **still be inserted**, while the system logs a warning. Therefore, seeing no 121 error does not prove documents satisfied all rules; inspect the validator configuration and application-layer validation.

### Scenario E: MongoDB Acknowledges the Write, but the Notification Email Fails to Send

Inserting and sending email are two separate systems. A failed email send cannot be a reason to resend the raw `insertMany`. Use an outbox/idempotent event mechanism or separate workflow to retry the notification step without creating duplicate data.

### Scenario F: Several Rows Lack Email Under a Unique Index

If a single-field unique index on email is not partial, multiple rows missing email can trigger E11000 due to `null` entries. Optional email fields require an appropriate schema/index design rather than dropping the entire unique constraint.

### Scenario G: Wrapping the Entire Batch in a Transaction to "Ensure No Rows Are Lost"

Transactions ensure atomicity of changes belonging to one transaction, but they do not fix bad data, do not guarantee an import file is always valid, and are not free in performance. For very large files, chunking into batches, checkpointing, and reconciling are usually more practical than one giant transaction.

## 17. Practice Exercises

### Exercise 1 — Predicting Collection State

Suppose the `students` collection has a unique index on `studentCode`, a validator requiring `age >= 16`, and `studentCode: "S1"` already exists. A batch contains:

~~~javascript
[
  { _id: 101, studentCode: "S2", age: NumberInt(17) },
  { _id: 102, studentCode: "S1", age: NumberInt(18) },
  { _id: 103, studentCode: "S3", age: NumberInt(15) },
  { _id: 104, studentCode: "S4", age: NumberInt(19) }
]
~~~

Create a table for each document when:

1. `ordered: true`, outside a transaction.
2. `ordered: false`, outside a transaction.
3. A transaction must abort due to a write error in the batch.

**Hint:** in case 1, only S2 is inserted; S1 causes an error; S3 and S4 are not attempted. In case 2, S2 and S4 can be inserted while S1 and S3 are rejected. In case 3, if the transaction aborts, none of the transaction's changes are committed, even if some operations ran earlier.

### Exercise 2 — Choosing the Right Index

Business rules require each seller to use a unique SKU; identical SKUs across different sellers are valid.

~~~javascript
{ sellerId: "SELLER-A", sku: "KB-01" }
{ sellerId: "SELLER-B", sku: "KB-01" }
~~~

Create a compound unique index for `(sellerId, sku)` and try inserting documents with the same pair. Discuss how to handle missing/null `sku` fields and case normalization per business rules.

### Exercise 3 — Distinguishing Incomplete Acknowledgement from Validation

An `insertMany` command reports:

~~~text
writeErrors: [ { index: 2, code: 121, ... } ]
writeConcernErrors: [ ... timeout ... ]
~~~

Explain why you cannot conclude the entire batch was "definitely not written." Identify which IDs must be saved and what reconciliation method to use before deciding on a retry.

### Exercise 4 — Designing a Rerunnable Import

A CSV file from a CRM system is resent daily; sometimes customers are duplicated, sometimes emails are invalid. Propose:

- A stable ID key for each customer.
- A unique index protecting the business key.
- Rules for "duplicate with same content" versus "duplicate with different content."
- A per-row status list, including `UNKNOWN`.
- A plan to repair error 121 data and rerun only the appropriate rows.

### Exercise 5 — Java Exception Handling

Write a Java method accepting `List<Document>`, calling `insertMany(..., ordered(false))`, and returning a list of statuses keyed by ID. Ensure the method distinguishes errors 11000, 121, and unknown errors. The method should clearly define its policy when receiving a network error without a reliable partial result.

## 18. Misconceptions to Avoid

| Misconception | Accurate Understanding |
| --- | --- |
| "If `insertMany` errors, the whole batch rolls back." | Outside a transaction, successful documents may already be saved. |
| "`ordered: true` means atomic." | `ordered` only governs how execution proceeds after a write error. |
| "`ordered: false` ignores errors without reporting them." | Write errors are still reported, even though other valid items are processed. |
| "A bulk exception means zero documents succeeded." | Inspect partial results and/or reconcile by ID. |
| "Every row absent from the database was invalid." | Some rows may not have been attempted because ordered stopped or the job terminated. |
| "E11000 only comes from duplicate `_id`." | It can come from any unique index, including compound indexes. |
| "Checking existence before inserting eliminates the need for a unique index." | Check-then-insert has a race condition under concurrent requests. |
| "Missing fields never interact with unique indexes." | Unique indexes have rules for `null` and missing fields; design appropriate partial/sparse/indexes. |
| "E121 is a Java serializer error." | 121 is a server-side collection validator error; the serializer may raise its own errors earlier. |
| "Having `$jsonSchema` means every invalid document is always rejected." | Depends on `validationAction`, `validationLevel`, and authorized bypasses. |
| "A timeout means the server wrote nothing." | Part of the operation may have executed without reaching the requested acknowledgement level. |
| "Retrying the whole batch will automatically fill in the missing rows." | It can generate new duplicate errors and obscure the outcome of each run. |
| "Just catch the exception and return HTTP 500." | Import APIs should accurately report succeeded, rejected, unattempted, and unknown items. |

## 19. Official MongoDB Documentation

- [Insert Many — mongosh](https://www.mongodb.com/docs/manual/reference/method/db.collection.insertMany/): `ordered`, `unordered`, write errors, write concern, and batch insert results.
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/): `_id`, unique compound indexes, null/missing values, duplicate keys.
- [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/): validators and document structure.
- [Handle Invalid Documents](https://www.mongodb.com/docs/manual/core/schema-validation/handle-invalid-documents/): `validationAction` and handling invalid documents.
- [MongoDB Error Codes](https://www.mongodb.com/docs/manual/reference/error-codes/): codes 11000, 121, and other server error codes.
- [Java Sync Driver — Insert Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/insert/): `InsertOneResult`, `InsertManyResult`, `MongoWriteException`, `MongoBulkWriteException`.
- [Java Sync Driver — Bulk Write Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/bulk/): bulk models, `BulkWriteResult`, `ordered`, and error handling.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): acknowledgement levels and cases where writes are not acknowledged as requested.

The right way to handle a MongoDB write that encounters errors is to **distinguish data-rejection errors, acknowledged write results, and uncertain results**. Unique indexes enforce uniqueness, validators enforce data structure, and `ordered` controls batch continuation. The application must combine those three elements with **stable IDs, partial results, transactions when required, and controlled reconciliation/retry mechanisms** so data stays accurate even when errors occur midway.
