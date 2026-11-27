# Creating, Listing, Selecting, and Dropping Databases or Collections in MongoDB

MongoDB organizes data according to the hierarchy **deployment → database → collection → document**. Before writing CRUD queries, learners need to know which database they are operating on, which collections already exist, how to create new objects, and the impact of dropping them. This is a foundational set of operations that also ties directly to access control, deployment, and data safety: a `dropDatabase()` command executed in the wrong context can wipe out an entire application's data.

This lesson uses **mongosh** for illustration. Examples assume you have an accessible MongoDB server, are running commands in a **dedicated lab environment**, and have appropriate privileges. Do not run the drop sections on a database containing data you need to keep.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the relationship between a database, a collection, and a document.
2. **Select** a database in mongosh using `use` or `db.getSiblingDB()` and understand that selecting does not necessarily mean creating.
3. **Create** a database by initializing a collection or writing the first document; explicitly create a collection via `db.createCollection()`.
4. **List** databases and collections using interactive commands or scriptable APIs.
5. **Inspect** the current context, existence, and metadata of a collection before operating on it.
6. **Drop** a single collection or an entire database intentionally, understanding the scope of data loss.
7. Distinguish deleting documents from dropping a collection or dropping a database; handle common errors and access-permission issues.

## 2. Hierarchical Model: Database, Collection, and Document

~~~mermaid
flowchart TD
    Deployment["MongoDB deployment"] --> DB1["Database: training_store"]
    Deployment --> DB2["Database: analytics"]
    DB1 --> C1["Collection: books"]
    DB1 --> C2["Collection: members"]
    DB1 --> C3["Collection: borrow_records"]
    DB2 --> C4["Collection: daily_reports"]
    C1 --> D1["Document {_id, title, ...}"]
    C1 --> D2["Document {_id, title, ...}"]
~~~

| Component | Role | Example |
|---|---|---|
| Deployment | A standalone server, replica set, or sharded cluster providing MongoDB | A local MongoDB server or a deployed cluster |
| Database | A logical namespace containing collections; also a boundary for access control and administration | `training_store` |
| Collection | A grouping of documents that may have its own validator, indexes, and storage options | `books` |
| Document | A BSON record composed of fields; typically contains a unique `_id` within the collection | `{_id: "b-001", title: "MongoDB Basics"}` |

If you are familiar with SQL, you can think of a database as roughly analogous to a database, a collection to a table, and a document to a row. However, MongoDB allows flexible document structures with nested arrays/objects and several schema validation, indexing, and collection type mechanisms that differ from relational tables.

**A named database does not equate to a physically existing database.** MongoDB can return a database reference handle so you can write commands, without yet creating storage resources for that database.

### A Running Example

We will use a study library management system:

~~~text
training_store (database)
  books (collection)
    {_id: "b-001", title: "MongoDB Basics", year: 2025}
  members (collection)
    {_id: "m-001", name: "Lan"}
  borrow_records (collection)
    {_id: "r-001", bookId: "b-001", memberId: "m-001"}
~~~

`training_store` is a name used only for practice exercises. If your environment already has a database with the same name, choose a different lab name and substitute it consistently across all commands.

## 3. Preparing mongosh and Verifying Your Connection

### 3.1. Opening a Connection

For example, on a lab machine where MongoDB listens on loopback:

~~~bash
mongosh "mongodb://127.0.0.1:27017"
~~~

In a managed environment, use the connection string provided by your administrator and configure TLS and authentication according to your environment's guidelines. Do not put passwords into documentation, commits, logs, or screenshots. Never expose an unauthenticated MongoDB instance to the Internet just for practice.

In mongosh:

~~~javascript
// Check connectivity to the server.
db.runCommand({ ping: 1 })

// View the database currently selected in the shell.
db.getName()

// Display the connected host/address according to shell info.
db.getMongo()
~~~

A successful `ping` result typically contains `ok: 1`. The `db.getName()` command only returns the database name in the **current context**; it does not prove that the database contains data or has been created.

### 3.2. Operate Only in the Lab Database

Before running any write, drop, or create-collection examples, always verify:

~~~javascript
db.getName()
~~~

Do not guess the current database from previously executed command history: different shells, connection sessions, or script files may select different contexts.

## 4. Selecting a Database: `use` and `getSiblingDB()`

### 4.1. Using the `use` Command in mongosh

~~~javascript
use training_store
db.getName()
~~~

From that point on, `db` in subsequent mongosh commands points to `training_store`:

~~~javascript
// After "use training_store":
db.getCollectionNames()
db.books.findOne()
~~~

`use` is a **mongosh shell helper**, not standard JavaScript syntax. You type `use training_store` directly at the prompt; do not place it inside a JavaScript function or treat it as a MongoDB wire-protocol statement.

### 4.2. Using `db.getSiblingDB()` in JavaScript

When writing scripts or working with another database without relying on `use`:

~~~javascript
const trainingDb = db.getSiblingDB("training_store")

print(trainingDb.getName())          // training_store
printjson(trainingDb.getCollectionNames())
~~~

You can also chain calls directly:

~~~javascript
db.getSiblingDB("training_store").books.findOne()
~~~

`getSiblingDB()` returns a handle to the target database on the same connection; creating the handle **does not automatically create the database on storage**. This is a convenient way for scripts to explicitly specify the database they manage without depending on where the shell user happens to be positioned.

### 4.3. Selecting Is Not Creating

~~~javascript
use temporary_empty_demo
db.getName()            // "temporary_empty_demo"
show dbs                // May not show temporary_empty_demo yet.
show collections        // No collections yet.
~~~

Simply typing `use temporary_empty_demo` does not make the database appear in the list. MongoDB typically materializes a database when a collection is created or when data is written for the first time. Listing also depends on account permissions and deployment state.

**Remember:** `use` = select context; `createCollection` or an appropriate write operation = create an actual object.

## 5. Creating a Database in MongoDB

There is no dedicated shell command equivalent to the common SQL `CREATE DATABASE name` for creating an empty database as a persistent object. Instead, you **select a name** and then **create a collection or insert a document**.

### 5.1. Method 1 — Creating a Database via an Explicit Collection

~~~javascript
use training_store

db.createCollection("books")
db.getCollectionNames()
~~~

If the database does not yet exist, creating the collection brings the database into existence. The `books` collection may be empty at that point, but it is an explicitly created collection.

`db.createCollection(name, options)` is useful when you need to create a collection with special options, even though MongoDB can auto-create collections in simpler scenarios.

### 5.2. Method 2 — Implicitly Creating a Database/Collection When Writing a Document

~~~javascript
use training_store

db.members.insertOne({
  _id: "m-001",
  name: "Lan",
  joinedAt: new Date(),
  active: true
})
~~~

If `members` does not exist yet, the write operation can **automatically create the `members` collection**, while also creating the `training_store` database if it does not yet exist. Afterward:

~~~javascript
show collections
show dbs
~~~

Re-running an insert with the same `_id` will raise a duplicate-key error; do not mistake that for MongoDB failing to create the collection.

### 5.3. Comparing the Two Creation Approaches

| Criterion | `db.createCollection("books")` | `db.books.insertOne({...})` |
|---|---|---|
| When is the collection actually created? | When the call succeeds | On the first write to a nonexistent collection name, if writes are permitted |
| Requires an initial document? | No | Yes |
| Configure collection options at creation? | Yes | Cannot pass collection options through `insertOne` |
| Best suited for | Initializing schema, validators, capped/time-series collections, or configuration management | Standard collections created implicitly by an application |
| When the collection already exists | Typically raises a namespace-already-exists error | Inserts the new document if valid |

In production environments, collection creation should follow a clear schema/index/validation change process; letting an application auto-create arbitrary collections from typos in collection names can make management difficult.

## 6. Creating Collections Explicitly and Initial Configuration

### 6.1. Standard Collection

~~~javascript
use training_store

db.createCollection("borrow_records")

// List to verify.
db.getCollectionNames()
~~~

To reference collection names flexibly, especially names containing hyphens:

~~~javascript
db.getCollection("books").findOne()
// Example collection named "book-events":
db.getCollection("book-events").findOne()
~~~

Avoid using `db.book-events`: JavaScript interprets the hyphen as subtraction between two expressions rather than a collection name.

### 6.2. Creating a Collection with Schema Validation

For example, a `catalog_items` collection requiring a title, item kind, and creation timestamp:

~~~javascript
db.createCollection("catalog_items", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["title", "kind", "createdAt"],
      properties: {
        title: {
          bsonType: "string",
          minLength: 1
        },
        kind: {
          enum: ["BOOK", "MAGAZINE"]
        },
        createdAt: {
          bsonType: "date"
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
})
~~~

Inserting valid data:

~~~javascript
db.catalog_items.insertOne({
  _id: "cat-001",
  title: "MongoDB Handbook",
  kind: "BOOK",
  createdAt: new Date()
})
~~~

An insert missing `createdAt` will be rejected by the validator under the configuration above. A **collection with a validator does not have to match every other collection in the same database**; each collection carries options appropriate to its data type.

If you need to modify the validator on an existing collection, MongoDB provides administrative mechanisms such as `collMod`. Do not call `createCollection` again expecting it to update the options of an existing collection.

### 6.3. Creating Indexes After Collection Creation

~~~javascript
db.books.createIndex(
  { isbn: 1 },
  {
    name: "uq_books_isbn",
    unique: true,
    partialFilterExpression: { isbn: { $type: "string" } }
  }
)

db.books.getIndexes()
~~~

This is an **additional** step, not something automatically included when calling `createCollection("books")`. Every standard collection has an index on `_id`; business-specific indexes must be designed separately. In the example above, the unique index ensures string ISBN values are unique within `books`. Creating a unique index can fail if existing data violates the constraint.

### 6.4. Specialized Collections Must Be Chosen at Creation Time

MongoDB offers specialized collection types and options. For example, a capped collection with a fixed size limit:

~~~javascript
db.createCollection("recent_lab_events", {
  capped: true,
  size: 1024 * 1024,
  max: 1000
})
~~~

Capped collections have different behaviors and limitations compared to standard collections, such as configured storage size and document count limits. Do not use a capped collection as a general-purpose retention mechanism for all workloads without understanding how older data is overwritten and what operation constraints apply.

For time-series data, MongoDB provides an option to create a **time-series collection** designed for time-stamped measurements; syntax and feature support depend on the version. When your goal is simply learning how to create, list, and drop collections, start with standard collections first and study specialized types afterward.

## 7. Listing Databases

### 7.1. Interactive Command in mongosh

~~~javascript
show dbs
~~~

`show dbs` displays the list of databases that the connection session is permitted to list. It **does not switch** the `db` context and may not show a database that was just selected with `use` if no collection has been created or data written yet.

A MongoDB server typically includes several internal/special databases:

| Database | Purpose |
|---|---|
| `admin` | Administrative tasks and authentication/authorization mechanisms |
| `local` | Instance-local data, such as replication metadata |
| `config` | System metadata and configuration, especially in clusters |

These are not arbitrary lab databases. Do not drop or modify system databases simply because they appear in `show dbs` output.

### 7.2. Command for Scripts

Instead of a shell helper, you can run a database command:

~~~javascript
db.adminCommand({
  listDatabases: 1,
  nameOnly: true
})
~~~

Filter specifically for the `training_store` database:

~~~javascript
db.adminCommand({
  listDatabases: 1,
  nameOnly: true,
  filter: { name: "training_store" }
})
~~~

The result is an object containing the database list (when the operation succeeds). This approach is better suited for scripts and command-level metadata checks than parsing the text output of `show dbs`.

Account permissions affect the output: some environments only allow seeing databases to which the account has been granted access, or reject the command if privileges are insufficient. **An empty list does not always mean the deployment contains no databases.**

### 7.3. Database Listing and Size

Some listing operations can provide overall size/status information. However:

- A logical database does not correspond one-to-one with a pure storage directory or size that can be summed mechanically.
- Allocated storage size, logical BSON data, indexes, and reusable free space are distinct concepts.
- In a replica set or sharded cluster, figures vary by node, shard, and how the command collects metrics.

To evaluate storage usage, you also need `db.stats()`, `db.collection.stats()`, and infrastructure metrics; `show dbs` is primarily for identifying visible databases.

## 8. Listing Collections in the Selected Database

### 8.1. Shell Command

~~~javascript
use training_store
show collections
~~~

For example, you might see:

~~~text
books
borrow_records
catalog_items
members
recent_lab_events
~~~

The list depends on which creation commands succeeded; it does not have to match the example identically.

### 8.2. mongosh Methods

~~~javascript
// Array of collection names.
db.getCollectionNames()

// Metadata about the collections.
db.getCollectionInfos()

// Look up metadata only for the collection named books.
db.getCollectionInfos({ name: "books" })
~~~

`getCollectionInfos()` lets you inspect returned collection names, types, and options. Do not expect the output to contain only application-created collections: depending on version, privileges, and namespace types, special objects or metadata entries may appear.

Example of working with another database without calling `use`:

~~~javascript
const store = db.getSiblingDB("training_store")
const names = store.getCollectionNames()

printjson(names)
print(names.includes("books"))
~~~

This is a reasonable pattern for **existence-check scripts**. However, checking first and creating afterward does not guarantee that another process will not create the same name in between the two steps; concurrent deployment systems still need to handle namespace-already-exists errors.

### 8.3. Using a MongoDB Command

~~~javascript
db.runCommand({
  listCollections: 1,
  nameOnly: true
})
~~~

This is the corresponding low-level command. The result may include a `cursor` returned in batches; do not assume a single command response always contains every collection when there are many. When writing scripts, `getCollectionNames()` or driver APIs are generally more convenient and handle cursor details automatically.

### 8.4. Inspecting Data in a Collection

Listing collections tells you their names, not whether they contain documents. You can check:

~~~javascript
db.books.findOne()
db.books.countDocuments({})
db.books.getIndexes()
~~~

In applications with large datasets, do not run full collection counts continuously as a cheap health check; query cost depends on the collection, indexes, and current workload. Choose monitoring methods according to your specific requirements.

## 9. How to Check Whether a Database or Collection Exists

MongoDB does not have a universal `db.exists` property in mongosh. You can combine the following approaches.

### 9.1. Checking the Name in the List

~~~javascript
const store = db.getSiblingDB("training_store")

const exists = store.getCollectionNames().includes("books")
print(exists)
~~~

A result of `true` indicates that a collection named `books` appears in the list the account is permitted to view at the time of the check.

### 9.2. Checking Collection Metadata

~~~javascript
const store = db.getSiblingDB("training_store")
const infos = store.getCollectionInfos({ name: "books" })

printjson(infos)
~~~

If you need to verify configuration, you can inspect `options`, `type`, or other metadata returned by `getCollectionInfos()`, depending on MongoDB version and access privileges.

### 9.3. Checking a Database at the Command Level

~~~javascript
const result = db.adminCommand({
  listDatabases: 1,
  nameOnly: true,
  filter: { name: "training_store" }
})

printjson(result)
~~~

Do not use `db.getSiblingDB("training_store") !== null` as an existence test: returning a handle does not mean the database exists on the server.

### 9.4. Pre-Change Verification Rules for Schema Operations

For deployment scripts:

1. Identify the **exact cluster**, database, and environment.
2. Read the list and metadata of the objects you plan to modify.
3. Ensure the script is designed to handle already-existing objects, missing objects, or permission errors.
4. Execute the create/alter step via the appropriate API.
5. Re-read metadata to verify the actual outcome.

This is a structural administration workflow, unlike allowing end users to trigger drop commands during routine API requests.

## 10. Dropping a Collection with `drop()`

When a collection is no longer needed, MongoDB lets you delete **the entire collection along with its documents and associated indexes**.

### 10.1. Basic Syntax

~~~javascript
use training_store

// Run only in a lab after confirming the name.
db.getCollection("recent_lab_events").drop()
~~~

The command can return `true` on successful deletion and `false` if the collection does not exist (depending on shell/version behavior). In production-grade scripts, check the return value or errors, then re-read the collection list.

~~~javascript
db.getCollectionNames()
~~~

**Impact of dropping a collection:**

- Deletes all documents in the collection.
- Deletes all indexes belonging to the collection.
- Removes the collection's validator and options, since the collection itself no longer exists.
- Is a metadata/DDL change that can affect active queries, cursors, or change streams.
- Can affect multiple applications depending on the collection, not just a single screen.

In a replica set or sharded cluster, drop takes effect across the entire scope the collection belongs to; do not use it as a way to "delete on one node" or as a manual disk-cleanup trick.

### 10.2. Difference Between `deleteMany({})` and `drop()`

At first glance both commands can leave a collection with zero documents, but they **differ in purpose and consequences**:

| Command | Documents | Collection/Validator | Indexes | When to consider |
|---|---|---|---|---|
| `db.books.deleteMany({})` | Deletes all documents matching the empty filter | Collection remains | Indexes remain | Need to preserve structure and only clear data |
| `db.books.drop()` | Deletes everything along with the collection | Collection is removed | Collection indexes are removed | Want to remove the namespace completely |
| `db.dropDatabase()` | Deletes all documents across all collections in the database | Drops the database and all collections inside it | Drops all associated indexes | Want to destroy an entire database intentionally |

`deleteMany({})` on a large collection can take significant time, generate load, and execute as a set of delete operations; do not treat it automatically as a collection-wide atomic operation. When you need to keep indexes and options, choose an approach suited to data scale and operational requirements.

### 10.3. When a Collection Does Not Exist

~~~javascript
const store = db.getSiblingDB("training_store")

print(store.getCollectionNames().includes("not_a_real_collection"))
~~~

If you need an idempotent drop in a script, design it so the absent-collection case is handled explicitly while still verifying the target namespace. **Do not use an "ignore if missing" pattern to mask a misconfigured cluster or wrong database name.**

### 10.4. Cases Where You Should Not Use Drop

- Want to delete a single record: use `deleteOne(filter)`.
- Want to delete a subset of documents matching conditions: use `deleteMany(filter)` with a strict filter.
- Want to expire old data according to policy: look into TTL/archival and retention policies.
- Want to rename a collection: look into `renameCollection` instead of automatically dropping and recreating.
- Want to reclaim disk space after deleting many documents: understand storage space reuse and compaction; drop is not the default choice when schema or data must be preserved.

## 11. Dropping an Entire Database with `dropDatabase()`

This is the **broadest-scope operation in this lesson**. It deletes the selected database along with all of its collections, documents, and indexes. There is no simple "undo" in mongosh; recovery generally depends on backups/snapshots and a restore plan.

### 11.1. Syntax

~~~javascript
use training_store
db.getName()      // Re-check: must be training_store.

// WARNING: The command below deletes the entire training_store database.
// Run only when this is a disposable lab database.
db.dropDatabase()
~~~

A way to make the target database explicit without relying on `use`:

~~~javascript
const targetDb = db.getSiblingDB("training_store")
print(targetDb.getName())

// WARNING: Running the command below will delete all collections in training_store.
targetDb.dropDatabase()
~~~

The commands above are **examples of actual destructive operations**, not inspection commands. When working in the shell, print the database name and collection list first and only run the drop line if you intentionally want to destroy all lab data.

### 11.2. Why Can Using `getSiblingDB` Be Safer in Scripts?

In a long sequence of commands, the `db` variable points to the current context and can change whenever `use` is executed. Writing:

~~~javascript
const targetDb = db.getSiblingDB("training_store")
~~~

makes the target database clearer in code. However, **this is not an automatic safeguard**: if the database name is mistyped or the connection string points to production by mistake, `targetDb.dropDatabase()` still carries the full consequence. Safety comes from environment verification, least privilege, target validation, and proper approval workflows.

### 11.3. Verifying After Dropping

In a lab you can run:

~~~javascript
db.adminCommand({
  listDatabases: 1,
  nameOnly: true,
  filter: { name: "training_store" }
})
~~~

If the database has been dropped and not recreated, the list will generally no longer include that database. However, another process could recreate the database/collection afterward, and listing privileges can also affect the output. If you need to verify the operation strictly, combine command results with environment logs, audit trails, and metadata.

### 11.4. Drop Is Not Backup/Restore

A replica set replicates valid database changes, including executed drop operations. Therefore, **replication does not equal the ability to undo a drop**. A restorable backup or snapshot, along with tested restore procedures, is what is required for important data.

## 12. Full Hands-On Workflow: Create → List → Select → Drop

To avoid confusion with standalone examples, this section uses a separate database named `db_lifecycle_lab` and performs a repeatable sequence on a clean environment.

### Step 1 — Select a Nonexistent Database

~~~javascript
use db_lifecycle_lab
db.getName()
~~~

At this point only the context is selected; the database may not yet appear in `show dbs`.

### Step 2 — Create an Empty Collection

~~~javascript
db.createCollection("notes")
show collections
~~~

### Step 3 — Insert Documents to Observe Data

~~~javascript
db.notes.insertMany([
  {
    _id: "n-001",
    title: "Database concepts",
    createdAt: new Date(),
    tags: ["database", "mongodb"]
  },
  {
    _id: "n-002",
    title: "Collection concepts",
    createdAt: new Date(),
    tags: ["collection", "mongodb"]
  }
])
~~~

### Step 4 — Create Another Collection via Implicit Insert

~~~javascript
db.topics.insertOne({
  _id: "t-001",
  name: "MongoDB",
  active: true
})
~~~

### Step 5 — List Databases and Collections

~~~javascript
show dbs
show collections

db.getCollectionNames()
db.getCollectionInfos({ name: "notes" })
~~~

### Step 6 — Select Another Database and Switch Back

~~~javascript
use admin
db.getName() // admin

const lab = db.getSiblingDB("db_lifecycle_lab")
lab.getCollectionNames()
lab.notes.findOne({ _id: "n-001" })
~~~

This is an important step: calling `lab.notes.findOne()` operates on `db_lifecycle_lab` even though the current `db` context is `admin`.

### Step 7 — Drop a Single Collection

~~~javascript
// Run only when db_lifecycle_lab is a disposable test database.
const lab = db.getSiblingDB("db_lifecycle_lab")

print(lab.getName())
printjson(lab.getCollectionNames())

lab.getCollection("topics").drop()

printjson(lab.getCollectionNames())
~~~

Afterward `notes` still exists; `topics` has been removed if the drop succeeded.

### Step 8 — Drop the Entire Test Database

~~~javascript
// Run only after confirming the entire db_lifecycle_lab can be deleted.
const labToDrop = db.getSiblingDB("db_lifecycle_lab")

print(labToDrop.getName())
printjson(labToDrop.getCollectionNames())

labToDrop.dropDatabase()
~~~

### Step 9 — Verify the Result

~~~javascript
db.adminCommand({
  listDatabases: 1,
  nameOnly: true,
  filter: { name: "db_lifecycle_lab" }
})
~~~

**Self-check:** After `use` without creation, the database may not appear; after `createCollection` or insert, the collection is present; after `drop()`, only one collection is removed; after `dropDatabase()`, the entire target database is gone.

## 13. Shell Commands and Corresponding Database Commands

MongoDB exposes multiple interface layers. This table distinguishes commands typed in the mongosh terminal from JavaScript calls and database commands.

| Task | Mongosh helper / method | Command or script usage |
|---|---|---|
| Select database | `use training_store` | `db.getSiblingDB("training_store")` |
| View current database | `db.getName()` | `db.getName()` |
| List databases | `show dbs` | `db.adminCommand({listDatabases: 1})` |
| Create collection | `db.createCollection("books")` | `db.runCommand({create: "books"})` |
| List collections | `show collections` | `db.getCollectionNames()` or `listCollections` |
| View collection metadata | `db.getCollectionInfos()` | `db.runCommand({listCollections: 1})` |
| Drop collection | `db.books.drop()` | `db.runCommand({drop: "books"})` |
| Drop current database | `db.dropDatabase()` | `db.runCommand({dropDatabase: 1})` |

Keep in mind:

- `use` and `show` are shell helpers convenient for interactive sessions.
- `db.getSiblingDB()`, `db.createCollection()`, and `db.dropDatabase()` are mongosh APIs.
- `listDatabases`, `create`, `listCollections`, `drop`, and `dropDatabase` are database commands.
- In Java/Node.js/Python drivers, the exact API calls differ from mongosh; use your driver's appropriate API rather than copying `show dbs` literally into application code.

Example of a command creating a collection in the selected database:

~~~javascript
const store = db.getSiblingDB("training_store")
store.runCommand({ create: "script_created_collection" })
~~~

This is simply an equivalent command-level approach; in typical learning code, `createCollection()` is easier to read.

## 14. Access Permissions and Special Databases

MongoDB enforces **authentication** and **role-based access control (RBAC)**. Not every account is permitted to:

- List all databases.
- View metadata for all collections.
- Create collections.
- Drop a collection or an entire database.

For example, a read-only account can query documents and metadata within its granted scope, but has no permission to create or drop collections. Application accounts should receive permissions suited to their business logic; do not grant cluster-wide admin privileges just to test `show dbs` or run CRUD.

### Why Might a Command Report Unauthorized?

~~~text
MongoServerError: not authorized ...
~~~

Permission errors differ from "namespace does not exist" errors:

- **Unauthorized / insufficient privileges:** the account is not permitted to perform the operation.
- **NamespaceExists:** the collection already exists and cannot be recreated with the same name by that command.
- **NamespaceNotFound:** the target object does not exist for commands that require it to be present.
- **DuplicateKey:** writing a document that violates a unique index, such as a duplicate `_id`.
- **Connection/timeout error:** unable to communicate or did not receive acknowledgment in time; verify actual state rather than assuming the operation fully succeeded or failed.

Do not resolve an Unauthorized error by turning on maximum administrative privileges for the application account. Identify the exact operation, target database, and least-privilege permissions required, or ask an operator to grant the appropriate role.

### `admin`, `local`, and `config`

These databases serve system and cluster functions, not practice exercise data. Because `db.dropDatabase()` destroys the current database scope, **never select a system database and test dropping it just to see what happens**.

## 15. Common Pitfalls

### Pitfall 1 — Thinking `use` Already Created the Database

~~~javascript
use demo_not_written_yet
show dbs
~~~

Not seeing the name in `show dbs` can be completely normal. Create a collection or write a document successfully, then check again.

### Pitfall 2 — Thinking an Empty Collection Does Not Exist

~~~javascript
db.createCollection("empty_but_real")
db.empty_but_real.findOne()  // May return null.
db.getCollectionNames()      // Still includes the collection name.
~~~

`findOne()` returning `null` is not sufficient to prove a collection does not exist. It could be an empty collection or simply have no document matching the filter.

### Pitfall 3 — Mixing Up the Selected Database

~~~javascript
use admin
db.dropDatabase()
~~~

This is an **illustration of a dangerous operation—do not execute it**. The issue is that `db.dropDatabase()` always targets the current `db` context. Before any drop operation, re-read `db.getName()`, confirm the connection, and use explicit database names where appropriate.

### Pitfall 4 — Confusing Document Deletion with Collection Drop

~~~javascript
db.books.deleteOne({ _id: "b-001" }) // Deletes one matching document.
db.books.deleteMany({})              // Deletes all documents in books.
db.books.drop()                       // Drops the entire books collection.
~~~

These three commands are not interchangeable. Impact escalates from a single document → all contents of a collection → the entire collection along with its structure and indexes.

### Pitfall 5 — Seeing a Missing Name in `show dbs` and Assuming Lack of Permission

The database may simply not have been created yet, or listing permissions may be restricted. Check with the appropriate account and commands instead of immediately requesting full administrative privileges.

### Pitfall 6 — Calling `createCollection` Repeatedly as an Idempotent Command

~~~javascript
db.createCollection("books")
db.createCollection("books") // May encounter NamespaceExists.
~~~

When writing migrations, state a clear strategy for when the collection already exists: inspect metadata, verify expected options, and modify only through appropriate mechanisms. Do not treat an "already exists" error as proof that the collection has the right configuration.

### Pitfall 7 — Dropping to "Free Up Space" Without Considering Consequences

Dropping deletes the collection, documents, indexes, and metadata. Do not use drop as a substitute for retention, archival, data partitioning, index cleanup, or storage capacity management when the business still needs the collection.

## 16. Safety Inspection Script Before Running DDL Operations

In deployment scripts, it is good practice to read state first and clearly separate observation steps from mutation steps.

~~~javascript
// Reads and reports state; this snippet does not delete anything.
const targetDb = db.getSiblingDB("training_store")
const targetName = "books"

print("Current target database: " + targetDb.getName())
print("Target collection: " + targetName)

const collections = targetDb.getCollectionNames()
const found = collections.includes(targetName)

print("Collection exists: " + found)
printjson(targetDb.getCollectionInfos({ name: targetName }))
~~~

This pattern gives operators enough information to make decisions, but **does not lock state**: another account can still create or drop the collection after the check. In real operations, combine access controls, change management, error handling, and post-operation verification.

If you need to establish a production deletion procedure, it should include:

1. Verifying the exact connection/deployment, database, and collection.
2. Identifying the owner, dependency scope, and data that must be retained.
3. Confirming recoverable backups and RPO/RTO targets.
4. Blocking or coordinating related read/write traffic during the planned change window.
5. Executing the drop command within an approved maintenance window, with logging/auditing.
6. Verifying metadata, applications, dashboards, and resources afterward.

For learning environments, still build the habit of verifying the target database before dropping; production governance steps are extended operational knowledge.

## 17. Architectural Perspective: Impact on Replica Sets and Sharded Clusters

The commands in this lesson look the same at the mongosh level, but topology affects how they are executed and observed.

### 17.1. Standalone

All operations target a single MongoDB server. Losing the server can cause service unavailability; data protection depends on storage/backups and the corresponding configuration.

### 17.2. Replica Set

Valid data and metadata changes are replicated via the deployment's replication mechanism. An accepted drop command must not be treated as "only deleted on the primary while secondaries hold a backup." Secondaries do not replace a backup plan.

### 17.3. Sharded Cluster

A collection's data may be distributed across multiple shards. Creating or dropping a collection or database can involve cluster metadata and coordination across nodes. Users should connect through the proper cluster entry component, follow version recommendations, and understand that a drop applies across the logical scope of the entire collection/database.

### 17.4. Availability and DDL Operations

Do not repeatedly create/drop structures as a default part of user requests. DDL operations can impact active client queries, indexes, schema validation, or change streams. Put structural changes into migrations with logging, error handling, application compatibility, and recoverability.

## 18. Comprehensive Lab: Managing Data Namespaces

**Scenario:** A training application has a database `academy_practice` containing:

- `courses`: course catalog.
- `learners`: students.
- `enrollments`: student registrations.

### Part A — Select and Create

1. Connect to the lab MongoDB instance; note the current database.
2. Select `academy_practice` without writing data; observe whether it appears in the database list.
3. Explicitly create `courses` using `createCollection`.
4. Create `learners` using `insertOne` with a sample learner.
5. Explicitly create `enrollments` and attach a simple validator requiring `courseId`, `learnerId`, and `joinedAt`.

### Part B — List and Cross-Check

1. Use `show dbs` and `listDatabases` to list databases.
2. Use `show collections`, `getCollectionNames()`, and `getCollectionInfos()` on `academy_practice`.
3. Use `getSiblingDB` to read `academy_practice.courses` even when `db` points to another database.
4. Check collection existence, document count, and its index list.

### Part C — Drop at Two Scopes

1. In the lab only, drop just `enrollments` using `drop()`.
2. Prove that `courses` and `learners` still exist.
3. Confirm none of the three collections contain data that needs to be kept.
4. Drop the entire `academy_practice` database; verify the database name is no longer in the current list.

### Questions to Explain

- Why might `use academy_practice` not make the database appear immediately?
- Which command should be used if you need an empty collection with a validator already configured?
- Why is `getSiblingDB` better suited for scripts when multiple databases are accessed?
- Does `findOne() === null` prove a collection does not exist?
- If you only want to remove one learner, why should you not use `drop()`?
- Why do indexes and validators have to be recreated if you drop and recreate a collection with the same name?
- If a drop command is targeting production instead of a lab, what signs help catch it before execution?
- Can a replica set be used as a backup to "recover" a collection that was just dropped?

## 19. Quick Review Questions

**Question 1.** Does `use sales` immediately create the `sales` database?

**Answer:** Not necessarily. It is a command that selects the database context in mongosh. The database is typically materialized when a collection is created or an appropriate write operation occurs.

**Question 2.** How do you list databases in mongosh?

**Answer:** `show dbs`; in scripts you can use `db.adminCommand({listDatabases: 1})`, subject to permissions.

**Question 3.** How do you list collections in the current database?

**Answer:** `show collections` or `db.getCollectionNames()`; view metadata with `db.getCollectionInfos()`.

**Question 4.** What is the difference between `db.books.drop()` and `db.books.deleteMany({})`?

**Answer:** `drop()` removes the collection along with its indexes and metadata, whereas `deleteMany({})` deletes matching documents while keeping the namespace, indexes, and validator.

**Question 5.** Can you create a database by calling `db.getSiblingDB("new_db")`?

**Answer:** That call only obtains a handle; it does not create storage resources for the database.

**Question 6.** What do you use when you need to initialize a collection with a validator?

**Answer:** `db.createCollection("name", {validator: ...})` (within the options supported by your version), then inspect metadata and test inserting valid data.

**Question 7.** Why should you not run `dropDatabase()` just because you see one collection that is no longer needed?

**Answer:** Because it deletes all collections in the target database; to delete only a single collection, use `collection.drop()`.

**Question 8.** `show dbs` does not list the expected database. What could be the cause?

**Answer:** The database has only been selected but not yet actually created, the account has restricted listing permissions, or you are connected to the wrong deployment.

**Question 9.** If you create a collection named `book-events`, how do you access it?

**Answer:** Use `db.getCollection("book-events")`; dot notation with a hyphen is not valid.

**Question 10.** What should you verify right before dropping a database?

**Answer:** The right connection/deployment, database name, collection list, whether the data is needed, and backup/restore readiness per environment procedures.

## 20. Essential Command Cheat Sheet

| Purpose | Command |
|---|---|
| Select database | `use training_store` |
| Explicitly select database in a script | `const d = db.getSiblingDB("training_store")` |
| View current database name | `db.getName()` |
| List databases | `show dbs` |
| List databases via command | `db.adminCommand({listDatabases: 1})` |
| Create an empty collection | `db.createCollection("books")` |
| Create collection on first insert | `db.books.insertOne({...})` |
| List collection names | `show collections` or `db.getCollectionNames()` |
| View collection metadata | `db.getCollectionInfos({name: "books"})` |
| Access collection with special characters | `db.getCollection("book-events")` |
| Delete one document | `db.books.deleteOne(filter)` |
| Delete all documents but keep collection | `db.books.deleteMany({})` |
| Drop collection along with indexes | `db.books.drop()` |
| Drop entire currently selected database | `db.dropDatabase()` |

The sequence to remember when working with MongoDB is **connect to the right deployment → identify the database → select/create the collection → inspect metadata → operate on data → verify the result**. For drop operations in particular, always clarify the scope of impact and recoverability before executing.
