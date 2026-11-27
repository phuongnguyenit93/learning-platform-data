# Modeling One-to-One, One-to-Many, and Many-to-Many Relationships in MongoDB

## 1. Why Does MongoDB Still Need Relationship Modeling?

MongoDB stores data as **BSON documents** inside **collections**. A single document can hold scalar fields, nested objects, and arrays, allowing multiple parts of an entity to live in one record. However, business entities still relate to each other: a user has a profile, a customer has many orders, and a student can enroll in many courses.

**Cardinality** describes how many records on side B can be associated with each record on side A:

| Relationship | Explanation | Example |
| --- | --- | --- |
| **One-to-One (1:1)** | One A associates with at most one B, and one B associates with at most one A | User – optional profile |
| **One-to-Many (1:N)** | One A can associate with many B; each B belongs to one A in the model under consideration | Customer – orders |
| **Many-to-Many (N:N)** | One A has many B and one B also has many A | Student – courses |

The labels "1" and "N" describe **business rules**, not automatically how data should be stored. In MongoDB, you must choose whether to place data in **the same document** (*embedding*), store a **reference identifier** in another document (*referencing*), or combine both approaches.

Consider the same customer–order relationship:

```text
Embedded model:
customers
└── customer KH01
    └── orders: [DH01, DH02, ...]

Referenced model:
customers                   orders
└── KH01                    ├── DH01 (customerId = KH01)
                           └── DH02 (customerId = KH01)
```

Embedding all orders into the customer may make sense when the count is tiny and strictly bounded, but it is unsuitable when order history grows continuously. The goal of document design is to **serve real read/write operations, keep data sizes under control, and guarantee required consistency**.

After this lesson, learners will be able to:

1. Distinguish 1:1, 1:N, and N:N relationships at the business level.
2. Decide when to embed or reference, and determine which side holds the reference.
3. Use `mongosh` to create and query basic relationship patterns.
4. Apply `unique index`, `compound index`, and `$lookup` appropriately.
5. Understand the limits of embedded arrays, referential integrity, and multi-document updates.

## 2. Two Ways to Represent Relationships: Embedding and Referencing

### 2.1. Embedding Data

Embedding means storing related data directly inside the parent document:

```javascript
{
  _id: "USER-01",
  name: "Minh",
  profile: {
    displayName: "Minh Nguyen",
    locale: "vi-VN"
  },
  addresses: [
    { label: "Home", city: "Ho Chi Minh City" },
    { label: "Office", city: "Da Nang" }
  ]
}
```

Common advantages:

- Both the parent document and related data can be read in a single query.
- No need to join collections on every display.
- A write operation on **one document** is atomic, even when modifying multiple nested fields or elements within that document.
- The data structure directly mirrors the object the application typically uses.

Trade-offs:

- The document grows in size as nested arrays or subobjects expand.
- A BSON document has a size limit of **16 MiB**.
- Embedded information duplicated across many documents can be difficult to synchronize when it changes.
- Data that needs independent querying, permissions, or updates may fit better in its own collection.

### 2.2. Referencing Data

Referencing means keeping documents separate and storing an identifier to link them:

```javascript
// Collection users
{
  _id: "USER-01",
  name: "Minh"
}

// Collection orders
{
  _id: "ORDER-01",
  customerId: "USER-01",
  totalAmount: 750000
}
```

Advantages:

- Entities can evolve and be updated independently.
- Very large subsets can be queried using indexes and pagination.
- Avoids placing unbounded growing arrays inside parent documents.
- Documents with different lifecycles or access policies are managed separately.

Trade-offs:

- May require running multiple queries or using the `$lookup` aggregation stage.
- If business logic modifies multiple documents at once, an appropriate consistency mechanism is required.
- MongoDB does not automatically enforce SQL-style foreign key constraints between two collections merely because a field is named `customerId`.

**Preliminary rule of thumb:** embed data segments that are **bounded, frequently read together, and tightly coupled in lifecycle**; reference when **counts grow large, queries are independent, data is shared, or updates occur independently**. This is a starting guideline, not a rigid law.

### 2.3. What to Ask Before Deciding?

| Question | If the answer is "yes" |
| --- | --- |
| Are A and B typically fetched together in the same screen/API? | Lean toward embedding |
| Is the number of B per A small and stably bounded? | Embedding is easier to manage |
| Could the number of B grow to thousands/millions? | Lean toward referencing |
| Does B need to exist or be queried independently of A? | Lean toward referencing |
| Is one B shared by many A's? | Referencing avoids unnecessary duplication |
| Must A and B be modified together as one atomic unit? | Embedding can reduce the need for multi-document transactions |
| Does B contain data requiring different permissions, lifecycle, or update frequency than A? | A separate collection is usually more flexible |

In particular, pay attention to **access direction**: does the application more often ask for "all orders of customer X", or "customer details for order Y", or both? Access direction affects where the reference key lives and how indexes are chosen.

## 3. One-to-One Relationships (1:1)

### 3.1. When Is It 1:1?

For example, an account has at most one set of personal preferences:

```text
users                       userPreferences
_id = USER-01       1 : 0..1   userId = USER-01
```

The notation `0..1` indicates that preferences may not have been created yet, but there must never be two preference records for one user. If business rules mandate exactly one record on both sides, corresponding creation and maintenance workflows must be added.

### 3.2. Approach 1: Embed a Subobject

```javascript
{
  _id: "USER-01",
  email: "minh@example.test",
  preferences: {
    language: "vi",
    theme: "dark",
    emailNotifications: true
  }
}
```

Embedding works well when preferences are small, always accompany the account, and need no separate access control. When changing language, you can update a single nested field:

```javascript
db.users.updateOne(
  { _id: "USER-01" },
  { $set: { "preferences.language": "en" } }
);
```

This is a single-document operation; no cross-collection relationship is needed.

### 3.3. Approach 2: Separate Collection with a Unique Index

Splitting into a separate collection helps when the related part is very large, rarely read together, has a different update cycle, or needs separate permissions. For instance, an internal profile can be kept separate from login credentials.

Hands-on example in `mongosh`, using the lab database `mongo_relations_lab` and documents tagged with `runId`:

```javascript
const lab = db.getSiblingDB("mongo_relations_lab");
const runId = "row71-" + new ObjectId().toHexString();
const userId = new ObjectId();

lab.users.insertOne({
  _id: userId,
  runId: runId,
  username: "minh-row71",
  email: "minh@example.test"
});

// Each userId appears at most once in userPreferences.
lab.userPreferences.createIndex(
  { userId: 1 },
  { unique: true }
);

lab.userPreferences.insertOne({
  _id: new ObjectId(),
  runId: runId,
  userId: userId,
  language: "vi",
  theme: "dark"
});

printjson(lab.userPreferences.findOne({ userId: userId }));
```

Here, `userId` must have the **same data type** as `users._id`. In the example, both are `ObjectId`; if one side is a string and the other is an `ObjectId`, matching queries will not match even if the characters look identical.

The **unique index** on `userPreferences.userId` prevents two preference documents from sharing the same user ID. However, it **does not check whether that user actually exists in the `users` collection**, nor does it require every user to have preferences. If `userId` is an optional field, note that a single-field unique index treats `null` values and missing fields as a `null` index key; require the field to be valid or design a partial index suited to real data.

### 3.4. Querying Both Sides of a 1:1 Relationship

Two reads by ID:

```javascript
const account = lab.users.findOne({ _id: userId });
const preferences = lab.userPreferences.findOne({ userId: userId });
printjson({ account: account, preferences: preferences });
```

Or use `$lookup` to return combined data:

```javascript
lab.users.aggregate([
  { $match: { _id: userId } },
  {
    $lookup: {
      from: "userPreferences",
      localField: "_id",
      foreignField: "userId",
      as: "preferences"
    }
  },
  {
    $unwind: {
      path: "$preferences",
      preserveNullAndEmptyArrays: true
    }
  }
]);
```

`$lookup` produces an array field `preferences` because its general mechanism can match multiple elements. `$unwind` turns the array element into a single result; with a unique index, each user has at most one preferences document. The `preserveNullAndEmptyArrays` option keeps users who do not yet have preferences in the output.

## 4. One-to-Many Relationships (1:N)

A customer can create many orders; each order belongs to one customer in the basic model:

```text
customers                         orders
KH01 ---------------------------> DH01 (customerId = KH01)
     ---------------------------> DH02 (customerId = KH01)
     ---------------------------> DH03 (customerId = KH01)
```

A 1:N relationship has at least two notable representations: an **embedded array on the "one" side** and a **reference on the "many" side**.

### 4.1. Embed When the Subset Is Small and Co-Read

An order has a number of line items locked in at placement time:

```javascript
{
  _id: "ORDER-01",
  customerId: "USER-01",
  items: [
    { productId: "P01", name: "Notebook", quantity: 2, unitPrice: 50000 },
    { productId: "P02", name: "Pen", quantity: 3, unitPrice: 15000 }
  ],
  totalAmount: 145000
}
```

In this example, `items` is a subset of the order. Embedding is convenient because order detail APIs typically fetch the entire list of line items. The `name` and `unitPrice` fields are **snapshots at purchase time**, so they do not need synchronization when catalog names or prices change.

Embedding does not mean embedding everything: `customerId` still references the customer, while the line items are embedded.

Example updating the quantity of an existing line item:

```javascript
db.orders.updateOne(
  { _id: "ORDER-01", "items.productId": "P02" },
  { $set: { "items.$.quantity": 4 } }
);
```

The positional `$` operator in this example updates the first array element matching the filter; if business rules require updating multiple elements by specific criteria, you can use `arrayFilters` or give each element a unique identifier. For real orders, total fields must be recalculated consistently; this example only illustrates manipulating an embedded array.

### 4.2. Reference When the Subset Grows Continuously

If you embed the **entire order history** inside the customer document, the `orders` array can grow indefinitely. The more common approach is making each order a separate document and storing `customerId` on the "many" side.

Continuing the example with `lab`, `runId`, and `userId` from Section 3.3:

```javascript
const order1Id = new ObjectId();
const order2Id = new ObjectId();

lab.orders.insertMany([
  {
    _id: order1Id,
    runId: runId,
    customerId: userId,
    createdAt: ISODate("2026-11-10T02:00:00Z"),
    status: "PAID",
    items: [
      { productId: "P01", quantity: 2, unitPrice: 50000 }
    ],
    totalAmount: 100000
  },
  {
    _id: order2Id,
    runId: runId,
    customerId: userId,
    createdAt: ISODate("2026-11-12T03:00:00Z"),
    status: "NEW",
    items: [
      { productId: "P02", quantity: 3, unitPrice: 15000 }
    ],
    totalAmount: 45000
  }
]);

// Supports querying order history by customer, newest first.
lab.orders.createIndex({ customerId: 1, createdAt: -1 });
```

Reading a customer's order history:

```javascript
lab.orders.find(
  { customerId: userId },
  { _id: 1, createdAt: 1, status: 1, totalAmount: 1 }
).sort({ createdAt: -1 }).limit(20);
```

Querying by `customerId` and sorting by `createdAt` descending is a very common pattern; the compound index `{ customerId: 1, createdAt: -1 }` generally fits well. At large scale, use pagination based on a stable sort key (e.g., combining `createdAt` and `_id`) rather than defaulting to deep `skip`.

Reading customer details from an order:

```javascript
const order = lab.orders.findOne({ _id: order1Id });
const customer = lab.users.findOne({ _id: order.customerId });
printjson({ order: order, customer: customer });
```

Or combining with `$lookup`:

```javascript
lab.orders.aggregate([
  { $match: { _id: order1Id } },
  {
    $lookup: {
      from: "users",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  { $unwind: "$customer" },
  {
    $project: {
      _id: 1,
      totalAmount: 1,
      createdAt: 1,
      "customer.username": 1
    }
  }
]);
```

If the customer document is deleted or does not exist, `$lookup` returns an empty array; `$unwind` by default drops the record from the results. If you still want to see the order despite a missing reference, use `preserveNullAndEmptyArrays: true` and handle that business case.

### 4.3. Why Avoid Storing ID Lists on Both Sides?

You might encounter a model like this:

```javascript
// users
{ _id: "U1", orderIds: ["O1", "O2"] }

// orders
{ _id: "O1", customerId: "U1" }
{ _id: "O2", customerId: "U1" }
```

Storing both `orderIds` and `customerId` forces every order creation, ownership change, or deletion to update **both sides**. If one write fails, the two representations diverge. The `orderIds` array also grows with history. Usually you only need the primary reference on `orders.customerId`, paired with an index for reverse lookups.

Sometimes a small, bounded list (such as `recentOrderIds` or a few pinned items) is useful to optimize a screen; this is **bounded derived data**, which must have explicit sync rules and should not be treated as a complete mirror of the entire relationship.

### 4.4. The "Subset" Strategy for One-to-Many

An intermediate solution embeds **a frequently viewed slice of data** while keeping full records in a separate collection. For example, a customer document stores at most a few recent orders for quick display, while the `orders` collection stores the full history.

```javascript
{
  _id: "USER-01",
  recentOrders: [
    { orderId: "ORDER-200", totalAmount: 90000 },
    { orderId: "ORDER-199", totalAmount: 120000 }
  ]
}
```

This reduces queries for summary screens, but you must maintain update logic, bound the array size, and establish the `orders` collection as the source of truth. When using caching/denormalization, the application must accept or handle sync lag according to business requirements.

## 5. Many-to-Many Relationships (N:N)

For example, a student can join many courses and a course has many students:

```text
students                       courses
An      ────────────────────── MongoDB
  └────────────┐           ┌── Java
Binh ──────────┴───────────┘
```

This model differs from 1:N because you cannot simply say each course belongs to one student or each student belongs to one course. Two common approaches exist:

1. Store a small ID array on one side (when the relationship is bounded and only traversed in one direction).
2. Create an intermediate **join/association collection** where each document represents one link pair. This is usually the flexible choice when link counts are large or links carry their own attributes.

### 5.1. Embed an ID Array When the Relationship Is Small and Bounded

For example, an article has a small, stable set of tags:

```javascript
// posts
{
  _id: "POST-01",
  title: "MongoDB Basics",
  tagIds: ["mongo", "nosql", "database"]
}

// tags
{ _id: "mongo", name: "MongoDB" }
{ _id: "nosql", name: "NoSQL" }
{ _id: "database", name: "Database" }
```

A tag can belong to many posts; each post has many tags. Querying posts by tag:

```javascript
db.posts.find({ tagIds: "mongo" });
db.posts.createIndex({ tagIds: 1 });
```

MongoDB can match a scalar value against array elements and build a **multikey index** on the array field. This model works well if each post has only a bounded number of tags and no extra attributes need to be stored per link.

Avoid automatically adding `postIds` to every tag and updating it alongside `posts.tagIds` without a clear reason; bidirectional duplication creates synchronization overhead.

### 5.2. Intermediate Collection for Large or Attributed N:N

In an online learning platform, the enrollment relationship itself may carry:

- enrollment timestamp (`enrolledAt`);
- status (`ACTIVE`, `CANCELLED`);
- progress or grade;
- semester/cohort code if a student can re-enroll in different terms.

In that case, the `enrollments` collection is a business entity:

```text
students                  enrollments                     courses
_id = S01   <--- studentId = S01, courseId = C01 --->   _id = C01
_id = S02   <--- studentId = S02, courseId = C01 --->
            <--- studentId = S01, courseId = C02 --->   _id = C02
```

Each enrollment has its own document. Neither `students` nor `courses` needs to store an array of all links.

### 5.3. Hands-On Creation of Three Collections

Continuing the `mongosh` session with `lab` and `runId` from Section 3.3:

```javascript
const studentAnId = new ObjectId();
const studentBinhId = new ObjectId();
const courseMongoId = new ObjectId();
const courseJavaId = new ObjectId();

lab.students.insertMany([
  { _id: studentAnId, runId: runId, name: "An" },
  { _id: studentBinhId, runId: runId, name: "Binh" }
]);

lab.courses.insertMany([
  { _id: courseMongoId, runId: runId, title: "MongoDB Basics" },
  { _id: courseJavaId, runId: runId, title: "Java Fundamentals" }
]);

// Only one enrollment per studentId + courseId pair.
lab.enrollments.createIndex(
  { studentId: 1, courseId: 1 },
  { unique: true }
);

// Used when querying the student list for a course.
lab.enrollments.createIndex({ courseId: 1, studentId: 1 });

const enrollment1Id = new ObjectId();
const enrollment2Id = new ObjectId();
const enrollment3Id = new ObjectId();

lab.enrollments.insertMany([
  {
    _id: enrollment1Id,
    runId: runId,
    studentId: studentAnId,
    courseId: courseMongoId,
    status: "ACTIVE",
    enrolledAt: ISODate("2026-11-10T01:00:00Z")
  },
  {
    _id: enrollment2Id,
    runId: runId,
    studentId: studentAnId,
    courseId: courseJavaId,
    status: "ACTIVE",
    enrolledAt: ISODate("2026-11-11T02:00:00Z")
  },
  {
    _id: enrollment3Id,
    runId: runId,
    studentId: studentBinhId,
    courseId: courseMongoId,
    status: "ACTIVE",
    enrolledAt: ISODate("2026-11-12T03:00:00Z")
  }
]);
```

Here the relationships are:

- An is enrolled in MongoDB and Java.
- Binh is enrolled in MongoDB.
- The MongoDB course has both An and Binh.

The **compound unique index** `{ studentId: 1, courseId: 1 }` ensures there cannot be two enrollments for the same pair, enforcing the rule "each student has only one enrollment per course." If the application allows re-enrolling across different cohorts, include `offeringId`/`termId` in the unique key or model a cohort entity instead of using an overly restrictive unique key.

### 5.4. Querying N:N in Both Directions

Find courses An is enrolled in:

```javascript
lab.enrollments.find(
  { studentId: studentAnId },
  { _id: 0, courseId: 1, status: 1, enrolledAt: 1 }
);
```

Find students in the MongoDB course:

```javascript
lab.enrollments.find(
  { courseId: courseMongoId },
  { _id: 0, studentId: 1, status: 1 }
);
```

Fetch course titles instead of IDs only:

```javascript
lab.enrollments.aggregate([
  { $match: { studentId: studentAnId } },
  {
    $lookup: {
      from: "courses",
      localField: "courseId",
      foreignField: "_id",
      as: "course"
    }
  },
  { $unwind: "$course" },
  {
    $project: {
      _id: 0,
      status: 1,
      enrolledAt: 1,
      courseId: "$course._id",
      courseTitle: "$course.title"
    }
  },
  { $sort: { enrolledAt: -1 } }
]);
```

Conversely, to fetch student names for a course, run `$match` on `courseId` and `$lookup` into `students` via `studentId`. The intermediate collection enables bidirectional queries and lets you attach attributes to **the relationship itself**.

### 5.5. Should You Store Both `studentIds` in Course and `courseIds` in Student?

Only do this when there is a concrete need, such as caching a small bounded list. If each side maintains an array of all IDs from the other side, a single new enrollment may require updating two documents (or more alongside `enrollments`), increasing the risk of data drift.

For N:N links that can grow large, the `enrollments` collection is typically the **canonical source of truth**. Any counter fields or short lists on `students`/`courses`, if present, are derived data updated through a defined workflow.

## 6. Relationship Constraints: What Does MongoDB Enforce Automatically?

### 6.1. Every Document Has a Unique `_id`, but a Reference Is Not a Foreign Key

MongoDB automatically creates a unique index on `_id` within a collection. You can create unique indexes on other fields or combinations of fields. However:

```javascript
// MongoDB can accept a document like this without additional checks:
{
  _id: "ORDER-NOT-FOUND",
  customerId: "CUSTOMER-DOES-NOT-EXIST"
}
```

Naming a field `customerId` does not create an automatic constraint requiring the customer document to exist. To protect relationships, applications typically verify target entities upon creation, define policies for parent deletion, and use transactions when multiple operations must remain consistent together.

### 6.2. Which Rules Can Be Enforced with Indexes?

| Business Rule | MongoDB Mechanism | Limitation |
| --- | --- | --- |
| Each document has one identifier in the collection | Default unique index on `_id` | Scoped only to that collection |
| Each user has at most one preferences doc | `unique` on `userPreferences.userId` | Does not require an actual user to exist |
| No duplicate student–course enrollments | `unique` on `{studentId:1,courseId:1}` | Does not verify student/course still exists |
| Faster lookup of many orders by one customer | Index on `customerId`, optionally combined with `createdAt` | Index optimizes queries, does not enforce foreign key |
| Field and data type checks | Collection validation, e.g. `$jsonSchema` | Does not replace cross-collection relational rules |

A unique index guarantees **uniqueness** across indexed fields; it does not enforce a minimum count in a relationship or replace business-layer logic validation.

### 6.3. Validation for Reference Identifiers

At the schema level, you can require `studentId` and `courseId` to be `ObjectId` to prevent mismatched types:

```javascript
db.createCollection("validatedEnrollments", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["studentId", "courseId", "status"],
      properties: {
        studentId: { bsonType: "objectId" },
        courseId: { bsonType: "objectId" },
        status: {
          enum: ["ACTIVE", "CANCELLED"]
        }
      }
    }
  }
});
```

`validatedEnrollments` is just an illustrative standalone collection. Validation can enforce document shape and types, but cannot check whether `studentId` actually exists in the `students` collection.

### 6.4. Single-Document Atomicity and Multi-Document Transactions

With embedded documents, a command such as `updateOne` modifying multiple fields in the same document is atomic within that document. For operations that must write across multiple collections, consider a **multi-document transaction** when business rules require updates to succeed or fail together.

For example, course enrollment may involve inserting an enrollment and decrementing remaining seats. If only the enrollment succeeds while seat count does not decrement, data becomes inconsistent. Using transactions requires a compatible MongoDB topology and environment, along with handling retries, transient errors, and write conflicts according to business rules.

One way to express the flow:

```text
Begin transaction
    |
    +--> Check/update course capacity with an appropriate condition
    |
    +--> Create enrollment (unique index blocks duplicates)
    |
    +--> If all succeed: COMMIT
    |
    +--> If any step fails: ABORT
```

Not every cross-collection relationship needs a transaction: a read-only reference may accept eventual consistency strategies or application-level checks. Identify the **business invariant** before paying the synchronization cost.

### 6.5. Handling Deletions or Relationship Changes

In relational databases, foreign keys can be configured with `ON DELETE CASCADE`. In MongoDB, **there is no automatic cascade** merely because `customerId` references a customer.

The application must decide:

- **Restrict:** forbid deleting a customer while retained orders still exist.
- **Soft delete:** mark the customer inactive while preserving orders for history/auditing.
- **Application-driven cascade:** delete or deactivate related documents through a controlled workflow.
- **Detach:** clear the reference when business rules allow child records to live independently.

For instance, e-commerce systems typically must preserve orders even if a customer account is closed; deleting all orders with the customer would violate accounting and historical requirements.

## 7. Designing Queries and Indexes by Cardinality

### 7.1. Query Patterns Matter More Than Relationship Names

Two systems may both have a customer–order relationship yet have different needs:

- A profile page displays the 5 most recent orders.
- An admin page filters all orders by date and status.
- A monthly revenue report aggregates totals across many customers.
- An order detail API needs per-product price snapshots.

A typical fit is a separate `orders` collection with `customerId` and embedded `items`. However, indexes must match the highest-priority queries, for example:

```javascript
// Fetch a customer's order history, newest first.
lab.orders.createIndex({ customerId: 1, createdAt: -1 });

// When frequently filtering by status within a single customer:
lab.orders.createIndex({ customerId: 1, status: 1, createdAt: -1 });
```

Do not create both indexes just because you can: every index consumes storage and adds write overhead. Pick indexes based on queries and inspect execution plans with `explain()` on representative data.

### 7.2. Indexes for Many-to-Many

In `enrollments`:

```javascript
lab.enrollments.createIndex(
  { studentId: 1, courseId: 1 },
  { unique: true }
);
lab.enrollments.createIndex({ courseId: 1, studentId: 1 });
```

The first index supports queries by `studentId` and prevents duplicate pairs; the second supports queries by `courseId`. Field order in a compound index determines index prefix usability. For example, an index starting with `studentId` is not naturally optimal for queries filtering only by `courseId`.

With `$lookup`, the joined field in the target collection should have an appropriate index. Joining on `_id` leverages the default index; joining on `userPreferences.userId` can use the unique index created earlier.

### 7.3. When to Use `$lookup`?

`$lookup` combines data across collections inside an aggregation pipeline. It is useful when an API must return a combined payload or a report needs to correlate data. However:

- You still must account for input document volume, `$match` selectivity, and indexes on the foreign side.
- A large N:N relationship can cause results to explode if `$lookup`/`$unwind` is used without limits.
- In list APIs, filter and paginate appropriately before expanding data whenever query semantics allow.
- When only a few fields are needed, use `$project` to trim returned data.

Good document design does not demand a strict "never use `$lookup`." What matters is choosing structures and queries suited to data scale and access frequency.

## 8. Patterns That Quickly Become Problems

| Data Organization | Scaling Problem | Improvement Direction |
| --- | --- | --- |
| A customer embeds an array of all orders | Array grows without bound, document bloats; hard to paginate | Separate `orders`, put `customerId` on order, create index |
| Each course stores all student IDs and each student stores all course IDs | Must update two sides; easy to miss or duplicate links | Use `enrollments` collection as canonical source |
| Copy the full customer profile into every order | Large data and prone to drift if profile must stay current | Snapshot only purchase-time fields; reference live attributes |
| No unique index for at-most-one relationships | Concurrent requests can create duplicate records | Add unique index matching the business key |
| Assuming references check existence automatically | Easy to create orphan documents | Validate in application and handle updates/deletes deliberately |
| Storing IDs with mixed data types | `ObjectId` and string fail to match on joins | Standardize key types across both sides |
| Embedding frequently updated data in many places | Increases sync cost and produces stale reads | Reference canonical source or define sync mechanism |
| Creating arbitrary indexes on every key | Write cost and index storage grow | Base indexes on query patterns and real measurements |
| Modeling every N:N as two ID arrays | Hard to attach link attributes, prone to inconsistency | Association collection storing link records |

### 8.1. When Cardinality Changes Over Time

A feature starting as "a user has at most five addresses" might later become "an organization has tens of thousands of locations." The logical 1:N relationship stays the same, but **the distribution of N** has shifted, and the initial embedding choice may no longer fit. When designing, document assumptions about current counts and expected bounds.

### 8.2. Embedded Documents Still Have a Business Lifecycle

When embedding data, decide whether child elements need their own identifiers. For example, a cart can embed `items`, yet individual items sometimes need an `itemId` for precise in-array updates. If elements are edited independently, searched across many parents, or have long lifecycles, a separate collection may be simpler.

### 8.3. Distinguish Snapshots from "Always Current" Data

Orders typically store `shippingAddress`, `unitPrice`, or `productName` at purchase time. Even though this appears duplicated from customer/product, it is kept as a **historical snapshot** and should not change automatically. Conversely, copying a customer's current avatar into every order would force unnecessary synchronization. Document clearly which fields are snapshots and which reference a canonical source.

## 9. Modeling Workflow for a New Requirement

Suppose you need to design a feature where "users follow authors and authors have many followers." You can start with these steps:

1. **Identify the relationship:** a user follows many authors, and an author has many followers → N:N.
2. **Estimate relationship size:** popular authors can have millions of followers → do not embed all IDs into a single author document.
3. **Identify primary queries:** list of followed authors, follower count, check whether currently following.
4. **Establish the source of truth:** a `follows` collection containing `followerId`, `authorId`, `followedAt`.
5. **Prevent duplicates:** unique index on `{ followerId: 1, authorId: 1 }`.
6. **Optimize both directions:** reverse index `{ authorId: 1, followerId: 1 }` when querying followers of an author.
7. **Define deletion rules:** unfollowing deletes one link; closing an account requires a policy for related links.

A document might look like:

```javascript
{
  followerId: ObjectId("64b64a000000000000000001"),
  authorId: ObjectId("64b64a000000000000000002"),
  followedAt: ISODate("2026-11-14T08:00:00Z")
}
```

If the application displays follower counts directly on author lists, consider a carefully maintained counter field. In that case, `follows` remains the canonical link source while the count is derived data requiring an appropriate update strategy or lag tolerance.

## 10. Comprehensive Practice: Which Relationship Pattern Should You Use?

For each scenario, analyze three factors: **cardinality**, **expected count**, and **query pattern**.

| Scenario | Starting Option to Consider | Why |
| --- | --- | --- |
| Account has a small UI settings object | Embed `preferences` object | Small, usually read together with account |
| Account has a medical record or separately permissioned data | Separate collection, 1:1 reference and unique index | Different lifecycle and access policies |
| An order has a few line items | Embed `items` inside order | Read together, historical snapshot, bounded count |
| A user has thousands of orders | Collection `orders` with `customerId` | Long-term growth, requires pagination and filtering |
| An article has a few tags | Bounded `tagIds` array | Simple N:N model; queryable by tag |
| Students take many courses with grades and statuses | Collection `enrollments` | N:N with own attributes and lifecycle |
| Users follow accounts at large scale | Collection `follows` | Large N:N relationship needing bidirectional queries |

### 10.1. Verify Data Created in the Practice Session

If you ran the examples in the **same `mongosh` session**, you can verify:

```javascript
print("userPreferences=" +
  lab.userPreferences.countDocuments({ userId: userId }));

print("ordersOfUser=" +
  lab.orders.countDocuments({ customerId: userId }));

print("enrollmentsOfAn=" +
  lab.enrollments.countDocuments({ studentId: studentAnId }));

print("studentsOfMongoCourse=" +
  lab.enrollments.countDocuments({ courseId: courseMongoId }));
```

With the sample data unmodified, the respective counts are `1`, `2`, `2`, `2`.

### 10.2. Clean Up Lab Data Using Your Own Identifier Tag

The examples create data in the `mongo_relations_lab` database with a unique `runId`. Before cleaning up, verify the right connection and preview the documents created by this run:

```javascript
const ownedCollections = [
  "enrollments",
  "courses",
  "students",
  "orders",
  "userPreferences",
  "users"
];

print("database=" + lab.getName());
print("runId=" + runId);
for (const name of ownedCollections) {
  const collection = lab.getCollection(name);
  print(name + "=" + collection.countDocuments({ runId: runId }));
  printjson(
    collection.find(
      { runId: runId },
      { _id: 1, runId: 1 }
    ).limit(10).toArray()
  );
}
```

If the list matches **only the data you just created** and this is your test environment, you can delete strictly by the verified `runId`:

```javascript
// Only run after verifying the database, runId, and counts above.
for (const name of ownedCollections) {
  const collection = lab.getCollection(name);
  const result = collection.deleteMany({ runId: runId });
  print(name + ": deleted=" + result.deletedCount);
}

// Confirm no documents remain from this practice run.
for (const name of ownedCollections) {
  print(name + ": remaining=" +
    lab.getCollection(name).countDocuments({ runId: runId }));
}
```

Never use `deleteMany({})`, `drop()`, or `dropDatabase()` to clean up exercises when the environment may be shared. If you do not remember `runId` or the preview output looks unexpected, stop and identify the data you own before deleting.

## 11. Self-Check Questions

1. Why can a 1:1 relationship be stored either as an embedded object or in a separate collection? What decides the choice?
2. Does a unique index on `userPreferences.userId` automatically prevent a document from pointing to a non-existent user?
3. Why is `orders.customerId` usually more flexible than an array of all `customers.orderIds` when order history grows indefinitely?
4. In a student–course relationship, when is a `courseIds` array enough? When is an `enrollments` collection needed?
5. If each enrollment has `status`, `enrolledAt`, and `score`, do those fields belong to the student entity, the course entity, or the link itself?
6. Why are different indexes needed when querying enrollments by student versus by course?
7. If you delete a customer, does MongoDB automatically delete all orders referencing that customer? What policies should the application choose from?
8. When is a copied field in an order a valid business snapshot, and when does it simply create data drift risk?

**Key takeaway:** cardinality answers **"how entities relate to each other"**; embedding, referencing, indexes, and write workflows answer **"how to store and access that relationship in MongoDB."** A sound design emerges from realistic counts, query patterns, data lifecycles, and the consistency level required by the business.
