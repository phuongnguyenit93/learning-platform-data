# Documents, Collections, and Firestore Data Modeling

> **Chapter:** Firestore and Firebase  
> **Module:** CLOUD_PROVIDERS_GCP

An online store needs to manage customers, products, and orders. With a relational database, we usually start with tables, foreign keys, and `JOIN` operations. With **Cloud Firestore**, the first questions are: **which groups of data will the application read together, which fields will it filter on, who is allowed to access them, and how will the data grow?**

Firestore is a **document**-oriented NoSQL database that supports document reads/writes, indexed queries, and application data synchronization. Firebase provides SDKs, Authentication, Security Rules, and developer tools for mobile/web; backend applications running on **Cloud Run/GKE/Compute Engine** can use Google Cloud Firestore server client libraries. This lesson uses **Firestore Standard edition, Native mode** as the baseline to explain common operations. When using Firestore Enterprise edition or another mode, you must cross-check the corresponding query capabilities, indexes, and pricing models.

In the **CLOUD_PROVIDERS_GCP** track, this knowledge helps you select the right database, protect data with IAM/Rules, release applications, and monitor cost/reliability.

**After this lesson, you will be able to:**

1. Distinguish **collection, document, document ID, field, map, array**, and **subcollection**.
2. Read Firestore paths in the alternating collection/document order; understand that a subcollection can still exist even if its parent document does not.
3. Choose between **embedded map/array**, **subcollection**, or **root collection** based on queries and scale.
4. Design a `users / products / orders / items` model for an ordering application.
5. Write Java server SDK code to create/read/update documents and query collections; distinguish it from the Firebase web SDK.
6. Understand the role of **single-field/composite indexes**, collection group queries, and pagination.
7. Recognize that **Security Rules are not a query filter**, whereas the server SDK relies on IAM.
8. Avoid hot documents, sequential IDs, oversized documents, and deleting a parent while leaving child data behind.
9. Estimate reads/writes/indexes/storage and practice improving a data model.

## 1. Mental Model: Documents Live Inside Collections

Firestore stores **documents**, and each document contains a set of **fields** (key/value pairs). Documents are organized into **collections**. A document can contain maps/arrays in its fields as well as nested **subcollections** underneath it.

~~~mermaid
flowchart TD
    DB["Firestore database"] --> USERS["collection: users"]
    DB --> ORDERS["collection: orders"]
    USERS --> U["document: user_123"]
    ORDERS --> O["document: order_abc"]
    U --> MAP["fields: displayName, email,\npreferences (map)"]
    U --> ADDRS["subcollection: addresses"]
    ADDRS --> A["document: address_01"]
    O --> OF["fields: userId, status,\ntotalCents, createdAt"]
    O --> ITEMS["subcollection: items"]
    ITEMS --> I["document: line_01"]
~~~

### 1.1. The alternating path rule

Paths always alternate **collection / document / collection / document**:

| Path | Target | Valid? |
| --- | --- | --- |
| `users` | Root collection | Yes |
| `users/user_123` | Document | Yes |
| `users/user_123/addresses` | Subcollection | Yes |
| `users/user_123/addresses/address_01` | Document in subcollection | Yes |
| `orders/order_abc/items/line_01` | Document in subcollection | Yes |
| `users/addresses` if treating `addresses` as a collection right under `users` | Does not match intended model | Not a collection path; it is a document path |

**Path depth does not define a "table."** `orders/order_abc` is a document reference; `orders/order_abc/items` is a collection reference. Never place a collection directly under a collection or a document directly under a document.

### 1.2. Collections and documents are created when data is written

When writing `users/user_123` for the first time, Firestore creates the document and its collection if they do not exist yet; no SQL `CREATE TABLE` command is needed. Creating a reference **does not mean data already exists**. Similarly, `orders/order_abc/items/line_01` can exist even when the parent document `orders/order_abc` has no data.

**Very important note:** Deleting a parent document via the SDK **does not automatically delete subcollections**. You need a separate recursive deletion workflow, verifying permissions and read/delete costs. Never assume deleting `orders/order_abc` will delete all `items` of that order.

### 1.3. A document is not an arbitrary JSON file

Illustrative example of document `users/user_123`:

~~~json
{
  "displayName": "Mai",
  "status": "active",
  "preferences": {
    "language": "vi",
    "notifications": true
  },
  "roles": ["buyer"],
  "loyaltyPoints": 120
}
~~~

Firestore supports specialized value types such as **Timestamp, GeoPoint, Bytes, and Reference**, alongside String, Boolean, Number, Null, Map, and Array. When serializing to JSON for an API, convert specialized types to appropriate representations; do not assume a Firestore Timestamp is stored as an ISO string in the database.

## 2. Limits That Shape Data Design

| Limit/characteristic in Firestore Standard | Reference level | Consequence |
| --- | --- | --- |
| Size per document | **Max 1 MiB** | Do not store entire order or chat histories inside one document |
| Map/array field nesting depth | **Max 20** | Do not nest objects indefinitely inside a document |
| Subcollection nesting depth | **Max 100 levels** | Subcollection hierarchy differs from map depth |
| Collection/document ID name | Typically max **1,500 bytes**, cannot contain `/` | Validate IDs; never build paths from raw unvalidated user input |
| Full document path name | **Max 6 KiB** | Deep paths or very long IDs can exceed the limit |
| Index entries per document | **Max 40,000** | Large arrays/maps and many indexes can increase index fanout |
| Queries in Standard mode | Index-backed | Complex filter + sort combinations may require a composite index |

Additional limits depend on database edition and product updates. Check [Usage and limits](https://firebase.google.com/docs/firestore/quotas) before finalizing a production schema.

### 2.1. Choosing document IDs

- For documents without a natural key, prefer distributed **auto-generated IDs**.
- If using a business ID, ensure it is unique, does not expose PII, and remains stable for access.
- Avoid sequentially increasing IDs like `order-00001`, `order-00002` at high write rates; they can create a **hotspot** on adjacent key ranges.
- Never put emails, phone numbers, access tokens, or customer PII in document paths; paths can appear in logs and metrics.
- Auto-generated IDs distribute writes; they **do not guarantee** that querying/indexing by `createdAt` will be free from index hotspots.

### 2.2. Money and timestamp data

For example, an e-commerce app should store `totalCents: 129900` (an integer in the smallest currency unit) along with `currency: "VND"` or a well-defined decimal model; avoid defaulting to floating-point for monetary math. For VND, naming it `amountMinor` with an explicit currency convention is clearer in multi-currency systems.

Use **server timestamps** for `createdAt`/`updatedAt` when supported, rather than trusting client device clocks to establish business ordering. If you must continuously query by timestamp at very high write rates, evaluate index hotspots and partitioning/sharding architectures.

## 3. Three Ways to Organize Related Data

Firestore modeling typically chooses among **a map/array inside a document**, a **subcollection**, or **multiple root collections**. The right choice depends on read patterns, growth, and authorization.

| Approach | Best when | Pros | Limitations |
| --- | --- | --- | --- |
| **Map/array in document** | Data is small, bounded, and usually read with the parent | Single document read, easy to return together | Parent bloats; every change updates the document/indexes |
| **Subcollection** | List can grow unbounded and belongs naturally to a parent | Easy to query per list, paginate, and update individual elements | More reads when all items are needed; subcollection cleanup is complex |
| **Root collection** | Need to filter/query across many parents; entities have independent lifecycles | Easy to query by user/status/time across the database | Must store linking IDs/references; no SQL JOINs |

### 3.1. Embedded map: bounded data

For example, current shipping details embedded in an order:

~~~json
{
  "userId": "user_123",
  "status": "CREATED",
  "shipping": {
    "recipient": "Mai",
    "city": "Ho Chi Minh City",
    "country": "VN"
  },
  "totalMinor": 129900,
  "currency": "VND"
}
~~~

The `shipping` info is a **snapshot** at order placement time; keeping it with the order ensures it does not break if the user changes their address later. One document read retrieves the full order data, though you should never embed every address the user has ever saved into the order.

### 3.2. Array: small, stable lists

`tags: ["new", "fragile"]` can fit cleanly inside a product document. However, unbounded lists like `comments`, `reviews`, or `orderItems` will bloat the document and complicate pagination and concurrent writes. For those lists, use a **subcollection** or root collection.

**Partial field updates:** `update("shipping.city", "Da Nang")` updates a nested field; replacing the entire `shipping` map via `set` without merge can wipe out other nested fields. Only use dot notation matching planned field paths.

### 3.3. Subcollection: independently growing children

~~~text
orders/order_abc
  ├── fields: userId, status, createdAt, totalMinor
  └── items/line_01
        ├── productId: sku_001
        ├── quantity: 2
        └── priceMinor: 64950
      items/line_02
        ├── productId: sku_002
        └── quantity: 1
~~~

You can fetch the first 10 items, paginate forward, and update each line item independently. However, **reading `orders/order_abc` does not automatically include its items**; you must query the subcollection. Deleting a parent document does not automatically delete its items.

### 3.4. Root collections: querying across parents

If a "My Orders" screen routinely lists all orders for a user, storing `orders` at the **root** with a `userId` field directly supports:

~~~text
orders.where(userId == currentUser).orderBy(createdAt, desc).limit(20)
~~~

Using `users/user_123/orders/...` also works when every query is user-scoped; however, workflows like "all pending orders" or "orders for a branch" will then require collection group queries or additional duplicated/search indexes. **Design from access patterns**, not from a preference for deep nesting.

## 4. Designing from Queries: Ordering Application Example

### 4.1. List use cases before deciding on a schema

| Requirement | Desired query | Recommended organization |
| --- | --- | --- |
| View user profile after sign-in | Document by UID | `users/{uid}` |
| View product details | Document by productId | `products/{productId}` |
| List active products by category | `where(status, active)` + `where(categoryId)` + `orderBy(displayRank)` | Root `products` + composite index |
| List orders for a user | `where(userId)` + `orderBy(createdAt desc)` | Root `orders` |
| View details of an order and its line items | Parent read + subcollection query | `orders/{orderId}/items` |
| Query all line items across the system for a SKU | Collection group `items`, or another table/projection | Only create if a real use case exists |
| Update inventory stock | Transaction/atomic counter as designed | `products/{productId}` or load-appropriate partitions |

**Firestore does not auto-JOIN relationships.** If you need the product name at purchase time, store a **snapshot of `productName` and `unitPriceMinor`** in the item. If you need the latest product info, store `productId` to fetch the product document separately. This is **intentional denormalization**.

### 4.2. A consistent schema diagram

~~~mermaid
flowchart LR
  USERS["users/{uid}\ndisplayName, status"] --> ADDR["addresses/{addressId}\nrecipient, city"]
  ORDERS["orders/{orderId}\nuserId, status, createdAt,\ntotalMinor, currency, shipping"] --> ITEMS["items/{lineId}\nproductId, productName,\nquantity, unitPriceMinor"]
  PRODUCTS["products/{productId}\nname, categoryId,\nstatus, priceMinor, stock"] -. "product snapshot at checkout" .-> ITEMS
  USERS -. "referenced via userId" .-> ORDERS
~~~

Path structure:

~~~text
users/user_123
users/user_123/addresses/address_01

products/sku_001
products/sku_002

orders/order_abc
orders/order_abc/items/line_01
orders/order_abc/items/line_02
~~~

**Business invariants should be defined explicitly:**

- `orders.userId` identifies the owner; clients must never be allowed to change it to read someone else's orders.
- Order `totalMinor` is calculated by the backend from items; never trust prices sent by the client.
- `items.unitPriceMinor` is a price **snapshot** at checkout; the current price in `products.priceMinor` may change later.
- An item cannot exist without a valid order per business rules, even though Firestore **does not enforce foreign keys**.
- Checkout must ensure creating parent/order items and updating stock occur in an appropriate transaction/batch within practical limits, not just two disconnected writes.

## 5. Query Patterns and Indexes

### 5.1. Indexes serve queries, not arbitrary optimization

In Firestore Standard, **single-field indexes** are usually created automatically. Queries combining multiple field filters and sorting may require a **composite index**. If a required index does not exist yet, the SDK typically returns an error with instructions/a link to create it; the query **does not scan the entire collection** like a SQL table scan.

Example:

~~~text
orders
  .where("userId", "==", "user_123")
  .orderBy("createdAt", "desc")
  .limit(20)
~~~

Depending on existing indexes and database edition, a composite index may be needed:

~~~text
collection: orders
fields:
  userId    ASC
  createdAt DESC
query scope: Collection
~~~

Design indexes around **real queries**; unnecessary indexes increase index storage/write fanout and cost. Use the link in query errors, the Firebase Console/CLI, or IaC to configure them, and verify that index builds complete.

### 5.2. Collection-group queries

If multiple parents have subcollections with the same ID `items`, you can query **all** `items` via a collection group:

~~~text
orders/order_abc/items/line_01
orders/order_xyz/items/line_02
...
collectionGroup("items")
  .where("productId", "==", "sku_001")
~~~

**Important requirements:**

1. Queries scope across **all collections named `items`** in the database, even if another feature uses the same ID under a different structure.
2. A matching **collection-group index** is required.
3. Mobile/web access also needs **Security Rules supporting collection group queries**, typically using rules version 2.
4. Ownership/tenant metadata (such as `ownerUid`/`tenantId`) must be placed on the items if you want to filter by user/tenant; do not assume parent paths alone authorize client reads on every item.

If the main use case is querying all line items by SKU across millions of orders, consider a projection/root collection or BigQuery analytics rather than expensive collection-group queries. **Firestore does not replace analytical joins/reporting tools.**

### 5.3. Cursor-based pagination

Read the latest 20 orders, take the last document as a cursor, and query the next page with `startAfter(lastSnapshot)` using the same filter/order/limit. Using a **document snapshot** cursor avoids tie-breaking issues on duplicate sort fields; avoid using `offset` to "skip 10,000 rows" because Firestore can still bill reads for skipped documents.

**Limitation:** Paginated results need consistent rules when documents are added/deleted between pages; realtime data can shift positions while a user is paging through.

### 5.4. Queries and missing fields

A query with `orderBy("createdAt")` only returns documents **that have the `createdAt` field**. If you evolve a schema and older documents were not backfilled, they can disappear from lists even though they still exist in the database. Set default values/backfill and test compatibility when adding sort fields.

## 6. Java Server SDK: Creating Documents and Subcollections

Examples use `com.google.cloud:google-cloud-firestore` with **Application Default Credentials (ADC)**. On Cloud Run/GKE, the runtime service account needs appropriate IAM permissions on the database/project; local development uses a test account or the Firestore Emulator. Never put service account JSON keys into source code.

**Prerequisites:** The project has Firestore enabled, the Java app includes a JDK-compatible version of the Google Cloud Firestore dependency, appropriate IAM permissions are granted, and the default `(default)` database is used. The code below demonstrates basic APIs; it is not yet a production order service.

### 6.1. Create a parent order with an auto ID

~~~java
import com.google.cloud.firestore.DocumentReference;
import com.google.cloud.firestore.FieldValue;
import com.google.cloud.firestore.Firestore;
import com.google.cloud.firestore.FirestoreOptions;
import java.util.HashMap;
import java.util.Map;

public class CreateOrderExample {
    public static void main(String[] args) throws Exception {
        Firestore db = FirestoreOptions.getDefaultInstance().getService();

        try {
            DocumentReference order = db.collection("orders").document();

            Map<String, Object> data = new HashMap<>();
            data.put("userId", "user_123");
            data.put("status", "CREATED");
            data.put("currency", "VND");
            data.put("totalMinor", 129900L);
            data.put("createdAt", FieldValue.serverTimestamp());

            order.set(data).get();
            System.out.println("Created order ID: " + order.getId());
        } finally {
            db.close();
        }
    }
}
~~~

`document()` creates a reference with an **auto-generated ID**; `set(data)` writes the document. `get()` blocks on the asynchronous future; production apps should manage timeouts/exceptions/latency and **reuse the `Firestore` client** across the service lifecycle rather than creating/closing it per HTTP request.

### 6.2. Create a subcollection item

Assume `orderId` is the newly created, validated order ID:

~~~java
DocumentReference orderRef =
    db.collection("orders").document(orderId);

DocumentReference itemRef =
    orderRef.collection("items").document("line_01");

Map<String, Object> item = Map.of(
    "productId", "sku_001",
    "productName", "Insulated mug",
    "quantity", 2L,
    "unitPriceMinor", 64950L
);

itemRef.set(item).get();
~~~

This is a **code snippet** assuming valid `db` and `orderId` variables in scope, not a standalone file. Writing the order and item via **two separate `set()` calls is not atomic**: if writing the item fails, the order may exist without items. For data requiring consistency, use a **batched write** or **transaction** and validate business invariants inside the operation.

### 6.3. Read and query by user

~~~java
import com.google.cloud.firestore.DocumentSnapshot;
import com.google.cloud.firestore.Query;
import com.google.cloud.firestore.QuerySnapshot;

DocumentSnapshot order = db.collection("orders")
    .document(orderId)
    .get()
    .get();

if (!order.exists()) {
    throw new IllegalArgumentException("Order not found");
}

QuerySnapshot page = db.collection("orders")
    .whereEqualTo("userId", "user_123")
    .orderBy("createdAt", Query.Direction.DESCENDING)
    .limit(20)
    .get()
    .get();

page.getDocuments().forEach(doc ->
    System.out.println(doc.getId() + ": " + doc.getString("status"))
);
~~~

Without a matching composite index, the query may fail requesting index creation. Do not use this code to dump full order details containing PII into logs. **The backend must authenticate requests and verify user read permissions**; the server SDK is not automatically blocked by Firestore Security Rules.

### 6.4. Scoped updates

~~~java
import com.google.cloud.firestore.FieldValue;

db.collection("orders").document(orderId)
    .update(
        "status", "CONFIRMED",
        "updatedAt", FieldValue.serverTimestamp()
    )
    .get();
~~~

`update()` fails if the document does not exist; `set()` without merge can **overwrite all fields**. If you want an upsert that preserves existing fields, use `set(data, SetOptions.merge())`. For `status`, production code should use transactions/preconditions or a state machine to prevent invalid transitions (e.g., `CANCELLED → SHIPPED`).

## 7. Firebase Web SDK and Data Read Authorization

For web/mobile apps accessing Firestore directly, **Firebase Authentication + Firestore Security Rules** serve as the client authorization layer. For a Java server SDK running on Cloud Run/GKE, the app uses **Application Default Credentials and IAM**; **server client libraries bypass Security Rules**, so the backend must enforce caller business authorization itself.

### 7.1. Web client querying the signed-in user's orders

Example using the **Firebase Web modular SDK**; assumes `app` is initialized with a valid Firebase config and Firebase Authentication has a signed-in user:

~~~javascript
import { getAuth } from "firebase/auth";
import {
  getFirestore, collection, query, where,
  orderBy, limit, getDocs
} from "firebase/firestore";

const db = getFirestore(app);
const uid = getAuth(app).currentUser?.uid;
if (!uid) throw new Error("Authentication required");

const q = query(
  collection(db, "orders"),
  where("userId", "==", uid),
  orderBy("createdAt", "desc"),
  limit(20)
);

const snapshot = await getDocs(q);
const orders = snapshot.docs.map(d => ({ id: d.id, ...d.data() }));
~~~

This is an **in-app snippet for an already configured Firebase project**, not a standalone script. The query requires a matching index and **Rules permitting the user to read their own data**. Never use a client-supplied `userId` instead of the verified UID when making authorization decisions.

### 7.2. Sample Security Rules: read only your own orders

~~~javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /orders/{orderId} {
      allow get, list: if request.auth != null
        && resource.data.userId == request.auth.uid;

      // This app only writes orders through a controlled backend.
      allow create, update, delete: if false;

      match /items/{itemId} {
        allow get, list: if request.auth != null
          && get(/databases/$(database)/documents/orders/$(orderId))
               .data.userId == request.auth.uid;
        allow create, update, delete: if false;
      }
    }
  }
}
~~~

**How to interpret this:**

- Clients can only read `orders/{orderId}` if `userId` matches the Firebase Auth UID.
- Clients can read the `items` subcollection when they own the parent document.
- This example allows **reads** only; writes go through a backend that validates the user, prices, inventory, and status.
- A `get(parent)` rule call can incur **document reads** and counts against Rules read quotas; do not trigger it unboundedly across thousands of documents.
- This is a **partial ruleset sample**; if the app has other collections, define them explicitly—never add `match /{document=**} { allow read, write: if true; }`.

**Rules are not a filter.** A `collection("orders")` query without filtering `userId` will be **rejected outright** if Firestore cannot guarantee every potential document belongs to the current user. Clients must query `where("userId","==",uid)`; you cannot "fetch everything and let Rules filter out other people's orders."

### 7.3. Collection-group security rules

When mobile/web runs `collectionGroup("items")`, you need **rules version 2** with a match covering the subcollection paths in the group, plus an index with **collection group scope**. If different parent branches share the name `items`, your rules must cover **all** cases the query could return while enforcing owner/tenant boundaries.

Never add a wildcard `allow read: if request.auth != null` across an entire collection group. When authorization is complex, consider querying through an IAM/business-checked backend or adding an `ownerUid` field on each item and testing Rules with the emulator.

### 7.4. The Firestore server SDK is not blocked by Rules

A Java backend using ADC with IAM `roles/datastore.user` (or a custom role with matching permissions) can access data within its granted scope **without passing through Firebase Security Rules**. If a backend endpoint handles `GET /orders/{id}`, it must verify the order's `userId` against the authenticated principal; never expect client-side Rules to protect server endpoints.

**Layering:**

| Layer | What does it protect? |
| --- | --- |
| Firebase Authentication | End-user identity |
| Firestore Security Rules | Web/mobile SDK read/write access based on auth/data |
| Google Cloud IAM | Workloads/servers/service accounts access to Firestore |
| Backend business checks | Inventory, order eligibility, pricing calculation, and transaction state |
| App Check where appropriate | Reduces traffic from spoofed clients; **does not replace auth or Rules** |

## 8. Consistency: Batches, Transactions, and Snapshots

Firestore does not automatically enforce a **foreign key** between `orders.userId` and `users/{uid}`. Nor does it validate `totalMinor = sum(items)`. When multiple documents must change together in one operation, you must design for it explicitly.

### 8.1. Batched writes: atomic multi-document writes

If you only need to create an order and items using data **already validated in the backend**, use `WriteBatch`:

~~~java
import com.google.cloud.firestore.WriteBatch;

DocumentReference orderRef =
    db.collection("orders").document();
DocumentReference itemRef =
    orderRef.collection("items").document("line_01");

Map<String, Object> orderData = Map.of(
    "userId", "user_123",
    "status", "CREATED",
    "totalMinor", 129900L
);
Map<String, Object> itemData = Map.of(
    "productId", "sku_001",
    "quantity", 2L,
    "unitPriceMinor", 64950L
);

WriteBatch batch = db.batch();
batch.set(orderRef, orderData);
batch.set(itemRef, itemData);
batch.commit().get();
~~~

**Either the entire batch commits or no writes are applied.** This example does not update stock, set `createdAt`, calculate tax, or perform business validation; it only illustrates atomicity when writing a parent and item. For large bulk imports, do not pack unbounded documents into one batch; use tools like `BulkWriter` and observe API limits.

### 8.2. Transactions: read then decide to write

If you need to check and deduct inventory, use a transaction. Logic example **clarifying an operation on a single product**:

~~~java
DocumentReference product =
    db.collection("products").document("sku_001");

db.runTransaction(tx -> {
    DocumentSnapshot snapshot = tx.get(product).get();
    Long available = snapshot.getLong("stock");
    long requested = 2L;

    if (available == null || available < requested) {
        throw new IllegalStateException("Out of stock");
    }
    tx.update(product, "stock", available - requested);
    return null;
}).get();
~~~

Firestore may **retry a transaction callback** on contention. Therefore **never send emails, call payment gateways, or publish to Pub/Sub inside the callback**: side effects may execute multiple times. For a proper checkout flow, add an order ID/idempotency key, write related documents inside a valid transaction, and test retry scenarios.

A **hot stock document** for a bestselling SKU can still suffer contention even when the transaction is correct. At very high traffic, consider distributed counters, reservations/queues, or a dedicated inventory model; you cannot increase throughput merely by adding more clients.

### 8.3. When should you store a snapshot instead of reading a reference?

An order item should store `unitPriceMinor` and `productName` at purchase time. A year later, the product price may change or the product may be deleted, yet historical invoices still need to reflect what was bought. Duplicating a few fields is intentional:

- **Read model** is faster because no multi-document JOIN is required.
- **Write path** must take responsibility for keeping/capturing snapshots at the right time.
- **Consistency** is a design trade-off—there is no single rule to "always normalize" or "always embed."

## 9. Scaling and Avoiding Hotspots

### 9.1. Common anti-patterns

| Error-prone design | Why it is risky | How to improve |
| --- | --- | --- |
| A single `orders-summary` document holding a counter for all orders | Contention when many writers update the same document | Appropriate distributed counter/aggregation |
| Document IDs `order-000001`, `order-000002` | Sequential keys create hotspots at high write rates | Auto IDs or distributed IDs |
| All chat messages in an array inside `rooms/{id}` | Document bloats, 1 MiB limit, update contention | `rooms/{id}/messages/{messageId}` |
| Sequentially increasing `createdAt` field that is **indexed** at high write rates | Index hotspot; collections with indexed sequential fields hit a threshold around **500 writes/s** | Exempt the index if not queried; partition workload if querying is needed |
| Indexing an entire `largeBlobText` or large map/array | Wastes storage and increases index fanout | Single-field index exemption when not queried |
| Client reads all `orders` and filters by user | High cost and incompatible with Rules | Filter in Firestore query and Rules |
| `offset(10000)` for pagination | Skipped documents can still be billed as reads | Query cursor + limit |
| Deleting parent order assuming items vanish | Orphan subcollection documents | Recursive cleanup/TTL workflow per model |
| Overwriting a document via `set` with missing fields | Loss of existing field data | Update/merge/precondition |
| Overly deep hierarchy with no purpose | Complex Rules, indexes, cleanup, and queries | Choose a hierarchy serving real read paths |

**Important distinction:** 500 writes/s refers to hotspots when **sequentially increasing/decreasing field values are indexed**, not an absolute ceiling on every Firestore collection. Firestore can scale much higher if IDs, indexes, key distribution, and traffic ramp-up are designed properly.

### 9.2. Index fanout affects write latency

On every document write, Firestore updates affected index entries. A document with many array elements, many indexed fields, and numerous composite indexes can generate heavy index writes. When large fields are not used for filtering or sorting, evaluate **single-field exemptions**, balancing performance against queryability.

**Do not disable indexes on `userId` or `createdAt` if primary screens still query them.** Any exemption proposal must be backed by a query inventory and regression tests.

### 9.3. Ramp up traffic gradually

Firestore manages storage partitioning automatically, but when sending data/traffic to a new key range, never push full load instantaneously. For migrations and imports, use **gradual ramp-up**, random/scattered IDs, and monitor p95, retry/contention errors, and index builds. Use **Key Visualizer** where supported to detect hotspots in document/index key ranges.

## 10. Deleting Data, TTL, and Schema Evolution

### 10.1. Deleting a parent does not clean up subcollections

Suppose you have:

~~~text
orders/order_abc
orders/order_abc/items/line_01
orders/order_abc/items/line_02
~~~

If the SDK calls `orders/order_abc.delete()`, documents `items/line_01` and `items/line_02` **still exist**. Therefore:

- For **soft delete**, set `deletedAt`/`status` and exclude them from queries per policy, followed by controlled background cleanup.
- For **hard delete**, use a runbook that queries and deletes subcollections and the parent in appropriate batches, handling retries/idempotency and read/delete costs.
- For data with retention/audit obligations, define retention, backup, and deletion policies before deleting anything.
- **TTL** deletes documents based on a timestamp field; TTL deleting a parent also **does not replace** recursive subcollection cleanup.

Some **Delete document** actions in the Firebase Console include UI-driven nested cleanup behavior; never assume SDK `delete()` calls behave like the Console. For code or production automation, always verify the semantics of the **specific API**.

### 10.2. Safe schema migrations

Firestore does not force every document in a collection to have the exact same set of fields. This brings flexibility, but when an API changes from `total` to `totalMinor`, older documents may lack the new field.

A safe migration:

1. **Expand:** the application reads both old and new schemas; new writes populate the canonical field.
2. **Backfill:** update older documents in batches with checkpoints and retries; avoid loading the entire collection at once.
3. **Observe:** verify migrated document counts, query indexes, and Rules.
4. **Switch:** point read paths to the new field and monitor error rates.
5. **Contract:** remove old-field support after the rollback window closes, and clean up indexes/data after approval.

In event-driven systems, Cloud Functions/Cloud Run triggers can synchronize projections, but they must handle **at-least-once delivery, duplicate events, and out-of-order updates**. Never assume a trigger runs only once.

## 11. Cost, Observability, and Database Selection

### 11.1. Factors driving cost

Firestore Standard bills for **document reads, writes, deletes**, index entry reads depending on query type, storage (documents and indexes), network egress, backups/PITR/TTL, and auxiliary features. With realtime listeners, document updates can generate additional document reads across active listeners.

Suppose a list screen loads **20 orders**, and then loads **5 items** separately for each order:

~~~text
Orders:         20 document reads (conceptual)
Items:       20 × 5 = 100 document reads
Minimum total: 120 document reads per page load (assuming items exist)
~~~

This illustrates **documents read**, not an exact bill: actual charges also depend on index reads, additional Rules reads, caching, listeners, offsets, and API execution. If an order list screen only needs a summary, do not fetch all items for every order upfront.

### 11.2. Essential metrics and checks

| Signal | Question to answer |
| --- | --- |
| Document reads/writes/deletes | Which screen or job is driving read spikes? |
| Index storage & index builds | Are there redundant or missing indexes? |
| Query latency/p95 | Is a query missing an index, hitting a hotspot, or returning too many results? |
| Permission denied | Misconfigured Rules, incompatible query, or missing IAM? |
| Contention/retries | Is a single document receiving too many writes? |
| Orphan subcollections | Were parents deleted without proper cleanup? |
| Billing/Budgets | Are costs exceeding forecasts across reads, storage, or egress? |
| Data residency/location | Does the database region/multi-region match users and the Cloud Run backend? |

Choose a location **close to users and compute services** to reduce latency and data transfer costs; regional vs multi-region locations involve trade-offs across availability, cost, and write latency.

### 11.3. When should you NOT use Firestore?

| Requirement | Consideration |
| --- | --- |
| Multi-table transactions with complex JOINs, strict schema, SQL reporting | **Cloud SQL / AlloyDB** |
| Analytics scanning billions of records, large joins/aggregations | **BigQuery** |
| Ultra-low-latency key-value/cache with TTL | **Memorystore/Redis-compatible cache** |
| Storing PDFs, images, large videos | **Cloud Storage**, with Firestore holding metadata/URLs |
| Document-oriented apps with small records, key lookups, and indexed queries | **Firestore** fits well |

These are not absolute rules; evaluate every choice against SLAs, data shape, query patterns, IAM, cost, and integration requirements.

## 12. Common Troubleshooting

| Symptom | Likely cause | Remediation |
| --- | --- | --- |
| `PERMISSION_DENIED` from Firebase web SDK | Missing auth, Rules block query, or wrong collection-group rules | Check UID, query constraints, Rules Emulator |
| Java backend can read, but web cannot | Java server SDK uses IAM, **bypassing Rules** | Add properly scoped Rules; never make public |
| Filter+sort query reports missing index | Composite index does not exist | Create index from error link/IaC and wait for build |
| `orderBy` query misses older documents | Documents lack the sort field | Backfill/ensure defaults |
| Document exceeds 1 MiB | Unbounded embedded array/history | Move list to a subcollection |
| Read latency spikes when loading orders page | N+1 queries loading all items | Load items only when opening an order; paginate |
| Continuous order writes are slow | Hot document/index or stock contention | Auto IDs, optimize indexes, shard counters |
| Deleted user still shows addresses via direct path | SDK does not cascade subcollections | Recursive cleanup/retention |
| Cannot update a non-existent document | `update()` requires the document to exist | Use `set(..., merge)` when upserting |
| Replacing a map loses nested fields | `set()` overwrites entire document/map | Dot-path update or merge |
| Transaction callback runs multiple times | Firestore retries on contention | Remove side effects from callback; use idempotency |
| Money totals are wrong | Used floats or trusted client-sent prices | Integer minor units; recalculate on backend |
| Old invoices change with new product name/price | Stored only a reference without a snapshot | Store immutable price/name on order items |
| Index storage grows rapidly | Too many fields/large arrays indexed | Query inventory + appropriate exemptions |

**Investigation order:** right path/database → document exists → Auth/Rules/IAM → query/index → schema fields → read/write patterns → contention/cost. Never grant Owner or set `allow read, write: if true` to troubleshoot.

## 13. Case Study: Evolving Beyond an MVP Design

**Context:** A team builds an ordering app on Firebase, initially handling 200 orders/day; six months later, volume reaches 100,000 orders/day. MVP design:

~~~json
{
  "userId": "user_123",
  "orders": [
    {"id": "o1", "totalMinor": 129900},
    {"id": "o2", "totalMinor": 259800}
  ]
}
~~~

All `orders` were embedded inside `users/user_123`.

**Growth problems:** User documents bloat, writes contend, pagination/counting is hard, and loading a profile drags along the entire order history. Proposed redesign:

~~~text
users/user_123
  displayName, preferences

orders/order_abc
  userId, status, createdAt, totalMinor, currency, shipping
  items/line_01
  items/line_02
~~~

**Benefits:** Orders are separate documents with auto IDs supporting user-scoped listing/querying; the `items` subcollection can grow without inflating the parent order. **Trade-offs:** Order details take extra reads, composite indexes are required, Rules must restrict by `userId`, and parent/child deletion requires careful handling.

**Additional decision:** Multi-dimensional revenue analytics should stream events/controlled syncs into BigQuery instead of asking Firestore to perform large joins and aggregations.

## 14. Design and Verification Lab

You can use the **Firestore Emulator** to avoid writing to production. If using a real cloud environment, pick an authorized lab project and database; never use real customer data or payment details.

### 14.1. Safe preparation

1. Select **Firestore in Native mode** with the edition/dialect matching the guide.
2. Use the Firebase Emulator Suite if you have Firebase CLI and a lab project.
3. For the Java backend: configure ADC for the appropriate environment or point the client to the emulator; never commit service account JSON keys.
4. For the web app: use Firebase Authentication test accounts and the Rules emulator.
5. Enable budgets/alerts if accessing a real cloud database.

Example starting the emulator in a **lab directory that already has `firebase.json` configured for emulators**, not inside the lesson repository:

~~~bash
firebase emulators:start --only firestore --project demo-firestore-lab
~~~

The Java backend can set `FIRESTORE_EMULATOR_HOST=127.0.0.1:8080` (matching the configured emulator port). The emulator does not replace production load testing or validate all edition/multi-region behaviors, but it lets you verify schemas and Security Rules.

### 14.2. Tasks

| Step | Action | Evidence |
| --- | --- | --- |
| 1 | Diagram `users/products/orders/items` and alternating paths | Collection/document diagram |
| 2 | Create 2 users, 3 products, 3 orders with mock data | Paths and fields with proper types |
| 3 | Add 1–3 items per order | No unbounded list embedded in order |
| 4 | Query a user's orders, `orderBy(createdAt desc)` | Accurate results with index |
| 5 | Query items of one order | Without re-reading all orders |
| 6 | Test Rules: user A reads order A, order B is denied | Emulator test results |
| 7 | Test `collectionGroup("items")` and matching index | Verify scope correctness |
| 8 | Delete a **test parent order** via SDK | Prove items remain; write cleanup plan |
| 9 | Compare reads when orders page reads summaries vs loading items | Cost estimate for both approaches |
| 10 | Write a backfill plan for a new field | Zero lost legacy orders |

**Never test deletes on real data.** When naming multiple subcollections `items`, review collection-group queries and Rules before exposing the API.

### 14.3. Completion criteria

- Paths follow alternating collection/document order.
- Explained why one field is embedded while another list lives in a subcollection.
- Indexes support primary queries and read access is scoped by UID.
- Distinguished Java server IAM from Firebase client Rules.
- Atomic write strategy for order + items where business logic requires it.
- Recorded notes on reads, performance, and subcollection cleanup.

## 15. Review Questions and Checklist

### 15.1. Questions with short answers

1. **How does Firestore differ from SQL tables?** Data lives in documents inside collections, without traditional SQL JOINs.
2. **What does `users/u1/orders/o1` point to?** Document `o1` inside the `orders` subcollection of document `users/u1`.
3. **Does creating a collection require DDL?** No; collections appear when data is written.
4. **How does a map differ from a subcollection?** A map lives inside one document; a subcollection holds separate documents that can be queried independently.
5. **What data should be snapshotted inside an order?** Product price/name at checkout and shipping address at order placement time.
6. **Can a single document grow infinitely?** No; Standard limits it to 1 MiB.
7. **Does deleting an order document delete its items?** Not by default with SDK delete.
8. **Can two `items` collections under different orders be queried together?** Yes, via a collection group query with appropriate indexes and Rules.
9. **Are sequential order IDs good for high write volume?** They risk hotspots; use distributed IDs.
10. **What does a `where(userId)` + `orderBy(createdAt)` query likely need?** A composite index.
11. **Do Security Rules filter query results automatically?** No; the query itself must satisfy Rules.
12. **Is the Java server SDK restricted by Security Rules?** No; it uses IAM, and the backend must enforce permissions.
13. **If a document lacks the `orderBy` field, is it returned?** No.
14. **How does a transaction differ from a batch?** A transaction can read data, decide writes, and retry; a batch writes atomically without reads.
15. **Should payment processing go inside a transaction callback?** No; the callback can run multiple times on retry.
16. **Should an array store 10,000 chat messages in one document?** No; store them as documents in a subcollection.
17. **Why can having many Firestore indexes slow down writes?** Index fanout increases the number of index entry updates.
18. **Is a large pagination offset or a cursor better?** A cursor is usually better and avoids billed reads for skipped results.
19. **Does deleting a user account automatically delete all subcollections?** No; an explicit deletion workflow is required.
20. **Does Firestore replace BigQuery analytics?** No; choose based on workload and reporting needs.

### 15.2. Production checklist

- [ ] Use cases and query paths documented in a table before creating the schema.
- [ ] Document IDs chosen appropriately without leaking sensitive info.
- [ ] Fields use explicit types: integer minor units for money, timestamps, status enums.
- [ ] Maps/lists embedded only when bounded and always read with the parent.
- [ ] Subcollections hold data that can grow large or needs pagination.
- [ ] Root collections support cross-user/order queries and entities with independent lifecycles.
- [ ] Indexes support filters/sorts without unnecessary indexes causing write fanout.
- [ ] Security Rules tested in the Emulator with real/mock users; server IAM follows least privilege.
- [ ] Backend verifies business ownership and access permissions rather than trusting client fields.
- [ ] Batches/transactions/idempotency used where consistency is required.
- [ ] No hot counters, hot documents, or sequential IDs/indexes under high load.
- [ ] Retention/TTL, recursive delete, backup/restore, and migration plans in place.
- [ ] Pagination, read costs, listener lifecycles, data location, and budgets monitored.
- [ ] Logs/traces exclude tokens, personal addresses, and sensitive order details.

## 16. Official Documentation

- [Firestore data model](https://firebase.google.com/docs/firestore/data-model) — documents, collections, subcollections, and collection groups.
- [Choose a data structure](https://firebase.google.com/docs/firestore/manage-data/structure-data) — embedded data, root collections, and subcollections.
- [Usage and limits](https://firebase.google.com/docs/firestore/quotas) — 1 MiB/document, nesting, and indexes.
- [Add and update data](https://firebase.google.com/docs/firestore/manage-data/add-data) — `set`, `update`, server timestamps, and nested fields.
- [Query data](https://firebase.google.com/docs/firestore/query-data/queries) — filters, sorting, collection groups.
- [Indexes](https://firebase.google.com/docs/firestore/query-data/indexing) — single-field/composite indexes and index exemptions.
- [Query cursors](https://firebase.google.com/docs/firestore/query-data/query-cursors) — pagination without offsets.
- [Transactions and batched writes](https://firebase.google.com/docs/firestore/manage-data/transactions) — atomicity and transaction retries.
- [Security Rules](https://firebase.google.com/docs/firestore/security/get-started) — Firebase Auth vs server IAM.
- [Test Security Rules](https://firebase.google.com/docs/firestore/security/test-rules-emulator) — Emulator tests.
- [Delete documents and collections](https://firebase.google.com/docs/firestore/manage-data/delete-data) — deleting a parent does not cascade subcollections.
- [Best practices](https://docs.cloud.google.com/firestore/native/docs/best-practices) — index fanout, hotspotting, and traffic ramp-up.
- [Firestore pricing](https://firebase.google.com/docs/firestore/pricing) — reads/writes/deletes, storage, and index costs.
- [Firestore Java client](https://cloud.google.com/java/docs/reference/google-cloud-firestore/latest/overview) — Java SDK and ADC.

**Remember:** In Firestore, **collections organize documents; documents hold fields; subcollections hold child documents**. Design from **queries, access permissions, and growth rates**, not from SQL table diagrams. Embed small data, split growing data into separate documents, index real queries, and always account for **Security Rules, IAM, child cleanup, hotspotting, and read costs**.
