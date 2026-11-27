# MongoDB: insertOne, insertMany, and Write Result Structure

When an application needs to add new data to MongoDB, the two fundamental operations are **insertOne()** to add a single document and **insertMany()** to add multiple documents in a single call. Both target a **collection**, accept data in BSON structure, and return information about the write operation if the request is acknowledged.

The key point to understand is that **"command sent," "write acknowledged," and "all documents added" are not always the same state**. In scenarios involving duplicate unique keys, validation failures, dropped connections, or different write concerns, the application must read the result or error accurately to know which portion of the data was saved.

This lesson uses **mongosh** as the primary example environment, then connects to Java, Node.js, and Python to distinguish the result APIs of each driver.

## 1. Where Do Insert Operations Fit in the MongoDB Model?

MongoDB organizes data in the following hierarchy:

~~~text
Database: bookstore
└── Collection: books
    ├── Document: { _id, isbn, title, price, stock }
    ├── Document: { _id, isbn, title, price, stock }
    └── Document: { _id, isbn, title, price, stock }
~~~

In **mongosh**, select a database and access a collection:

~~~javascript
use bookstore

db.books
~~~

To add data to **bookstore.books**, you can use:

~~~javascript
db.books.insertOne({
  isbn: "9786040000001",
  title: "Introduction to MongoDB",
  price: 190000,
  stock: 12
});
~~~

Or add multiple books:

~~~javascript
db.books.insertMany([
  {
    isbn: "9786040000002",
    title: "Document Data Modeling",
    price: 240000,
    stock: 6
  },
  {
    isbn: "9786040000003",
    title: "Queries and Indexes",
    price: 260000,
    stock: 9
  }
]);
~~~

Both commands are **write operations**. They add new documents and are not used to modify existing documents. If you want to update fields of an existing document, you must use the appropriate update or replace operations.

### Quick Comparison

| Aspect | insertOne() | insertMany() |
| --- | --- | --- |
| Input | One document | An array of documents |
| Purpose | Add exactly one record | Add a group of records |
| Success result in mongosh | acknowledged, insertedId | acknowledged, insertedIds |
| Atomicity | Single document | Per document, not atomic across the entire batch |
| Ordering configuration | Not applicable | ordered: true or false |
| On error | Command fails and reports an error | Part of the batch may have been added successfully |
| Typical use | Creating a user, order, or post | Importing data, creating multiple events, seeding initial data |

## 2. Before Inserting: Documents and the _id Field

Every document in a regular MongoDB collection has an **_id** field as its identifier key.

Example of data sent by an application:

~~~javascript
{
  sku: "BOOK-001",
  title: "Introduction to MongoDB",
  price: 190000
}
~~~

If **_id** is not provided, the driver or MongoDB can generate an identifier value. For typical operations in mongosh, the commonly generated value is an **ObjectId**:

~~~javascript
{
  _id: ObjectId("674000000000000000000001"),
  sku: "BOOK-001",
  title: "Introduction to MongoDB",
  price: 190000
}
~~~

The ObjectId in the example is an illustrative value. Each actual insert typically generates a different ObjectId.

### 2.1. _id Can Be Provided by the Application

MongoDB does not require every _id to be an ObjectId. The application can choose a string value or another suitable type:

~~~javascript
db.products.insertOne({
  _id: "BOOK-001",
  title: "Introduction to MongoDB",
  price: 190000
});
~~~

This approach is useful when a business code is designed as the primary key and its stability and uniqueness within the collection can be guaranteed.

If the collection already has a document with **_id: "BOOK-001"**, a new insert using the same _id will encounter a **duplicate key error**, rather than automatically replacing the old record.

### 2.2. _id Is Protected by a Unique Index

A regular collection has a unique index on **_id**. Therefore, two documents in the same collection cannot have the same _id value under that constraint.

~~~javascript
db.products.insertOne({
  _id: "BOOK-001",
  title: "Book A"
});

db.products.insertOne({
  _id: "BOOK-001",
  title: "Book B"
});
~~~

Assuming the collection does not initially have that key, the first command succeeds. The second command reports a duplicate key error with the common code **E11000** (error code **11000**).

Two different collections can still contain documents with the same _id; the scope of identification and the unique index here is the **collection**.

### 2.3. _id Does Not Represent Insert Order

An ObjectId often contains a timestamp component and can help infer certain information, but **_id should not be treated as absolute proof of write order**. IDs may be generated on different clients before being sent, or the application may use a different _id type.

If business event ordering is needed, design a **createdAt** field, sequence, or suitable sort key and understand the reliability of the time source.

## 3. insertOne(): Adding a Single Document

Syntax in mongosh:

~~~javascript
db.collection.insertOne(
  <document>,
  <options>
);
~~~

Where:

- **document** is the object to add.
- **options** is an optional settings object, such as **writeConcern** or other options supported by the current version.

Example:

~~~javascript
use bookstore

const result = db.books.insertOne({
  isbn: "9786040000101",
  title: "MongoDB for Java Developers",
  author: {
    name: "Nguyen An",
    country: "VN"
  },
  categories: ["database", "backend"],
  price: NumberDecimal("215000.00"),
  stock: 10,
  createdAt: new Date()
});

printjson(result);
~~~

A typical successful result:

~~~javascript
{
  acknowledged: true,
  insertedId: ObjectId("674000000000000000000101")
}
~~~

On each run, **insertedId** may differ.

### 3.1. Meaning of acknowledged

**acknowledged** indicates whether the operation was acknowledged according to the applied **write concern**. For an acknowledged write request, this field is typically **true**.

You should not infer from **acknowledged: true** that the data has necessarily been replicated to every replica set member or cannot be rolled back in any scenario. The level of acknowledgement and durability expectations depend on the **write concern**, topology, and deployment state.

### 3.2. Meaning of insertedId

**insertedId** is the _id value of the newly inserted document according to the API result.

If the application does not send _id, the MongoDB driver typically generates _id before inserting. If the application already sent _id, the result reflects the value used:

~~~javascript
db.books.insertOne({
  _id: "BOOK-JAVA-01",
  title: "Java and MongoDB"
});
~~~

Illustrative result:

~~~javascript
{
  acknowledged: true,
  insertedId: "BOOK-JAVA-01"
}
~~~

**insertedId is not a document count**. With insertOne(), a single command adds at most one document, and insertedId is used to locate the added document.

### 3.3. Verifying a Document After Insert

You can use the returned ID to read it back:

~~~javascript
const writeResult = db.books.insertOne({
  title: "Understanding BSON",
  price: NumberDecimal("149000.00")
});

const saved = db.books.findOne({
  _id: writeResult.insertedId
});

printjson(saved);
~~~

If the application needs to check which fields the saved record actually contains, a readback operation like the one above lets you observe the document after writing. However, reading back is not a mandatory part of every insert operation; you must weigh the cost and consistency level of the read.

In a replica set, read preference/read concern and secondary synchronization timing also affect visibility when reading across different members.

### 3.4. Insert Can Create a Non-Existent Collection

For a regular collection, the first insert can cause MongoDB to create the collection if it does not already exist:

~~~javascript
use bookstore

db.publisherNotes.insertOne({
  title: "Release Notes",
  content: "Test build"
});
~~~

Even so, you should not rely entirely on implicit collection creation when you need to configure **schema validation**, **collation**, **capped collections**, or specialized options. Those cases generally require explicitly creating and configuring the collection beforehand.

## 4. insertMany(): Adding Multiple Documents in One Call

Syntax:

~~~javascript
db.collection.insertMany(
  [ <document1>, <document2>, ... ],
  <options>
);
~~~

The input must be an **array containing documents**.

Example:

~~~javascript
use bookstore

const result = db.books.insertMany([
  {
    isbn: "9786040000201",
    title: "MongoDB Architecture",
    price: NumberDecimal("250000.00"),
    stock: 8
  },
  {
    isbn: "9786040000202",
    title: "BSON and Data Types",
    price: NumberDecimal("180000.00"),
    stock: 14
  },
  {
    isbn: "9786040000203",
    title: "Index Design",
    price: NumberDecimal("230000.00"),
    stock: 7
  }
]);

printjson(result);
~~~

The **mongosh** result typically has the structure:

~~~javascript
{
  acknowledged: true,
  insertedIds: {
    "0": ObjectId("674000000000000000000201"),
    "1": ObjectId("674000000000000000000202"),
    "2": ObjectId("674000000000000000000203")
  }
}
~~~

The ObjectIds above are only for illustrating the result.

### 4.1. What Is insertedIds?

**insertedIds** in the mongosh result maps **the index of each document in the input array** to the _id value used for that document.

~~~text
Input array:
  [0] book "MongoDB Architecture"
  [1] book "BSON and Data Types"
  [2] book "Index Design"

insertedIds:
  "0" -> _id of document at index 0
  "1" -> _id of document at index 1
  "2" -> _id of document at index 2
~~~

Do not confuse the keys **"0", "1", "2"** with the value of the _id field. These are only the **input indices**; the corresponding values are the actual _ids used during insertion.

In some drivers, the same concept is represented as a map or a list instead of an object like in mongosh. When a partial error occurs, how you obtain information about IDs and the number of successful operations can differ from when the entire batch succeeds.

### 4.2. Providing _id in Advance

~~~javascript
db.books.insertMany([
  {
    _id: "B-001",
    title: "First Book"
  },
  {
    _id: "B-002",
    title: "Second Book"
  }
]);
~~~

Illustrative result:

~~~javascript
{
  acknowledged: true,
  insertedIds: {
    "0": "B-001",
    "1": "B-002"
  }
}
~~~

Proactively assigning _id can help coordinate across services or implement idempotency, but you still need to handle reused IDs and inspect write results.

### 4.3. Inserting Multiple Documents Is Not Atomic Across the Entire Batch

Suppose you have three documents:

~~~text
D1 = product A
D2 = product B
D3 = product C
~~~

MongoDB guarantees atomicity for **each individual document** during writes. However, **insertMany does not automatically turn D1, D2, and D3 into an all-encompassing transaction**.

If D1 has already been written, D2 encounters a duplicate key error, and D3 is either skipped or processed depending on the **ordered** option, the outcome may be that only part of the documents appear in the collection.

If the business logic requires **all three to succeed or none to be added**, you need a multi-document transaction on a supported deployment, or choose a different suitable data model.

## 5. ordered: true and ordered: false

An important option of **insertMany()** is **ordered**.

- **ordered: true** is the default. Operations are processed in order and stop when a write error is encountered.
- **ordered: false** allows MongoDB/the driver to continue processing other documents when a write error occurs on one document, within the scope of errors that allow continuation. Execution order is not guaranteed as it is when ordered is true.

### 5.1. ordered: true — Stop at the First Error

Suppose the **inventoryOrdered** collection is initially empty. Execute:

~~~javascript
db.inventoryOrdered.insertMany(
  [
    { _id: "P-001", sku: "BOOK-001" },
    { _id: "P-001", sku: "BOOK-002" },
    { _id: "P-003", sku: "PEN-003" }
  ],
  { ordered: true }
);
~~~

The second document duplicates the _id of the first document. Given the order:

~~~text
[0] _id = P-001  -> Inserted successfully
[1] _id = P-001  -> Duplicate key error
[2] _id = P-003  -> Not processed because ordered=true
~~~

The command can throw an error even though the first document was already saved. This is an example of **partial success**.

A common misconception is "insertMany threw an error so no documents were written." That conclusion is false without an enclosing transaction.

### 5.2. ordered: false — Continue Independent Documents

Use another test collection, initially empty:

~~~javascript
db.inventoryUnordered.insertMany(
  [
    { _id: "P-001", sku: "BOOK-001" },
    { _id: "P-001", sku: "BOOK-002" },
    { _id: "P-003", sku: "PEN-003" }
  ],
  { ordered: false }
);
~~~

Typical result:

~~~text
[0] _id = P-001  -> Success
[1] _id = P-001  -> Duplicate key error
[2] _id = P-003  -> Still processed and can succeed
~~~

The command can still report an aggregate error (bulk write error). **ordered: false does not mean ignoring errors as if everything succeeded completely**, nor does it mean continuing regardless of severe errors such as lost connections or cluster-wide failures.

With unordered inserts, MongoDB is free to organize or reorder processing for optimization. Therefore, do not write business logic that depends on document insertion order when **ordered: false**.

### 5.3. Comparison in Error Scenarios

| Property | ordered: true | ordered: false |
| --- | --- | --- |
| Default value | Yes | No |
| Processed in input order | Yes | Not guaranteed |
| On single-document write error | Stops subsequent operations in the ordered sequence | Continues eligible remaining operations |
| Partial success possible | Yes | Yes |
| Guarantees whole-batch atomicity | No | No |
| Usage goal | Need to stop on error, want order control | Loading independent data, want to continue despite some failing documents |
| Requires aggregate error handling | Yes | Yes |

### 5.4. When to Choose ordered: false?

Suppose you are importing survey data from independent systems. One record with a duplicate ID should not prevent other valid records from being written. You can use **ordered: false**, then collect the errors, check the count of successful records, and handle the uninserted records.

Conversely, if order has business significance and encountering an error must halt the entire sequence, **ordered: true** is more appropriate. However, using ordered true alone still **does not roll back** documents already inserted before the error.

## 6. Write Result Structure: Reading Each Field Correctly

Field names appearing in **mongosh**, Node.js, PyMongo, or Java can differ. You must distinguish between the **success result returned by the driver** and the **raw server response**.

### 6.1. Success Results in mongosh

**insertOne()**:

~~~javascript
{
  acknowledged: true,
  insertedId: ObjectId("674000000000000000000301")
}
~~~

**insertMany()**:

~~~javascript
{
  acknowledged: true,
  insertedIds: {
    "0": ObjectId("674000000000000000000302"),
    "1": ObjectId("674000000000000000000303")
  }
}
~~~

| Field | Present in command | Meaning |
| --- | --- | --- |
| acknowledged | insertOne / insertMany | Whether the operation was acknowledged according to the write concern |
| insertedId | insertOne | The _id of the inserted document on success |
| insertedIds | insertMany | The _ids mapped to input document positions on success |

In mongosh, do not assume **insertMany()** always also returns **insertedCount** like the Node.js Driver. Different wrappers have different APIs.

### 6.2. Driver-Specific Results

| Tool | insertOne success result | insertMany success result |
| --- | --- | --- |
| **mongosh** | acknowledged, insertedId | acknowledged, insertedIds |
| **Node.js Driver** | acknowledged, insertedId | acknowledged, insertedCount, insertedIds |
| **PyMongo** | acknowledged, inserted_id | acknowledged, inserted_ids |
| **Java Sync Driver** | wasAcknowledged(), getInsertedId() | wasAcknowledged(), getInsertedIds() |

In Java, **getInsertedIds()** returns a map keyed by input index; in PyMongo, **inserted_ids** is a list ordered by the input documents. Node.js uses an ID object/map by index and also provides **insertedCount** in the successful result.

You should not port a snippet using **result.insertedIds** directly from Node.js to Python or Java without adapting to the driver's API.

### 6.3. Write Result Differs from Remaining Document Count

The number of documents added in a write result does not necessarily equal the number of documents that remain in existence afterward. After an insert, other operations can delete, replace, or move data through valid mechanisms.

**insertedCount** in the Node.js Driver reports information about the **acknowledged insert operation**, not a count of the entire collection and not a permanent snapshot of the system.

If you want to count current documents, use a count query with appropriate filters and consistency options, such as:

~~~javascript
db.books.countDocuments({
  category: "Database"
});
~~~

The count command executes a new query and is not part of the insert result.

## 7. Why Can an Insert Operation Fail?

### 7.1. Unique Key Violation

MongoDB can reject a document if it violates a unique index, most commonly a duplicate **_id**.

~~~javascript
db.accounts.insertOne({
  _id: "ACC-001",
  email: "an@example.test"
});

db.accounts.insertOne({
  _id: "ACC-001",
  email: "binh@example.test"
});
~~~

The second command, if the first succeeded, typically reports the error:

~~~text
E11000 duplicate key error
~~~

If the collection has a unique index on **email**, documents with different _ids can also violate uniqueness when emails collide.

### 7.2. Schema Validation

A collection can enforce validation rules, for example allowing price only as a decimal number or requiring specific mandatory fields.

If a document is invalid, the server can reject the operation with a **document validation failure**. When using insertMany, a validation error on one document can also lead to partial success depending on processing order and the ordered mode.

Example creating a collection with validation:

~~~javascript
db.createCollection("catalogValidated", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["sku", "title", "price"],
      properties: {
        sku: { bsonType: "string" },
        title: { bsonType: "string" },
        price: { bsonType: "decimal" }
      }
    }
  }
});
~~~

Valid insert:

~~~javascript
db.catalogValidated.insertOne({
  sku: "BOOK-101",
  title: "Introduction to BSON",
  price: NumberDecimal("179000.00")
});
~~~

The following insert can be rejected because **price** is a string:

~~~javascript
db.catalogValidated.insertOne({
  sku: "BOOK-102",
  title: "Invalid Data Type",
  price: "179000"
});
~~~

The presence of **_id** is handled by MongoDB independently of validation on defined business fields.

### 7.3. Invalid BSON Size or Format

A regular BSON document has a size limit of **16 MiB**. Writing a document that is too large or data that cannot be validly encoded as BSON can fail.

In some situations, the error occurs **in the driver before sending the request**; in other situations, the server rejects it. Therefore, you should not assume every insert error is returned in the exact same format.

### 7.4. Connection, Permission, or Write Concern Errors

Other scenarios include:

- The user lacks permission to insert into the collection.
- The server is unavailable or the connection drops.
- The primary changes during the write.
- The requested write concern acknowledgement is not met or times out.
- A transaction containing the insert is aborted.

With ambiguous network errors, the application can end up in a state where it is **uncertain whether the server performed the insert**. You cannot always conclude "no success response means nothing was written." You must design safe retry and reconciliation mechanisms.

## 8. Handling Bulk Write Errors and Partial Success

Suppose an application inserts a batch of 4 documents:

~~~text
D0: valid
D1: violates unique index
D2: valid
D3: valid
~~~

**ordered: true** can result in D0 succeeding, D1 failing, and D2/D3 not being processed.

**ordered: false** can result in D0, D2, and D3 succeeding while D1 fails. However, if a network error or batch-halting error occurs, the outcome must be verified according to the actual situation.

### 8.1. Catching Errors in mongosh

Example using a test collection with intentional _ids:

~~~javascript
try {
  db.bulkDemo.insertMany(
    [
      { _id: "BATCH-001", value: 1 },
      { _id: "BATCH-001", value: 2 },
      { _id: "BATCH-003", value: 3 }
    ],
    { ordered: false }
  );

  print("Batch completely succeeded");
} catch (error) {
  print("insertMany error occurred:");
  print(error.message);

  // Observe the properties provided by the mongosh version.
  printjson(error);
}
~~~

The example assumes the collection did not already contain these IDs. Depending on the mongosh and driver versions, the error object may contain **writeErrors**, the count of inserted operations, indices of failed operations, or other details. You should not write production code relying on an error object's shape without checking the API of the version in use.

### 8.2. Reconciling Saved Data

After encountering a partial error, you can check specific _ids:

~~~javascript
db.bulkDemo.find({
  _id: {
    $in: ["BATCH-001", "BATCH-003"]
  }
});
~~~

This read result helps verify the current state in the collection. In a system with multiple writers, you need to account for other concurrent operations and choose an appropriate read consistency level.

If you need to process a large batch accurately, give each input **a stable identifier key**, maintain a mapping between inputs and _ids, and record processed statuses. Relying solely on array position may be insufficient when the program needs to retry after a network failure.

### 8.3. Distinguishing Per-Document Errors from Overall Errors

| Error Type | Scenario | What to Note |
| --- | --- | --- |
| Duplicate key | An _id or unique value already exists | That document is rejected; other documents may have been written |
| Validation error | Document fails schema validation | Depending on ordered, other documents may still be processed |
| BSON encoding error | Client value cannot be serialized | Can occur before sending the request |
| Write concern error | Requested acknowledgement level not reached | Write may have already been applied even though the app receives an error |
| Network/server error | Connection lost or topology change | Write state may be uncertain |
| Transaction abort | Transaction is not committed | Changes belonging to the transaction are not committed |

You should not treat all errors as "nothing was written." The actual state depends on the error type, topology, and write mode.

## 9. Write Concern and acknowledged

MongoDB has a **write concern** mechanism that describes the level of write operation acknowledgement requested by the client. Common examples:

- **w: 1**: the primary acknowledges that it processed the write operation as requested.
- **w: "majority"**: waits for acknowledgement according to the replica set's majority rule.
- **j: true**: requests journal-related acknowledgement according to the configuration.
- **wtimeout**: sets a timeout limit waiting to satisfy the write concern.

You should not equate **acknowledged: true** with **majority acknowledged**: a true value depends on the write concern configured for the command or client.

### 9.1. Example Specifying writeConcern in mongosh

~~~javascript
db.auditEvents.insertOne(
  {
    eventType: "LOGIN",
    occurredAt: new Date()
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
~~~

This example requests majority acknowledgement and a specific timeout. If the write concern cannot be satisfied under current conditions, the operation can report a **write concern error**. That does not prove the document was not written to the primary.

### 9.2. Unacknowledged Write

When using write concern **w: 0**, the client does not ask the server to return normal write result acknowledgement.

In drivers, the successful result of an unacknowledged operation typically has **acknowledged: false** or an equivalent property, and some accessors such as insertedId/insertedIds may not be permitted to be read.

Conceptual example:

~~~text
Client sends insert with w: 0
        |
        v
Does not wait for write acknowledgement from server
        |
        v
Client has no response proof to conclude each document was written
~~~

**w: 0 is not suitable when the application must know for certain that each insert succeeded.** In business systems, you must weigh the write concern and reliability expected by users before optimizing for latency.

## 10. Java Application Examples: InsertOneResult and InsertManyResult

The MongoDB Java Sync Driver has its own result types and calling conventions that differ from mongosh.

### 10.1. insertOne() in Java

~~~java
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;

import com.mongodb.client.result.InsertOneResult;
import org.bson.Document;
import org.bson.BsonValue;

public class InsertOneExample {
    public static void main(String[] args) {
        String uri = "mongodb://localhost:27017";

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("bookstore");
            MongoCollection<Document> books = db.getCollection("books");

            Document book = new Document("isbn", "9786040000301")
                    .append("title", "Working with MongoDB in Java")
                    .append("price", 199000)
                    .append("stock", 5);

            InsertOneResult result = books.insertOne(book);

            System.out.println("Acknowledged: " + result.wasAcknowledged());

            if (result.wasAcknowledged()) {
                BsonValue id = result.getInsertedId();
                System.out.println("Inserted ID: " + id);
            }
        }
    }
}
~~~

**InsertOneResult** provides:

- **wasAcknowledged()**: whether the operation was acknowledged.
- **getInsertedId()**: the BSON value of _id when an acknowledged result is available.

If configured as unacknowledged, certain methods that read specific details may be unusable. Therefore, the illustrative code checks **wasAcknowledged()** first.

The example assumes MongoDB is running, the connection configuration permits writes, and the project includes the appropriate Java Sync Driver dependency.

### 10.2. insertMany() in Java

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.InsertManyOptions;
import com.mongodb.client.result.InsertManyResult;

import org.bson.Document;
import org.bson.BsonValue;

import java.util.Arrays;
import java.util.List;
import java.util.Map;

public class InsertManyExample {
    public static void main(String[] args) {
        try (MongoClient client = MongoClients.create(
                "mongodb://localhost:27017")) {

            MongoDatabase db = client.getDatabase("bookstore");
            MongoCollection<Document> books = db.getCollection("books");

            List<Document> documents = Arrays.asList(
                new Document("isbn", "9786040000401")
                    .append("title", "Lesson A"),
                new Document("isbn", "9786040000402")
                    .append("title", "Lesson B")
            );

            InsertManyResult result = books.insertMany(
                documents,
                new InsertManyOptions().ordered(false)
            );

            System.out.println("Acknowledged: " + result.wasAcknowledged());

            if (result.wasAcknowledged()) {
                Map<Integer, BsonValue> ids = result.getInsertedIds();

                for (Map.Entry<Integer, BsonValue> entry : ids.entrySet()) {
                    System.out.println(
                        "Input index = " + entry.getKey()
                        + ", _id = " + entry.getValue()
                    );
                }
            }
        }
    }
}
~~~

**getInsertedIds()** returns a map associating **the input document index** with its BSON _id. This helps link insert results back to the original input list.

If the batch encounters an error, **insertMany** may throw **MongoBulkWriteException** or an appropriate exception rather than returning a successful **InsertManyResult** as in the example. The program needs a separate error-handling branch if it wants to support partial success.

### 10.3. Handling Bulk Exceptions in Java

Sample error-handling example for an insertMany command:

~~~java
import com.mongodb.MongoBulkWriteException;

// Other MongoDB Java imports are the same as the example above.

try {
    books.insertMany(
        documents,
        new InsertManyOptions().ordered(false)
    );
} catch (MongoBulkWriteException e) {
    System.out.println(
        "Number of recorded inserts: "
        + e.getWriteResult().getInsertedCount()
    );

    e.getWriteErrors().forEach(error -> {
        System.out.println(
            "Input index = " + error.getIndex()
            + ", error code = " + error.getCode()
        );
    });
}
~~~

This is an **illustrative exception-handling snippet within a context where books/documents are already created**. It does not cover all errors (such as network exceptions), does not guarantee that successful indices can be reconstructed from every error message, and does not replace designing retry/idempotency for a real system.

## 11. Node.js Example: Result with insertedCount

The Node.js Driver provides slightly different result fields.

~~~javascript
import { MongoClient } from "mongodb";

const client = new MongoClient("mongodb://localhost:27017");

async function run() {
  await client.connect();

  try {
    const books = client.db("bookstore").collection("books");

    const one = await books.insertOne({
      isbn: "9786040000501",
      title: "Node.js and MongoDB"
    });

    console.log(one.acknowledged);
    console.log(one.insertedId);

    const many = await books.insertMany(
      [
        { isbn: "9786040000502", title: "Node Book A" },
        { isbn: "9786040000503", title: "Node Book B" }
      ],
      { ordered: true }
    );

    console.log(many.acknowledged);
    console.log(many.insertedCount);
    console.log(many.insertedIds);
  } finally {
    await client.close();
  }
}

run().catch(console.error);
~~~

When **insertMany** succeeds and is acknowledged, the Node.js result typically contains:

~~~javascript
{
  acknowledged: true,
  insertedCount: 2,
  insertedIds: {
    "0": ObjectId("674000000000000000000501"),
    "1": ObjectId("674000000000000000000502")
  }
}
~~~

The two IDs above are illustrative. The **insertedCount** field is convenient for knowing how many documents were inserted in a successful result; **insertedIds** is used to correlate each document by index.

For bulk errors, Node.js can return a **MongoBulkWriteError** with error information and partial results, depending on the API and version. You cannot rely on the **then/success** branch to handle a batch that reported errors.

## 12. Python/PyMongo Example: snake_case and List of IDs

PyMongo uses Pythonic property naming.

~~~python
from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017")
books = client["bookstore"]["books"]

one = books.insert_one({
    "isbn": "9786040000601",
    "title": "Python and MongoDB"
})

print("Acknowledged:", one.acknowledged)
print("Inserted ID:", one.inserted_id)

many = books.insert_many(
    [
        {"isbn": "9786040000602", "title": "Python Book A"},
        {"isbn": "9786040000603", "title": "Python Book B"}
    ],
    ordered=False
)

print("Acknowledged:", many.acknowledged)
print("Inserted IDs:", many.inserted_ids)
~~~

**inserted_ids** is a **list of IDs in the order of documents in the input**. Example:

~~~python
[
    ObjectId("674000000000000000000601"),
    ObjectId("674000000000000000000602")
]
~~~

If **insert_many** encounters write errors on one or more documents, PyMongo can raise **BulkWriteError**. To process the details, the program can inspect the exception details:

~~~python
from pymongo.errors import BulkWriteError

try:
    books.insert_many(
        [
            {"_id": "P-001", "title": "A"},
            {"_id": "P-001", "title": "B"},
            {"_id": "P-003", "title": "C"}
        ],
        ordered=False
    )
except BulkWriteError as error:
    details = error.details

    print("nInserted:", details.get("nInserted"))
    print("writeErrors:", details.get("writeErrors", []))
~~~

Assuming the collection does not already contain these _ids, a duplicate _id record will raise an error. **nInserted** and **writeErrors** reflect the information the driver received for the write command and do not replace reconciliation if an ambiguous connection error occurs.

## 13. Performance and Batch Size

insertMany reduces the number of round trips between client and server compared to executing many sequential insertOne calls, but larger batches are not always better.

### 13.1. Reasons to Use insertMany

If an application has 1,000 independent events:

~~~text
Approach A:
  1,000 separate insertOne calls

Approach B:
  Group events into batches
  Call insertMany per batch
~~~

Batching can reduce network overhead and leverage bulk processing in the driver/server. With independent data and appropriate error handling, **ordered: false** can also improve flexibility when a portion of documents is rejected.

### 13.2. Limits and Batch Splitting

MongoDB has a BSON document size limit and a limit per write batch. The driver can **automatically split large requests into multiple batches** according to server/protocol limits.

Therefore:

- Do not assume one insertMany API call corresponds to exactly one network packet.
- Do not accumulate an unbounded amount of huge data into a single array in RAM.
- Choose a batch size suitable for document count, document size, error handling speed, and resource limits.
- Maintain a mapping between input documents and identifier keys so partial batch failures can be handled.

Even when the driver API sends multiple internal batches, atomicity remains **per document** unless the operations are wrapped in an appropriate transaction.

### 13.3. ordered=false Is Not a Parallel Transaction

The **ordered: false** option allows operations not to be bound to strict processing order, but it does not mean each document is processed in an independent transaction that can roll back the whole lot. It is a choice about **batch error handling and execution order**, not a guarantee of whole-batch atomicity.

### 13.4. Impact of Indexes

Every inserted document must update the relevant indexes. If a collection has many indexes, write costs can be higher, even though indexes speed up queries. When importing large volumes of data, the index strategy must balance ingestion cost, uniqueness enforcement, and read requirements.

Never remove a unique index just to speed up an import if doing so drops an important business constraint.

## 14. Inserts and Transactions: When Is All-or-Nothing Needed?

Suppose a business workflow requires creating simultaneously:

- An **orders** document.
- An **orderAudits** document.
- An **inventoryReservations** document.

If inserts succeed in two collections but fail in the remaining collection, the system may end up in an inconsistent state according to business requirements.

You can use a **multi-document transaction** on a supported deployment to group operations that must commit or abort together.

### Node.js Example with Session

~~~javascript
import { MongoClient } from "mongodb";

const client = new MongoClient("mongodb://localhost:27017");

async function createOrder() {
  await client.connect();

  const session = client.startSession();

  try {
    const database = client.db("bookstore");

    await session.withTransaction(async () => {
      await database.collection("orders").insertOne(
        {
          _id: "ORD-1001",
          customerId: "CUS-101",
          status: "CREATED",
          createdAt: new Date()
        },
        { session }
      );

      await database.collection("orderAudits").insertOne(
        {
          orderId: "ORD-1001",
          action: "CREATE",
          occurredAt: new Date()
        },
        { session }
      );
    });

    console.log("Transaction committed");
  } finally {
    await session.endSession();
    await client.close();
  }
}

createOrder().catch(console.error);
~~~

This example requires a MongoDB replica set or sharded cluster that supports transactions and an appropriate connection configuration. A single standalone mongod is not an environment for practicing this transaction.

**Do not send emails or call payment gateways inside a transaction callback assuming they will roll back if the transaction aborts.** The callback may be retried, and side effects outside MongoDB require separate idempotency/orchestration mechanisms.

### When Transactions Are Not Needed

Not every insertMany needs a transaction. If loading independent event documents, handling each document succeeding or failing individually may fit the business logic. In that case, **ordered: false**, recording errors, and reconciling the batch is a reasonable choice.

Only use transactions when there is an **invariant requiring multiple documents to commit or abort together**, because transactions carry operational overhead and their own retry mechanisms.

## 15. Preventing Duplicates and Safe Retries

A network error can happen **after the server has executed the insert but before the client receives the response**. In that case, the application does not know for sure whether the document was saved.

If you retry by generating a new ObjectId for the same business event, the system can create logically duplicate records even though the _ids differ.

### 15.1. Stable Identifier Keys

For example, each order creation request has a unique **requestId** determined stably by the client or server:

~~~javascript
db.orders.createIndex(
  { requestId: 1 },
  { unique: true }
);

db.orders.insertOne({
  requestId: "REQ-2025-1001",
  customerId: "CUS-101",
  status: "CREATED",
  createdAt: new Date()
});
~~~

If a request is re-sent with the same **requestId**, the unique index prevents multiple documents from storing the same request code. The application must distinguish between:

- Duplicate key caused by **retrying the exact request that previously succeeded**.
- Duplicate key caused by **two different requests being assigned the same requestId**.
- A genuine write failure that did not create a document.

Do not automatically interpret every duplicate key as "success" without verifying the key, payload, and idempotency rules.

### 15.2. Retryable Writes

Some drivers support **retryable writes** by default in eligible topologies. This mechanism can handle certain transient errors without creating unwanted duplicate operations, under conditions defined by MongoDB and the driver.

However, **retryable writes do not replace business/idempotency keys**. The application must still handle situations where a user submits the same action twice or a request is recreated with a new session/ID.

### 15.3. Reliable Result-Handling Flow

~~~text
Create document + stable business key
            |
            v
        Send insert
            |
      +-----+------+
      |            |
   Success       Error
      |            |
  Save ID    Identify error type
                   |
          +--------+---------+
          |                  |
   Duplicate key     Network/write concern
          |                  |
   Verify key         State may be ambiguous
   and payload        -> query, safe retry
          |
     Return appropriate business status
~~~

Do not use **insertedId** alone as proof that a business workflow has completed if the process still depends on other operations.

## 16. Common Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| insertOne automatically updates if _id already exists | insertOne inserts a new document; duplicate key results in an error |
| insertMany is a transaction because it sends one API command | Each document is written atomically on its own; the whole batch is not implicitly all-or-nothing |
| insertMany reporting an error means nothing was written | Partial success can occur before or alongside errors |
| ordered=false ignores errors and returns success | The command can still report an aggregate error; partial success must be handled |
| ordered=true automatically rolls back inserts before the error | It stops at the first error but does not automatically roll back already-written documents |
| insertedIds is an immutable ordered list of written positions across all drivers | Result shapes vary; mongosh/Node.js use index mapping, PyMongo uses a list |
| insertedId is the document count | insertedId is the _id key of the inserted document |
| _id is always an ObjectId | Applications can use strings, UUIDs, and other valid types |
| acknowledged=true means majority acknowledged | Acknowledgement level depends on the write concern |
| Network error always means the server did not insert | The server may have written it while the response was lost |
| Using w:0 still lets you know for sure each record was saved | No acknowledgement is requested, so there is no response evidence for that conclusion |
| insertMany always sends exactly one request to the server | The driver may split batches according to system limits |
| Unique index understands logically duplicate business documents | The index protects the configured key value; it does not infer business relationships |
| Having insertedId means the entire order-creation workflow is done | Insert only confirms writing that document, not payments or actions outside the database |

## 17. Practice Exercises with mongosh

The following exercises use the test database **insert_lab**. Run them in a learning environment separate from production data.

### Exercise 1: Insert One Document and Read the Result

~~~javascript
use insert_lab

const one = db.students.insertOne({
  studentCode: "SV001",
  fullName: "Nguyen Mai",
  active: true,
  createdAt: new Date()
});

printjson(one);

db.students.findOne({ _id: one.insertedId });
~~~

Answer:

1. What is the value of **acknowledged**?
2. Is **insertedId** the studentCode field?
3. When _id is not provided, what does the stored document's _id look like?
4. Can **one.insertedId** be used to query the newly added record?

### Exercise 2: Insert Multiple Documents

~~~javascript
const many = db.students.insertMany([
  {
    studentCode: "SV002",
    fullName: "Tran Binh",
    active: true
  },
  {
    studentCode: "SV003",
    fullName: "Le An",
    active: false
  }
]);

printjson(many);
~~~

Observe the **"0"** and **"1"** keys of **insertedIds**, and identify which input document each corresponds to.

### Exercise 3: Duplicate _id with ordered=true

~~~javascript
try {
  db.orderedExercise.insertMany(
    [
      { _id: "EX-01", score: 10 },
      { _id: "EX-01", score: 20 },
      { _id: "EX-03", score: 30 }
    ],
    { ordered: true }
  );
} catch (error) {
  print(error.message);
}

db.orderedExercise.find().sort({ _id: 1 });
~~~

Run this on a collection that does not yet have these _ids to see the result clearly. Explain why **EX-03** was not added even though that document itself does not have a duplicate key.

### Exercise 4: Duplicate _id with ordered=false

~~~javascript
try {
  db.unorderedExercise.insertMany(
    [
      { _id: "EX-01", score: 10 },
      { _id: "EX-01", score: 20 },
      { _id: "EX-03", score: 30 }
    ],
    { ordered: false }
  );
} catch (error) {
  print(error.message);
}

db.unorderedExercise.find().sort({ _id: 1 });
~~~

Point out the difference from Exercise 3. Why does the presence of document **EX-03** not mean the entire batch succeeded?

### Exercise 5: Using Client-Provided _id

~~~javascript
const result = db.lessons.insertOne({
  _id: "MONGODB-INSERT-01",
  title: "insertOne and insertMany"
});

printjson(result);
~~~

Compare **insertedId** in Exercise 5 with Exercise 1. Answer when to choose a client-generated _id instead of an auto-generated ObjectId.

### Exercise 6: Designing Retry Handling

Suppose a service sends a user creation request:

~~~text
requestId = REQ-001
email = member@example.test
~~~

MongoDB saved the document, but the client lost connection before receiving the response. The service does not know for sure whether the request succeeded.

Propose:

1. Which business key should remain stable across retries?
2. Which field should have a unique index to enforce the no-duplicates rule?
3. When a retry receives a duplicate key error, what needs to be verified?
4. Why can generating a new ObjectId on every retry lead to duplicate records?
5. In what cases should the application read back the state before returning a result to the user?

**Key takeaway:** insertOne and insertMany add new data to a collection, but when building real systems you must understand **per-document atomicity boundaries, batch processing order, driver result structures, write concerns, and the possibility of partial write success**. Only by distinguishing these aspects can an application handle inserts and retries reliably.

## References

- [MongoDB Manual — db.collection.insertOne()](https://www.mongodb.com/docs/manual/reference/method/db.collection.insertOne/)
- [MongoDB Manual — db.collection.insertMany()](https://www.mongodb.com/docs/manual/reference/method/db.collection.insertMany/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Java Sync Driver — Insert Documents](https://www.mongodb.com/docs/drivers/java/sync/current/usage-examples/insertOne/)
- [PyMongo — insert_one and insert_many](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/write/insert/)
