# Embedding Documents vs. Referencing: Selection Criteria

MongoDB stores data as **BSON documents** inside **collections**. When two pieces of data are related, there are typically two ways to organize them: **embedding** related data inside the same document, or **referencing** by storing an identifier to retrieve documents from another collection when needed. This decision directly affects read speed, number of queries, update operations, consistency, document size, and system scalability.

This lesson belongs to the **Document Model** topic in MongoDB. The goal is not to offer a rule like "embedding is always faster" or "referencing is always cleaner," but to know **when to choose each approach and why**. The examples use `mongosh` and an illustrative e-commerce system; the same principles apply to blogs, social networks, IoT, and enterprise management.

After this lesson, you will be able to:

- Distinguish **embedded documents**, **arrays of subdocuments**, **manual references**, **DBRefs**, and intentional data duplication.
- Analyze **cardinality**, access direction, update patterns, lifecycle, and growth bounds of a relationship.
- Choose representations for **one-to-one**, **one-to-few**, **unbounded one-to-many**, and **many-to-many** relationships.
- Explain the relationship between document design and **single-document atomicity**, **multi-document transactions**, and **`$lookup`**.
- Apply design patterns such as **subset**, **extended reference**, **snapshot**, **bucket**, or hybrid models when needed.
- Identify anti-patterns such as **unbounded arrays**, duplication without synchronization rules, and references lacking proper indexes.

## 1. Foundational Concepts

### 1.1. Embedding

**Embedding** means placing related data as a **nested document** or an **array of nested documents** directly inside the parent document. For example, a customer has contact details and a few shipping addresses:

~~~javascript
{
  _id: "C-100",
  name: "An",
  contact: {
    email: "an@example.test",
    phone: "0900000000"
  },
  shippingAddresses: [
    { addressId: "A1", city: "Hanoi", isDefault: true },
    { addressId: "A2", city: "Da Nang", isDefault: false }
  ]
}
~~~

Here `contact` is an **embedded document**; each element of `shippingAddresses` is a **subdocument** in an array. A single read of the customer document retrieves all related details without querying another collection.

~~~text
customers
└── Customer C-100
    ├── name
    ├── contact { email, phone }
    └── shippingAddresses [
          { addressId, city, isDefault },
          { addressId, city, isDefault }
        ]
~~~

Embedding makes sense when child data is **usually read with the parent**, has a **small or clearly bounded count**, and has a **lifecycle tied to the parent**. Examples include a user profile with a personal settings object, or an order with a set of line items locked in at purchase time.

### 1.2. Referencing

**Referencing** means related data lives in its own document, and the current document stores the **ID of that other document**. For example:

~~~javascript
// Collection customers
{ _id: "C-100", name: "An", email: "an@example.test" }

// Collection orders
{
  _id: "O-1001",
  customerId: "C-100",
  status: "PAID",
  total: 290000
}
~~~

~~~text
customers                        orders
┌────────────────────┐          ┌───────────────────────┐
│ _id: C-100         │ <------- │ customerId: C-100     │
│ name: An           │          │ _id: O-1001           │
└────────────────────┘          │ total: 290000         │
                                └───────────────────────┘
~~~

The example above uses a **manual reference**: manually defining a `customerId` field with the same value and **same BSON type** as `customers._id`. MongoDB does not automatically turn this field into a foreign key constraint. To display the customer's name from an order, the application can run another query against `customers` or use the `$lookup` aggregation stage.

Referencing is usually appropriate when related data **can grow without bound**, is read/updated **independently**, has its **own lifecycle**, or is shared by multiple entities.

### 1.3. Manual Reference vs. DBRef

A **manual reference** simply stores the ID:

~~~javascript
{ _id: "O-1001", customerId: "C-100" }
~~~

A **DBRef** is a convention for representing a reference as a document with fields such as `$ref` (collection), `$id` (ID), and optionally `$db` (database):

~~~javascript
{
  customerRef: {
    $ref: "customers",
    $id: "C-100"
  }
}
~~~

This is an **illustration of DBRef structure**, not an automatic join or foreign key. MongoDB Server does not automatically resolve DBRefs across queries; dereferencing support depends on drivers/tools and application logic. In most typical data models, **manual references** are simpler and easier to control. Only choose DBRef when there is a specific compatibility reason with a framework, schema, or existing system.

### 1.4. Relationships vs. Physical Layout

Putting two objects in the same document provides **single-document atomicity**, while placing them in separate collections lets them evolve and scale more independently. However:

- Being in the same collection **does not mean** being in the same document; two documents in the same collection still have separate atomicity boundaries.
- Being in different collections **does not mean** combined data can never be fetched; MongoDB has `$lookup`, or the application can query by ID.
- A MongoDB document should not be treated like a SQL table simply because it has many fields.
- `ObjectId` is a common ID type, **not mandatory**; a reference can use a string, number, or `ObjectId` as long as it is consistent.

## 2. The Most Important Decision Criteria

Do not choose embedding vs. referencing based on a single criterion. Evaluate **actual access patterns**, growth rate, and data consistency obligations.

| Criterion | Favors **Embedding** | Favors **Referencing** |
|---|---|---|
| **Data reads** | Parent and child are almost always read together. | Often only the parent or only the child is needed. |
| **Cardinality** | One-to-one, one-to-few, or strictly bounded one-to-many. | One-to-very-many, many-to-many, long-term unbounded growth. |
| **Size growth** | Predictable and safely below the document size limit. | Can grow without bound, or each element is very large. |
| **Update frequency** | Child data is stable, or usually changes together with parent. | Child data changes independently and frequently. |
| **Lifecycle** | Child belongs to parent; deleting parent typically removes child. | Child must survive parent changes/deletion or is shared. |
| **Ownership & reuse** | Data belongs exclusively to one business aggregate. | One entity is referenced by many documents. |
| **Required atomicity** | Fields must change atomically within one document. | Independent updates, or transactions needed for multi-document writes. |
| **Duplication / consistency** | Intentional snapshot, e.g. price and name at purchase time. | Need a single canonical record updated in one place. |
| **Indexes & queries** | Usually filtered/read via parent; nested field indexes suffice. | Need to search, paginate, sort, or index children independently. |
| **Permissions / retention** | Same access policy, retention, and TTL logic. | Different permissions, retention periods, or archiving needs. |
| **Sharding / scaling** | Queried within the same document, minimizing cross-shard dependencies. | Data needs to be partitioned/scaled independently. |
| **Join cost** | Prioritize a single read returning data together. | Accept extra queries or controlled `$lookup` usage. |

### 2.1. Cardinality: Count the Actual Number of Children

Common relationship labels include:

| Relationship | Example | Initial Option to Evaluate |
|---|---|---|
| **One-to-one** | A user has one display settings object | Embed when sharing lifecycle and access pattern. |
| **One-to-few** | A product has a few specs; a user has a few addresses | Embed if there is a realistic growth bound. |
| **Bounded one-to-many** | An order has a business-capped number of line items | Can embed to read/write together with the order. |
| **Unbounded one-to-many** | An article has millions of comments | Reference: comments are separate documents. |
| **Many-to-many** | Students enroll in many courses; courses have many students | Typically use a link/junction collection with references. |

**Cardinality alone is not enough to decide.** A one-to-one relationship should still be split into separate documents if the fields have completely different security policies, update rates, or lifecycles. A one-to-many relationship can still be embedded when the element count is **truly bounded** and always fetched with the parent.

In particular, "currently there are only 8 elements" is **different** from "business rules enforce a maximum of 8 elements." Always ask how large the child set will grow over 1–3 years.

### 2.2. Query Locality: Is the Data Actually Used Together?

MongoDB shines when the fields an operation needs reside in **the same document**, eliminating a second client round trip or join stage to fetch related data.

For example, an order confirmation page typically needs in one fetch: order details, line items, paid prices, and the shipping address **at the time of ordering**. These are strong candidates to embed in the order.

Conversely, a product page might have **hundreds of thousands of reviews** while displaying only the 5 latest reviews. Embedding all reviews in the product makes the document unnecessarily huge. Store reviews separately, index by `productId` and timestamp, and run bounded paginated queries.

### 2.3. Atomicity Boundaries

A write operation on **a single document** in MongoDB is atomic, even when modifying multiple nested fields and subdocuments. Therefore, if a business invariant is tightly bound to a single aggregate, embedding can protect that invariant without a multi-document transaction.

Conversely, referencing creates **two or more independent documents**. Updating both is not inherently a single atomic operation. If business rules require "both commit or both abort," evaluate **transactions** on a supported deployment, or a workflow with proper **idempotency/compensation**.

**Do not embed solely to avoid every transaction.** If child data is unbounded or has an independent lifecycle, forcing it into the same document can cause bigger problems than the atomicity benefit is worth.

### 2.4. Change Semantics and Historical Truth

Two distinct needs are often confused:

- **Live data:** a customer's current email, a product's current price, current inventory level. When multiple places share one latest value, referencing the **source of truth** avoids out-of-sync copies.
- **Event-frozen data (snapshot/historical data):** the product name and price **at purchase time**, the address used to deliver an order. Embedding a snapshot is the right choice even though the data also exists in another collection. If the product name/price changes later, old invoices **must not change retroactively**.

Because of this, many production systems use a **hybrid model**: referencing the source entity **and** embedding a few snapshot fields that must be preserved.

## 3. Typical Cases for Embedding

### 3.1. A Configuration Object Tied to a Parent

~~~javascript
// A user has a small display configuration object.
db.getSiblingDB("modeling_lab").users.insertOne({
  _id: "U-100",
  name: "An",
  preferences: {
    language: "vi",
    theme: "dark",
    notifications: { email: true, push: false }
  }
})
~~~

A single user read fetches `preferences`. When changing the theme, you can update the nested field:

~~~javascript
db.getSiblingDB("modeling_lab").users.updateOne(
  { _id: "U-100" },
  { $set: { "preferences.theme": "light" } }
)
~~~

**Why embed:** one-to-one, small object, usually read with the user, lifecycle tied to the user. However, if `preferences` contains sensitive data requiring separate access control or a different retention cycle, re-evaluate.

### 3.2. Orders Embedding Line Items and Snapshots

Each order is a **business aggregate**. A typical reasonable design:

~~~javascript
{
  _id: "O-1001",
  customerId: "C-100",
  createdAt: ISODate("2026-11-12T10:00:00Z"),
  status: "PAID",
  shippingAddress: {
    recipient: "An",
    city: "Hanoi",
    addressLine: "12 Street A"
  },
  items: [
    {
      productId: "P-10",
      sku: "BOOK-01",
      nameAtPurchase: "Notebook",
      unitPriceAtPurchase: 120000,
      quantity: 2
    },
    {
      productId: "P-11",
      sku: "PEN-02",
      nameAtPurchase: "Ink Pen",
      unitPriceAtPurchase: 50000,
      quantity: 1
    }
  ],
  total: 290000
}
~~~

This design combines **both embedding and referencing**:

- `customerId` and `productId` are references to independently living entities.
- `shippingAddress`, `nameAtPurchase`, and `unitPriceAtPurchase` are historical snapshots.
- `items` is a child set belonging exclusively to the order; it usually has a practical business limit.

All items, the snapshot address, and the order status live in one document, fitting the invoice detail page well. When catalog prices in `products` change, **do not update locked-in prices on existing orders**.

If the system allows an order to have a massive or unbounded auto-generated number of line items, consider separating order lines into their own collection; do not assume every order is small by default.

### 3.3. Reading and Updating Subdocuments

Accessing embedded fields uses **dot notation**:

~~~javascript
const lab = db.getSiblingDB("modeling_lab")

// Fetch paid orders for customers in Hanoi.
lab.orders.find(
  { "shippingAddress.city": "Hanoi", status: "PAID" },
  { _id: 1, status: 1, total: 1 }
)

// Update one field without replacing the entire order.
lab.orders.updateOne(
  { _id: "O-1001" },
  { $set: { status: "PACKING" } }
)
~~~

For an array of embedded documents, use `$elemMatch` to apply multiple conditions to **the same element**:

~~~javascript
lab.orders.find({
  items: {
    $elemMatch: {
      productId: "P-10",
      quantity: { $gte: 2 }
    }
  }
})
~~~

If you write `"items.productId"` and `"items.quantity"` as independent conditions without `$elemMatch`, they can match **two different elements** in the same array. This is an important distinction when modeling embedded arrays.

## 4. Typical Cases for Referencing

### 4.1. A Product with Very Many Reviews

Reviews can grow continuously, be paginated chronologically, filtered by rating, and moderated independently. Embedding all reviews into the product causes the product document to bloat, putting pressure on document size, update costs, cache, and queries.

Referencing model:

~~~javascript
// products
{
  _id: "P-10",
  name: "Notebook",
  currentPrice: 120000
}

// reviews
{
  _id: "R-1001",
  productId: "P-10",
  authorId: "U-100",
  rating: 5,
  content: "Good paper",
  createdAt: ISODate("2026-11-12T10:00:00Z")
}
~~~

Each review is a separate document. Paginated query with an index:

~~~javascript
const lab = db.getSiblingDB("modeling_lab")

// Optimized for querying the newest reviews of a product.
lab.reviews.createIndex({ productId: 1, createdAt: -1, _id: -1 })

lab.reviews.find({ productId: "P-10" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(5)
~~~

At large scale, **keyset/cursor** pagination (`createdAt` and `_id`) is usually better than deep `skip`, because `skip` must scan past many results. Having an index aligned with the access pattern matters far more than what field name is used for the reference.

**Benefit:** reviews grow without bloating the product document indefinitely; reviews can be queried, deleted, moderated, and aggregated independently.

### 4.2. Many-to-Many Relationships Using a Link Collection

Suppose **students** and **courses** have a many-to-many relationship: each student takes many courses, and each course has many students.

A bidirectional reference design using two arrays `student.courseIds` and `course.studentIds` is hard to maintain, especially when a course has very large enrollment. A **link collection** `enrollments` represents each relationship as one document:

~~~javascript
// students
{ _id: "S-1", name: "Minh" }

// courses
{ _id: "K-1", title: "MongoDB Fundamentals" }

// enrollments
{
  _id: "E-1",
  studentId: "S-1",
  courseId: "K-1",
  enrolledAt: ISODate("2026-11-12T10:00:00Z"),
  progressPercent: 20
}
~~~

~~~javascript
const lab = db.getSiblingDB("modeling_lab")

// A student can only enroll once in the same course.
lab.enrollments.createIndex(
  { studentId: 1, courseId: 1 },
  { unique: true }
)

// List courses for a student.
lab.enrollments.find({ studentId: "S-1" })

// List students in a course by enrollment time.
lab.enrollments.createIndex({ courseId: 1, enrolledAt: -1 })
lab.enrollments.find({ courseId: "K-1" }).sort({ enrolledAt: -1 })
~~~

`enrollments` can store **relationship attributes** such as enrollment date and progress. An enrollment document has its own lifecycle and update patterns, making it much more suitable than embedding an unbounded array inside `course`.

### 4.3. Relationships That Must Exist Independently or Be Shared

Use referencing when:

- A **customer** has very many **orders**; orders need independent queries by time and status.
- A **user** has very many **activity events**; events need separate retention, partitioning, or archiving.
- A **product** appears in millions of orders; the catalog holds current info while orders hold snapshots.
- An **organization** manages many **employees**, and employees transferring departments have a lifecycle that is not simply child data of an organization.
- An **article** has an unbounded number of comments.

A reference can be schema-valid yet point to a document that **has been deleted or does not exist**. MongoDB does not automatically enforce foreign keys or cascade deletes like an RDBMS. The application must define policies for **delete prevention**, **cascading**, **soft deletion**, **keeping snapshots**, or **asynchronous cleanup** according to business rules.

## 5. Retrieving Referenced Data

### 5.1. Two Queries from the Application

Given an order containing `customerId`:

~~~javascript
const lab = db.getSiblingDB("modeling_lab")
const order = lab.orders.findOne({ _id: "O-1001" })

if (order !== null) {
  const customer = lab.customers.findOne({ _id: order.customerId })
  printjson({ order, customer })
}
~~~

The advantage is simplicity and control over projections and caching; the drawback is an extra round trip if multiple IDs are not batched. When loading a list of 100 orders, **do not** query customers one order at a time in an N+1 pattern. Collect unique `customerId` values and use a single `$in` query or a `$lookup` aggregation.

### 5.2. Combining with `$lookup`

The `$lookup` aggregation stage can join documents from another collection **in the same database** using matching conditions:

~~~javascript
const lab = db.getSiblingDB("modeling_lab")

lab.orders.aggregate([
  { $match: { _id: "O-1001" } },
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  {
    $unwind: {
      path: "$customer",
      preserveNullAndEmptyArrays: true
    }
  },
  {
    $project: {
      _id: 1,
      status: 1,
      total: 1,
      "customer._id": 1,
      "customer.name": 1
    }
  }
])
~~~

`$lookup` returns **an array** in the `customer` field because in principle multiple documents could match. `$unwind` flattens the array element into the result document; `preserveNullAndEmptyArrays` prevents dropping the order if the customer does not exist. When joining on `_id`, the default index on `customers._id` supports finding the related document.

**`$lookup` does not turn referencing into embedding.** The engine still must process the join; joining large collections or returning many elements can be resource-intensive. Filter early, limit results, project appropriately, index the join side, and check `explain()`. `$lookup` support on sharded collections and other limitations depend on the MongoDB version; consult the Database Manual for your deployment.

### 5.3. No Automatic Foreign Key Constraints

Creating a `customerId` field does **not** automatically:

- verify that the ID exists in `customers` upon insert;
- create an index on `orders.customerId`;
- delete orders when a customer is deleted;
- synchronize customer name/email changes into orders;
- lock across two collections to enforce business invariants.

The application must choose appropriate policies and create indexes matching queries:

~~~javascript
lab.orders.createIndex({ customerId: 1, createdAt: -1 })

// Look up orders for a customer:
lab.orders.find({ customerId: "C-100" })
  .sort({ createdAt: -1 })
  .limit(20)
~~~

Remember that **ID types must match**: the string `"65..."` does not equal BSON `ObjectId("65...")` even if the displayed hex string looks identical.

## 6. Hybrid Models: Embed Some Parts, Reference the Rest

In practice, the choice does not have to be "embed everything" or "separate everything." A hybrid model often achieves a better balance.

### 6.1. Extended Reference Pattern

An order references a customer, yet list screens need to show the **customer name** very frequently. You can embed a small subset of fields to avoid lookups:

~~~javascript
{
  _id: "O-1001",
  customerId: "C-100",            // canonical reference
  customerDisplay: {              // read-optimized copy
    name: "An",
    membershipTierAtOrder: "GOLD"
  },
  status: "PAID",
  total: 290000
}
~~~

This is an **extended reference**: it keeps the canonical ID while holding a few needed fields at the read site. However, you must clearly answer:

- Is `customerDisplay.name` a **snapshot at order time**, or must it always reflect the current name?
- If it must reflect the current name, who is responsible for updating copies when a customer renames?
- If synchronization fails, how long is showing stale data acceptable?

Without answering these three questions, duplication easily becomes **data drift**. For data that must always be strictly fresh, a live lookup or an update workflow with stronger guarantees may be more suitable.

### 6.2. Subset Pattern: Embed a Small Portion, Reference the Full Set

A product page only needs a few recent reviews and the total review count, while all reviews live in a separate collection:

~~~javascript
// products
{
  _id: "P-10",
  name: "Notebook",
  ratingCount: 12450,
  ratingAverage: 4.6,
  recentReviews: [
    { reviewId: "R-900", authorName: "Minh", rating: 5, excerpt: "Good" },
    { reviewId: "R-899", authorName: "Lan", rating: 4, excerpt: "Okay" }
  ]
}

// reviews contains the full set of reviews, looked up by productId.
~~~

`recentReviews` must have a **strict bound** (e.g., at most 3–5 elements); it is a presentation cache, not the primary source of reviews. To maintain a list of at most 5 newest IDs inside `product`:

~~~javascript
db.getSiblingDB("modeling_lab").products.updateOne(
  { _id: "P-10" },
  {
    $push: {
      recentReviewIds: {
        $each: ["R-901"],
        $position: 0,
        $slice: 5
      }
    }
  }
)
~~~

The snippet above demonstrates **how to cap an array**; it does not automatically guarantee that the new review exists or that updating product and review is atomic across two documents. If strong consistency between them is needed, consider transactions or accept asynchronous updates with a recovery mechanism.

### 6.3. Snapshot Pattern: Freezing Event Data

At order placement, the catalog price is 120,000 VND. A week later the price changes to 130,000 VND. A finalized invoice **must retain 120,000**, so the order embeds `unitPriceAtPurchase`. The `productId` reference remains useful to link back to the catalog, but **never use the live price to recalculate paid amounts**.

This resembles extended reference in data shape, but differs in **semantics**: a historical snapshot **intentionally does not synchronize**, whereas a current-state cache **requires a synchronization strategy**.

### 6.4. Bucket Pattern for Long Data Series

An IoT sensor can emit millions of readings, each very small. Embedding every reading into a single `sensor` document is not viable. You can store each reading as a separate document, or group them into **size- or time-bounded buckets**:

~~~javascript
// readingsBuckets
{
  _id: "sensor-7:2026-11-14T10",
  sensorId: "sensor-7",
  hourStart: ISODate("2026-11-14T10:00:00Z"),
  samples: [
    { second: 0, temperature: 27.1 },
    { second: 15, temperature: 27.2 }
    // ... bounded by time window or element count
  ]
}
~~~

Bucketing is **embedding inside each bounded window**, while **referencing/querying by sensorId and time range** across buckets. For telemetry/time-series workloads, also evaluate **MongoDB time series collections**, as the server provides specialized storage optimizations; do not build manual bucketing if native time series collections meet your needs.

## 7. Size Limits, Growth, and Performance

### 7.1. The 16 MiB Limit for a BSON Document

MongoDB caps a regular **BSON document** at **16 MiB**. If you embed an array that grows forever, sooner or later the document will hit the limit and new writes will fail. Even before reaching 16 MiB, overly large documents can:

- cause excessive data reads and inflate network payloads;
- put pressure on the working set and cache;
- increase the processing cost of updating a hot document;
- complicate pagination or retention management;
- force all child updates to contend on a single document.

**GridFS** is meant for large files, not as a workaround to keep embedding unbounded business arrays. Define an **element ceiling** and a **size ceiling** for a relationship before embedding.

### 7.2. Anti-Pattern: Unbounded Array

Risky example:

~~~javascript
{
  _id: "ARTICLE-1",
  title: "MongoDB",
  comments: [
    // Continuously appending every comment from millions of readers...
  ]
}
~~~

The issue is not that MongoDB lacks array support: **bounded arrays** are a strength of the document model. The issue is putting an **entire unbounded child set** into **a single document**. Instead:

~~~javascript
// articles
{ _id: "ARTICLE-1", title: "MongoDB", commentCount: 1000000 }

// comments
{
  _id: "COMMENT-1001",
  articleId: "ARTICLE-1",
  authorId: "U-100",
  text: "Helpful article",
  createdAt: ISODate("2026-11-14T10:00:00Z")
}
~~~

Create an index for querying comments per article:

~~~javascript
db.getSiblingDB("modeling_lab").comments.createIndex({
  articleId: 1,
  createdAt: -1,
  _id: -1
})
~~~

If you want to display a few recent comments directly on the article, use a **subset** with a fixed element cap while keeping all comments in their own collection.

### 7.3. Indexes on Embedded Fields and Multikey

MongoDB can index nested fields using dot notation:

~~~javascript
const lab = db.getSiblingDB("modeling_lab")
lab.orders.createIndex({ "shippingAddress.city": 1, status: 1 })
~~~

For an array field, MongoDB can create a **multikey index**:

~~~javascript
lab.orders.createIndex({ "items.productId": 1 })
~~~

Multikey indexes support queries on arrays, but come with specific rules and constraints, especially when compound indexes involve multiple array fields. Each array element can affect the number of index entries and write overhead; large arrays do not automatically become a good design just because an index exists.

When child data is frequently queried, filtered, sorted, or paginated **independently across very many parent documents**, a separate collection with proper indexes can be simpler and more efficient.

### 7.4. Update Costs and Document Hotspots

If a product stores thousands of views/likes/comments in the same document, concurrent users updating it can create a **hot document** and write conflicts. Splitting high-write events into a separate collection or using an appropriate aggregation mechanism can reduce contention.

Conversely, over-splitting into tiny collections forces every request to make many round trips or `$lookup` stages, adding operational cost and consistency complexity. Good design finds **document boundaries** aligned with read/write units and system growth limits.

## 8. Atomicity, Consistency, and Data Lifecycle

### 8.1. Embedding Keeps an Invariant Within One Document

Suppose an order has `status` and a list of `items`. An update changing `status` and related fields within the order itself is atomic:

~~~javascript
db.getSiblingDB("modeling_lab").orders.updateOne(
  { _id: "O-1001", status: "PENDING" },
  {
    $set: {
      status: "PAID",
      paidAt: ISODate("2026-11-14T10:00:00Z")
    }
  }
)
~~~

If two workers simultaneously try to confirm the same order, the `status: "PENDING"` filter ensures only one worker transitions the state while the document is still eligible. Combine `matchedCount` with application-level idempotency to handle retries. This does not require a multi-document transaction for **updating order status alone**.

### 8.2. Referencing Does Not Synchronize Documents Automatically

If a single request must **decrement product inventory** and **create an order** so both commit or abort together, two separate writes do not automatically guarantee joint atomicity:

~~~text
Write 1: products[P-10].stock -= 1
Write 2: insert orders[O-1001]

If one write succeeds and the other fails:
    the state may violate business invariants.
~~~

When ACID guarantees across multiple documents are needed, you can use a **multi-document transaction** on a supported deployment. However, transactions incur overhead, resource limits, and retry rules; do not turn every write into a transaction simply because references exist. For workflows spanning multiple independent services, also evaluate **outbox**, **saga/compensation**, and idempotency.

### 8.3. Deletions and Relationship Changes

For example, deleting a customer:

- Should historical orders be kept? Usually yes, depending on business/legal policy.
- When a customer is deleted, does `orders.customerId` become an unresolvable reference, or does the order store snapshots so it still renders?
- Can you soft-delete the customer to preserve links, or anonymize personal information inside orders under data protection requirements?
- A custom application-level cascade delete must handle partial failures; MongoDB does not perform it automatically.

Relationship design must come with clear **lifecycle policies**, not just field layouts.

### 8.4. Avoid Duplication Without an Owner

Suppose `customers.name`, `orders.customerName`, and `invoices.customerName` are all used to display the **current name**. If a customer changes their name, who updates the two copies? If one update fails, how is it recovered?

Three design directions:

1. **Pure reference** when canonical live values are needed and lookup latency is acceptable.
2. **Intentional snapshot** when historical data must remain unchanged.
3. **Controlled denormalization** when read speed is prioritized and eventual consistency is acceptable; define an owner, event/update propagation, and reconciliation.

Never add a duplicated field to a schema without knowing whether it is a snapshot, a cache, or canonical data.

## 9. Sharding and Scale: Is the Data Co-Located?

In a sharded cluster, data distribution and the **shard key** affect queries and joins. An embedded document is stored as **one logical document**, so fields needed together have better locality than referenced documents that may live on different shards. However:

- You cannot embed an unbounded array merely to avoid cross-shard access.
- References can point to documents on other shards; evaluate **targeted queries** via the shard key.
- `$lookup` on sharded collections has version-dependent support/constraints and pipeline restrictions; never assume distributed joins are cheap.
- An extremely hot document remains a contention point even if placed on the right shard.
- The 16 MiB document limit applies regardless of how many shards a cluster has.

Do not choose embedding just because "we will shard later." Base the decision on **co-read frequency, cardinality, and write rate**, then analyze shard key impact once a concrete sharding plan exists.

## 10. A Repeatable Decision Process

### Step 1 — Write Down Data Usage Operations

Instead of starting from a SQL entity diagram, list actual requests:

~~~text
GET /products/P-10         -> product, current price, 5 newest reviews
GET /products/P-10/reviews -> 20 reviews/page, sorted by createdAt
GET /orders/O-1001         -> order, item snapshots, locked address, status
GET /customers/C-100/orders -> 20 most recent orders
POST /orders               -> create order + handle inventory and payment
PUT /users/U-100/preferences -> update a group of settings
~~~

Which fields does each request need? What percentage of the time are they read together? Do child items need pagination? Do child items need independent filtering/sorting?

### Step 2 — Estimate Scale and Growth Rate

Record real numbers or verifiable assumptions:

~~~text
Customer:
  addresses: average 2, business cap 10
  orders: can grow to tens of thousands

Product:
  categories: a few items
  reviews: unbounded

Order:
  items: capped in the checkout flow
  events/status history: may require long retention
~~~

An array is only safe to embed when there is a **system-enforced ceiling**, not merely based on sample data.

### Step 3 — Define Ownership and Consistency

Ask:

- Does child data survive independently if the parent is deleted?
- Is it shared across multiple parents?
- How many concurrent tasks update the child?
- Should name/price/address be the **current value** or the **value at event time**?
- Must two or more fields/documents commit together?

### Step 4 — Propose Document Boundaries and Indexes

Choose a representation, then **inspect query plans** with representative data. If embedding, add indexes suitable for nested fields and array query patterns. If referencing, add indexes for logical foreign keys and real sort/filter paths; account for extra query round trips or `$lookup` cost.

### Step 5 — Stress-Test Limits and Failure Cases

Ask critical questions:

- If child count grows 100x, is the parent document still reasonable?
- Does a child data change force thousands of copies to synchronize?
- If a target reference does not exist, how does the application behave?
- Is there a risk of hot documents, hitting 16 MiB, or heavy write conflicts?
- When moving to sharding, can access patterns target shards efficiently?

### Step 6 — Document Decisions and Assumptions

Record briefly in architecture docs: **rationale for embedding/referencing, growth bounds, source of truth, update rules, indexes, deletion policy, and performance metrics**. When workload changes, the team knows which assumptions trigger a redesign.

## 11. Decision Table for Common Scenarios

| Scenario | Design Suggestion | Why? |
|---|---|---|
| User has a small `preferences` object | **Embed** in user | Usually read/updated with user, same lifecycle. |
| User has a few bounded shipping addresses | **Embed**, or split if permissions/access differ | Few items, though check real cap and independent queries. |
| Order has at most a few dozen line items | **Embed** items | Read with order, preserves snapshot and single-doc atomicity. |
| Customer has hundreds of thousands of orders | **Reference** from order to customer | Should not embed unbounded order history into customer. |
| Product has millions of reviews | **Reference** reviews; optionally embed subset | Independent pagination, unbounded growth; preview needs little data. |
| Catalog product referenced by many orders | **Reference ID + snapshot on order** | Catalog lives independently; invoices preserve history. |
| Student–Course many-to-many | **Link collection** `enrollments` | Relationship scales large, needs attributes and own indexes. |
| Sensor emits continuous time-series data | **Time series or bounded buckets** | Prevent a sensor document from growing without bound. |
| Contract has a few clauses always signed together | **Embed** if size/lifecycle are stable | Must be read and modified in the same document. |
| Comment has independent moderation/retention | **Reference** | Independent lifecycle, filtering/sorting, and updates. |
| List of 5 latest notifications on user | **Bounded subset** + events collection | Fast UI read, long history stored separately. |
| Sensitive config needing different access than public profile | Usually **reference / separate collection** | Easier to enforce separate access control and lifecycle. |

No table replaces workload measurement. A referenced model can be fast with proper indexes and caching; an embedded model can be slow if it ships megabytes of data just to display a single name.

## 12. Complete Example: Shop Design Combining Both Approaches

The following commands create standalone data in the `modeling_lab` database. This illustrates structure, not a full e-commerce transaction engine.

### 12.1. Create Canonical Customer and Product

~~~javascript
const lab = db.getSiblingDB("modeling_lab")

lab.customers.replaceOne(
  { _id: "C-100" },
  {
    _id: "C-100",
    name: "An",
    email: "an@example.test",
    preferences: { language: "vi" }
  },
  { upsert: true }
)

lab.products.replaceOne(
  { _id: "P-10" },
  {
    _id: "P-10",
    sku: "BOOK-01",
    name: "Notebook",
    currentPrice: 120000
  },
  { upsert: true }
)
~~~

`preferences` is **embedded** inside `customer`; `product` is an independent entity holding the current price.

### 12.2. Create Order Containing Reference IDs and Historical Snapshots

~~~javascript
lab.orders.replaceOne(
  { _id: "O-1001" },
  {
    _id: "O-1001",
    customerId: "C-100",
    createdAt: ISODate("2026-11-12T10:00:00Z"),
    status: "PAID",
    shippingAddress: {
      recipient: "An",
      city: "Hanoi",
      addressLine: "12 Street A"
    },
    items: [
      {
        productId: "P-10",
        sku: "BOOK-01",
        nameAtPurchase: "Notebook",
        unitPriceAtPurchase: 120000,
        quantity: 2
      }
    ],
    total: 240000
  },
  { upsert: true }
)
~~~

Here:

1. `orders.customerId` is a **reference**, allowing lookup of the current customer.
2. `orders.items[].productId` is a **reference**, linking back to the catalog if needed.
3. `orders.items[].unitPriceAtPurchase` and `shippingAddress` are embedded **snapshots**, so order contents are unaffected by later catalog/customer updates.
4. `orders.items` is a **subdocument array** bounded by checkout rules.

### 12.3. Create Separate Reviews

~~~javascript
lab.reviews.replaceOne(
  { _id: "R-1" },
  {
    _id: "R-1",
    productId: "P-10",
    authorId: "C-100",
    rating: 5,
    content: "Product fits well",
    createdAt: ISODate("2026-11-13T08:00:00Z")
  },
  { upsert: true }
)

lab.reviews.createIndex({ productId: 1, createdAt: -1 })
lab.orders.createIndex({ customerId: 1, createdAt: -1 })
~~~

`reviews` is an independent collection because its count can grow indefinitely; the index supports loading reviews by product. `orders` also needs an index by customer because a customer can place many orders.

### 12.4. Test Updating Catalog While Preserving History

~~~javascript
lab.products.updateOne(
  { _id: "P-10" },
  { $set: { currentPrice: 130000 } }
)

printjson(lab.products.findOne({ _id: "P-10" }))
printjson(lab.orders.findOne({ _id: "O-1001" }))
~~~

`products.currentPrice` is now 130,000, while `orders.items[0].unitPriceAtPurchase` **remains 120,000** — matching historical invoice requirements. Without a snapshot, looking up `products.currentPrice` to recompute the order would misrepresent past payment data.

## 13. Evolving the Model as Workload Changes

An initial model need not anticipate every scenario, but it should have an **evolution path**. Suppose reviews were initially embedded because each product had only a few; as products become popular, the array starts growing large.

A conceptually safe migration path:

1. **Establish the new canonical source** (`reviews` collection) and define its schema, IDs, and indexes.
2. **Backfill existing data** from embedded arrays into review documents, keeping IDs stable and handling duplicates.
3. **Update write paths** so two conflicting truths are not produced. If a dual-write phase is used, ensure clear retry/reconciliation mechanisms.
4. **Switch read paths** to the new collection, optionally supporting fallback during the transition.
5. **Reconcile counts and rendered outputs**; only after verification, remove the old embedded array or keep only a bounded subset.

Never run a "copy once and immediately drop the array" migration on a system receiving continuous writes: new data can arrive during the transition window. For large collections, plan for backfilling, change capture, idempotency, and rollout timing.

An application-level **schema version** (e.g., `schemaVersion: 2`) can help read both old and new data shapes during transition; it is completely distinct from MongoDB Server version and FCV.

## 14. Common Misconceptions

| Misconception | Accurate Perspective |
|---|---|
| "MongoDB is a document database so every relationship must be embedded." | The document model supports embedding, referencing, and hybrid models. |
| "MongoDB has no joins." | MongoDB provides the `$lookup` aggregation stage, though joins have specific costs and scope constraints. |
| "For one-to-many, just embed an array." | Only embed if growth is appropriately bounded; avoid unbounded arrays. |
| "For one-to-one, always embed." | Check lifecycle, security, update frequency, and access pattern first. |
| "Storing `customerId` creates a foreign key." | Manual references do not automatically create constraints, indexes, or cascades. |
| "Reference `ObjectId` only needs to match the display string." | BSON types must match; a string is not equal to an `ObjectId`. |
| "Embedding eliminates all need for transactions." | Atomicity only covers **a single document**; multi-document business flows may still need transactions. |
| "Referencing is always slow because of multiple queries." | You can batch with `$in`, use caches/indexes, or `$lookup`; measure actual workload. |
| "Copying customer name into an order always causes inconsistency." | Historical snapshots intentionally keep old values; live caches require synchronization. |
| "After using `$lookup`, you can treat results as an enforced foreign key." | `$lookup` only combines data at read time; it does not enforce relational constraints. |
| "An index on an array lets you embed indefinitely." | Indexes do not remove the 16 MiB limit or large-document update overhead. |
| "Referencing means child data must be in a different collection." | Documents can reference within the same collection or across collections; base it on the model. |

## 15. Practice Exercises and Suggested Answers

### Exercise 1 — User Accounts

Each user has a set of UI settings: language, theme, email notification preferences, at most a couple dozen fields. The profile screen always displays them together with the user.

**Question:** Embed or reference?

**Hint:** **Embed** `preferences` in the user document because it is one-to-one, small, co-read, and shares the same lifecycle; evaluate exceptions if separate access permissions or lifecycles are needed.

### Exercise 2 — Articles and Comments

Each article can have from 0 to millions of comments; the page displays only 20 comments at a time and sorts chronologically.

**Hint:** **Reference** comments to the article via `articleId` and create an index for pagination. You may embed a bounded subset of a few latest comments on the article if clear update rules exist.

### Exercise 3 — Orders and Catalog

Products change prices weekly; paid orders must retain prices, names, and shipping addresses from the time of ordering.

**Hint:** Use **reference IDs** to the catalog/customer and **embed snapshots** inside the order. Never use live prices to recalculate finalized invoices.

### Exercise 4 — Student and Course

A student enrolls in many courses, and a course has many students; progress must be tracked per student–course pair.

**Hint:** Use a **link collection** `enrollments` with `studentId`, `courseId`, `progressPercent`. Create a compound unique index on the ID pair if business rules forbid duplicate enrollments.

### Exercise 5 — Growing Embedded Array

A design puts `users.notifications[]` containing every notification since signup. Each user can generate several hundred notifications per day.

**Hint:** Move notifications to a separate collection with `userId` indexed by timestamp; optionally keep `recentNotifications` capped at 5–10 items inside the user document if fast UI rendering is needed.

### Exercise 6 — Atomicity

One request updates `orders.status` and `products.stock` across two documents. Does using a `productId` reference automatically guarantee both succeed together?

**Hint:** **No**. Each document has its own atomicity boundary; if both must commit/abort together, evaluate transactions or a workflow with idempotency and compensation.

### Exercise 7 — Small Document Under Heavy Updates

A `viewCount` field is embedded in `article`; thousands of clients per second increment the same document. Document size is tiny, yet update latency climbs.

**Hint:** The cause is likely **hot document / write contention**, not the 16 MiB limit. Consider throttling update frequency, batching metrics, or sharding counters and aggregating, depending on accuracy and latency requirements.

### Exercise 8 — Review IDs Inside Product

`Product` stores a `reviewIds` array of **all** reviews, even though review content lives in a separate collection. Is this a safe referencing design?

**Hint:** **Not necessarily**. The ID array still grows without bound and can hit the document size limit. Instead of storing every ID on `product`, query `reviews` by `productId` with an index.

## 16. Official Documentation for Deeper Reading

The links below belong to the **MongoDB Database Manual**. Select your exact server version in the documentation version picker; `/docs/manual/` paths may change over time. If a URL moves, start from the **Data Modeling** section of your version's docs.

- [Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/) — overview of document design based on access patterns.
- [Embedding vs. References](https://www.mongodb.com/docs/manual/data-modeling/concepts/embedding-vs-references/) — criteria for choosing embedding vs. referencing.
- [Embedded Data](https://www.mongodb.com/docs/manual/data-modeling/concepts/embedded-documents/) — nested document modeling.
- [References](https://www.mongodb.com/docs/manual/data-modeling/concepts/references/) — manual references and DBRefs.
- [Document Structure](https://www.mongodb.com/docs/manual/core/document/) — BSON documents, nested fields, and size limits.
- [`$lookup` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/) — combining data from another collection.
- [Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/) — single-document atomicity boundaries and concurrent updates.
- [Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/) — indexes on array fields.
- [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — enforcing structure and types alongside flexible schemas.
- [Unbounded Arrays](https://www.mongodb.com/docs/manual/data-modeling/design-antipatterns/unbounded-arrays/) — avoiding embedding arrays that grow without limit.
- [Subset Pattern](https://www.mongodb.com/docs/manual/data-modeling/design-patterns/subset-pattern/) and [Extended Reference Pattern](https://www.mongodb.com/docs/manual/data-modeling/design-patterns/extended-reference-pattern/) — hybrid patterns optimizing access patterns.
- [Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/) — specialized option for time-series data.

A sound document design decision can be expressed as: **"This data is read together, has a compatible lifecycle, clear growth bounds, and required invariants fall cleanly inside the document boundary."** Whenever any of those conditions stops holding, referencing or a hybrid model is usually worth evaluating. Choose designs based on **real workloads and consistency requirements**, and verify with representative queries rather than generic NoSQL slogans.
