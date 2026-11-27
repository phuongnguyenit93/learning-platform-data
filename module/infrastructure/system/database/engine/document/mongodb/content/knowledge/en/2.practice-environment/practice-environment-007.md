# Creating a Sample Dataset and Reproducible MongoDB Practice Conventions

## 1. Objectives and Context

When learning MongoDB, a query is only meaningful if the learner knows the exact initial state of the data. If you manually insert a few ad-hoc documents each time you practice, results of find, update, aggregation, or index commands will differ from session to session. Therefore, before diving into CRUD and aggregation, we need a **sample dataset with an explicit contract** and a **repeatable initialization procedure** (reproducible seed).

After this lesson, you will be able to:

- Design a set of documents that demonstrates document database characteristics while maintaining a consistent structure for easy querying.
- Distinguish key BSON types such as String, Boolean, Date, Int32, Decimal128, Array, and Embedded Document.
- Create three collections linked by stable identifiers, along with indexes for practice exercises.
- Re-run the seed script multiple times without inflating document counts or distorting the sample dataset.
- Quickly inspect data state, run sample queries, and clean up only the data owned by this practice lab.

We use a **stationery and accessories store** scenario. Orders reference customers, while individual line items are embedded in each order to record quantity and **unit price at the time of ordering**. This models both reference relationships and MongoDB embedded structures.

> **Safety Scope:** The commands below are intended for a dedicated practice machine or database. The script uses the **mongo_replay_lab_v1** database, collections prefixed with **lab_**, and only deletes documents tagged with **dataset: "practice-v1"**. Do not run this on production databases or uncontrolled shared databases.

## 2. Locking In Data Conventions Before Writing the Script

### 2.1. Contract for Three Collections

| Collection | Document Count | Fixed Identifiers | Purpose |
| --- | ---: | --- | --- |
| **lab_customers** | 3 | `c001`, `c002`, `c003` | Customer details and join date |
| **lab_products** | 4 | `p001`, `p002`, `p003`, `p004` | Product catalog, price, and sample stock |
| **lab_orders** | 5 | `o001` through `o005` | Orders with customer reference and embedded line items |

Fields used consistently across collections:

| Field | Convention | Rationale |
| --- | --- | --- |
| **_id** | Fixed string, e.g., `c001` or `o003` | Readable seed results, stable across repeated runs |
| **dataset** | Always the string `practice-v1` | Isolates lab-owned data and scopes cleanup |
| **customerId / productId** | Reference string matching the target `_id` type | Avoids type-mismatch comparisons in filters or `$lookup` |
| **email / sku** | Unique string within the same dataset | Suitable for creating unique compound indexes |
| **createdAt / joinedAt** | BSON Date with fixed UTC timestamps | Time-based comparisons independent of when the script runs |
| **price / unitPrice / total** | BSON Decimal128, e.g., `NumberDecimal("75000.00")` | Intentional base-10 representation for monetary values |
| **stock / quantity** | BSON Int32 via `NumberInt` | Represents integer counts |
| **status** | One of `pending`, `paid`, `shipped`, `cancelled` | Enables status-based filtering and grouping practice |
| **lineItems** | Array of documents containing `productId`, `quantity`, `unitPrice` | Preserves order structure and price snapshot |

In real-world systems, MongoDB normally auto-generates an `ObjectId` for **_id**. Here, fixed strings are a deliberate choice to make re-runs and result verification straightforward. Do not infer that all MongoDB systems should use strings instead of `ObjectId`.

**Field naming consistency:** use camelCase for fields (`customerId`, `lineItems`, `createdAt`), plural collection names, lowercase English status labels, and a single consistent data type for every field sharing the same meaning. All prices throughout this lesson are in **VND**, never converted implicitly to JavaScript floating-point numbers.

### 2.2. Why Both Referencing and Embedding?

A single customer can place many orders, so **lab_orders.customerId** stores the customer ID instead of duplicating the full customer profile into every order. Conversely, **lab_orders.lineItems** belongs to the order itself: quantity, product, and selling price at purchase time must remain unchanged even if catalog prices later change.

~~~text
lab_customers                    lab_orders
_id: "c001"  <--- customerId ---  _id: "o001"
name: "Lan"                      customerId: "c001"
                                  lineItems: [
                                    { productId: "p001", quantity: 2,
                                      unitPrice: Decimal128("75000.00") },
                                    { productId: "p002", quantity: 3,
                                      unitPrice: Decimal128("12000.00") }
                                  ]
                                  total: Decimal128("186000.00")

lab_products
_id: "p001"  <--- lineItems[].productId
price: Decimal128("75000.00")
~~~

MongoDB does not automatically enforce foreign key constraints like relational database management systems. Seed data must actively ensure `customerId` and `productId` point to existing IDs. In production applications, that integrity is typically enforced at the application layer or through data validation workflows.

## 3. Preparing the Practice Environment

You need a reachable MongoDB server and **mongosh**. You can use MongoDB running locally, in a container, or in a dedicated learning environment with permissions to create collections and indexes.

Verify connectivity with `mongosh`:

~~~bash
mongosh "mongodb://127.0.0.1:27017" --eval "db.runCommand({ ping: 1 })"
~~~

On success, the output includes **ok: 1**. If using another environment, substitute the appropriate URI. Never put passwords or connection strings containing secrets into documentation, source code, or commit history.

Create any working directory, then copy the entire JavaScript block in the next section into a file named **seed_mongo_lab.js**. Execute the file from that directory:

~~~bash
mongosh "mongodb://127.0.0.1:27017" --file seed_mongo_lab.js
~~~

You do not need a **use** statement inside the script. Calling **db.getSiblingDB("mongo_replay_lab_v1")** targets the destination explicitly, even if the URI points to another default database.

## 4. Script to Create the Sample Dataset

The script below fixes all IDs, timestamps, prices, quantities, and statuses. Before re-inserting, it deletes **only documents with `dataset = practice-v1`** across the three lab collections. Consecutive runs therefore produce identical data. The IIFE wrapper allows re-running via **load("seed_mongo_lab.js")** inside an interactive `mongosh` session without triggering `const` redeclaration errors.

~~~javascript
// seed_mongo_lab.js
(() => {
  const lab = db.getSiblingDB("mongo_replay_lab_v1");
  const DATASET = "practice-v1";

  const customers = [
    {
      _id: "c001",
      dataset: DATASET,
      name: "Nguyen Lan",
      email: "lan@example.test",
      city: "Hanoi",
      joinedAt: ISODate("2025-12-15T09:00:00.000Z"),
      active: true
    },
    {
      _id: "c002",
      dataset: DATASET,
      name: "Tran Minh",
      email: "minh@example.test",
      city: "Ho Chi Minh City",
      joinedAt: ISODate("2025-12-20T10:30:00.000Z"),
      active: true
    },
    {
      _id: "c003",
      dataset: DATASET,
      name: "Le Hoa",
      email: "hoa@example.test",
      city: "Da Nang",
      joinedAt: ISODate("2026-01-02T08:15:00.000Z"),
      active: false
    }
  ];

  const products = [
    {
      _id: "p001",
      dataset: DATASET,
      sku: "ST-001",
      name: "Notebook",
      category: "stationery",
      price: NumberDecimal("75000.00"),
      stock: NumberInt(80),
      active: true
    },
    {
      _id: "p002",
      dataset: DATASET,
      sku: "ST-002",
      name: "Ballpoint Pen",
      category: "stationery",
      price: NumberDecimal("12000.00"),
      stock: NumberInt(200),
      active: true
    },
    {
      _id: "p003",
      dataset: DATASET,
      sku: "AC-001",
      name: "Ceramic Mug",
      category: "accessory",
      price: NumberDecimal("95000.00"),
      stock: NumberInt(40),
      active: true
    },
    {
      _id: "p004",
      dataset: DATASET,
      sku: "EL-001",
      name: "Keyboard",
      category: "electronics",
      price: NumberDecimal("450000.00"),
      stock: NumberInt(25),
      active: true
    }
  ];

  const orders = [
    {
      _id: "o001",
      dataset: DATASET,
      customerId: "c001",
      createdAt: ISODate("2026-01-05T08:00:00.000Z"),
      status: "paid",
      lineItems: [
        {
          productId: "p001",
          quantity: NumberInt(2),
          unitPrice: NumberDecimal("75000.00")
        },
        {
          productId: "p002",
          quantity: NumberInt(3),
          unitPrice: NumberDecimal("12000.00")
        }
      ],
      total: NumberDecimal("186000.00")
    },
    {
      _id: "o002",
      dataset: DATASET,
      customerId: "c002",
      createdAt: ISODate("2026-01-10T09:30:00.000Z"),
      status: "shipped",
      lineItems: [
        {
          productId: "p003",
          quantity: NumberInt(1),
          unitPrice: NumberDecimal("95000.00")
        },
        {
          productId: "p002",
          quantity: NumberInt(5),
          unitPrice: NumberDecimal("12000.00")
        }
      ],
      total: NumberDecimal("155000.00")
    },
    {
      _id: "o003",
      dataset: DATASET,
      customerId: "c001",
      createdAt: ISODate("2026-02-03T14:00:00.000Z"),
      status: "pending",
      lineItems: [
        {
          productId: "p004",
          quantity: NumberInt(1),
          unitPrice: NumberDecimal("450000.00")
        }
      ],
      total: NumberDecimal("450000.00")
    },
    {
      _id: "o004",
      dataset: DATASET,
      customerId: "c003",
      createdAt: ISODate("2026-02-10T16:00:00.000Z"),
      status: "cancelled",
      lineItems: [
        {
          productId: "p001",
          quantity: NumberInt(1),
          unitPrice: NumberDecimal("75000.00")
        }
      ],
      total: NumberDecimal("75000.00")
    },
    {
      _id: "o005",
      dataset: DATASET,
      customerId: "c002",
      createdAt: ISODate("2026-02-14T11:45:00.000Z"),
      status: "paid",
      lineItems: [
        {
          productId: "p004",
          quantity: NumberInt(1),
          unitPrice: NumberDecimal("450000.00")
        },
        {
          productId: "p003",
          quantity: NumberInt(2),
          unitPrice: NumberDecimal("95000.00")
        }
      ],
      total: NumberDecimal("640000.00")
    }
  ];

  // Clean up only data owned by this practice lab.
  // Do not drop databases or collections.
  const names = ["lab_orders", "lab_products", "lab_customers"];
  for (const name of names) {
    lab.getCollection(name).deleteMany({ dataset: DATASET });
  }

  // Insert in order: customers, products, orders.
  lab.getCollection("lab_customers").insertMany(customers);
  lab.getCollection("lab_products").insertMany(products);
  lab.getCollection("lab_orders").insertMany(orders);

  // Unique indexes scoped to the dataset.
  lab.getCollection("lab_customers").createIndex(
    { dataset: 1, email: 1 },
    { name: "ux_lab_customers_dataset_email", unique: true }
  );
  lab.getCollection("lab_products").createIndex(
    { dataset: 1, sku: 1 },
    { name: "ux_lab_products_dataset_sku", unique: true }
  );

  // Indexes supporting common order queries.
  lab.getCollection("lab_orders").createIndex(
    { dataset: 1, customerId: 1, createdAt: -1 },
    { name: "ix_lab_orders_customer_date" }
  );
  lab.getCollection("lab_orders").createIndex(
    { dataset: 1, status: 1, createdAt: -1 },
    { name: "ix_lab_orders_status_date" }
  );

  const counts = {
    customers: lab.getCollection("lab_customers").countDocuments({
      dataset: DATASET
    }),
    products: lab.getCollection("lab_products").countDocuments({
      dataset: DATASET
    }),
    orders: lab.getCollection("lab_orders").countDocuments({
      dataset: DATASET
    })
  };

  if (
    counts.customers !== 3 ||
    counts.products !== 4 ||
    counts.orders !== 5
  ) {
    throw new Error("Unexpected document counts after seed: " +
      JSON.stringify(counts));
  }

  print("Seed completed: " + JSON.stringify(counts));
})();
~~~

When run successfully, you will see counts matching:

~~~text
Seed completed: {"customers":3,"products":4,"orders":5}
~~~

**Explanation of execution order:**

1. Select the database explicitly by name and declare the `dataset` tag. Every sample document carries this tag.
2. Construct data inline in source code without random values or current system timestamps. All dates carry the **Z** suffix indicating UTC.
3. Clean up sample data from the previous run using a filtered delete. Other collections and documents without this dataset tag are untouched.
4. Insert documents and create named indexes. When an index with the exact same definition already exists, MongoDB reuses it.
5. Re-count documents to detect obvious storage errors immediately during seeding.

The delete-then-insert sequence **is not an atomic transaction**: if the script is interrupted mid-run, part of the data may temporarily be empty. In an isolated practice environment, simply re-run the entire file to restore it. In production applications, evaluate transactions, migrations, upserts, and proper orchestration mechanisms. Never use bulk delete-and-reinsert as a production data deployment pattern.

## 5. Practicing Queries Against a Known Data State

After seeding, open `mongosh` or create a separate JavaScript file to run the snippets below. Every query targets the exact database and filters on **dataset** to guarantee results belong strictly to this lab.

### 5.1. Find Orders with Total >= 200,000 VND

~~~javascript
const lab = db.getSiblingDB("mongo_replay_lab_v1");

lab.getCollection("lab_orders")
  .find(
    {
      dataset: "practice-v1",
      total: { $gte: NumberDecimal("200000.00") }
    },
    { _id: 1, customerId: 1, status: 1, total: 1 }
  )
  .sort({ _id: 1 })
  .toArray();
~~~

**Expected result:** `o003` (450,000 VND, `pending`) and `o005` (640,000 VND, `paid`). This query filters by amount **without filtering for completed status**, so the pending order also appears.

### 5.2. Join Orders with Customer Names Using `$lookup`

~~~javascript
lab.getCollection("lab_orders").aggregate([
  { $match: { dataset: "practice-v1" } },
  {
    $lookup: {
      from: "lab_customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  { $unwind: "$customer" },
  {
    $project: {
      _id: 1,
      customerId: 1,
      customerName: "$customer.name",
      status: 1,
      total: 1
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
~~~

The result has **5 orders**: `o001` and `o003` carry `Nguyen Lan`, `o002` and `o005` carry `Tran Minh`, and `o004` carries `Le Hoa`. **$lookup** joins documents by matching keys; **$unwind** turns the single element in the `customer` array into a flat subdocument for convenient field projection.

### 5.3. Calculate Valid Revenue per Customer

Suppose the lesson's reporting rule counts only **paid** or **shipped** orders. **pending** and **cancelled** orders are excluded from revenue.

~~~javascript
lab.getCollection("lab_orders").aggregate([
  {
    $match: {
      dataset: "practice-v1",
      status: { $in: ["paid", "shipped"] }
    }
  },
  {
    $group: {
      _id: "$customerId",
      orderCount: { $sum: 1 },
      revenue: { $sum: "$total" }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
~~~

| Customer | Counted Orders | Expected Revenue |
| --- | --- | ---: |
| `c001` | `o001` | 186,000.00 VND |
| `c002` | `o002` and `o005` | 795,000.00 VND |
| `c003` | No qualifying orders | 0 VND, absent from `$group` output |
| **Total** | **3 orders** | **981,000.00 VND** |

The **revenue** field has type Decimal128 because the source **total** field is Decimal128. Summation in aggregation does not implicitly coerce values to floating-point numbers.

### 5.4. Reconcile Order Totals Against Line Items

Each order's total can be recomputed as **sum of (quantity × unitPrice)**. Below is a query to detect **orders with mismatched totals**:

~~~javascript
lab.getCollection("lab_orders").aggregate([
  { $match: { dataset: "practice-v1" } },
  {
    $project: {
      total: 1,
      calculatedTotal: {
        $sum: {
          $map: {
            input: "$lineItems",
            as: "item",
            in: {
              $multiply: ["$$item.quantity", "$$item.unitPrice"]
            }
          }
        }
      }
    }
  },
  { $match: { $expr: { $ne: ["$total", "$calculatedTotal"] } } }
]).toArray();
~~~

**Expected result:** an empty array **[]**. For instance, `o001` computes to 2 × 75,000 + 3 × 12,000 = 186,000 VND. This is a practice query for inspecting data, not a comprehensive auditing workflow for a retail application.

### 5.5. Inspecting Indexes and Explaining Query Plans

~~~javascript
lab.getCollection("lab_orders").getIndexes();

lab.getCollection("lab_orders")
  .find({
    dataset: "practice-v1",
    customerId: "c002"
  })
  .sort({ createdAt: -1 })
  .explain("executionStats");
~~~

The index **{ dataset: 1, customerId: 1, createdAt: -1 }** aligns with filtering on `dataset`, `customerId`, and descending order on `createdAt`. However, with only 5 orders, MongoDB may choose a collection scan over an index scan; **do not assume every `explain` output will show `IXSCAN`**. Inspect the `executionStats` fields and compare them when scaling up dataset size in a later lesson.

## 6. Verifying Reproducibility

A genuinely repeatable seed must leave the exact same logical state after every run. Perform these steps in order:

1. Run **seed_mongo_lab.js** a first time.
2. Run the queries in Section 5 and record document counts, IDs, statuses, and revenue.
3. Re-run **that exact seed file** a second time without altering input values.
4. Re-run the queries. Document counts and outputs must remain unchanged.

Example running the file twice from the terminal:

~~~bash
mongosh "mongodb://127.0.0.1:27017" --file seed_mongo_lab.js
mongosh "mongodb://127.0.0.1:27017" --file seed_mongo_lab.js
~~~

Or inside an active `mongosh` session:

~~~javascript
load("seed_mongo_lab.js");
load("seed_mongo_lab.js");
~~~

Verify quickly with a read-only verification snippet:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_replay_lab_v1");
  const filter = { dataset: "practice-v1" };

  print("customers = " +
    lab.getCollection("lab_customers").countDocuments(filter));
  print("products = " +
    lab.getCollection("lab_products").countDocuments(filter));
  print("orders = " +
    lab.getCollection("lab_orders").countDocuments(filter));

  print("orderIds = " + JSON.stringify(
    lab.getCollection("lab_orders")
      .find(filter, { _id: 1 })
      .sort({ _id: 1 })
      .toArray()
      .map(order => order._id)
  ));
})();
~~~

The output must show **3 customers**, **4 products**, and **5 orders**, with IDs **o001, o002, o003, o004, o005**. If after two runs there are 10 orders, the seeding logic is flawed: typically due to generating random `_id` values or appending inserts without cleaning prior data. If outputs vary by run date, the script likely depends on current `Date` values or unpinned random data.

**Differences across approaches:**

| Approach | On Re-Run | Best Suited When |
| --- | --- | --- |
| `insertMany` with random `_id` | Easily duplicates documents | One-time controlled ingestion of new data |
| `insertMany` with fixed `_id` without cleanup | Fails on second run with duplicate key | Intentionally preventing overwrites, not repeatable seeding |
| `deleteMany` filtered by dataset then fixed `insertMany` | Resets sample dataset to baseline | Dedicated lab, needing deterministic results each session |
| `replaceOne` with `upsert` on fixed `_id` | Overwrites matching documents without wiping all | Per-record sync; still requires handling stale records removed from seed |

Example single-record upsert if you want to explore key-based synchronization:

~~~javascript
lab.getCollection("lab_products").replaceOne(
  { _id: "p001", dataset: "practice-v1" },
  {
    _id: "p001",
    dataset: "practice-v1",
    sku: "ST-001",
    name: "Notebook",
    category: "stationery",
    price: NumberDecimal("75000.00"),
    stock: NumberInt(80),
    active: true
  },
  { upsert: true }
);
~~~

**replaceOne** replaces the entire matching document (except the immutable `_id`). If you change the schema or remove a product from the seed list, upserting current records alone will **not automatically delete old records**. Since this lesson's goal is always returning to an exact small baseline dataset, scoped cleanup followed by re-insertion is easier to reason about.

## 7. Cleaning Up Lab-Owned Data

Once finished practicing, you can delete strictly the documents tagged with the lab's dataset while preserving the database, collections, and indexes:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_replay_lab_v1");
  const filter = { dataset: "practice-v1" };

  for (const name of ["lab_orders", "lab_products", "lab_customers"]) {
    const result = lab.getCollection(name).deleteMany(filter);
    print(name + ": deleted " + result.deletedCount);
  }
})();
~~~

If the dataset is intact, the deleted counts will be **5, 4, 3** respectively. Re-running the seed script recreates all data. Do not use **db.dropDatabase()** or **collection.drop()** in this lab because their scope exceeds dataset cleanup and they also drop the corresponding indexes.

## 8. Common Issues and Self-Troubleshooting

| Symptom | Common Cause | How to Check or Fix |
| --- | --- | --- |
| Cannot connect to MongoDB | Server not running, wrong URI, or unauthenticated | Re-check URI, server status, and practice account permissions |
| `E11000 duplicate key` | Colliding `_id`/`email`/`sku` with an existing document | Confirm the dedicated database, inspect the conflicting document, and clean up only data you own |
| `countDocuments` returns 0 | Inspecting the wrong database or forgot dataset filter | Print `lab.getName()`, verify collection names and the `practice-v1` filter |
| Price or total calculation discrepancies | Entered prices as JS Numbers, mixed types, or miscomputed totals | Use `NumberDecimal`, inspect `$type`, and run the line-item check in Section 5.4 |
| Date comparisons behave wrongly | Stored dates as strings or inconsistent timezones | Use `ISODate` in UTC and inspect actual BSON types |
| Subsequent runs add duplicate records | Generated new `ObjectId`s, appended inserts, or skipped reset | Use fixed `_id` values and run the full seed script |
| Index creation fails on name conflict | Existing index shares the name with altered keys or options | Inspect `getIndexes()`; only modify indexes intentionally inside your own lab database |

To inspect stored BSON types, run:

~~~javascript
lab.getCollection("lab_products").aggregate([
  { $match: { _id: "p001", dataset: "practice-v1" } },
  {
    $project: {
      _id: 1,
      priceType: { $type: "$price" },
      stockType: { $type: "$stock" }
    }
  }
]).toArray();
~~~

On the sample data above, **priceType** is **decimal**, and **stockType** is **int**. When operating through a programming language driver, use the driver's corresponding types; **NumberDecimal**, **NumberInt**, and **ISODate** in this lesson are `mongosh` helpers.

## 9. Self-Practice Exercises

1. **Filter by date and status:** Find orders with `status = paid` and `createdAt` from `2026-02-01` UTC onward. Expected result is strictly **o005**.
2. **Query nested arrays:** Find orders containing product `p003` by filtering on **lineItems.productId**. Expected results are **o002** and **o005**.
3. **Aggregate by category:** Count products belonging to `category = stationery`; expected result is **2**.
4. **Observe reversible mutations:** Update `p001`'s `stock` to `1`, verify the change, re-run the seed script, and confirm `stock` returns to **80**.
5. **Explain the modeling decision:** Explain why `lineItems` must store its own `unitPrice` even though `lab_products` already has `price`. Then try updating `p001`'s `price` and observe that `o001`'s `total` stays **186,000 VND**.

Hint snippets for Exercises 2 and 4:

~~~javascript
// Exercise 2
lab.getCollection("lab_orders")
  .find(
    { dataset: "practice-v1", "lineItems.productId": "p003" },
    { _id: 1 }
  )
  .sort({ _id: 1 })
  .toArray();

// Exercise 4
lab.getCollection("lab_products").updateOne(
  { _id: "p001", dataset: "practice-v1" },
  { $set: { stock: NumberInt(1) } }
);
// Then re-run seed_mongo_lab.js to restore stock = 80.
~~~

After completing any exercise that mutates data, re-run **seed_mongo_lab.js** to restore the baseline state. When everyone uses the exact same seed and field conventions, subsequent lessons on CRUD, aggregation, indexing, `$lookup` joins, and update handling all share a deterministic starting point and easily comparable outcomes.
