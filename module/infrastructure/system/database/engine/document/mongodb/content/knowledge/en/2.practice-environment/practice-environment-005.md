# Connecting with mongosh and Working with MongoDB Compass

## 1. Practice Objectives

This lesson is part of the **Practice Environment** chapter of **Database Engine Document MongoDB**. After completing it, you will be able to:

- Distinguish MongoDB Server, `mongosh`, and MongoDB Compass, and choose the right tool for each task.
- Connect to MongoDB running locally or to a MongoDB Atlas cluster using a connection string.
- Use `mongosh` to verify connectivity, select a database, create data, and perform CRUD, aggregation, and indexing operations.
- Work with the same data through the MongoDB Compass UI and observe changes across both tools.
- Identify and resolve common connection, authentication, and authorization errors.

Sample commands are designed to run on a **dedicated practice database**. When working with organizational databases, ensure you select the right environment and permissions before performing write or delete operations.

## 2. Three Components in a MongoDB Environment

| Component | Role | How to Recognize |
|---|---|---|
| **MongoDB Server** (`mongod` or Atlas-managed cluster) | Stores data and executes queries | Has host, port, accounts, and databases |
| **mongosh** | Command-line program for sending commands to MongoDB Server; supports interactive JavaScript | Type `mongosh` in terminal; shell prompt appears |
| **MongoDB Compass** | Graphical desktop app for browsing documents, filtering, editing, running aggregations, and inspecting indexes | Open the app and enter a connection string |

Both `mongosh` and Compass are **clients**. Installing both tools does not mean MongoDB Server is running. You can connect both clients to the **same server, database, and collection** to compare results.

MongoDB organizes data hierarchically:

~~~text
MongoDB Server / Cluster
└── Database: bookshop
    ├── Collection: books
    │   ├── Document: { _id: "bk001", title: "...", ... }
    │   └── Document: { _id: "bk002", title: "...", ... }
    └── Other collections (if any)
~~~

A database acts like a container for data; a collection groups documents; a document looks similar to JSON but is stored in BSON format, supporting additional types such as `ObjectId`, `Date`, and `Decimal128`.

## 3. Preparation Before Connecting

You need:

1. **An accessible MongoDB Server**: install and run MongoDB Community Server locally, use Docker with port mapping, or create a MongoDB Atlas cluster. The server must actually be running before connecting.
2. **mongosh**: install MongoDB Shell for your OS. Run `mongosh --version` in a terminal; if it reports command not found, check the installation and `PATH` variable.
3. **MongoDB Compass**: install and launch the application. UI layout or button labels may vary by version, but Connection, Documents, Aggregations, and Indexes serve the same purpose.
4. **Connection details**: host address, port, database name if needed, username/password if the server enforces authentication, and network/TLS configuration for remote connections.

If using a local server with default settings, the typical address is `127.0.0.1:27017`. In Docker environments, this address only works from the host when the container port is properly published. If using Atlas, copy the connection string from the cluster's **Connect** button, create a **database user** with the required roles, and allow your machine's IP address in the project's Network Access settings.

### 3.1. What Is a Connection String?

Two common URI formats:

~~~text
mongodb://HOST:PORT/DATABASE?option=value
mongodb+srv://CLUSTER_HOST/DATABASE?option=value
~~~

- `mongodb://`: typically used for direct connections to a server or list of servers. MongoDB's default port is `27017`.
- `mongodb+srv://`: uses DNS SRV records to discover cluster hosts; typically provided by Atlas. This form depends on DNS and usually uses TLS per cluster configuration.
- `DATABASE` after `/` sets the session's default database; it **does not automatically create** the database.
- Options such as `authSource=admin` specify the database used for authentication when the user was created in a different database.

Example local connection without authentication enabled:

~~~text
mongodb://127.0.0.1:27017/bookshop
~~~

If you must embed username and password directly in the URI, special characters in credentials must be percent-encoded per URI rules. In practice, prefer Compass's authentication dialog or `mongosh`'s interactive password prompt to avoid exposing passwords in terminal history, scripts, and screenshots.

## 4. Connecting and Verifying with `mongosh`

### 4.1. Connecting to Local MongoDB

Run in your **OS terminal**:

~~~bash
mongosh "mongodb://127.0.0.1:27017/bookshop"
~~~

If the server requires authentication, pass the username and let `mongosh` prompt for the password:

~~~bash
mongosh "mongodb://127.0.0.1:27017/bookshop" \
  --username demoUser \
  --authenticationDatabase admin \
  --password
~~~

The example above uses Bash-style line continuation `\`. In **PowerShell/Windows**, enter the full command on one line or use PowerShell's line continuation syntax. Replace `demoUser` and `admin` with your actual account; `admin` is only right if the user was created in that authentication database.

Once connected, the `mongosh` prompt appears. From here, enter **MongoDB Shell commands**, without prefixing `mongosh`:

~~~javascript
db.runCommand({ ping: 1 })
db.getName()
show dbs
show collections
~~~

Meaning:

- `db.runCommand({ ping: 1 })`: checks if the server responds; normally returns `ok: 1`.
- `db.getName()`: displays the current database, expected to be `bookshop`.
- `show dbs`: lists databases visible to the account; empty databases may not appear yet.
- `show collections`: lists collections in the current database.

You can also switch databases directly inside the shell:

~~~javascript
use bookshop
db.getName()
~~~

`use bookshop` only **switches context**. MongoDB normally does not show the database in `show dbs` until data or a collection is created.

End the session with:

~~~javascript
exit
~~~

### 4.2. Connecting to MongoDB Atlas

In Atlas, open the cluster connection dialog, choose **Shell**, and copy the `mongodb+srv://...` host provided by Atlas. Command pattern:

~~~bash
mongosh "mongodb+srv://cluster0.example.mongodb.net/bookshop" --username demoUser --password
~~~

`cluster0.example.mongodb.net` is only an **illustrative address**; replace it with your cluster's actual host. If connection fails, check in order: cluster is running, database user and password are correct, current network IP is allowed, DNS resolves SRV records, and internet connectivity works.

Immediately after connecting, verify with:

~~~javascript
db.runCommand({ ping: 1 })
db.getName()
~~~

With Atlas, an application account does not necessarily have permission to list all databases or manage users. Read/write permissions on the practice database are sufficient for the CRUD exercises below.

## 5. Creating a Sample Dataset from `mongosh`

To practice and compare results in Compass, we use the `bookshop` database and `books` collection. Each document describes a book with string, numeric, array, and nested object fields.

In the `mongosh` session, run:

~~~javascript
use bookshop

var sampleBooks = [
  {
    _id: "bk001",
    title: "MongoDB Fundamentals",
    author: "Minh",
    category: "Database",
    price: 280000,
    stock: 12,
    tags: ["mongodb", "nosql"],
    publisher: { name: "Tech Books", city: "Hanoi" }
  },
  {
    _id: "bk002",
    title: "MongoDB Aggregation",
    author: "Linh",
    category: "Database",
    price: 340000,
    stock: 5,
    tags: ["mongodb", "aggregation"],
    publisher: { name: "Tech Books", city: "Ho Chi Minh City" }
  },
  {
    _id: "bk003",
    title: "Java Backend",
    author: "Nam",
    category: "Backend",
    price: 320000,
    stock: 9,
    tags: ["java", "spring"],
    publisher: { name: "Practical Lab", city: "Da Nang" }
  },
  {
    _id: "bk004",
    title: "Designing REST APIs",
    author: "Ha",
    category: "Backend",
    price: 260000,
    stock: 0,
    tags: ["api", "rest"],
    publisher: { name: "Practical Lab", city: "Hanoi" }
  },
  {
    _id: "bk005",
    title: "Indexing for Applications",
    author: "Linh",
    category: "Database",
    price: 300000,
    stock: 7,
    tags: ["index", "performance"],
    publisher: { name: "Tech Books", city: "Da Nang" }
  }
];

sampleBooks.forEach(book => {
  db.books.replaceOne({ _id: book._id }, book, { upsert: true });
});

db.books.countDocuments({});
~~~

This snippet uses `replaceOne` with `upsert: true`: if a document with the matching `_id` does not exist, it inserts one; if it already exists, it replaces it with the sample data. That prevents duplicate `_id` errors when re-running, though it also **resets** any edits made to the 5 sample documents. Do not re-run this seed script when you want to keep modifications from exercises.

In a fresh database, `countDocuments({})` returns `5` after seeding. If the collection previously held other documents, the total may be greater than 5.

Here we use **string** `_id` values (`"bk001"`, ...), making cross-referencing in Compass easy. For documents without an explicit `_id`, MongoDB automatically generates an `ObjectId`; queries must always match the stored type of `_id`.

## 6. CRUD Operations in `mongosh`

CRUD stands for **Create**, **Read**, **Update**, and **Delete**. The following examples use the `db.books` collection created above.

### 6.1. Create: Insert a Document

~~~javascript
db.books.insertOne({
  _id: "bk006",
  title: "MongoDB Compass Practice",
  author: "An",
  category: "Tooling",
  price: 220000,
  stock: 4,
  tags: ["compass", "gui"],
  publisher: { name: "Tech Books", city: "Hanoi" }
});
~~~

The result returns `acknowledged: true` and `insertedId: "bk006"` on success. If you run it again without deleting `bk006`, the server throws a duplicate `_id` key error (typically containing `E11000 duplicate key`). To repeat the exercise, verify whether the document already exists before inserting again.

### 6.2. Read: Find and Project Fields

Find a single document by key:

~~~javascript
db.books.findOne({ _id: "bk001" })
~~~

Find all Database books priced at 300,000 or higher; return only title and price, sorted by price descending:

~~~javascript
db.books.find(
  { category: "Database", price: { $gte: 300000 } },
  { _id: 0, title: 1, price: 1 }
).sort({ price: -1 }).limit(10)
~~~

In the query above:

- The filter combines both conditions with implicit logical AND.
- `$gte` means **greater than or equal**.
- Projection `{ _id: 0, title: 1, price: 1 }` hides `_id` and retains only the two selected fields.
- `sort({ price: -1 })` sorts descending; `1` is ascending.
- `limit(10)` caps the number of returned documents.

Query a field inside a nested object and match a value in an array:

~~~javascript
db.books.find({ "publisher.city": "Hanoi" })
db.books.find({ tags: "mongodb" })
~~~

MongoDB uses **dot notation** to access `publisher.city`. When `tags` is an array, `{ tags: "mongodb" }` matches documents that contain an element equal to `"mongodb"`.

Count books currently in stock:

~~~javascript
db.books.countDocuments({ stock: { $gt: 0 } })
~~~

### 6.3. Update: Targeted Modifications

Increase `bk002`'s stock by 2 and mark it as featured:

~~~javascript
db.books.updateOne(
  { _id: "bk002" },
  {
    $inc: { stock: 2 },
    $set: { featured: true }
  }
);

db.books.findOne({ _id: "bk002" });
~~~

`$inc` adds to the current numeric value; `$set` updates or adds fields. The `updateOne` result includes `matchedCount` and `modifiedCount` so you can check whether a document matched and whether anything actually changed.

**Note:** replacing an entire document and updating specific fields are not the same. `replaceOne` replaces most of the existing document, whereas `updateOne` with `$set` preserves unspecified fields. Never attempt to alter an existing document's `_id`.

### 6.4. Delete: Remove the Right Document

~~~javascript
db.books.deleteOne({ _id: "bk004" });
db.books.findOne({ _id: "bk004" });
~~~

On success, `deletedCount` is `1` and the follow-up query returns `null`. If it was already deleted earlier, `deletedCount` will be `0`.

With real data, avoid running `deleteMany({})` or `dropDatabase()` unless you are certain of the database and scope: those commands can wipe broad datasets.

## 7. Basic Aggregation and Indexes in `mongosh`

Aggregation processes documents through **stages**. The example below considers only in-stock books, then calculates the book count and average price per category:

~~~javascript
db.books.aggregate([
  { $match: { stock: { $gt: 0 } } },
  {
    $group: {
      _id: "$category",
      soDauSach: { $sum: 1 },
      giaTrungBinh: { $avg: "$price" }
    }
  },
  { $sort: { soDauSach: -1, _id: 1 } }
]);
~~~

- `$match` filters inputs before grouping.
- `$group` groups by `category`, with `_id` as the group key.
- `$sum: 1` counts documents; `$avg: "$price"` computes the average price.
- `$sort` orders the output.

Indexes help MongoDB find and sort faster on suitable datasets. Try creating a **compound index**:

~~~javascript
db.books.createIndex({ category: 1, price: -1 });
db.books.getIndexes();

db.books.find({
  category: "Database",
  price: { $gte: 300000 }
}).explain("executionStats");
~~~

The `explain` output displays the execution plan and metrics such as `totalDocsExamined` and `totalKeysExamined`. You may see `IXSCAN` when using an index or `COLLSCAN` when scanning the collection. With **5–6 sample documents**, the query planner may legitimately choose a collection scan; do not conclude an index is broken based solely on a tiny dataset. Read counts and execution times also depend on data distribution, server version, and the selected plan.

## 8. Connecting with MongoDB Compass

Open MongoDB Compass and follow these steps:

1. Go to **New Connection** or the connections list and choose to create a connection.
2. Enter the URI for the same MongoDB Server used in `mongosh`. For local: `mongodb://127.0.0.1:27017/bookshop`.
3. If the server requires authentication, fill in the Authentication section or supply the appropriate URI. When using Atlas, obtain the URI from Atlas and verify network/TLS settings.
4. Click **Connect** (or **Save & Connect** to store the profile) to view the database list.
5. Open the `bookshop` database, then open the `books` collection to view documents in the **Documents** tab.

Across Compass versions, button locations may vary. What matters is confirming that **host/cluster, database, and collection** match your `mongosh` session.

If `bookshop` does not appear after connecting, confirm you ran the seed script from Section 5, refresh the database list, and verify you are connected to the right server. If the current user only has permissions on one database, the list may not show all databases in the cluster.

### 8.1. Filtering, Projecting, and Sorting Documents

In the **Documents** tab, Compass's Query Bar typically provides Filter, Project, Sort, Skip, Limit fields and a Find/Apply button. Enter the expressions below into their matching fields:

| Field in Compass | Value to Enter | Meaning |
|---|---|---|
| **Filter** | `{"category":"Database","price":{"$gte":300000}}` | Database books priced at 300,000 or higher |
| **Project** | `{"_id":0,"title":1,"price":1}` | Show only title and price |
| **Sort** | `{"price":-1}` | Price descending |
| **Limit** | `10` | Return at most 10 documents |

Click **Find** or **Apply** to run the query. Results should include `bk002` and `bk005` (unless modified or deleted).

Expressions in Compass are entered as JSON with **double quotes** around field names and strings. In `mongosh`, they are JavaScript objects where keys do not always need quotes. This is an **input syntax** difference, not a difference in query semantics.

Try another Filter matching a nested object field:

~~~json
{"publisher.city":"Hanoi"}
~~~

Or find books tagged `mongodb`:

~~~json
{"tags":"mongodb"}
~~~

### 8.2. Inserting, Editing, and Deleting Documents in Compass

**Insert:** in the Documents tab, select **Add Data → Insert Document** (or equivalent button), switch to JSON mode if needed, and enter:

~~~json
{
  "_id": "bk007",
  "title": "Notes from Compass",
  "author": "An",
  "category": "Tooling",
  "price": 190000,
  "stock": 3,
  "tags": ["compass"],
  "publisher": {
    "name": "Practical Lab",
    "city": "Hanoi"
  }
}
~~~

Click **Insert** to write. The input must be valid JSON: double quotes, numbers without thousands separators, and no trailing commas. `_id` must be unique in the collection. No mandatory schema needs to be declared per document in a default collection unless the server has validation rules configured.

**Edit:** filter with `{"_id":"bk007"}`, click the Edit action (usually a pencil icon), change `stock` from `3` to `8`, and confirm **Update/Save**. Refresh results to verify the new value.

**Delete:** with Filter `{"_id":"bk007"}`, click Delete on that document and confirm in the dialog. Re-run the Filter to confirm the document is gone. Deleting in Compass affects the server directly just like a delete command from `mongosh`.

If Compass lets you switch between Table/Tree/JSON views, changing the view only alters presentation; the document stored in MongoDB remains the same.

### 8.3. Building an Aggregation Pipeline in Compass

Open the **Aggregations** tab of the `books` collection and create a new pipeline. Depending on version, you can enter the full pipeline in **Text View** or add stages one by one in the stage builder. JSON form of the pipeline:

~~~json
[
  {
    "$match": {
      "stock": { "$gt": 0 }
    }
  },
  {
    "$group": {
      "_id": "$category",
      "soDauSach": { "$sum": 1 },
      "giaTrungBinh": { "$avg": "$price" }
    }
  },
  {
    "$sort": {
      "soDauSach": -1,
      "_id": 1
    }
  }
]
~~~

If the UI asks you to select each stage operator individually, choose `$match`, `$group`, and `$sort` in order and paste **each stage's inner body** rather than pasting the entire pipeline array into one box. Run the pipeline and compare against `db.books.aggregate([...])` in `mongosh`.

Compass can display a live preview for each stage, which is useful for seeing how documents are filtered or grouped. Results reflect the collection's state at runtime.

### 8.4. Inspecting and Creating Indexes in Compass

In the **Indexes** tab:

1. View existing indexes, including the default index on `_id` and `{category: 1, price: -1}` if created in Section 7.
2. If absent, open **Create Index**, add `category` ascending and `price` descending, and confirm.
3. Return to Documents and run a query on `category` and `price`. If Compass offers **Explain Plan**, open it to inspect the execution plan.

Avoid creating duplicate indexes with identical key patterns just to test the UI. Indexes speed up certain queries but consume storage and add write overhead; evaluate them against real workloads and dataset sizes.

Some Compass versions also include a **Schema** tab, which samples documents and visualizes field types and value distributions. This helps explore data shape, though it does not replace server-side schema validation if the application requires data constraints.

## 9. Verifying Both Clients Operate on the Same Data

The following test proves that `mongosh` and Compass act on the same server database:

1. In **Compass**, insert document `bk007` as in Section 8.2, without deleting it yet.
2. In **mongosh** connected to the same server/database, run:

   ~~~javascript
   db.books.findOne({ _id: "bk007" })
   ~~~

3. In `mongosh`, increment that document's stock:

   ~~~javascript
   db.books.updateOne(
     { _id: "bk007" },
     { $inc: { stock: 2 } }
   );
   ~~~

4. Return to **Compass**, refresh the Documents tab, and filter `{"_id":"bk007"}`. If the initial value was `3`, `stock` should now be `5`.
5. In Compass, change `stock` to `8`; then re-run `db.books.findOne({ _id: "bk007" })` in `mongosh`. The output should reflect `8`.
6. Delete `bk007` in Compass; confirm `findOne` in `mongosh` returns `null`.

If both sides do not show identical data, compare URI, hostname, active database (`db.getName()`), collection name, and active Filters. Data is not synced *between the two apps* via a special step; both simply read from and write to the same server.

## 10. Troubleshooting Common Issues

| Symptom | Common Cause | Remediation |
|---|---|---|
| `mongosh: command not found` or `mongosh is not recognized` | `mongosh` is not installed or its executable directory is not in `PATH` | Check version, install the right tool, and reopen the terminal |
| `ECONNREFUSED 127.0.0.1:27017` | Local MongoDB Server is not running or listens on another port | Check `mongod` process/service, port, and Docker port mappings |
| `Server selection timed out` | Cannot reach host/cluster, wrong address, firewall, or blocked network | Check URI, DNS, VPN, firewall, server status, and Atlas IP access list |
| `Authentication failed` | Wrong username/password or `authSource` | Verify database user and authentication database, re-enter password |
| `not authorized on ...` | Authenticated successfully, but lacks role for the operation | Verify the account's read/write roles for that database/collection |
| Cannot resolve `mongodb+srv` | DNS cannot query SRV records or hostname is wrong | Copy exact URI from Atlas, verify DNS and network connectivity |
| TLS/certificate error | Incorrect TLS settings or untrusted certificate | Check URI, certificates, and server/cluster TLS config; never disable TLS verification as a "quick fix" |
| Compass appears empty even though `mongosh` has data | Different host/database/collection, lingering filter, or unrefreshed UI | Compare URIs, run `db.getName()`, clear Filter, refresh |
| `E11000 duplicate key error` | Document with the same `_id` or unique key already exists | Check existing documents/indexes before inserting; use update/upsert appropriately |

To isolate issues, check **from connectivity to permissions to data**: does the server respond to `ping` → are you in the right database → is the collection visible → do you have query permissions → does the filter use the right data type.

Specifically, `"bk001"` (string) and `ObjectId("...")` are distinct types. In Compass, the Filter must match the stored `_id` type; do not wrap a string value in `ObjectId(...)` just because the field is named `_id`.

## 11. Self-Check Practice

Perform these steps sequentially on the `bookshop` database:

1. Connect via `mongosh`, run `ping`, and note the active database.
2. Re-seed the five sample books from Section 5, then open the `books` collection in Compass.
3. Filter books with `category` set to `Database` and `price` at least `300000`; sort price descending. On the sample data, the results are **MongoDB Aggregation (340,000)** and **Indexing for Applications (300,000)**.
4. Find books published in **Hanoi** via `publisher.city`, and find books tagged `mongodb` via `tags`.
5. Use `mongosh` to increase `bk002`'s stock from `5` to `7`; refresh Compass to verify.
6. Run an aggregation grouping by `category` for books with `stock > 0` and observe the differences between the two groups.
7. Inspect the `category`/`price` compound index in Compass; run Explain and explain why `IXSCAN` may not appear on tiny datasets.
8. Insert a document with a new `_id` using Compass, read it back in `mongosh`, and delete it after confirming.

Quick reference commands:

~~~javascript
db.runCommand({ ping: 1 });
db.getName();
db.books.find({ category: "Database", price: { $gte: 300000 } })
        .sort({ price: -1 });
db.books.find({ "publisher.city": "Hanoi" });
db.books.find({ tags: "mongodb" });
db.books.findOne({ _id: "bk002" });
db.books.getIndexes();
~~~

Execute the seeding and stock update steps in order. If you re-run `replaceOne(..., {upsert:true})`, the sample data resets to its initial state.

## 12. Notes for Real-World Projects

- **Use `mongosh`** for quick connection checks, repeatable commands, controlled maintenance scripts, and inspecting raw MongoDB responses.
- **Use Compass** to visually browse documents, test Filter/Projection/Sort expressions, build pipelines stage by stage, and inspect indexes and field types.
- **Always verify the environment** (local, staging, production), database, and collection before any write/delete operation. Practice accounts should receive only minimal required privileges.
- **Never expose passwords** or URIs containing credentials in repositories, shared command histories, public documentation, or screenshots. Store connection profiles locally according to your organization's security policy.
- **Run a read query with your Filter before updating/deleting** important data; inspect matching document counts and `matchedCount`, `modifiedCount`, `deletedCount`.
- **Distinguish UI state from actual data**: saved changes in Compass affect MongoDB Server and will appear in `mongosh` whenever a client queries the same server.

With the same connection string and appropriate permissions, you can move seamlessly between CLI operations and the graphical interface without exporting or importing data between `mongosh` and Compass.
