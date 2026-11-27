# MongoDB: Database, Collection, Document, Field, and Namespace

MongoDB is a document-oriented database management system (document database). Rather than starting from tables and rows as in relational databases, MongoDB organizes data into **database → collection → document → field**. Each collection also has a **namespace** so MongoDB can distinguish it from other collections in the system.

Understanding these five concepts helps you read data structures accurately, write correct queries, and decide where to place information when designing an application.

## 1. The Big Picture: Where Does Data Live?

Suppose we are building a bookstore system. A MongoDB deployment can contain a **bookstore** database; inside that database are the **books**, **customers**, and **orders** collections; each collection holds documents; and each document holds fields.

~~~text
MongoDB deployment
└── Database: bookstore
    ├── Collection: books                  Namespace: bookstore.books
    │   ├── Document: book A
    │   │   ├── _id
    │   │   ├── title
    │   │   ├── price
    │   │   ├── author
    │   │   │   ├── name
    │   │   │   └── country
    │   │   └── tags
    │   └── Document: book B
    ├── Collection: customers              Namespace: bookstore.customers
    │   └── Document: customer A
    └── Collection: orders                 Namespace: bookstore.orders
        └── Document: order A
~~~

| Concept | Role | Example |
| --- | --- | --- |
| **Database** | Logical grouping of related collections | bookstore |
| **Collection** | Group of documents within the same database | books |
| **Document** | Data record in BSON structured format | A book with ISBN, title, price, and author |
| **Field** | Name–value pair inside a document | title, price, author.name |
| **Namespace** | Fully qualified name of a collection scoped by its database | bookstore.books |

This is a **logical structure** for working with data. These concepts do not necessarily correspond one-to-one with a directory or a physical file on disk.

## 2. Database: The Space for Organizing Data

A **database** is a logical organizational unit containing collections. A MongoDB deployment can manage multiple databases; different databases can have collections with the same name while remaining independent in identity.

For example:

~~~text
bookstore.books
bookstore.orders
analytics.events
analytics.reports
~~~

In this case, **bookstore** and **analytics** are two databases; **books**, **orders**, **events**, and **reports** are collections.

### Selecting a Database in mongosh

In MongoDB Shell (**mongosh**), the following command switches the current context to the **bookstore** database:

~~~javascript
use bookstore
~~~

You can check the current context and list collections:

~~~javascript
db.getName()
db.getCollectionNames()
show dbs
~~~

Three actions should be distinguished:

- **use bookstore** only selects the database for subsequent commands. It does not by itself guarantee that the database has been persisted as a populated database.
- A database appears when data or a collection is actually created, such as after a valid write operation.
- **show dbs** lists the databases that the current account has permission to see; the result also depends on whether the database already has data or created metadata.

You can also access another database without changing how you think about data structure:

~~~javascript
const reportingDb = db.getSiblingDB("analytics");
reportingDb.getCollectionNames();
~~~

### When Should You Split Databases?

Splitting databases is useful when data domains differ in application ownership, access permissions, administrative requirements, or operational lifecycle. However, **a database does not by itself create an absolute security boundary**: access permissions must be configured using MongoDB's authentication and authorization mechanisms.

You should not by default create a new database for every type of document. If data types belong to the same application and need to be managed together, multiple collections within one database are usually a clear starting point.

## 3. Collection: A Group of Documents

A **collection** is a set of documents residing in a database. A collection is analogous to a *table* in a relational database, but documents in a collection **are not required to have the exact same set of fields**.

For example, two documents in the **books** collection can differ:

~~~javascript
{
  title: "MongoDB Fundamentals",
  price: 180000,
  authors: ["Nguyen An"]
}

{
  title: "Document Data Modeling",
  price: 240000,
  authors: ["Tran Binh"],
  ebookAvailable: true,
  editions: [1, 2]
}
~~~

The second document has additional **ebookAvailable** and **editions** fields. This is a characteristic of a *flexible schema* data model. However, flexibility does not mean every document should have an arbitrary structure: the application still needs consistency in field meanings, data types, and necessary constraints.

### Creating and Viewing Collections

~~~javascript
use bookstore

// Create a collection explicitly.
db.createCollection("books");

// List collections in the current database.
show collections

// Get the collection object for querying.
db.getCollection("books")
~~~

In standard write scenarios, MongoDB can automatically create a collection when inserting the first document into a non-existent collection:

~~~javascript
db.customers.insertOne({
  name: "Le Minh",
  memberSince: new Date()
});
~~~

To configure a collection type or special options, explicit creation may be necessary.

### What Does a Collection Manage?

- **A set of documents** belonging to the same data domain, such as books or orders.
- **Indexes** for queries and constraints; indexes are defined per collection, not separately per document.
- **Validation rules** when you need to control data types, required fields, and accepted structures.
- Collection-specific options as required, such as specialized collection types.

MongoDB typically creates an index on the **_id** field when a collection is created. This field serves as the basis for identifying a document within the collection. When using sharding, additional rules regarding the scope of index uniqueness enforcement must be understood.

Example of adding a unique index on the ISBN code:

~~~javascript
db.books.createIndex(
  { isbn: 1 },
  { unique: true }
);
~~~

This index helps prevent two documents in the **books** collection from sharing the same **isbn** value according to unique index rules. A collection can have multiple indexes for different query needs.

### A Collection Is Not a Folder of JSON Files

A collection has administrative operations, indexes, queries, and authentication/authorization policies. MongoDB stores data in BSON format and manages storage via its storage engine; comparing a collection to a “folder containing many JSON files” is only an illustrative analogy and does not describe how the system actually stores data.

## 4. Document: The Fundamental Unit of Data

A **document** is a data unit structured as a set of **field–value** pairs. You can think of a document as similar to a JavaScript object or a data object in a Java application, except MongoDB data is represented in **BSON (Binary JSON)**.

Example of a document representing a book in the **bookstore.books** collection:

~~~javascript
{
  _id: ObjectId("6739a00a21f4b2a1c10e1111"),
  isbn: "9786040000123",
  title: "Introduction to MongoDB",
  price: NumberDecimal("199000.00"),
  stock: 12,
  available: true,
  publishedAt: ISODate("2024-09-15T00:00:00Z"),
  author: {
    name: "Nguyen An",
    country: "VN"
  },
  tags: ["database", "mongodb", "backend"],
  description: null
}
~~~

The document above has:

- Simple fields such as **isbn**, **title**, **stock**, **available**.
- An **embedded document** in the **author** field, containing two subfields **name** and **country**.
- An **array** in the **tags** field.
- BSON types such as **ObjectId**, **Decimal128**, and **Date**.
- A **description** field with the value **null**.

This example uses mongosh display syntax. When exporting data to standard JSON or Extended JSON, the representation of special BSON types may differ.

### The Role of the _id Field

Every document in a standard collection needs an **_id** field as its identifier. If the client does not provide one, the driver or MongoDB typically generates a value automatically (commonly an **ObjectId**).

~~~javascript
db.books.insertOne({
  isbn: "9786040000123",
  title: "Introduction to MongoDB",
  stock: 12
});
~~~

After insertion, the stored document has an **_id** added, even though the initial insert operation did not declare this field.

**_id** does not have to be an ObjectId: other valid types, such as string, can be used when there is a clear design reason. Even so, changing the identifier strategy should be considered carefully because **_id** is a stable identifier and cannot be modified with a regular update operation.

An **_id** value is meaningful within the scope of a collection. Two different collections can contain documents with the same **_id**, because their namespaces differ.

### How Does BSON Differ from JSON?

Standard JSON has common types such as string, number, boolean, null, object, and array. BSON also supports database-oriented data types, including:

| Data Category | Representation in mongosh | When Used |
| --- | --- | --- |
| String | "Introduction to MongoDB" | Text, string-based identifiers |
| Int32 / Int64 | NumberInt(12), NumberLong("9000000000") | Integers according to required range |
| Double | 3.14 | Floating-point values when appropriate |
| Decimal128 | NumberDecimal("199000.00") | Decimal values requiring precision, such as money |
| Boolean | true | True/false status |
| Date | ISODate("2024-09-15T00:00:00Z") | Timestamps |
| ObjectId | ObjectId("6739a00a21f4b2a1c10e1111") | Commonly used identifier |
| Array | ["database", "mongodb"] | List of values |
| Embedded document | { name: "Nguyen An" } | Group of nested data |
| Null | null | Explicitly stored null value |

You should not assume every number in MongoDB has the same type. The same displayed value can belong to different BSON types; this affects arithmetic, data conversion, and how the application handles it.

**Size limit:** A standard BSON document has a maximum size of **16 MiB**. For large data such as binary files, an appropriate storage method is required, such as GridFS for suitable cases, rather than trying to pack everything into a single document.

### Embedded Documents and Referencing

MongoDB allows storing related data directly inside a parent document:

~~~javascript
{
  orderNumber: "ORD-1001",
  customer: {
    name: "Le Minh",
    phone: "0900000000"
  },
  items: [
    { isbn: "9786040000123", quantity: 2, unitPrice: 199000 },
    { isbn: "9786040000456", quantity: 1, unitPrice: 150000 }
  ]
}
~~~

This approach fits when components are frequently read together and share a closely coupled lifecycle. For relationships with a very large number of elements or data that needs independent updates, documents can be stored in separate collections and referenced by ID.

For example, an order can store **customerId** pointing to a customer document in **bookstore.customers**. MongoDB does not automatically turn every ID field into a foreign key like a relational DBMS; the application and data design determine how consistency is managed. Aggregation can combine data across collections using mechanisms like **$lookup** when appropriate.

## 5. Field: Names and Values Inside a Document

A **field** is a pair consisting of a **field name (key)** and a **value**. Field names identify the information to read, filter, or update; values can be simple BSON types or nested structures.

Example:

~~~javascript
{
  title: "Introduction to MongoDB",
  stock: 12,
  author: {
    name: "Nguyen An",
    country: "VN"
  },
  tags: ["mongodb", "backend"]
}
~~~

In this document, **title**, **stock**, **author**, and **tags** are top-level fields. **name** and **country** are fields of the document nested inside **author**.

### Fields and Dot Notation

MongoDB supports **dot notation** to access nested field paths:

~~~javascript
// Filter books whose author is from VN.
db.books.find({ "author.country": "VN" });

// Return only title and author name, hiding _id.
db.books.find(
  { stock: { $gt: 0 } },
  { _id: 0, title: 1, "author.name": 1 }
);

// Update a subfield while preserving other fields in author.
db.books.updateOne(
  { isbn: "9786040000123" },
  { $set: { "author.country": "VN" } }
);
~~~

In the example above:

- **author** is a field whose value is an embedded document.
- **author.country** is a *field path* used to access **country** inside **author**.
- **$gt** is the “greater than” operator, and **$set** is an update operator. Symbols starting with **$** here are MongoDB operator syntax.

**author.country is not a namespace.** It is a path name inside a document. A namespace identifies a collection at the database level, whereas this dot notation accesses structure inside a document.

### Arrays Can Also Be a Field's Value

~~~javascript
{
  title: "Introduction to MongoDB",
  tags: ["database", "mongodb", "backend"],
  reviews: [
    { user: "an", stars: 5 },
    { user: "binh", stars: 4 }
  ]
}
~~~

Queries can match elements of an array:

~~~javascript
// Match documents if the tags array contains the element "mongodb".
db.books.find({ tags: "mongodb" });

// Find documents with at least one review where stars = 5.
db.books.find({ "reviews.stars": 5 });
~~~

If you need to require **multiple conditions to hold on the same array element**, use an appropriate operator such as **$elemMatch**:

~~~javascript
db.books.find({
  reviews: {
    $elemMatch: { user: "an", stars: 5 }
  }
});
~~~

### A Missing Field Differs from a Field with Value null

The following two documents have different meanings:

~~~javascript
{ name: "An", email: null }
{ name: "Binh" }
~~~

The first document has the **email** field stored with the value **null**. The second document **does not have an email field**.

In MongoDB, the following query normally matches **both null fields and missing fields**:

~~~javascript
db.customers.find({ email: null });
~~~

Appropriate operators must be used to distinguish them:

~~~javascript
// Only documents that have the email field, even if its value is null.
db.customers.find({ email: { $exists: true } });

// Only documents where email has BSON type Null.
db.customers.find({ email: { $type: "null" } });

// Only documents without the email field.
db.customers.find({ email: { $exists: false } });
~~~

This distinction is very important when checking for missing data, creating validation rules, or writing business conditions.

### Field Naming and Maintaining Schema Consistency

Use short, meaningful field names with consistent casing, such as **createdAt**, **customerId**, and **totalAmount**. Avoid creating **phone**, **phoneNumber**, and **telephone** for the same concept without a clear reason.

MongoDB has specific rules regarding field names, especially the **.** character and the **$** sign. Some versions support storing names containing those characters, but querying/updating, path resolution, export/import, and tooling can become complicated. For standard application schemas, avoid using **.** or names starting with **$** as actual field names so they are not confused with dot notation and operator syntax.

## 6. Namespace: The Full Name of a Collection

A **namespace** is typically written in the following pattern:

~~~text
<database-name>.<collection-name>
~~~

Examples:

~~~text
bookstore.books
bookstore.customers
bookstore.orders
analytics.events
~~~

In **bookstore.books**:

- **bookstore** is the database name.
- **books** is the collection name.
- **bookstore.books** is the full namespace of that collection.

A namespace serves to identify an object within a MongoDB deployment. Two collections with the same name belonging to different databases have different namespaces:

~~~text
bookstore.orders     -> Orders of the bookstore system
archive.orders       -> Orders stored in the archive database
~~~

The two names above do not refer to the same collection. Similarly, **bookstore.books** and **bookstore.customers** are two distinct namespaces even though they belong to the same database.

### Viewing Namespaces in mongosh

~~~javascript
use bookstore

db.getName();                  // "bookstore"
db.books.getName();            // "books"
db.books.getFullName();        // "bookstore.books"
~~~

You can work with collections whose names are inconvenient to write with standard property syntax using **getCollection**:

~~~javascript
db.getCollection("order-items").findOne();
~~~

### Distinguishing Namespace, Field Path, and _id

These three concepts often share dots or identifiers, but their meanings differ:

| Expression | Meaning | Level |
| --- | --- | --- |
| bookstore.books | Namespace of the **books** collection | Database + collection |
| author.country | Path to a subfield inside a document | Document + field |
| _id: ObjectId(...) | Identifier of a document | Document |
| bookstore.orders | Namespace of the **orders** collection | Database + collection |

If you encounter an expression like **bookstore.books.author.country** in an explanatory diagram, understand that **bookstore.books** locates the collection and **author.country** describes a field path *inside* a document of that collection. This is just a combined notation for explanation, not a new collection namespace.

In a Java program, you can store a namespace as two components: **databaseName** and **collectionName**. Drivers usually accept these two names separately:

~~~java
MongoDatabase database = mongoClient.getDatabase("bookstore");
MongoCollection<Document> books = database.getCollection("books");
~~~

In this example, the logical namespace value of the **books** collection is **bookstore.books**. The example code assumes **mongoClient** has already been created and the necessary MongoDB Java Driver classes have been imported.

### Naming Considerations

Choose database and collection names that are meaningful, stable, easy to search, and compliant with the naming limits of the MongoDB version in use. Do not create application collections with system-reserved names, such as names starting with **system.**. Avoid designs that rely on special characters that are difficult to handle across environments.

Renaming a collection changes the namespace used by the application; query code, permissions, configurations, and related processes may need to be updated accordingly. Therefore, the namespace is part of the data contract between the application and the database.

## 7. Complete Example: From Database to Field

Suppose we need to store a book catalog. The steps in **mongosh** show how each concept appears in real operations.

### Step 1: Select the Database and Create a Collection

~~~javascript
use bookstore

db.createCollection("books");
~~~

At this point:

- Selected database: **bookstore**.
- Created collection: **books**.
- Collection namespace: **bookstore.books**.

### Step 2: Insert Two Documents

~~~javascript
db.books.insertMany([
  {
    isbn: "9786040000123",
    title: "Introduction to MongoDB",
    category: "Database",
    price: NumberDecimal("199000.00"),
    stock: 12,
    author: { name: "Nguyen An", country: "VN" },
    tags: ["mongodb", "backend"],
    createdAt: new Date()
  },
  {
    isbn: "9786040000456",
    title: "Document Data Modeling",
    category: "Database",
    price: NumberDecimal("249000.00"),
    stock: 5,
    author: { name: "Tran Binh", country: "VN" },
    tags: ["mongodb", "modeling"],
    createdAt: new Date(),
    ebookAvailable: true
  }
]);
~~~

After the write operation:

- The **bookstore.books** collection has two documents (assuming the operation succeeded on an initially empty collection).
- Each document has an **_id** field generated by the system/client when not provided.
- Both documents share **isbn**, **title**, and **price**, but the second document also has **ebookAvailable**.
- **author** is an embedded document; **tags** is an array.

### Step 3: Read and Filter Data

~~~javascript
// Read all books, displaying only title and price.
db.books.find(
  {},
  { _id: 0, title: 1, price: 1 }
);

// Find books with an author from VN that are in stock.
db.books.find({
  "author.country": "VN",
  stock: { $gt: 0 }
});

// Find an exact ISBN.
db.books.findOne({ isbn: "9786040000123" });
~~~

Here, **db** represents the current database, **books** is the collection, the conditions inside **find** filter documents, and individual names like **stock** and **author.country** specify fields.

### Step 4: Update a Field

~~~javascript
db.books.updateOne(
  { isbn: "9786040000123" },
  {
    $inc: { stock: -1 },
    $set: { "author.country": "VN" }
  }
);
~~~

**$inc** changes the numeric value of the **stock** field; **$set** assigns the value of the subfield. This action updates a document selected by ISBN rather than changing the namespace or creating another collection.

### Step 5: Check Collection Names

~~~javascript
db.getName();
db.books.getName();
db.books.getFullName();
~~~

From there you can map:

~~~text
Database             bookstore
Collection           books
Namespace            bookstore.books
A document           book with ISBN 9786040000123
Top-level fields     isbn, title, category, price, stock, author, tags, createdAt
Nested fields        author.name, author.country
~~~

This is the essential chain of information to identify when reading API documentation or error logs: **which database, which collection, which document, and which field is being operated on**.

## 8. Relationship to Relational Databases

If you are already familiar with SQL, you can use the following table as an initial bridge:

| Relational Database | MongoDB | Key Point to Remember |
| --- | --- | --- |
| Database/schema (depends on DBMS) | Database | Logical grouping has similarities; administration is not identical |
| Table | Collection | Collections allow documents with different structures |
| Row | Document | Documents can contain nested objects and arrays |
| Column | Field | Fields can be absent or have complex structures |
| Primary key | _id | Used to identify a document; data type can be chosen |
| Fully qualified table name | Namespace | Usually formatted as database.collection |

You should not infer from the comparison table that every field is a fixed column, or that a document is always normalized into multiple tables. MongoDB typically designs schemas around **how the application reads and updates data**.

Example of an order system:

- In SQL, orders and line items are usually two linked tables.
- In MongoDB, line items can be an **items** array inside the order document, if access patterns and size fit.
- If the related list grows unboundedly or has an independent lifecycle, you can choose multiple collections and store references.

These choices belong to data model design; they do not change the fundamental definitions of database, collection, document, field, and namespace.

## 9. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| Running **use bookstore** means a populated database has been created | This command mainly selects the context; data/collections must be actually created |
| A collection enforces a rigid schema like a table | Documents can differ in fields; use conventions and validation when needed |
| Each document is a separate JSON file | A document is a BSON data unit managed by MongoDB |
| Every document in MongoDB has a globally unique _id across the system | Identification is scoped per collection; multiple collections can contain the same _id value |
| **author.country** is a namespace | This is a nested field path; an example namespace is **bookstore.books** |
| A missing field and a null field are the same | They differ; queries like **{ email: null }** require special care because they can match both |
| You can update _id like a normal field | _id is an immutable identifier in standard update operations |
| Schema flexibility means no data control is needed | Consistent structure and data type checks are still necessary for application reliability |

A helpful rule when reading a MongoDB query is to always identify components in order: **current database → target collection → document selection filter → fields being read or updated**. This order clarifies which part of the system is being affected.

## 10. Self-Exploration Practice Exercise

Practice in a separate test database to identify all five concepts. The following commands work with **mongosh**:

~~~javascript
use school_demo

db.students.insertOne({
  studentCode: "SV001",
  fullName: "Nguyen Mai",
  active: true,
  contact: {
    city: "Da Nang",
    email: null
  },
  skills: ["Java", "MongoDB"]
});

db.students.find(
  { "contact.city": "Da Nang" },
  { _id: 0, studentCode: 1, fullName: 1, skills: 1 }
);

db.students.getFullName();
~~~

From this example, you can identify:

1. **Database:** school_demo.
2. **Collection:** students.
3. **Namespace:** school_demo.students.
4. **Document:** the record of the student with **studentCode** equal to **SV001**.
5. **Field:** **fullName**, **active**, **contact**, **skills**; **contact.city** and **contact.email** are nested field paths.

Try adding a student without the **contact.email** field, then compare query results using **$exists** and **$type**. This exercise lets you directly observe the difference between a **missing field** and a **field with a null value**, while reinforcing the use of namespaces and dot notation.
