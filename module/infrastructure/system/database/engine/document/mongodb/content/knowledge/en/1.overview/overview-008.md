# Core Terminology and How to Look Up MongoDB Documentation by Version

When learning MongoDB, two challenges often arise at the same time: a term can mean something different than in relational database management systems, and examples found online may be written for a different MongoDB version than the system you are using. This lesson builds a shared vocabulary, then shows how to identify the actual version and look up the exact official documentation before applying commands or features.

After this lesson, you should be able to:

- Explain the relationship among **database, collection, document, field, BSON**, and **`_id`**.
- Read a query containing **filter, projection, operator, cursor**, distinguish standard queries from an **aggregation pipeline**, and understand the role of an **index**.
- Recognize operational terms such as **replica set, primary, secondary, sharding, read concern, write concern**.
- Distinguish **MongoDB Server version**, **Feature Compatibility Version (FCV)**, **driver version**, **`mongosh` version**, and **Stable API**.
- Trace from a real-world problem to the documentation page for the **exact product and exact version**, then check changelogs and compatibility conditions.

> **Convention:** Command examples in this lesson use `mongosh` (MongoDB Shell). The version paths `v8.0` and `v7.0` are **examples of pinning a version**, not an implication that they are always the two latest releases. For another system, choose the documentation branch matching your actual version.

## 1. Concept Map: How Is MongoDB Data Organized?

In the document model, a **deployment** (a running MongoDB system) can contain multiple **databases**; a database contains multiple **collections**; each collection contains **documents**. Documents consist of **field–value** pairs. Data is stored in **BSON** format.

```text
MongoDB deployment
└── Database: shop
    ├── Collection: customers
    │   ├── Document: { _id: ..., name: ..., ... }
    │   └── Document: { _id: ..., name: ..., ... }
    └── Collection: orders
        └── Document
            ├── Field: orderNo -> "ORD-1001"
            ├── Field: customer -> { id: "C01", city: "Hanoi" }
            └── Field: items -> [ { sku: "A01", qty: 2 }, ... ]
```

| Term | Meaning | Memory Tip / Note |
|---|---|---|
| **Deployment** | A MongoDB environment, which may be a standalone instance, replica set, or sharded cluster. | Know which deployment type you are connected to before running administrative commands. |
| **Database** | Logical namespace containing collections and related objects. | `shop` is a database name; it does not equate to a physical server. |
| **Collection** | A group of documents, roughly analogous to a table in SQL. | Documents in the same collection **are not required** to have the exact same list of fields. |
| **Document** | A record made of field–value pairs; the core data unit of MongoDB. | Can contain nested structures and arrays. |
| **Field** | Attribute name inside a document. | For example, `orderNo`, `customer.city`. |
| **BSON** | Binary representation of document-style data, supporting more data types than standard JSON. | For example, `ObjectId`, `Date`, `Decimal128`, binary data. |
| **`_id`** | Document identifier within a standard collection, holding a unique value. | Does not mean the type must always be `ObjectId`. |
| **Namespace** | Object identifier, usually written in the form `database.collection`. | For example, `shop.orders`. |

### 1.1. Document, JSON, and BSON Are Not Identical

A sample document in `mongosh`:

```javascript
{
  _id: ObjectId("65d000000000000000000001"),
  orderNo: "ORD-1001",
  customer: { id: "C01", city: "Hanoi" },
  items: [
    { sku: "A01", qty: 2, unitPrice: 120000 },
    { sku: "B02", qty: 1, unitPrice: 50000 }
  ],
  status: "PAID",
  createdAt: ISODate("2026-11-01T03:00:00Z")
}
```

This is **shell display syntax**, not pure JSON: pure JSON has no `ObjectId(...)` or `ISODate(...)` calls. In storage, MongoDB uses BSON. When transferring BSON data through tools or JSON files, you may encounter **Extended JSON** with representations such as `{"$oid":"..."}` or `{"$date":"..."}` to preserve data types. Do not treat a 24-character hex string and a BSON `ObjectId` value as the same type.

`_id` is the identifier key; when inserting a document without supplying `_id`, the driver or server typically generates an `ObjectId`. An `ObjectId` consists of 12 bytes, usually displayed as 24 hex characters and containing a timestamp component. However, `_id` can also be a string or another suitable BSON type; do not assume a system must use `ObjectId`. In standard collections, MongoDB has a unique index on `_id` by default. Some specialized collection types have different rules, so consult the corresponding documentation page.

**Important limit:** a standard BSON document has a maximum size of **16 MiB**. For larger files, MongoDB provides **GridFS** to split files into chunks; there is no reason to cram an entire large file into one document.

### 1.2. Embedded Document, Array, Reference, and Schema

- **Embedded document** is a document nested inside another field, such as `customer: { id, city }`. Querying nested fields uses **dot notation**: `"customer.city"`.
- **Array** is a list of values or documents, such as `items`. Querying and updating arrays has its own syntax and conditions; do not assume every comparison on an array behaves like a scalar comparison.
- **Reference** means storing an identifier linking to another document, such as `customerId: ObjectId(...)`, and retrieving related data as needed. MongoDB provides `$lookup` to combine data in aggregation, but does not automatically enforce SQL-style foreign key constraints.
- **Flexible schema** means documents within a collection can vary in their field sets or field types. It **does not mean** data needs no conventions: applications still require data contracts; MongoDB supports **schema validation** to enforce rules, such as via JSON Schema.

When modeling data, consider **embedding** if information is frequently read together, has bounded size, and shares coupled lifecycles; consider **referencing** when relationships are large, data is updated independently, or multiple documents reference the same entity. This is a design decision based on data access patterns, not an absolute formula.

## 2. Query Vocabulary: What Does MongoDB Do with Documents?

MongoDB supports **CRUD**: Create, Read, Update, Delete. Distinguish the **operation** (e.g., `find()`), **condition** (filter), **result shaping** (projection), and **operator**.

| Category | Term / Method | Role |
|---|---|---|
| Create | `insertOne()`, `insertMany()` | Insert documents. |
| Read | `find()`, `findOne()` | Find documents matching a condition; `find()` returns a cursor. |
| Update | `updateOne()`, `updateMany()`, `replaceOne()` | Modify or replace matching documents. |
| Delete | `deleteOne()`, `deleteMany()` | Remove matching documents. |
| Filter / predicate | `{ status: "PAID" }`, `{ amount: { $gt: 100 } }` | Specifies which documents are selected. |
| Projection | `{ orderNo: 1, _id: 0 }` | Selects fields to return; normally `_id` is included unless explicitly excluded. |
| Query operator | `$gt`, `$in`, `$and`, `$exists` | Expresses comparison or logical conditions. |
| Update operator | `$set`, `$inc`, `$unset`, `$push` | Expresses how fields are modified. |
| Cursor | Traversal result of `find()` | Allows streaming/iterating through results incrementally; not by default an array holding all results. |
| Sort / limit | `.sort()`, `.limit()` | Defines ordering and caps the number of returned documents. |
| Upsert | `upsert: true` in an eligible update operation | If no document matches, can create a new document from the filter and update specification. |

### 2.1. Read–Write Example to Try in a Practice Database

Example illustrating operations on test data—do not run directly against production collections:

```javascript
use shop_demo

db.orders.insertOne({
  orderNo: "ORD-1001",
  customer: { id: "C01", city: "Hanoi" },
  items: [
    { sku: "A01", qty: 2, unitPrice: 120000 },
    { sku: "B02", qty: 1, unitPrice: 50000 }
  ],
  status: "PAID",
  createdAt: ISODate("2026-11-01T03:00:00Z")
})

// Filter: PAID orders in Hanoi; projection: return only orderNo and status.
db.orders.find(
  { status: "PAID", "customer.city": "Hanoi" },
  { orderNo: 1, status: 1, _id: 0 }
)

// $set is an update operator; $in is a query operator.
db.orders.updateOne(
  { orderNo: { $in: ["ORD-1001", "ORD-1002"] } },
  { $set: { status: "SHIPPED" } }
)

// Read results newest first, at most 5 documents.
db.orders.find({}, { orderNo: 1, createdAt: 1 })
  .sort({ createdAt: -1 })
  .limit(5)
```

Here, `1` in projection means include the field, while `-1` in sort means descending order. Those two values sit in **two different syntactic contexts**. In update operations, distinguish `$set` (assigning a field value) from **replacing the entire document** via `replaceOne()`.

**Atomicity:** a write operation on **a single document** is atomic at the document level, even when updating multiple fields within that same document. If business logic must consistently modify multiple documents, study **multi-document transactions** and their prerequisites; do not extrapolate single-document atomicity to collection-wide atomicity.

### 2.2. Aggregation: Pipelines and Stages

An **aggregation pipeline** passes documents through a sequence of **stages**. Each stage filters, computes, transforms, or groups data for the next stage. Stage names typically start with `$`, but do not confuse an **aggregation stage** with a **query operator** or **update operator**: they belong to different syntactic positions.

```javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      totalQuantity: { $sum: "$items.qty" }
    }
  },
  { $sort: { totalQuantity: -1 } }
])
```

Explanation: `$match` filters paid orders, `$unwind` expands each element of `items`, `$group` sums quantities per SKU, and `$sort` orders the results. Inside `$group`, the `_id` field is the **group key**, not necessarily the original document's `_id`. Other pipelines may use `$project`, `$lookup`, `$facet`, `$merge`, and more; verify each stage against the documentation for the version in use.

### 2.3. Indexes, Query Planner, and `explain()`

An **index** is a data structure supporting efficient data lookup, analogous to indexes in other database systems. MongoDB supports several index types, such as **single-field**, **compound** (multiple fields), **multikey** (indexing array data), **unique**, **TTL**, **text**, and specialized indexes. Each type has specific rules and limits.

```javascript
// Example compound index for status filter and createdAt ordering.
db.orders.createIndex({ status: 1, createdAt: -1 })

// Inspect the plan and counts of documents/index entries examined.
db.orders.find({ status: "PAID" })
  .sort({ createdAt: -1 })
  .explain("executionStats")
```

- The **query planner** selects an execution plan from the candidate plans evaluated by the system.
- **`COLLSCAN`** indicates a collection scan; **`IXSCAN`** indicates an index scan in common plan trees. Seeing `IXSCAN` does not guarantee an optimal query if the number of keys and documents examined is excessive.
- **`totalDocsExamined`**, **`totalKeysExamined`**, and **`nReturned`** in execution statistics help compare read work against returned results. Field names, placement, and `explain` tree structure can vary by MongoDB version and execution engine.
- Indexes can accelerate certain queries at the cost of storage space and write overhead; never create indexes based solely on field names without actual queries.

Read the **Indexing** and **Explain Results** sections for your exact version before judging an execution plan as good or bad. In particular, the query engine's internal representation may evolve across versions while the business semantics of the query remain unchanged.

## 3. Deployment, Availability, and Consistency Terminology

When reading MongoDB cluster operations documentation, know whether commands apply to **standalone**, a **replica set**, or a **sharded cluster**. The following terms frequently appear together:

| Term | Practical Explanation |
|---|---|
| **`mongod`** | The MongoDB server process that stores/processes data. |
| **`mongos`** | Query router process for a sharded cluster; does not itself store shard data. |
| **Standalone** | A single independent `mongod`; lacks replica set automatic failover. |
| **Replica set** | A group of `mongod` processes maintaining data copies to increase availability. |
| **Primary / secondary** | Roles in a replica set; the primary receives normal writes, while secondaries replicate data from the oplog. Roles can change after an election. |
| **Oplog** | Operations log supporting replication within a replica set. |
| **Election / failover** | Electing a new primary and transitioning roles when cluster conditions change. |
| **Sharding** | Distributing a collection's data across multiple shards to scale out. |
| **Shard key** | A field or set of fields used to distribute and route documents of a sharded collection. |
| **Config server** | Stores configuration metadata required by a sharded cluster. |
| **Read preference** | Directive specifying which member type to prefer for reads, such as primary or secondary. |
| **Read concern** | Guarantee level regarding the data observable by a read operation. |
| **Write concern** | Acknowledgment criteria for a write operation from the system, such as acknowledgment by a specified number of members. |
| **Session / transaction** | Client session context and mechanism for grouping multiple operations into a transaction when appropriate. |
| **Atlas** | Cloud-managed MongoDB database service. |

Visualizing the two common topologies:

```text
Replica set:
Application / mongosh -> Primary mongod
                         ├── Secondary mongod
                         └── Secondary mongod
         (members coordinate elections and data replication)

Sharded cluster:
Application / driver -> mongos
                        ├── Shard A (typically a replica set)
                        ├── Shard B (typically a replica set)
                        └── Config server replica set (metadata)
```

**Three easily confused concepts:**

1. **Read preference** determines *where to read from*; it does not by itself establish the consistency level of the data read.
2. **Read concern** defines *data visibility guarantees*; levels such as `local`, `majority`, and `snapshot` have distinct semantics and prerequisites.
3. **Write concern** defines *when a write is acknowledged*; `w: 1` and `w: "majority"` do not provide the same durability guarantee, while `journal`/`j` is a separate dimension.

For example, configuring an application to read from a secondary via a read preference **does not automatically** mean it will immediately see every write just committed on the primary. When business logic demands freshness, causality, or cross-operation consistency, read the **Read Preference**, **Read Concern**, **Write Concern**, and **Transactions** documentation together for your exact server and driver versions.

## 4. Tooling and API Terminology: Read the Right Documentation Set

For the same task (such as querying orders), syntax differs across `mongosh`, Java Driver, Spring Data MongoDB, and the Atlas UI:

| Component | Function | Primary Documentation to Consult |
|---|---|---|
| **MongoDB Server / Database Manual** | Data model, database commands, query/index/replication/sharding mechanics. | Database Manual matching the **server version**. |
| **`mongosh`** | Interactive MongoDB Shell; provides helpers such as `db.orders.find()`. | MongoDB Shell docs and the **mongosh Methods** section in the Manual. |
| **MongoDB Driver** | Client libraries for application languages such as Java, Python, Node.js. | Driver guide/API matching the **installed library version**. |
| **Spring Data MongoDB** | Spring mapping, repository, and template abstractions. | **Spring Data MongoDB** documentation matching the Spring Data version. |
| **MongoDB Compass** | Graphical interface for querying and exploring data. | Compass documentation. |
| **MongoDB Atlas** | Cloud cluster management, backups, permissions, connectivity. | Atlas documentation and cluster version details. |
| **Database Tools** | Admin/backup utilities such as `mongodump`, `mongorestore`, `mongoexport`. | Database Tools documentation matching the tool version. |

For instance, `db.orders.find({ status: "PAID" })` is convenient `mongosh` syntax. In the Java Sync Driver, queries go through `MongoCollection` and builders like `Filters.eq(...)`; in Spring Data, through `MongoTemplate` or repositories. **Do not paste shell syntax directly into Java** and conclude the docs are wrong. First identify whether you are reading documentation for the **server**, **shell**, **driver**, or **framework**.

## 5. 'MongoDB Version' Actually Has Multiple Layers

An application can run MongoDB Server `8.0.x`, Java driver `5.x`, and `mongosh` with an entirely different version number, while the cluster still holds an **FCV** from an earlier release during an upgrade. Consequently, answering “Which version of MongoDB are we using?” is insufficient to determine whether every command or feature is supported.

| Version Layer | What Is It? | What Does It Govern? |
|---|---|---|
| **Server version** (`X.Y.Z`) | MongoDB version running on `mongod`/`mongos`. | Server command syntax, limits, features, and server behavior. |
| **Server release series** (`8.0`, `7.0`, ...) | Release and documentation branch series. | Selecting the matching Database Manual branch. |
| **Feature Compatibility Version (FCV)** | Compatibility gate for features that can persist data in formats incompatible with older releases. | Checking certain features after upgrades/downgrades; does **not** replace server version. |
| **Driver version** | Client library version, such as Java Sync Driver. | Application APIs, data types, configuration, and server compatibility matrix. |
| **`mongosh` version** | Version of the shell binary installed locally. | Shell helper capabilities/syntax; never infer server version from it. |
| **Stable API version** | Server API contract a client can request (e.g., `apiVersion: "1"`). | Stabilizes behavior for the **subset of commands in the Stable API** across server upgrades. |
| **Atlas / tools / framework version** | Environment and wrapper-layer versions. | Management features, UI, CLI utilities, or framework APIs. |

### 5.1. How to Read `X.Y.Z`

Under MongoDB Server versioning conventions, `X` is **major**, `Y` is **minor**, and `Z` is **patch**. Major/minor releases can introduce new features or behavioral changes requiring compatibility checks; patch releases generally focus on bug fixes within the same release series. MongoDB has different release tracks and availability policies depending on deployment method, so check **MongoDB Versions and Upgrade Paths** instead of guessing whether a release is available on Atlas or self-managed.

Do not use the website's **Latest** badge as proof that your system runs the newest version. `Latest` is a documentation target **that shifts over time**; for reproducibility, always record the exact release series (`8.0`, `7.0`, ...) and running patch version, especially in production runbooks.

### 5.2. FCV Is Not the Binary Version

For example, after upgrading a deployment from MongoDB `7.0` to `8.0`, the server binary is `8.0` while FCV may remain `7.0` until the corresponding upgrade steps are finalized. FCV gates features that store backward-incompatible on-disk state; it is **not a toggle that turns a 7.0 binary into 8.0**, nor is it a driver version number.

**Reading** FCV for diagnostics is different from **changing** FCV. Running `setFeatureCompatibilityVersion` affects upgrade/downgrade paths and carries version-dependent confirmations and prerequisites; execute it only as part of an official upgrade procedure after verifying topology, backups, and release notes. This lesson only uses read-only inspection commands.

### 5.3. Stable API Is Not 'Server Version 1'

**Stable API** (introduced in MongoDB Server 5.0, formerly called **Versioned API**) allows a client to declare a stable contract for the command set covered by the Stable API. Specifying `apiVersion: "1"` does not mean connecting to MongoDB Server `1.0`, nor does it guarantee that **every** new feature or command in MongoDB will work on an older server. Features outside the Stable API set, FCV requirements, and driver compatibility must still be checked separately.

## 6. Identify Exact Versions Before Opening the Docs

Start with the **deployment the application actually connects to**. A binary installed on a developer laptop may not match the version running on Atlas or a remote server.

### 6.1. Checking Server Version in `mongosh`

```javascript
// Version of the connected mongod or mongos instance.
db.version()

// Build metadata; select the version field for a concise check.
db.adminCommand({ buildInfo: 1 }).version
```

The output is a string like `"8.0.x"`. When connected to a **sharded cluster**, keep in mind that checking through a router does not substitute for verifying versions across **all** cluster components, especially during a rolling upgrade. Also verify you are connected to the intended endpoint/environment (dev, staging, production).

To **read** FCV from a `mongod` with appropriate privileges:

```javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
})
```

The result typically includes `featureCompatibilityVersion.version`. This `getParameter` command **is not run on `mongos`**; for sharded clusters, follow the official instructions per component and privilege level. If you lack permission to read parameters, ask an operator rather than modifying configurations yourself.

### 6.2. Checking Local Binaries and Application Libraries

In a terminal on the machine where tools are installed:

```bash
mongod --version
mongosh --version
```

These two commands report the **local binaries**, not the version of a remote server. For Java, verify the actual dependency version in `build.gradle`, `pom.xml`, or the dependency tree—such as `org.mongodb:mongodb-driver-sync`—and open the **Java Sync Driver** docs for that exact version line. For Spring Data MongoDB, check the Spring Data version as well, since Spring Data APIs are not raw MongoDB Java Driver APIs.

If using **Atlas**, check the server version in the corresponding deployment/cluster page. When suspecting a mismatch between dashboard display and the connected endpoint, re-verify the endpoint with `db.version()` and check the cluster's upgrade status.

### 6.3. Environment Template When Requesting Support

```text
Environment: staging
Deployment: Atlas / replica set / sharded cluster (specify exact type)
MongoDB Server: 8.0.x (read from active endpoint)
FCV: 8.0 (if permitted to read)
Client: mongosh ... or Java Sync Driver ...
Framework (if any): Spring Data MongoDB ...
Feature / command to use: ...
Referenced docs link: ... (v8.0 branch)
```

This template is helpful when discussing compatibility issues: others immediately know **which server**, **which client**, and **which documentation** are being referenced.

## 7. Step-by-Step Workflow for Version-Specific Official Docs

### Step 1 — Formulate a Precise Technical Question

Do not simply search `MongoDB aggregate`. Define the exact task—for example: “In MongoDB Server 8.0, how does `find()` select specific fields using projection?” or “Where does my current Java Sync Driver version configure read concern?”. The more specific the question, the easier it is to pick the right product and reference page.

### Step 2 — Choose the Documentation Set Before Picking a Page

| If you need to know... | Start from... |
|---|---|
| Meaning of documents, BSON, indexes, replication, sharding, database commands | **Database Manual** for your server version |
| Helper syntax `db.collection.find()` in the shell | **mongosh Methods** in the Manual / MongoDB Shell docs |
| `MongoClient`, `MongoCollection`, `Filters`, `Updates` in Java | **Java Sync Driver** for your driver version |
| `MongoTemplate`, `MongoRepository`, Spring Data mapping | **Spring Data MongoDB** for your Spring Data version |
| Cluster management, backups, UI, and cloud service limits | **MongoDB Atlas Docs** and deployment configuration |
| `mongodump`, `mongorestore`, or JSON/CSV export | **MongoDB Database Tools** for your tool version |

### Step 3 — Pin the Version Branch

Examples of two official branches for the Server Manual:

- [Database Manual — 8.0 branch](https://www.mongodb.com/docs/v8.0/)
- [Database Manual — 7.0 branch](https://www.mongodb.com/docs/v7.0/)

Example of the same **Documents** topic across two branches:

- [Documents — 8.0](https://www.mongodb.com/docs/v8.0/core/document/)
- [Documents — 7.0](https://www.mongodb.com/docs/v7.0/core/document/)

Paths containing `v8.0` or `v7.0` identify the branch; pages under `/docs/manual/` may point to the current release and shift over time. For drivers, version numbering and URL paths are **driver-specific**—you cannot mechanically substitute `v8.0` into a driver URL. Many pages also include a version switcher directly in the UI; always verify the version badge after navigating or clicking search results.

### Step 4 — Open the Right Page Type and Read All Callouts

When opening a feature or method page, read in order:

1. **Definition / Overview** — what problem does the feature solve?
2. **Syntax / Parameters / Examples** — which parameters, data types, and examples are valid?
3. **Compatibility / Behavior / Restrictions** — which deployment types are supported, and are there FCV or privilege requirements?
4. **New in version / Changed in version / Deprecated** — in which release was the feature introduced, changed, or deprecated?
5. **Release Notes / Upgrade Guide** — are there compatibility changes, caveats, or bug fixes in relevant patch releases?

A `New in version 8.0` note on the **8.0** documentation does not mean the feature is available in **7.0**. Conversely, an old snippet that still runs on 8.0 does not prove it remains the recommended approach: newer replacement APIs or security/operational changes may exist.

### Step 5 — Cross-Check Server, FCV, Client, and Environment

For example, a Manual page may confirm a command is supported starting in server 8.0, while the Java Driver exposes the corresponding API starting in a specific driver release. Check **both**: whether the server understands the command and whether the current client can issue it as intended. For administrative operations or features involving backward-incompatible persisted state, check **FCV** as well; on Atlas, also verify support for your cluster type/tier.

### Step 6 — Validate in an Appropriate Environment and Record Sources

Read-only examples can be tested in a development environment with isolated data. Operations that modify data or configuration must follow your system's change-management process. When documenting findings, record the **versioned doc branch link**, **actual patch version**, and **date checked** if releases may continue to evolve. Keeping the versioned URL prevents future readers from accidentally following instructions meant for a different release series.

### 7.1. Searching Effectively When Documentation Is Large

Useful search queries (replace the version number with your branch):

```text
site:mongodb.com/docs/v8.0/ "db.collection.find" projection
site:mongodb.com/docs/v8.0/ "read concern" "majority"
site:mongodb.com/docs/v8.0/ "Changed in version" index
site:mongodb.com/docs/drivers/java/sync/ "MongoCollection" "find"
```

These are **web search queries**, not MongoDB commands. Search results only point the way; verify details on the official page after opening it. If a URL redirects, inspect the final version badge and path. Old blog posts or forum answers should only guide keyword discovery, never replace version-specific documentation when determining compatibility.

## 8. Practical Example: Looking Up `bulkWrite` When Upgrading from 7.0 to 8.0

Suppose a team needs to write multiple changes across **multiple collections** in a single request. Searching turns up two very similar names:

- **`db.collection.bulkWrite()`** — a `mongosh` method for performing multiple write operations on a **single collection**.
- **`bulkWrite` database command** introduced in **MongoDB Server 8.0** — supports bulk operations spanning **multiple collections** in a single request.

Looking only at the name `bulkWrite`, the team might mistakenly assume a 7.0 deployment already supports both forms. The proper lookup workflow:

1. State the requirement clearly: “multi-collection bulk write, MongoDB Server 7.0 or 8.0?”.
2. Check `db.version()` on the deployment and inspect FCV if the environment is mid-upgrade.
3. Open [MongoDB 8.0 Release Notes](https://www.mongodb.com/docs/v8.0/release-notes/8.0/) to confirm which version introduced the new **command**.
4. Open the **database command** reference and the corresponding **`db.collection.bulkWrite()`** page; read limits, privileges, syntax, prerequisites, and driver support.
5. If the environment is still on 7.0, do not attempt to use the 8.0 server command merely because a similarly named method exists in 7.0. If already on 8.0, continue verifying patch version, FCV, and the appropriate client call path.

This example illustrates why you must distinguish **feature name**, **API type**, **documentation product**, and **version branch**. Similar-looking code snippets are never sufficient proof of compatibility.

## 9. Common Misconceptions and How to Correct Them

| Misconception | Accurate Understanding |
|---|---|
| “A collection is a SQL table, so every document must have the same columns.” | Collections store documents with flexible schemas; schema rules can be enforced via validation and at the application layer. |
| “BSON is just an encoded JSON string.” | BSON is a binary format with rich data types; shell/Extended JSON display does not mean stored data is JSON text. |
| “`_id` is always an ObjectId.” | `_id` is an identifier; `ObjectId` is merely a common type, not mandatory in every case. |
| “`find()` directly returns an array.” | `find()` typically returns a **cursor**; iterate over it or convert to an array when needed while watching memory. |
| “Every `$`-prefixed operator works anywhere.” | Query operators, update operators, aggregation expressions, and pipeline stages belong to distinct syntactic contexts. |
| “Adding an index makes every query fast.” | Indexes must align with filters/sorts, and you must inspect execution plans, real data, and write overhead. |
| “Replica sets and sharding are the same thing.” | Replication provides availability/copies; sharding distributes data. Shards typically use replica sets, yet the two are distinct mechanisms. |
| “Reading from a secondary always sees the latest write immediately.” | Depends on replication, read preference, read concern, and session context. |
| “`mongosh --version` is the running database version.” | That is the local shell version; `db.version()` reports the connected server instance. |
| “FCV = server version = Stable API version.” | These are three independent layers with distinct purposes. |
| “If a `/manual/` link works today, it will always refer to the same version.” | The current-release path can shift; save fixed-branch URLs when reproducibility matters. |
| “If a feature is in the Server Manual, my Java Driver definitely has that API.” | Read the driver documentation, compatibility matrix, and client release notes as well. |

## 10. Self-Check Exercises

**Exercise 1 — Term classification.** Using the `orders` document in Section 1, identify the database, collection, nested field, array, and identifier key. Answer: illustrative database `shop`, collection `orders`, nested field `customer.city`, array `items`, identifier key `_id`.

**Exercise 2 — Command prediction.** What does `db.orders.find({ status: "PAID" }, { orderNo: 1, _id: 0 })` do? Answer: the filter selects documents with `status = "PAID"`; the projection returns `orderNo` and excludes `_id`; the result is a cursor.

**Exercise 3 — Pipeline recognition.** In `[{ $match: ... }, { $group: ... }]`, which stage filters documents and which aggregates? Answer: `$match` filters, and `$group` groups/aggregates by the group key.

**Exercise 4 — Version-based lookup.** A developer workstation has the latest `mongosh` installed, but the application connects to MongoDB Server 7.0. You plan to use a stage marked `New in version 8.0` in the 8.0 docs. Can you apply it directly? Answer: **you cannot conclude it is usable yet**; verify against the actual server deployment, 7.0 documentation, FCV/driver/environment prerequisites, and test on an appropriate system.

**Exercise 5 — Distinguishing versions.** When `db.version()` returns `8.0.x` while `featureCompatibilityVersion.version` is `7.0`, how should this be recorded? Answer: the server binary is on the 8.0 branch while FCV is currently at 7.0; consult the official upgrade guide before using FCV-gated features, and never change the parameter casually just to test.

## 11. Official Reference Documentation Set

The links below are for further lookup; for unpinned documentation pages, verify the version selector and product label in the UI:

- [MongoDB Database Manual (current branch)](https://www.mongodb.com/docs/manual/) — general entry point.
- [Database Manual 8.0](https://www.mongodb.com/docs/v8.0/) and [Database Manual 7.0](https://www.mongodb.com/docs/v7.0/) — examples of version-pinned documentation branches.
- [Documents — 8.0](https://www.mongodb.com/docs/v8.0/core/document/) — BSON documents, fields, `_id`, size limits, dot notation.
- [Databases and Collections — 8.0](https://www.mongodb.com/docs/v8.0/core/databases-and-collections/) — data organization.
- [CRUD Operations — 8.0](https://www.mongodb.com/docs/v8.0/crud/) and [`db.collection.find()` — 8.0](https://www.mongodb.com/docs/v8.0/reference/method/db.collection.find/) — query operations.
- [Manual Reference — 8.0](https://www.mongodb.com/docs/v8.0/reference/) — glossary, commands, mongosh methods, query language, limits.
- [MongoDB Versions and Upgrade Paths](https://www.mongodb.com/docs/mongodb-versions/) — version numbering and upgrade paths.
- [Release Notes — 8.0](https://www.mongodb.com/docs/v8.0/release-notes/) — release/patch changes.
- [`db.version()`](https://www.mongodb.com/docs/manual/reference/method/db.version/) — checking the connected instance version.
- [Feature Compatibility Version / `setFeatureCompatibilityVersion`](https://www.mongodb.com/docs/manual/reference/command/setfeaturecompatibilityversion/) — FCV semantics and how to **read** FCV via `getParameter`; read the matching version branch before administrative actions.
- [Stable API](https://www.mongodb.com/docs/manual/reference/stable-api/) — scope of API compatibility guarantees.
- [Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — Java driver documentation; select your project's exact library version.

What to keep consistent while learning MongoDB is always naming **the exact component** you are referring to and always recording **the exact version** of that component. Once you know whether a name belongs to the data layer, query layer, topology layer, or client layer, you will find the right documentation faster and avoid applying mismatched guidance across releases.
