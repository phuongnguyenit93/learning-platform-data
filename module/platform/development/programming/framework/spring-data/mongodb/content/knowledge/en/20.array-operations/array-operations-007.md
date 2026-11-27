# Array Filters with $[identifier] and filterArray

## 1. Objectives and Business Problem

A MongoDB order can contain an `items` array with multiple line items. When a staff member adjusts the quantity of SKU `BOOK-A`, the application needs to update **only the matching elements**, without replacing the entire array, affecting other SKUs, or relying on a fixed array index. MongoDB provides the **filtered positional operator** `$[identifier]` paired with the **`arrayFilters`** option to do this.

In Spring Data MongoDB, the `Update` class provides `filterArray(...)` methods to include element-selection predicates in write commands via `MongoOperations`/`MongoTemplate`. This topic belongs to the **Array Operations** chapter of the **SPRING_DATA_MONGODB** module: using Spring Data MongoDB to connect, map documents, and operate via templates or repositories; designing queries, aggregations, indexes, transactions, reactive access, testing, and data performance diagnostics.

After this lesson, you will be able to:

1. Distinguish `$`, `$[]`, `$[identifier]`, and `$elemMatch` by **read/filter/update role**.
2. Write `updateOne`/`updateMany` with `arrayFilters` to select the exact elements inside document arrays.
3. Use Spring Data's `Update.filterArray(...)` and know where to use **Java property names** versus **BSON field names**.
4. Handle multiple matching elements, multiple identifiers, nested arrays, and documents lacking valid arrays.
5. Interpret `matchedCount`/`modifiedCount` and enforce tenant, status, and concurrency guards in write filters.
6. Write integration tests and evaluate indexes, syntax errors, and MongoDB version support.

**Key takeaway:** The filter in `Query` selects **which documents** to update; the filter in `arrayFilters` selects **which elements inside the array** of those documents to modify. These two condition layers are not interchangeable.

## 2. Preparing Sample Data

### 2.1. BSON Documents

Examples use a test `orders` collection:

```javascript
db.orders.insertMany([
  {
    _id: "ord-001",
    tenantId: "tenant-a",
    status: "READY_TO_SHIP",
    items: [
      { sku_code: "BOOK-A", quantity: 1, state: "NEW", priceVnd: NumberLong("90000") },
      { sku_code: "BOOK-B", quantity: 4, state: "NEW", priceVnd: NumberLong("60000") }
    ],
    updatedAt: ISODate("2026-11-19T08:00:00Z")
  },
  {
    _id: "ord-002",
    tenantId: "tenant-a",
    status: "READY_TO_SHIP",
    items: [
      { sku_code: "BOOK-A", quantity: 2, state: "NEW", priceVnd: NumberLong("90000") },
      { sku_code: "BOOK-A", quantity: 3, state: "NEW", priceVnd: NumberLong("90000") },
      { sku_code: "BOOK-C", quantity: 1, state: "NEW", priceVnd: NumberLong("75000") }
    ],
    updatedAt: ISODate("2026-11-19T09:00:00Z")
  },
  {
    _id: "ord-003",
    tenantId: "tenant-a",
    status: "CANCELLED",
    items: [],
    updatedAt: ISODate("2026-11-19T10:00:00Z")
  },
  {
    _id: "ord-004",
    tenantId: "tenant-b",
    status: "READY_TO_SHIP",
    items: [
      { sku_code: "BOOK-A", quantity: 7, state: "NEW", priceVnd: NumberLong("90000") }
    ],
    updatedAt: ISODate("2026-11-19T11:00:00Z")
  }
]);
```

These IDs and values are strictly for a practice database. Avoid running `insertMany` verbatim against real data or collections that already contain duplicate IDs.

```text
ord-001  (tenant-a, READY_TO_SHIP)
└── items
    ├── [0] sku=BOOK-A, quantity=1, state=NEW
    └── [1] sku=BOOK-B, quantity=4, state=NEW

ord-002  (tenant-a, READY_TO_SHIP)
└── items
    ├── [0] sku=BOOK-A, quantity=2, state=NEW
    ├── [1] sku=BOOK-A, quantity=3, state=NEW
    └── [2] sku=BOOK-C, quantity=1, state=NEW
```

We intentionally placed **two BOOK-A lines inside `ord-002`** to verify an important point: `$[identifier]` can modify **multiple elements** satisfying the filter, not always just one element.

### 2.2. Java Model with @Field BSON Renaming

```java
import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders")
public record OrderDocument(
    @MongoId(FieldType.STRING) String id,
    String tenantId,
    String status,
    List<OrderLine> items,
    Instant updatedAt
) {}

record OrderLine(
    @Field("sku_code") String sku,
    int quantity,
    String state,
    long priceVnd
) {}
```

| Concept | Java Property Name | BSON Field |
| --- | --- | --- |
| Order identifier | `id` | `_id` |
| Line-item array | `items` | `items` |
| Line SKU | `items.sku` | `items.sku_code` |
| Line quantity | `items.quantity` | `items.quantity` |
| Line state | `items.state` | `items.state` |

The purpose of `@Field("sku_code")` is to create a realistic example of a common pitfall: `arrayFilters` follows different mapping rules than a domain-typed `Query`.

## 3. Distinguishing Four Commonly Confused Syntaxes

| Syntax | Where Used? | Meaning |
| --- | --- | --- |
| `$elemMatch` | Query filter or supported projection | Requires **the same element** of an array to satisfy multiple conditions |
| `$` | Positional update path | References the first element matching the query's array condition in supported cases |
| `$[]` | All-positional update path | Updates **every element** of the targeted array |
| `$[line]` | Filtered positional update path | Updates **every element matching `arrayFilters` for `line`** |

Examples updating the `quantity` field:

```javascript
// (A) One element identified by positional $ and the query filter.
db.orders.updateOne(
  { _id: "ord-001", "items.sku_code": "BOOK-A" },
  { $set: { "items.$.quantity": 5 } }
);

// (B) Every element of items, regardless of SKU.
db.orders.updateOne(
  { _id: "ord-001" },
  { $set: { "items.$[].quantity": 5 } }
);

// (C) Every element with SKU BOOK-A.
db.orders.updateOne(
  { _id: "ord-001" },
  { $set: { "items.$[line].quantity": 5 } },
  { arrayFilters: [{ "line.sku_code": "BOOK-A" }] }
);
```

These three commands show **three alternatives**, not a sequence to run back-to-back if you want to observe each operator's individual effect. Reset the fixture or run each command on an isolated copy.

### 3.1. $elemMatch Does Not Update Automatically

```javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku_code: "BOOK-A",
      quantity: { $gte: 2 }
    }
  }
});
```

This command **only reads/filters documents**. It modifies no line items. When you need to update all matching lines, put that predicate into `arrayFilters` and use `$[line]` in the update path.

### 3.2. Why Is $[] Too Broad?

If the business requirement is “update only BOOK-A”, `"items.$[].quantity"` will also modify `BOOK-B` and `BOOK-C`. It is only right when a change applies to **all** elements, such as setting a uniform flag. Never pick `$[]` simply because its syntax is shorter.

### 3.3. $ Is Not $[line]

Filtered positional `$[line]` does not mean “select the first element named line”. `line` is a **developer-chosen label** bound to conditions in `arrayFilters`; every element matching the condition in the selected document can be affected.

## 4. Full Structure of $[identifier] and arrayFilters

A typical command has three parts:

```javascript
db.orders.updateOne(
  // 1. Select documents.
  {
    _id: "ord-002",
    tenantId: "tenant-a",
    status: "READY_TO_SHIP"
  },
  // 2. Specify the field to update in each matching element.
  {
    $set: {
      "items.$[line].quantity": 6
    }
  },
  // 3. Select which elements bind to identifier "line".
  {
    arrayFilters: [
      { "line.sku_code": "BOOK-A" }
    ]
  }
);
```

Result on `ord-002`:

```javascript
items: [
  { sku_code: "BOOK-A", quantity: 6, state: "NEW", priceVnd: NumberLong("90000") },
  { sku_code: "BOOK-A", quantity: 6, state: "NEW", priceVnd: NumberLong("90000") },
  { sku_code: "BOOK-C", quantity: 1, state: "NEW", priceVnd: NumberLong("75000") }
]
```

The command updates **both BOOK-A elements** and leaves `BOOK-C` untouched. For a single-document update, changes within the document are processed atomically by MongoDB.

### 4.1. Identifier Is an Update Command Variable

In `"items.$[line].quantity"`, `line` is not a BSON field. It is a variable name bound to a filter object containing `line.sku_code`.

A valid identifier must start with a **lowercase letter** and contain only alphanumeric characters per MongoDB rules; pick simple names like `line`, `item`, `row2`. Avoid colliding with `sku_code`, and avoid accents, spaces, or hyphens in identifiers.

Each distinct identifier used in the update must have a matching array filter condition. Do not declare two separate filter documents for the same identifier expecting the server to merge them: combine conditions into **one** filter document.

### 4.2. One Filter Document with Multiple Predicates

```javascript
db.orders.updateOne(
  { _id: "ord-002", tenantId: "tenant-a" },
  {
    $set: { "items.$[line].state": "CHECKED" }
  },
  {
    arrayFilters: [
      {
        "line.sku_code": "BOOK-A",
        "line.quantity": { $gte: 3 }
      }
    ]
  }
);
```

On the original `ord-002`, only the `BOOK-A` line with quantity 3 satisfies both conditions; the BOOK-A line with quantity 2 does not. If you already ran the earlier example setting quantity to 6, results will differ. Re-seed independent examples before comparing.

### 4.3. Syntax Rules and Limitations

- `$[line]` must have a filter for `line` in `arrayFilters`; otherwise the server reports an undefined identifier error.
- The identifier is not the name of the array field; the path on the left must still be `items` or the real BSON path.
- Restricted query operators such as `$expr`, `$text`, and `$where` cannot be used inside `arrayFilters`.
- Each identifier has one filter document; valid `$and`/`$or` expressions can be used inside that filter when needed.
- The outer filter of `updateOne` and `arrayFilters` serve **separate purposes**; identifiers do not automatically enforce tenant isolation or business status checks.

With older MongoDB deployments, verify array-filter support: filtered positional updates were introduced in MongoDB **3.6**. In projects using legacy Spring Data or driver versions, the convenience method `Update.filterArray(...)` might not exist; do not assume server support guarantees availability in every Java API version.

## 5. Document Filters and Element Filters Must Be Designed Together

A common mistake is focusing solely on `arrayFilters` and neglecting document scope.

### 5.1. Query Selects Orders, arrayFilters Selects Lines

```javascript
db.orders.updateMany(
  {
    tenantId: "tenant-a",
    status: "READY_TO_SHIP"
  },
  {
    $set: { "items.$[line].state": "RESERVED" }
  },
  {
    arrayFilters: [
      { "line.sku_code": "BOOK-A" }
    ]
  }
);
```

This command selects `tenant-a` orders in `READY_TO_SHIP` status and sets the state of BOOK-A lines across **each matching order**. It does not touch `ord-004` of tenant-b even though `ord-004` also contains BOOK-A.

If the document filter is too broad:

```javascript
// INAPPROPRIATE for an operation that must affect only one tenant.
db.orders.updateMany(
  { status: "READY_TO_SHIP" },
  { $set: { "items.$[line].state": "RESERVED" } },
  { arrayFilters: [{ "line.sku_code": "BOOK-A" }] }
);
```

arrayFilters **cannot enforce tenant boundaries**. Authorization and invariants belong in the application service and document-selection query.

### 5.2. MatchedCount Is Not Modified Array Element Count

When updating `ord-002` with two BOOK-A lines:

```javascript
const result = db.orders.updateOne(
  { _id: "ord-002", tenantId: "tenant-a" },
  { $set: { "items.$[line].state": "CHECKED" } },
  { arrayFilters: [{ "line.sku_code": "BOOK-A" }] }
);

printjson(result);
```

Normally `matchedCount` is the **number of documents** matching the filter, and `modifiedCount` is the **number of documents actually modified**. Even when two lines in the same document change, `modifiedCount` is still 1. The write result does not report how many array elements changed.

When a document matches yet no line satisfies the array filter, the operation returns `matchedCount=1` and `modifiedCount=0`. Therefore:

- `matchedCount=0`: no document matched the outer filter.
- `matchedCount=1`, `modifiedCount=0`: a document matched, yet the update was a no-op, no element matched, or the new value equaled the old value.
- `modifiedCount=1`: a document changed, not necessarily exactly one array element.

If exact element counts are needed for reporting, design before/after reads or dedicated calculations and clarify consistency/concurrency requirements; never infer element counts from `UpdateResult.getModifiedCount()`.

### 5.3. Requiring a Matching Line in the Outer Query

You can add `$elemMatch` so the outer filter only matches documents containing an eligible element:

```javascript
db.orders.updateOne(
  {
    _id: "ord-002",
    tenantId: "tenant-a",
    items: { $elemMatch: { sku_code: "BOOK-A", state: "NEW" } }
  },
  { $set: { "items.$[line].state": "RESERVED" } },
  {
    arrayFilters: [
      { "line.sku_code": "BOOK-A", "line.state": "NEW" }
    ]
  }
);
```

The outer filter decides whether the document meets prerequisites; the array filter must still carry the full conditions so only the right lines change. If an order contains both a `NEW` BOOK-A element and a `DONE` BOOK-A element, do not filter only by `sku_code` inside `arrayFilters` and accidentally overwrite the DONE line.

## 6. Spring Data: Basic Update.filterArray(...)

### 6.1. MongoOperations and MongoTemplate

Service example using `MongoOperations` rather than coupling directly to the concrete implementation:

```java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;

@Service
public class OrderLineCommandService {
    private final MongoOperations mongo;

    public OrderLineCommandService(MongoOperations mongo) {
        this.mongo = mongo;
    }

    public UpdateResult setQuantityForSku(
        String authenticatedTenantId,
        String orderId,
        String sku,
        int quantity
    ) {
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || orderId == null || orderId.isBlank()
                || sku == null || sku.isBlank()
                || quantity <= 0) {
            throw new IllegalArgumentException("Invalid input");
        }

        Query query = Query.query(
            Criteria.where("id").is(orderId)
                .and("tenantId").is(authenticatedTenantId)
                .and("status").is("READY_TO_SHIP")
        );

        Update update = new Update()
            .set("items.$[line].quantity", quantity)
            .filterArray(
                Criteria.where("line.sku_code").is(sku)
            );

        return mongo.updateFirst(query, update, OrderDocument.class);
    }
}
```

`MongoTemplate` is typically the implementation behind `MongoOperations`. In this example, `authenticatedTenantId` must come from an authenticated context, never trusting an unverified client-supplied tenantId.

### 6.2. Why Does filterArray Use line.sku_code Instead of line.sku?

This is the easiest mistake to make when using `@Field`. Spring Data supports entity-metadata mapping for queries and updates, yet **array filter expressions are forwarded to the driver without undergoing the same field/type mapping** as ordinary queries.

Thus:

```java
Update correct = new Update()
    .set("items.$[line].quantity", 5)
    .filterArray(Criteria.where("line.sku_code").is("BOOK-A"));

// PRONE TO FAIL if the entity renames Java property sku -> BSON sku_code.
Update wrong = new Update()
    .set("items.$[line].quantity", 5)
    .filterArray(Criteria.where("line.sku").is("BOOK-A"));
```

Inside the array filter, `line.sku_code` uses the **actual stored field name**. `line` is an identifier, not a Java entity for which Spring Data resolves `@Field("sku_code")`.

**Rule of thumb:** record and verify the **physical BSON** before writing `arrayFilters`, especially when custom converters, enums, ObjectIds, UUIDs, Dates, nested aliases, or external service writers are involved.

### 6.3. Query Mapping vs. Array Filter Mapping

Example:

```java
Query query = Query.query(
    Criteria.where("id").is("ord-001")
        .and("items.sku").is("BOOK-A")
);

Update update = new Update()
    .set("items.$[line].quantity", 5)
    .filterArray(Criteria.where("line.sku_code").is("BOOK-A"));
```

With `OrderDocument.class`, Spring Data maps:

| Component | Developer Supplies | Expected BSON |
| --- | --- | --- |
| Query on ID | `id` | `_id` |
| Query on SKU | `items.sku` | `items.sku_code` |
| Update path | `items.$[line].quantity` | `items.$[line].quantity` |
| Array filter | `line.sku_code` | `line.sku_code` |

Do not rely on `Update.toString()` or `Query.getQueryObject()` as complete proof of final mapping. Use integration tests or command monitoring to inspect the BSON actually sent by your exact Spring Data version.

### 6.4. Single Filter with Multiple Predicates

```java
Update update = new Update()
    .set("items.$[line].state", "CHECKED")
    .filterArray(
        Criteria.where("line.sku_code").is("BOOK-A")
            .and("line.quantity").gte(3)
            .and("line.state").is("NEW")
    );
```

All conditions above must hold **on the same array element**. For more complex logic, you can use `Criteria` with `andOperator`/`orOperator`, while ensuring the resulting BSON array filter is valid and the identifier is properly defined.

## 7. Two Ways to Supply filterArray and Managing BSON Expressions

Spring Data MongoDB versions supporting filtered positional updates offer `Update.filterArray(...)` overloads, including:

```java
// Pass a full CriteriaDefinition containing the prefixed identifier name.
Update byCriteria = new Update()
    .set("items.$[line].state", "RESERVED")
    .filterArray(
        Criteria.where("line.sku_code").is("BOOK-A")
    );
```

Another overload in supporting versions accepts **identifier and expression** separately; check the exact signature and serialization behavior of your library version. Do not assume an unprefixed `Criteria.where("sku")` will automatically map to `line.sku_code`.

### 7.1. When You Want Direct BSON Control

With the MongoDB Java driver, you can pass `arrayFilters` via `UpdateOptions`:

```java
import java.util.List;
import org.bson.Document;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.UpdateOptions;

MongoCollection<Document> collection =
    database.getCollection("orders");

collection.updateOne(
    new Document("_id", "ord-001")
        .append("tenantId", "tenant-a"),
    new Document("$set",
        new Document("items.$[line].state", "RESERVED")),
    new UpdateOptions().arrayFilters(
        List.of(new Document("line.sku_code", "BOOK-A"))
    )
);
```

Here `database` is a preconfigured `MongoDatabase` in the application; this snippet illustrates the driver layer, not creating a new MongoClient per request. The driver takes BSON names such as `_id` and `sku_code` and has no knowledge of `@Field`.

**Choosing the right tool:** prefer `MongoOperations` when already using Spring Data domain mapping. Drop to the driver API only for specific needs, as you then take direct responsibility for mapping, validation, sessions, callbacks, and consistency settings.

## 8. UpdateFirst vs. UpdateMulti Differ at the Document Level

### 8.1. updateFirst

```java
Query query = Query.query(
    Criteria.where("id").is("ord-001")
        .and("tenantId").is("tenant-a")
);

Update update = new Update()
    .set("items.$[line].state", "CHECKED")
    .filterArray(Criteria.where("line.sku_code").is("BOOK-A"));

var result = mongo.updateFirst(query, update, OrderDocument.class);
```

`updateFirst` selects **at most one document**. Inside that document, `$[line]` can still modify **multiple array elements**. Never confuse “first document” with “first element”.

### 8.2. updateMulti

```java
Query query = Query.query(
    Criteria.where("tenantId").is("tenant-a")
        .and("status").is("READY_TO_SHIP")
);

Update update = new Update()
    .set("items.$[line].state", "CHECKED")
    .filterArray(Criteria.where("line.sku_code").is("BOOK-A"));

var result = mongo.updateMulti(query, update, OrderDocument.class);
```

`updateMulti` can modify BOOK-A elements across **many matching documents**. `modifiedCount` is still reported **per document**.

| Question | `updateFirst` | `updateMulti` |
| --- | --- | --- |
| Maximum documents updated? | One | Many |
| Elements updated per document? | Many if multiple match the filter | Many if multiple match the filter |
| Atomicity across all updated documents? | Atomic for the single document written | Does not form a single transaction across documents |
| Needs tenant/status constraints? | Yes | Yes, critically important |
| Returns modified element count? | Not directly from UpdateResult | Not directly from UpdateResult |

### 8.3. Choosing the Exact Update Scope

If the requirement is “modify one line item of an order”, yet the schema permits two lines with the same SKU, `$[line]` filtering only by SKU will **modify both**. To target a single logical line, store a stable unique `lineId` in the array and filter by `line.lineId`.

```javascript
db.orders.updateOne(
  { _id: "ord-002", tenantId: "tenant-a" },
  { $set: { "items.$[line].quantity": 5 } },
  { arrayFilters: [{ "line.lineId": "line-002-b" }] }
);
```

This example **requires the schema to have `lineId`**; the dataset in section 2 does not include that field yet. If `lineId` must be unique within the array, enforce dedicated validation/logic: a unique multikey index should not be relied upon to guarantee distinct values across elements within a single document in all designs.

## 9. Updates with Multiple Filtered Identifiers

A shipment can contain multiple batches, each containing multiple packages. Consider a separate document:

```javascript
db.shipments.insertOne({
  _id: "shipment-001",
  tenantId: "tenant-a",
  batches: [
    {
      batchCode: "B1",
      packages: [
        { packageCode: "P1", state: "WAITING" },
        { packageCode: "P2", state: "WAITING" }
      ]
    },
    {
      batchCode: "B2",
      packages: [
        { packageCode: "P1", state: "WAITING" },
        { packageCode: "P3", state: "WAITING" }
      ]
    }
  ]
});
```

Requirement: update only package P1 inside batch B2:

```javascript
db.shipments.updateOne(
  { _id: "shipment-001", tenantId: "tenant-a" },
  {
    $set: {
      "batches.$[batch].packages.$[pkg].state": "READY"
    }
  },
  {
    arrayFilters: [
      { "batch.batchCode": "B2" },
      { "pkg.packageCode": "P1" }
    ]
  }
);
```

Two independent identifiers:

- `batch` selects elements in the `batches` array.
- `pkg` selects elements in the `packages` array inside the matched batches.

The command leaves P1 in batch B1 untouched. Updating nested multi-level arrays cleanly is a major benefit of the filtered positional operator over relying on a single positional slot.

### 9.1. Spring Data with Two Identifiers

```java
Update update = new Update()
    .set("batches.$[batch].packages.$[pkg].state", "READY")
    .filterArray(Criteria.where("batch.batchCode").is("B2"))
    .filterArray(Criteria.where("pkg.packageCode").is("P1"));
```

This snippet illustrates the `Update` structure. To execute it against `ShipmentDocument.class`, define the matching entity mapping and tenant/ID query; do not reuse `OrderDocument.class` from the earlier example to update the `shipments` collection.

### 9.2. Multiple Identifiers vs. Multiple Predicates for the Same Identifier

```javascript
// Clear approach: one filter document for "line" holding all predicates.
arrayFilters: [
  {
    "line.sku_code": "BOOK-A",
    "line.quantity": { $gte: 2 }
  }
]
```

Do not declare two separate entries with the same identifier name:

```javascript
// Not valid syntax for combining predicates with AND:
arrayFilters: [
  { "line.sku_code": "BOOK-A" },
  { "line.quantity": { $gte: 2 } }
]
```

In the invalid pattern, identifier `line` is defined multiple times. For predicates targeting the same identifier, combine them inside one filter object or valid logical expression.

## 10. Arithmetic Conditions on Elements: Incrementing, Bounds, and Invariants

### 10.1. $inc on Matching Elements

Example incrementing quantity of BOOK-A lines:

```javascript
db.orders.updateOne(
  { _id: "ord-002", tenantId: "tenant-a" },
  { $inc: { "items.$[line].quantity": 1 } },
  { arrayFilters: [{ "line.sku_code": "BOOK-A" }] }
);
```

If there are two BOOK-A lines, **both** increment by 1. Retrying this command will increment again. Thus `$inc` fits true additive changes, yet is not idempotent if the same command is re-executed unconditionally.

In Spring Data:

```java
Update update = new Update()
    .inc("items.$[line].quantity", 1)
    .filterArray(
        Criteria.where("line.sku_code").is("BOOK-A")
    );
```

### 10.2. Do Not Set Arbitrary Quantities Without Business Constraints

If quantity must stay between 1 and 100, input validation is necessary but **not sufficient** when rules also depend on current value, stock, or line state. Add constraints to the array filter when needed:

```javascript
db.orders.updateOne(
  {
    _id: "ord-002",
    tenantId: "tenant-a",
    status: "READY_TO_SHIP",
    items: {
      $elemMatch: {
        sku_code: "BOOK-A",
        state: "NEW",
        quantity: { $lte: 10 }
      }
    }
  },
  {
    $set: { "items.$[line].state": "RESERVED" }
  },
  {
    arrayFilters: [
      {
        "line.sku_code": "BOOK-A",
        "line.state": "NEW",
        "line.quantity": { $lte: 10 }
      }
    ]
  }
);
```

The outer filter checks “at least one eligible line exists”. The filter in `arrayFilters` restricts **each modified line**. Putting the quantity check only in the outer filter could still update another line in the same array that violates the threshold.

### 10.3. An Atomic Command Does Not Enforce Every Invariant Automatically

Single-document updates are atomic, yet MongoDB does not automatically know that:

- Sum of `quantity * priceVnd` must equal a total field elsewhere.
- Two lines may not share the same SKU if prohibited by business rules.
- `DONE` lines may never be edited.
- Inventory in another collection must decrement in the same transaction.

If updating an element requires updating an order total, add operators on the same document, check concurrency, or redesign to keep totals from going stale. For cross-collection invariants, consider transactions suited to your topology and workflow.

## 11. Missing Arrays, Null, and Objects Instead of Arrays

Filtered positional updates **require a valid array along the update path**. Malformed documents such as these can fail or find no elements to update:

```javascript
{ _id: "bad-001", tenantId: "tenant-a" }

{ _id: "bad-002", tenantId: "tenant-a", items: null }

{ _id: "bad-003", tenantId: "tenant-a", items: { sku_code: "BOOK-A" } }

{ _id: "empty-001", tenantId: "tenant-a", items: [] }
```

These cases are **not equivalent**:

| Data | Issue |
| --- | --- |
| Missing `items` | No array to traverse |
| `items: null` | Field exists, but is not an array |
| `items: {...}` | Wrong BSON type relative to expected schema |
| `items: []` | Valid array, zero matching elements |
| `items: [{ sku_code: "BOOK-B" }]` | Valid array, does not match BOOK-A filter |

### 11.1. Auditing Data Before Bulk Updates

```javascript
// Documents where items is a valid BSON array.
db.orders.find({
  tenantId: "tenant-a",
  items: { $type: "array" }
});

// Documents missing items.
db.orders.find({
  tenantId: "tenant-a",
  items: { $exists: false }
});

// Documents with BSON Null.
db.orders.find({
  tenantId: "tenant-a",
  items: { $type: "null" }
});
```

Adding type predicates to queries when necessary filters out malformed documents, yet **does not replace migration**. If a document requires `items` and stores an object or Null instead, find the bug's source and repair the data per the approved contract.

### 11.2. When You Need to Add a New Element

`$[line]` **does not create a BOOK-A element** if the array does not contain BOOK-A yet. To add an element, use `$push`/`$addToSet` or dedicated business logic, then enforce uniqueness and validation.

Never use filtered positional updates to “create a missing element” — that is not what the operator does.

## 12. Avoiding Inappropriate Upserts with $[identifier]

A command to “update a line item on an existing order” should normally use `updateFirst` **without upsert**. Enabling upsert can attempt to insert a new document while the filtered positional path requires an existing array.

### 12.1. Rule When Upsert Must Use arrayFilters

MongoDB imposes a specific restriction: if an operation using `$[identifier]` hits the **upsert insert branch**, the query must contain an **exact equality match** on the corresponding array field; otherwise the server can reject the command because there is no array path to update.

This pattern is **error-prone** and should not be used to edit orders:

```javascript
db.orders.updateOne(
  { _id: "ord-missing" },
  { $set: { "items.$[line].quantity": 5 } },
  {
    upsert: true,
    arrayFilters: [{ "line.sku_code": "BOOK-A" }]
  }
);
```

In normal workflows, keep these separate:

- **Creating a new order:** insert a document with a schema-valid `items` array.
- **Editing a line item:** update an existing document with `$[line]`.
- **Adding a line item:** use validated element-insertion logic, not filtered positional updates.

### 12.2. State Transitions Should Not Upsert

If an order is cancelled or missing, “mark line item RESERVED” should return a non-matching result, **not create a new order**. Keeping status checks in the document filter and **disabling upsert** accurately expresses the business contract.

## 13. Optimistic Locking, Versions, and Concurrency

### 13.1. Why Can Updates Overwrite Each Other?

Two workers read BOOK-A with quantity 2; one tries to set it to 3 and the other to 5. If both execute:

```javascript
{ $set: { "items.$[line].quantity": newValue } }
```

with `arrayFilters` matching only by SKU, the final value will simply be whichever ran last. Single-document atomicity **does not prevent business-level lost updates**.

### 13.2. Using Expected Version in the Document Filter

One way to guard against this is adding `version` to the document, checking it, and incrementing it in the same update:

```javascript
db.orders.updateOne(
  {
    _id: "ord-001",
    tenantId: "tenant-a",
    version: NumberLong("7"),
    status: "READY_TO_SHIP"
  },
  {
    $set: {
      "items.$[line].quantity": 5,
      updatedAt: new Date()
    },
    $inc: { version: NumberLong("1") }
  },
  {
    arrayFilters: [
      { "line.sku_code": "BOOK-A", "line.state": "NEW" }
    ]
  }
);
```

With a versioned schema and matching policy, only one update targeting version 7 wins; the other fails to match after version increments. Note that this illustrates an **extended schema**: the fixture in section 2 does not include `version` yet.

When using `@Version` in Spring Data, check how your update path behaves; never assume every `MongoTemplate.updateFirst(...)` call automatically checks the Java entity's version without explicit predicates or design.

### 13.3. Transitioning a Line State Using Expected State

An alternative when no document-wide version is used:

```java
Query query = Query.query(
    Criteria.where("id").is(orderId)
        .and("tenantId").is(authenticatedTenantId)
        .and("status").is("READY_TO_SHIP")
        .and("items").elemMatch(
            Criteria.where("sku").is(sku)
                .and("state").is("NEW")
        )
);

Update update = new Update()
    .set("items.$[line].state", "RESERVED")
    .filterArray(
        Criteria.where("line.sku_code").is(sku)
            .and("line.state").is("NEW")
    );

var result = mongo.updateFirst(
    query, update, OrderDocument.class
);
```

Both outer and inner filters check the expected state. To distinguish a *single logical line* when duplicate SKUs exist, use a unique `lineId` instead of SKU.

## 14. Indexes and Performance for Array Element Updates

### 14.1. Indexes Help Select Documents, Not Elements

The outer query must locate documents quickly. When updating a single order by `_id + tenantId`, the default `_id` index is often already sufficient to locate the document and verify tenant; do not create compound indexes mechanically.

For bulk updates by tenant/status/SKU:

```javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, "items.sku_code": 1 },
  { name: "ix_orders_tenant_status_item_sku" }
);
```

This is a candidate index for document filters containing `items.sku_code`. Because the field is inside an array, the index is **multikey**, adding write maintenance overhead when array elements change. Array filters do not turn into standalone index lookups: the server still inspects elements inside each matched document.

### 14.2. Should You Add SKU to the Outer Filter?

```javascript
db.orders.updateMany(
  {
    tenantId: "tenant-a",
    status: "READY_TO_SHIP",
    "items.sku_code": "BOOK-A"
  },
  { $set: { "items.$[line].state": "CHECKED" } },
  { arrayFilters: [{ "line.sku_code": "BOOK-A" }] }
);
```

Including `items.sku_code` in the outer filter lets an index select only relevant documents and skip orders lacking that SKU altogether. However, **`arrayFilters` is still required** to restrict which elements are written; the outer filter does not replace the inner filter.

### 14.3. explain: Measure the Filter First, Then Measure Writes

```javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "READY_TO_SHIP",
  "items.sku_code": "BOOK-A"
}).explain("executionStats");
```

Examine `winningPlan`, `IXSCAN`/`COLLSCAN`, `totalKeysExamined`, and `totalDocsExamined`. This evaluates the cost of finding **documents**, **not** the full cost of array updates (BSON rewrites, index updates, replication, locking, or document size).

Real measurement should distinguish:

| Scenario | What to Observe |
| --- | --- |
| One document, one element | Latency and modifiedCount |
| One document, many elements | In-document update cost |
| Many documents, updateMulti | Docs scanned, write throughput, replication load |
| Very long arrays | Document size, element count, processing time |
| Multikey indexes present | Index maintenance when modifying indexed fields |
| Concurrent updates | Contention, write conflicts/retries |

MongoDB has a **16 MiB** BSON document limit. If arrays grow unbounded, extract elements into a separate collection rather than pushing massive documents through `arrayFilters`.

## 15. Modifying Fields with @Field and Converters: Inspect Final BSON

### 15.1. Array Filters and Property Aliases

`OrderLine.sku` is stored as `sku_code`:

```java
@Field("sku_code")
String sku;
```

Expressions at different layers:

```java
// Query: uses entity mapping when executed with OrderDocument.class.
Criteria.where("items.sku").is("BOOK-A");

// Update quantity field: BSON and Java names match here.
new Update().set("items.$[line].quantity", 5);

// Array filter: forwarded to driver, uses actual BSON name.
Criteria.where("line.sku_code").is("BOOK-A");
```

With complex types such as `ObjectId`, `UUID`, or custom-converted enums, be extra careful: predicates inside `arrayFilters` do not automatically benefit from every conversion in `QueryMapper`. Pass the exact **BSON type** stored in the document and verify the generated command in integration tests.

### 15.2. Data Type Mismatch Example

Suppose `items.productId` stores a BSON ObjectId. Filtering with a 24-character hex string:

```javascript
arrayFilters: [
  { "line.productId": "507f1f77bcf86cd799439011" }
]
```

will **fail to match** a BSON ObjectId. When the schema stores ObjectId, pass ObjectId:

```javascript
arrayFilters: [
  { "line.productId": ObjectId("507f1f77bcf86cd799439011") }
]
```

Never conclude `arrayFilters` is broken simply from `modifiedCount=0` before checking the BSON type of every predicate value.

### 15.3. Safe Query/Update Logging

You can enable command monitoring or scoped logging in test environments to inspect document filters, update paths, and `arrayFilters`. In production, avoid logging full documents containing personal data, tokens, or sensitive fields; apply redaction and correlation IDs per project policy.

## 16. Fixed-Position Updates and Nested Arrays

### 16.1. When Is items.0.quantity Appropriate?

```javascript
db.orders.updateOne(
  { _id: "ord-001" },
  { $set: { "items.0.quantity": 5 } }
);
```

This path modifies only the element at **index 0**. It is appropriate only when position itself carries fixed business meaning, not when users can reorder lines or import new rows.

### 16.2. Combining $[] and $[identifier]

When you want to traverse all groups yet update only a package matching a code, put `$[]` on the outer array and `$[pkg]` on the inner array:

```javascript
db.shipments.updateOne(
  { _id: "shipment-001", tenantId: "tenant-a" },
  {
    $set: {
      "batches.$[].packages.$[pkg].state": "CHECKED"
    }
  },
  {
    arrayFilters: [
      { "pkg.packageCode": "P1" }
    ]
  }
);
```

Unlike the batch-B2-only example in section 9, this updates **every package P1 across all batches**. `pkg` filters the packages level, while `$[]` needs no identifier in `arrayFilters`.

### 16.3. Avoid Misusing Array Positions

Fixed indexes, `$`, `$[]`, and `$[identifier]` are distinct tools. When designing APIs, expose intent-revealing methods like `reserveLineById` or `markPackagesByCode` rather than an “update arbitrary path” endpoint where clients pass paths and operators.

## 17. Reactive Access, Transactions, and Version Compatibility

### 17.1. ReactiveMongoOperations

In a reactive application:

```java
import reactor.core.publisher.Mono;
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.ReactiveMongoOperations;

public final class ReactiveOrderLineWriter {
    private final ReactiveMongoOperations mongo;

    public ReactiveOrderLineWriter(ReactiveMongoOperations mongo) {
        this.mongo = mongo;
    }

    public Mono<UpdateResult> reserveBookA(
        String tenantId,
        String orderId
    ) {
        Query query = Query.query(
            Criteria.where("id").is(orderId)
                .and("tenantId").is(tenantId)
                .and("status").is("READY_TO_SHIP")
        );

        Update update = new Update()
            .set("items.$[line].state", "RESERVED")
            .filterArray(
                Criteria.where("line.sku_code").is("BOOK-A")
                    .and("line.state").is("NEW")
            );

        return mongo.updateFirst(query, update, OrderDocument.class);
    }
}
```

This assumes the same `Query`, `Criteria`, `Update`, and `OrderDocument` imports as earlier. `Mono<UpdateResult>` emits the result only upon subscription; calling the method does not immediately update the server if nobody subscribes.

Reactive execution does not automatically provide tenant authorization, unique array elements, or transactions. Never call `block()` on a non-blocking path to force imperative execution.

### 17.2. Multi-Document Transactions

When editing an array inside **one document**, single-document atomicity is usually sufficient at the database layer. When an order, shipment, and inventory across multiple collections must succeed or roll back together, evaluate MongoDB multi-document transactions with a supporting topology and transaction manager.

Do not treat `@Transactional` as a substitute for proper state transitions or accurate array filters. A transaction does not turn two conditions matched across different elements into a single-element match.

### 17.3. Version Support Checklist

| Component | What to Verify |
| --- | --- |
| MongoDB server | Supports `$[identifier]` and `arrayFilters`; which update commands accept the option |
| MongoDB Java driver | `UpdateOptions.arrayFilters(...)` and BSON encoding behavior |
| Spring Data MongoDB | `Update.filterArray(...)`, `MongoOperations.updateFirst/updateMulti`, mapping behavior |
| Spring Boot | Managed Spring Data/driver versions and `MongoTemplate`/reactive beans |
| Collection schema | `items` is truly an array with consistent nested fields and types |

MongoDB 3.6 introduced filtered positional array updates. Not every update pipeline syntax or operation accepts `arrayFilters` the same way `updateOne` does; check API support per version and operation type. In particular, **aggregation pipeline updates do not use the `arrayFilters` option**.

## 18. Comprehensive Testing: Right Document, Right Element, Right Field

### 18.1. Behavior Matrix

| Test | Expectation |
| --- | --- |
| Single BOOK-A line in `ord-001` | Only the BOOK-A line changes |
| Two BOOK-A lines in `ord-002` | **Both** change when filtering only by SKU |
| BOOK-B or BOOK-C lines | Remain unchanged |
| Document belonging to tenant-b | Remains unchanged |
| CANCELLED document | Remains unchanged when filter requires READY_TO_SHIP |
| No matching lines | Matched can be 1, modified 0 |
| Empty array | Zero elements updated |
| Missing/null/mistyped array | Test error or no-match behavior per structure and query |
| One identifier with two predicates | Only elements satisfying both change |
| Two identifiers at two array levels | Only elements at the exact batch/level change |
| Filter using `line.sku` instead of `line.sku_code` | Fails to match when BSON uses alias |
| Calling `$inc` twice | Value increments twice |
| Update with expected version | Prevents overwriting when version changed |
| Missing array filter identifier | Operation fails rather than silently skipping |

### 18.2. Integration Test Skeleton for Spring Data

JUnit 5 example assuming a MongoDB test context, fixture seeded as in section 2, and `MongoOperations` injected:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

class ArrayFilterIntegrationTest {
    MongoOperations mongo; // Injected via test configuration.

    @Test
    void changesAllMatchingLinesNotOtherSkus() {
        Query key = Query.query(
            Criteria.where("id").is("ord-002")
                .and("tenantId").is("tenant-a")
        );
        Update update = new Update()
            .set("items.$[line].state", "CHECKED")
            .filterArray(
                Criteria.where("line.sku_code").is("BOOK-A")
            );

        var result = mongo.updateFirst(
            key, update, OrderDocument.class
        );
        assertEquals(1, result.getMatchedCount());
        assertEquals(1, result.getModifiedCount());

        OrderDocument saved = mongo.findOne(key, OrderDocument.class);
        assertNotNull(saved);
        List<OrderLine> items = saved.items();
        assertEquals("CHECKED", items.get(0).state());
        assertEquals("CHECKED", items.get(1).state());
        assertEquals("NEW", items.get(2).state());
    }
}
```

This is a **learning test skeleton**, not a standalone runnable class as-is. Add test annotations/context, injection, pre-test fixture seeding, cleanup, and compatible Spring Data versions. Tests must reset fixtures so prior runs do not affect `modifiedCount`; on a record already set to CHECKED, setting CHECKED again yields `modifiedCount=0`.

### 18.3. Inspecting Actual BSON JSON

```javascript
db.orders.findOne(
  { _id: "ord-002", tenantId: "tenant-a" },
  { items: 1, status: 1 }
);
```

Verify:

- `sku_code` is the physical BSON field, not `sku`.
- `items` remains an array with its original element count.
- Only target fields changed.
- Non-matching lines and other tenants' documents remain unchanged.
- `matchedCount` and `modifiedCount` match contract expectations.

### 18.4. Concurrency and Retry Tests

Spawn two worker/test threads updating the same document with different expected versions; assert no unintended lost updates occur. For `$inc`, verify retry handling does not double-apply increments. For `updateMulti`, test partial failure handling and single-document atomicity rather than assuming the batch is one transaction.

## 19. Common Errors and Diagnostics

| Symptom | Possible Cause | Action to Take |
| --- | --- | --- |
| Identifier `line` has no filter | Used `$[line]` without `arrayFilters` | Register one filter for `line` |
| Duplicate identifier definition | Two `arrayFilters` objects use the same identifier | Merge predicates for `line` into one object |
| `modifiedCount=0` | No matching element or value unchanged | Inspect BSON; compare matchedCount vs. modifiedCount |
| `modifiedCount=1` while two lines changed | Counts documents, not elements | Assert element states by re-reading the document |
| BOOK-B also modified | Used `$[]` or missed inner predicate | Use `$[line]` with explicit `arrayFilters` |
| Duplicate BOOK-A lines both changed | SKU filter does not uniquely identify one line | Use `lineId` or tighter predicates |
| Another tenant's document modified | Outer filter lacked tenant constraint | Bind tenant from authentication context |
| `DONE` state overwritten to `RESERVED` | Filtered only by SKU without expected state | Add `line.state` to `arrayFilters` |
| `line.sku` fails to match | BSON stores `sku_code`; `arrayFilters` is not auto-mapped | Use actual BSON field name |
| Missing or Null array errors | Update path requires a valid array | Validate schemas and migrate data |
| Upsert errors on array path | Insert branch lacks exact array equality match | Avoid upsert for element updates |
| Query succeeds yet update is no-op | Query matched document; `arrayFilters` matched no element | Check both filter layers |
| Nested update touched wrong batch | Missing outer batch filter | Use two identifiers |
| Server rejects `$[line]` | Unsupported version or operation | Check MongoDB, driver, and Spring Data versions |
| Large array makes updates slow | Large BSON document, index maintenance, contention | Profile workload; consider extracting a child collection |
| Concurrent version change overwritten | Missing expected version or expected state in filter | Add concurrency guard |

### 19.1. Short Investigation Workflow

```text
1. Document filter: right _id, tenantId, status?
                 ↓
2. Actual BSON: is items an array? sku_code or sku?
                 ↓
3. Update path: items.$[line].quantity or items.$[]?
                 ↓
4. arrayFilters: do identifier line, predicates, and BSON types match?
                 ↓
5. UpdateResult: matchedCount / modifiedCount are per DOCUMENT.
                 ↓
6. Re-read the document and compare individual elements.
                 ↓
7. Optimize indexes/throughput only after logic is verified.
```

Never treat “no exception thrown” as proof an update modified the intended elements: an update can succeed while changing nothing.

## 20. Practice Exercises with Solutions

### Exercise 1 — Change Quantity Only for BOOK-A

**Prompt:** `ord-001` has BOOK-A quantity 1 and BOOK-B quantity 4. Set only BOOK-A to 5.

**Solution:**

```javascript
db.orders.updateOne(
  { _id: "ord-001", tenantId: "tenant-a" },
  { $set: { "items.$[line].quantity": 5 } },
  { arrayFilters: [{ "line.sku_code": "BOOK-A" }] }
);
```

BOOK-B remains untouched. Replacing with `$[]` would set both quantities to 5.

### Exercise 2 — Predict Modified Element Count

**Prompt:** Run Exercise 1's command on `ord-002`, which has **two** BOOK-A elements. How many elements change quantity? Will `modifiedCount` be 2?

**Solution:** **Two elements** can change quantity if the new value differs from the old; `modifiedCount` is still 1 because **one document** was modified. The driver reports document count, not array element count.

### Exercise 3 — One Element Must Satisfy Two Conditions

**Prompt:** Set state CHECKED only on BOOK-A lines with quantity >= 3.

**Solution:**

```javascript
db.orders.updateOne(
  { _id: "ord-002", tenantId: "tenant-a" },
  { $set: { "items.$[line].state": "CHECKED" } },
  {
    arrayFilters: [{
      "line.sku_code": "BOOK-A",
      "line.quantity": { $gte: 3 }
    }]
  }
);
```

Both predicates belong to **one filter for `line`**, so both apply to the same element. On the initial fixture, the BOOK-A line with quantity 3 updates while the line with quantity 2 does not.

### Exercise 4 — Using Spring Data Update.filterArray

**Prompt:** Entity uses `@Field("sku_code") String sku`. Write an `Update` changing `state` to RESERVED for BOOK-A lines currently in NEW.

**Solution:**

```java
Update update = new Update()
    .set("items.$[line].state", "RESERVED")
    .filterArray(
        Criteria.where("line.sku_code").is("BOOK-A")
            .and("line.state").is("NEW")
    );
```

Inside `arrayFilters`, use `line.sku_code` matching BSON. Then call `mongo.updateFirst(queryWithTenantAndStatus, update, OrderDocument.class)` with a separately validated query.

### Exercise 5 — Target Batch B2, Package P1

**Prompt:** In `shipments`, set `READY` only for package P1 of batch B2.

**Solution:**

```javascript
db.shipments.updateOne(
  { _id: "shipment-001", tenantId: "tenant-a" },
  { $set: { "batches.$[b].packages.$[p].state": "READY" } },
  {
    arrayFilters: [
      { "b.batchCode": "B2" },
      { "p.packageCode": "P1" }
    ]
  }
);
```

Two identifiers filter both levels. Do not use `batches.$[].packages.$[p]` when targeting only batch B2.

### Exercise 6 — Difference Between $elemMatch and arrayFilters

**Prompt:** A developer puts `items: {$elemMatch: {sku_code: "BOOK-A"}}` in the outer filter, yet uses `items.$[].state` in the update. Does this guarantee only BOOK-A is modified?

**Solution:** No. `$elemMatch` in the outer filter only decides which documents contain at least one BOOK-A. `$[]` in the update path still modifies **all elements**. Use `$[line]` with matching `arrayFilters`.

### Exercise 7 — No-Op and matchedCount

**Prompt:** `updateOne` returns `matchedCount=1` and `modifiedCount=0`. Is the conclusion “SKU BOOK-A is absent” necessarily right?

**Solution:** No. Either no element matched the filter, or matching elements already held the target value. Re-read BSON or adjust the query/checks to distinguish the two cases.

### Exercise 8 — Avoiding Cross-Tenant Updates

**Prompt:** An `updateMany` command uses `arrayFilters` for BOOK-A while its outer filter has only `status: READY_TO_SHIP`. What is the bug?

**Solution:** It can modify orders belonging to other tenants. Add `tenantId` from the security context and narrow the scope per use case; `arrayFilters` does not replace authorization.

### Exercise 9 — Choosing Update vs. Upsert

**Prompt:** A request edits a line item on an order that might not exist. Should you call `mongo.upsert(...)` with `items.$[line]`?

**Solution:** Usually **no**. The upsert insert branch requires exact equality on the array field and can error if no array exists. When editing an existing order, use `updateFirst` without upsert; when creating an order, run an insert workflow with a valid items list.

### Exercise 10 — Checking Concurrency

**Prompt:** Two workers set a line's quantity to 3 and 5, both filtering by SKU. How do you reduce lost updates?

**Solution:** Include version/expected state or expected quantity in the appropriate filter and perform an atomic update, checking `matchedCount`. When targeting one specific line, use a unique `lineId` instead of SKU, and test concurrent requests.

## 21. Handover Checklist

| Question | Verification Criteria |
| --- | --- |
| Does the API intend to edit one element or all matching elements? | Pick `$`, `$[]`, or `$[id]` accurately |
| Does the document filter enforce ID/tenant/status? | Cannot write out-of-scope data |
| Can the same SKU appear multiple times? | Use `lineId` if business logic targets one line |
| Are identifiers valid and declared? | One filter document per identifier |
| Must predicates apply to the same element? | Place them in one filter object for that identifier |
| Are BSON field names used in `arrayFilters`? | `line.sku_code` instead of `line.sku` |
| Any custom converters/ObjectId/enum types? | Test BSON types and `arrayFilters` matching |
| Can the array be null/missing/mistyped? | Data validation and legacy audit |
| Was `$elemMatch` confused with filtered updates? | Test document match vs. element match |
| Is upsert enabled on an array update? | Clarify insert branch; usually keep upsert off |
| Is there a concurrency guard? | Version/expected state in filter |
| Is `UpdateResult` interpreted at document level? | Never count elements with `modifiedCount` |
| Are cross-document transactions needed? | Verify topology and transaction manager |
| Do indexes support the document filter? | Check `getIndexes()` and `explain` |
| Are arrays growing too large? | Document size, workload, and child-collection option |
| Tested cross-tenant, multi-element, and no-op cases? | Integration tests on MongoDB + re-read verification |
| Do MongoDB and Spring Data versions support it? | Verify filtered positional/`arrayFilters` per dependency |

### Key Takeaways

1. **`$[identifier]`** is the filtered positional operator; **`arrayFilters`** defines the predicates for each identifier. It can update **multiple elements** within a single document.
2. **Query filters select documents**, while **arrayFilters select elements**. Place tenant, status, and other guards at the right layer.
3. Distinguish **`$`** (first positional match), **`$[]`** (all elements), **`$[line]`** (all matching elements), and **`$elemMatch`** (matching multiple predicates on the same element).
4. In Spring Data, `Update.filterArray(...)` should use **actual BSON field names** because filter expressions are not automatically mapped via domain entity `@Field` metadata.
5. `matchedCount`/`modifiedCount` count **documents**, not array elements. One document can have multiple lines updated.
6. With nested arrays, use multiple identifiers or combine `$[]` and `$[id]` appropriately; avoid positional array indexes unless ordering is guaranteed by schema.
7. Never rely on array filters as a substitute for schema validation, authorization, optimistic locking, unique line identity, or required transactions.
8. Always **re-read actual BSON**, test duplicate SKUs, malformed data, and concurrency, and verify index/version compatibility before shipping.
