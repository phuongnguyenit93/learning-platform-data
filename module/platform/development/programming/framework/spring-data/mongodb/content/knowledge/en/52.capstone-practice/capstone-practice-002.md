# Designing Documents, References, IDs, and Indexes

In a **Spring Data MongoDB** project, good data design starts from how the application **reads and writes data**, not just from a list of Java entities. A poor choice at the document level can force the system to join multiple collections on every request; an unbounded embedded array can exceed the document size limit; a misordered index may fail to support the most frequent queries and sorts.

This **capstone practice** guides data model design for a multi-tenant ordering service. Learners combine document modeling, embedding and referencing, `_id` design, unique constraints, compound indexes, `MongoTemplate`/repository operations, verification queries, and performance tests. The solution is a reference architecture explaining decisions and limitations, which can be adapted to real project requirements.

## 1. Problem Statement and Required Behaviors

Build an order management service for multiple stores (*tenants*). Each order belongs to exactly one tenant and one customer; each order has one or more line items. Products may change name or price in the future, but placed orders must preserve the price and name at the time of purchase. Inventory is updated frequently and must be protected against overselling.

The application must support the following operations:

| Code | Need | Access pattern |
| --- | --- | --- |
| Q1 | Fetch an order by `tenantId` + `orderNumber` | Point lookup, high frequency, must be unique within tenant |
| Q2 | View the 30 latest `PAID` orders in a tenant | Equality filter + descending sort + pagination |
| Q3 | View a customer's order history | Filter by tenant, customer, and sort by time |
| Q4 | Read order details, including each line's name/price at purchase time | Single read, consistent with order snapshot |
| Q5 | Fetch current product info for catalog display | Independent product, potentially updated frequently |
| Q6 | Deduct inventory when confirming an order | Conditional update, avoid deducting when stock is insufficient |
| Q7 | Report orders containing a specific product | Lower frequency, may require an index or separate analytics flow |

Initial assumptions: each order has at most 100 line items; order history must be retained for many years; a product may be referenced by thousands of orders; every tenant has its own order numbers; there is no requirement to transfer order ownership after creation. These are **exercise assumptions** and must be replaced with observed production data before deployment.

### Deliverables to Complete

Learners need to produce: a collection and relationship diagram, BSON samples for each collection, `_id`/business key generation rules, an index list mapped to Q1–Q7, basic Java mappings, verification queries using `MongoTemplate` or repositories, `explain("executionStats")` checks, and tests for data constraints and concurrent updates.

## 2. Starting from Aggregates and Update Boundaries

An **aggregate** is a cluster of data that must be checked for consistency against business rules. In MongoDB, design is often favorable when data frequently read and modified together resides in a single document, because writing to **one document** is atomic. However, a domain aggregate does not necessarily correspond one-to-one with a collection in every system.

For this problem:

- **Order** is an aggregate containing order metadata and the `lines` list. Line items together form the order's contents and total amount; line count is bounded, so they are suitable to **embed** in `orders`.
- **Product** has an independent lifecycle: name, description, current price, active status. Thousands of orders may reference the same product, so it is stored as a separate document in `products`.
- **Customer** has separate contact info that may change; orders store `customerId`, while optionally embedding a shipping address snapshot to preserve delivery details at purchase time.
- **Inventory** has a high write rate and separate contention rules; place stock in a separate `inventory` document per `(tenantId, productId)` for conditional updates.

~~~mermaid
flowchart LR
    C[(customers)] -->|customerId reference| O[(orders)]
    P[(products)] -->|productId + snapshot in lines| O
    P -->|productId| I[(inventory)]
    O --> L[embedded lines: SKU, name, unit price, quantity]
~~~

MongoDB **does not automatically enforce foreign keys** between `orders.customerId` and `customers._id`, or between `orders.lines.productId` and `products._id`. The application must enforce existence checks, tenant-scoped access control, soft delete/restore, and orphan reference handling. If an operation requires consistent multi-document updates, consider transactions when MongoDB and the application are configured accordingly.

## 3. Deciding Between Embed and Reference

There is no fixed rule saying "MongoDB must embed everything" or "keep everything separate." Answer questions about lifecycle, size, update frequency, and query shape for each relationship.

| Data | Choice | Rationale in this exercise |
| --- | --- | --- |
| Order line items | **Embed** `lines[]` in `orders` | Usually read with the order, bounded count, keeps price/name snapshot with order status |
| Product name/price at purchase time | **Embed copy** in `lines[]` | When catalog prices or names change, order history remains accurate |
| Customer owning the order | **Reference** via `customerId` | One customer has many orders; customer info changes independently |
| Confirmed shipping address | **Snapshot embed** in `orders` | An order's delivery address must not change with customer profile edits |
| Current inventory | **Separate collection** `inventory` | Changes frequently, avoids writing into every order or large product documents |
| Unbounded comments/tracking logs | **Separate collection**, queried by `orderId` | Avoids embedding unbounded arrays into order documents |

### Signals Favoring Embedding

Embedding fits when child elements share a tight lifecycle with the parent, are read alongside the parent, are small/bounded in count, and need atomic updates within the same document. For instance, an `OrderLine` with `productId`, `sku`, `nameAtPurchase`, `unitPriceMinor`, and `quantity` is a **snapshot**. Renaming the catalog item must not overwrite order history.

### Signals Favoring Referencing

Referencing fits when data has an independent lifecycle, is shared across many documents, updates frequently, or forms an unbounded subset. For example, do not embed the entire order history into a customer document: the history can grow forever, causing large updates and risking MongoDB's **16 MiB single-BSON-document limit**.

**Trade-offs to remember:** Referencing may require extra queries or `$lookup`. With many references, query load depends on batch fetching and pagination; never assume multi-ID reads are free. Embedding reduces read round-trips but increases document size and may duplicate updates across copies. Choose storage layout based on actual use cases.

## 4. Designing Sample Documents

### `orders` Collection

~~~javascript
{
  _id: "ord_01K8XYN7H4RG25K9P12B3A",          // Stable technical ID
  tenantId: "shop_01",
  orderNumber: "SO-2026-00127",                // Business code within tenant
  customerId: "cus_01K8XYG0N3E4K41ZTY0Q",
  status: "PAID",
  createdAt: ISODate("2026-11-20T03:15:00Z"),
  updatedAt: ISODate("2026-11-20T03:20:00Z"),
  currency: "VND",
  totalMinor: NumberLong("310000"),
  shippingAddress: {
    recipientName: "Nguyen An",
    city: "Ho Chi Minh City",
    addressLine: "Shipping address at purchase time"
  },
  lines: [
    {
      productId: "prd_01K8XX52P30A4T5ZXM6Q",
      skuAtPurchase: "MUG-RED",
      nameAtPurchase: "Red Ceramic Mug",
      unitPriceMinor: NumberLong("120000"),
      quantity: 2,
      lineTotalMinor: NumberLong("240000")
    },
    {
      productId: "prd_01K8XX8BTB0Y7F5CAW1R",
      skuAtPurchase: "BOOK-01",
      nameAtPurchase: "Notebook",
      unitPriceMinor: NumberLong("70000"),
      quantity: 1,
      lineTotalMinor: NumberLong("70000")
    }
  ],
  version: NumberLong("2")
}
~~~

`totalMinor` and `unitPriceMinor` use the currency's minor unit per system convention. For VND in this example, one integer unit corresponds to one dong; for other currencies, decimal places must follow the business contract. `long` avoids many floating-point rounding errors, though you still need overflow checks when summing totals and handling tax/promotion rules. Another option is **Decimal128** with explicit rounding conventions.

### `products` Collection

~~~javascript
{
  _id: "prd_01K8XX52P30A4T5ZXM6Q",
  tenantId: "shop_01",
  sku: "MUG-RED",
  displayName: "Red Ceramic Mug New Edition",
  currentPriceMinor: NumberLong("135000"),
  currency: "VND",
  active: true,
  updatedAt: ISODate("2026-11-21T02:00:00Z")
}
~~~

A product's name and price may change; they **do not alter** `nameAtPurchase` and `unitPriceMinor` in previously placed orders.

### `customers` Collection

~~~javascript
{
  _id: "cus_01K8XYG0N3E4K41ZTY0Q",
  tenantId: "shop_01",
  displayName: "Nguyen An",
  emailNormalized: "an@example.com",
  active: true
}
~~~

### `inventory` Collection

~~~javascript
{
  _id: "stock_shop01_mugred",
  tenantId: "shop_01",
  productId: "prd_01K8XX52P30A4T5ZXM6Q",
  available: 21,
  reserved: 3,
  updatedAt: ISODate("2026-11-20T03:20:00Z")
}
~~~

`inventory` has one document per `(tenantId, productId)` pair. The `_id` in the example is illustrative only; when generating real IDs, avoid collisions from string concatenation, case sensitivity, and special characters. Even when tenant/product are encoded into `_id`, you should still use a **unique index** on the business key fields to enforce uniqueness on the exact data being protected.

## 5. Designing IDs and Business Keys

### Distinguishing `_id`, Natural Keys, and Display Codes

| Key | Meaning | Notes |
| --- | --- | --- |
| `_id` | Unique technical identifier **within a collection**; MongoDB creates a unique index automatically | Should be immutable; can use ObjectId or consistently formatted String |
| `orderNumber` | User-visible order code | Only needs to be unique **within a tenant** per requirements; do not use as technical key if format may change |
| `(tenantId, sku)` | Business key identifying an SKU in a tenant catalog | Use compound unique index; same SKU can appear in another tenant |
| `inventory` `(tenantId, productId)` | Each product has one stock record per tenant | Use compound unique index and control concurrent updates |
| `customerId` in order | Reference to customer | Does not automatically guarantee customer exists, matches tenant, or is not deleted |

**ObjectId** is a common default for `_id`: compact, highly unique, and includes a timestamp component, though the ObjectId timestamp should not replace the business `createdAt` field. UUID/ULID/String IDs can also fit when services must pre-generate IDs; consider index size, potential information leakage, monotonicity, and cross-system compatibility.

With **Spring Data MongoDB**, `@Id String id` converts to BSON ObjectId in certain cases when the string value has a valid ObjectId format. If the contract requires `_id` to always be stored as a BSON string, you can use `@MongoId(FieldType.STRING)` and verify mapping on your Spring Data version. Never casually change the `_id` type of an existing populated collection: ObjectId and string look similar in logs but are **two different BSON types** and will not match in queries.

### ID Rules for Multi-Tenant Environments

MongoDB only guarantees `_id` is unique within a collection; it does not infer access permissions from IDs. Every user query must still enforce the appropriate `tenantId`. When a request sends an `orderId` from another tenant, the endpoint must reject or return not-found per API policy, even if `_id` is queryable.

If choosing sharding, additionally evaluate the **shard key** and MongoDB's unique index rules. In a sharded collection, to enforce global uniqueness across multiple fields, a unique index typically must align with shard key prefix rules and sharding configuration; do not assume all unique indexes behave identically to unsharded collections.

## 6. Entity Mapping with Spring Data MongoDB

Example entity mapping the `orders` document, using `@MongoId` to keep the technical ID as a string and `@Version` to guard `save` operations with version checks:

~~~java
import java.time.Instant;
import java.util.List;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;
    private String tenantId;
    private String orderNumber;
    private String customerId;
    private String status;
    private Instant createdAt;
    private Instant updatedAt;
    private String currency;
    private long totalMinor;
    private List<OrderLine> lines;

    @Version
    private Long version;

    // Constructors, getters, and setters omitted to focus on design.
}

record OrderLine(
    String productId,
    String skuAtPurchase,
    String nameAtPurchase,
    long unitPriceMinor,
    int quantity,
    long lineTotalMinor
) {}
~~~

`@Version` enables Spring Data-supported operations to check the version when updating documents, but it does not protect raw driver commands or custom updates that **bypass version conditions**. When using Spring Data with `Instant`, verify BSON Date handling and timezone policies against actual data. If using `@Field` to rename fields, any direct driver queries must use the actual physical field names.

You can declare `customerId` and `productId` purely as scalar references as shown, then batch-fetch via repositories/`MongoTemplate`. Spring Data MongoDB also provides `@DBRef` and `@DocumentReference` to model references via different mechanisms. However, MongoDB **does not automatically validate integrity** of these references; eager/lazy loading, query counts, circular references, and deleted targets still require careful design. For order detail flows that already embed snapshots, there is no need to automatically query products/customers for every line item.

## 7. Designing Indexes from Queries Q1–Q7

MongoDB automatically provides a unique index on `_id`. Additional indexes must serve concrete **query shapes** while balancing write overhead and storage size. Every index adds maintenance cost to `insert`/`update`/`delete` operations.

| Query | Primary filter/sort | Recommended index | Rationale |
| --- | --- | --- | --- |
| Q1 | `tenantId`, `orderNumber` | `{ tenantId: 1, orderNumber: 1 }` **unique** | Fast lookup and enforces unique order number per tenant |
| Q2 | `tenantId`, `status`, sort `createdAt -1, _id -1` | `{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }` | Equality first, followed by stable result ordering |
| Q3 | `tenantId`, `customerId`, sort `createdAt -1, _id -1` | `{ tenantId: 1, customerId: 1, createdAt: -1, _id: -1 }` | History pagination scoped to customer and tenant |
| Q4 | `tenantId` + `_id` | Default `_id` index (plus tenant check in query) | Point lookup by ID, tenant scope enforced at application layer |
| Q5 | `tenantId`, `sku` | `{ tenantId: 1, sku: 1 }` **unique** on `products` | One unique SKU per tenant |
| Q6 | `tenantId`, `productId` | `{ tenantId: 1, productId: 1 }` **unique** on `inventory` | Targets exact document for stock updates |
| Q7 | `tenantId`, `lines.productId` | `{ tenantId: 1, "lines.productId": 1 }` if needed | Multikey index for finding orders containing a product; create only if frequency warrants |

There is no need to create the Q7 index immediately: if the report runs rarely, a separate analytics pipeline can be used instead of adding a multikey index that raises write costs on every order. With multiple queries on one collection, evaluate **index prefix reuse** and keep only indexes that truly serve the workload.

### Creating Indexes with `mongosh`

~~~javascript
db.orders.createIndex(
  { tenantId: 1, orderNumber: 1 },
  { unique: true, name: "uq_orders_tenant_number" }
);

db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1 },
  { name: "idx_orders_tenant_status_recent" }
);

db.orders.createIndex(
  { tenantId: 1, customerId: 1, createdAt: -1, _id: -1 },
  { name: "idx_orders_tenant_customer_recent" }
);

db.products.createIndex(
  { tenantId: 1, sku: 1 },
  { unique: true, name: "uq_products_tenant_sku" }
);

db.inventory.createIndex(
  { tenantId: 1, productId: 1 },
  { unique: true, name: "uq_inventory_tenant_product" }
);

// Only add when Q7 is genuinely needed:
db.orders.createIndex(
  { tenantId: 1, "lines.productId": 1 },
  { name: "idx_orders_tenant_line_product" }
);
~~~

Before creating unique indexes on existing data, check for and resolve **duplicates**; index creation will fail if the collection already violates the constraint. Index rollouts also need their own deployment process rather than relying entirely on auto-index creation when multiple Spring Boot pods start up. With `@Indexed` or `@CompoundIndex` on entities, verify your application's index-creation policy; in modern Spring Data MongoDB versions, automatic index creation is disabled by default.

### Creating Indexes via `MongoTemplate`

If managed in code, a migration step or controlled initialization task can use `IndexOperations`:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;

public final class OrderIndexMigration {
    private final MongoTemplate mongo;

    public OrderIndexMigration(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public void ensureIndexes() {
        mongo.indexOps("orders").ensureIndex(
            new Index()
                .on("tenantId", Sort.Direction.ASC)
                .on("orderNumber", Sort.Direction.ASC)
                .unique()
                .named("uq_orders_tenant_number")
        );

        mongo.indexOps("orders").ensureIndex(
            new Index()
                .on("tenantId", Sort.Direction.ASC)
                .on("status", Sort.Direction.ASC)
                .on("createdAt", Sort.Direction.DESC)
                .on("_id", Sort.Direction.DESC)
                .named("idx_orders_tenant_status_recent")
        );
    }
}
~~~

This snippet illustrates only **two indexes for `orders`**; the remaining indexes must be declared similarly upon implementation. In real projects, run versioned migrations once in the deployment pipeline or under designed coordination, checking existing indexes and duplicate data before applying changes. Never run expensive index initialization inside HTTP requests.

## 8. Verifying Queries Q1, Q2, and Q3 with Spring Data

With `MongoTemplate`, point query Q1 can use:

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class OrderLookupService {
    private final MongoTemplate mongo;

    public OrderLookupService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public OrderDocument findByBusinessNumber(String tenantId, String orderNumber) {
        Query q = Query.query(Criteria.where("tenantId").is(tenantId)
            .and("orderNumber").is(orderNumber));
        return mongo.findOne(q, OrderDocument.class, "orders");
    }
}
~~~

For Q2, offset pagination (`skip`) skips increasingly many results on deep pages. If the UI only needs "next page", try **keyset pagination** using `(createdAt, _id)` to guarantee a stable order when multiple orders share a timestamp:

~~~javascript
// First page
db.orders.find({ tenantId: "shop_01", status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(30);

// Next page: cursor is (createdAt, _id) of the last document from the previous page.
db.orders.find({
  tenantId: "shop_01",
  status: "PAID",
  $or: [
    { createdAt: { $lt: ISODate("2026-11-19T08:00:00Z") } },
    {
      createdAt: ISODate("2026-11-19T08:00:00Z"),
      _id: { $lt: "ord_01K8X6RJH5TWA9KAMV7Z" }
    }
  ]
}).sort({ createdAt: -1, _id: -1 }).limit(30);
~~~

The cursor must come from an actual previous page result, be bound to the active filter and sort, and be validated when passed via API. Concurrent insertions/deletions between pages can still shift the result set; clearly communicate pagination semantics to consumers. When `_id` is a string, `$lt` compares according to BSON string ordering (and collation); do not assume string ID order strictly reflects creation time. `_id` here acts solely as a **tie-breaker** when `createdAt` values are equal.

Q3 is similar to Q2, adding `customerId` to the equality condition and using `{ tenantId, customerId, createdAt, _id }`. When using repositories with long derived method names, verify the actual filter, sort, and projection sent to MongoDB—especially when `@Field`, `@Query`, or custom converters are involved.

## 9. Atomically Updating Inventory for Q6

A common bug is reading `available = 3`, checking sufficiency in Java, and then calling `save` after subtracting 2. Two concurrent requests can both read 3 and both believe the order is valid. For single-product inventory, move the **sufficient stock** condition into the update statement itself on that single document.

Example using `MongoTemplate.findAndModify`:

~~~java
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public class InventoryService {
    private final MongoTemplate mongo;

    public InventoryService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public InventoryDocument reserve(String tenantId, String productId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be greater than 0");
        }

        Query q = Query.query(Criteria.where("tenantId").is(tenantId)
            .and("productId").is(productId)
            .and("available").gte(quantity));

        Update u = new Update()
            .inc("available", -quantity)
            .inc("reserved", quantity);

        InventoryDocument after = mongo.findAndModify(
            q, u, FindAndModifyOptions.options().returnNew(true),
            InventoryDocument.class, "inventory");

        if (after == null) {
            throw new IllegalStateException("Inventory not found or insufficient stock");
        }
        return after;
    }
}
~~~

`InventoryDocument` maps the `inventory` collection from Section 4. `available` and `reserved` must be initialized with proper numeric types in MongoDB. Because the filter and `$inc` execute in the same document update operation, two competing requests cannot both pass `available >= quantity` against the same stale stock value.

**Limitation of this example:** this provides atomicity **for a single inventory document**. Placing a multi-product order while writing to `orders` and updating multiple `inventory` documents is a broader workflow. If the business requires all steps to succeed or fail together, you need a MongoDB transaction on a suitable replica set/sharded cluster, `MongoTransactionManager`, and careful retry/commit handling—or a well-designed compensating saga/reservation flow. Do not assume several consecutive `findAndModify` calls automatically form a transaction.

## 10. Consistency Rules and Reference Lifecycles

Splitting collections requires enforcing certain invariants at the application layer:

| Rule | Enforcement mechanism |
| --- | --- |
| Order contains only products from the same tenant | Query products by **both** `_id` and `tenantId` before snapshotting |
| Customer belongs to the right tenant | Verify `(tenantId, customerId)` within the same authorization context |
| No overselling | Atomic conditional update/transaction or compensating reservation workflow |
| `orderNumber` unique per tenant | Unique index `(tenantId, orderNumber)` as final backstop |
| Purchased price/name unaffected by catalog edits | Snapshot `nameAtPurchase` and `unitPriceMinor` in `lines` |
| Accurate totals | Validate `quantity > 0`, non-negative prices, consistent currency, integer/decimal math with overflow checks |
| No duplicate orders on request retry | Use `idempotencyKey` with a suitable unique index or stable request key, returning the previous result |
| Order history readable after product deletion | Retain snapshots in orders and define soft-delete policy for products |

`@DBRef` or `@DocumentReference` only describe reference retrieval mechanics; they **do not replace** unique indexes, tenant access checks, or transaction rules. If a customer is deleted for personal-data compliance, balance contact anonymization/deletion against transaction record retention duties; design minimal snapshots and appropriate retention policies.

### Partial, TTL, and Multikey Indexes: Using Each Properly

- **Partial index**: useful for optional fields, such as `externalOrderId` present on only some orders. A regular unique index on an optional field can behave unexpectedly with missing or `null` values; use a proper partial filter condition and test against historical data.
- **TTL index**: fits self-expiring data like sessions or temporary tokens, but should not be used casually on `orders` that require historical retention. TTL deletion does not occur at the exact expiration second; the system must still enforce expiration in business logic.
- **Multikey index**: created when indexing array fields, such as `lines.productId`. A document with many lines adds many index entries; review multikey limits and avoid creating them indiscriminately just for rare reports.
- **Collation**: queries and indexes with differing comparison/case rules can produce unexpected results or plans. Normalize `emailNormalized`/SKUs according to the data contract, and test actual collation settings if locale-aware comparison is needed.

## 11. Using `explain("executionStats")` to Verify Indexes

An index that looks right on paper can still underperform under real data distributions. After creating indexes and loading a test dataset, run `explain` for Q2:

~~~javascript
db.orders.find({ tenantId: "shop_01", status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(30)
  .explain("executionStats");
~~~

Metrics to record:

| Metric | What to inspect |
| --- | --- |
| `winningPlan` / `indexName` | Is `idx_orders_tenant_status_recent` or an appropriate index being used? |
| `COLLSCAN` / `IXSCAN` | Full collection scan or bounded index scan? |
| `SORT` | Is there an in-memory sort outside index order? |
| `nReturned` | Returned at most 30 documents as requested? |
| `totalKeysExamined` | Is the number of index keys traversed reasonable relative to results? |
| `totalDocsExamined` | Did it read excessively many documents just to return a few orders? |
| `executionTimeMillis` | Server execution time reported by `explain`; compare under equivalent conditions |

A healthy Q2 result typically scans a narrow index range on `(tenantId, status)` with `(createdAt, _id)` supporting the sort, though there is no absolute guarantee on key counts. MongoDB has multiple execution engines and plan shapes vary by version; do not assert by hardcoding a JSON path like `winningPlan.inputStage`.

Also test skewed tenant/status distributions and compare plans. Use `explain` to understand database-side cost, then measure Spring Data MongoDB API p95/p99 latency, impact on inserts/updates, index size, and system load. Adding an index solely because of one slow `explain` on a handful of test rows can slow writes down without delivering real benefit.

## 12. Verification Test Suite

Run tests against a real MongoDB test instance. For multi-document transactions, use a replica set or transaction-capable sharded cluster; standalone MongoDB is not equivalent.

| Test case | Data/condition | Expected outcome |
| --- | --- | --- |
| A. Unique per tenant | Two orders with `(shop_01, SO-01)` | Second write encounters duplicate key |
| B. Same code in different tenant | `(shop_01, SO-01)` and `(shop_02, SO-01)` | Both are created successfully |
| C. Product price changed | Create order then edit `products.currentPriceMinor` | Order snapshot retains price at placement time |
| D. Product deactivated | Product `active=false`, old order has snapshot | Order history remains readable; new orders reject inactive product |
| E. Bounded line items array | Submit order exceeding 100 lines | Application rejects per input rule; prevents unbounded document growth |
| F. Two requests reserving same stock | `available=3`, two concurrent requests for 2 items | Only one request succeeds in reserving stock |
| G. Multi-document update failure | One item runs out of stock mid-checkout | Transaction rolls back or compensation preserves invariants per chosen architecture |
| H. Query Q2 pagination | Multiple orders with identical `createdAt` | No skipped or duplicated records due to unstable ordering on static data |
| I. Cross-tenant isolation | Request `orderId` of another tenant | Cannot read cross-tenant order under user permissions |
| J. Performance | Many orders, skewed tenant/status distribution | `explain` uses a helpful index; no excessive scanning/sorting |

Beyond happy-path data checks, test **write failures**: unique index exceptions, timeout after successful write before client receives response, retries of stale requests, and concurrent update errors. If using `@Version`, verify that a document whose version has changed cannot be overwritten via Spring Data-managed `save`.

## 13. Common Pitfalls in This Exercise

| Pitfall | Consequence | Better design |
| --- | --- | --- |
| Embedding all orders into `customers.orders[]` | Unbounded array growth, huge documents, costly updates/queries | Separate `orders` collection indexed by `tenantId`/`customerId` |
| Storing only `productId` in `OrderLine` and reading current price | Historical prices change whenever product price changes | Embed name/price snapshot at purchase time |
| Copying the whole product into every order | Bloat, leaks unnecessary fields, hard to protect data | Minimal snapshot serving receipts and order fulfillment |
| Using `orderNumber` as `_id` when only unique per tenant | Cross-tenant collisions or brittle key encoding | Separate `_id`; unique index `(tenantId, orderNumber)` |
| Querying only by `_id` without tenant check | Risk of leaking data across stores | Enforce tenant predicate in queries or verified authorization boundary |
| Adding single-field indexes hoping sorts stay fast | MongoDB may still scan broadly or sort in memory | Design compound indexes matching real filters + sorts |
| Reading stock in Java then calling `save` | Lost updates / overselling under contention | Atomic conditional update or appropriate transaction |
| Creating unique index on already-duplicated data | Index creation fails | Inspect and deduplicate data, then deploy versioned index |

## 14. Capstone Completion Checklist

Before considering the design complete, verify:

1. Every collection has a **reason to exist** grounded in lifecycle and read/write frequency; embedded arrays are bounded and safe from document growth limits.
2. Every reference defines **tenant scope**, existence validation, and a policy for when the target document is deleted or updated.
3. `_id` has a stable BSON type; business codes and natural keys are protected by unique indexes where needed.
4. Every index maps to one or more **concrete query shapes**, including filter predicates, sort, projection, collation, and call frequency.
5. `orders` keep product name/price snapshots; catalog updates do not alter historical orders.
6. Inventory updates use atomic conditions; multi-product/multi-document workflows have a clearly chosen consistency mechanism.
7. Queries through `MongoTemplate` or repositories are verified against real BSON, tested with `explain("executionStats")`, and benchmarked appropriately.
8. The test suite verifies uniqueness constraints, cross-tenant isolation, pagination, concurrency, retry/idempotency, and legacy data readability.

**The outcome of this practice** is not a diagram with the most collections or the most indexes. A good design is one where every embed, reference, ID, and index can be justified by **the queries it serves, its consistency rules, and its operational cost**. When assumptions about line counts, tenant counts, read/write ratios, or reporting change, re-measure and adapt the model rather than treating the initial structure as immutable.
