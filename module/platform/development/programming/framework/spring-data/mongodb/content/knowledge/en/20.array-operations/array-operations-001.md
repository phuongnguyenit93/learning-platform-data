# Distinguishing Full Array Replacement from Element-by-Element Updates

## 1. The Problem: Should a Small Change Rewrite the Entire Array?

Suppose an order document contains an **items** array of purchased products. A customer increases the book quantity from 2 to 3. There are two approaches:

1. Read the Order, modify the items list in Java, and call repository.save(...) to rewrite the document.
2. Send an update command to MongoDB that increments only the quantity property of the **matching element** in the array.

Both approaches may produce the same result when there is only a single request, but they differ significantly in **write scope, update conflicts, consistency, and processing cost**. A full-array replacement can overwrite concurrent changes to other elements; a targeted element update usually expresses the business condition much more accurately.

This is the topic **Distinguishing Full Array Replacement from Element-by-Element Updates**, in the **Array Operations** chapter of the **SPRING_DATA_MONGODB** module. The content focuses on MongoDB update operators and how to use them via **MongoTemplate**, repositories, or ReactiveMongoTemplate, while also connecting to queries, indexes, transactions, reactive access, testing, and performance diagnostics.

Learning objectives:

1. Explain the differences between **replacing an array with $set**, **saving/replacing a document**, and **updating a single element**.
2. Use **$**, **$[]**, **$[identifier]**, and **arrayFilters** to modify the exact target elements.
3. Choose **$push, $addToSet, $pull, $pop** for adding/removing elements.
4. Know when to use **$inc** instead of reading values and computing them in the application.
5. Understand single-document update atomicity, the limits of multi-document operations, and the risk of lost updates.
6. Apply query predicates, UpdateResult checks, optimistic locking, and business rules during updates.
7. Write tests that verify unrelated elements remain unchanged.

## 2. Sample Document and Java Model

Suppose the **orders** collection has the following document:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  orderNumber: "ORD-1001",
  status: "DRAFT",
  items: [
    {
      sku: "BOOK-001",
      quantity: NumberInt(2),
      unitPriceMinor: NumberLong("159000")
    },
    {
      sku: "PEN-002",
      quantity: NumberInt(1),
      unitPriceMinor: NumberLong("12000")
    }
  ],
  updatedAt: ISODate("2025-06-01T09:00:00Z")
}
~~~

Here **items** is a BSON array containing embedded documents. The elements live **inside the same Order document**, not as independent documents in another collection. Each item has a sku, quantity, and unit price at the time the order was created.

Java model:

~~~java
package com.example.orders;

import java.time.Instant;
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id ObjectId id,
    String orderNumber,
    String status,
    List<OrderItem> items,
    Instant updatedAt
) {}
~~~

~~~java
package com.example.orders;

public record OrderItem(
    String sku,
    int quantity,
    long unitPriceMinor
) {}
~~~

Records make it easy to visualize immutable data on the Java side. Even though a record cannot mutate fields directly, we can still build a new list or send an **Update** command so MongoDB modifies the BSON values directly. Those two approaches are not the same in how they execute.

### 2.1. Three Levels of Operations to Distinguish

| Operation Level | Example | Scope |
| --- | --- | --- |
| Replace document | repository.save(order) or replaceOne | Can rewrite the entire document from Java state |
| Replace only the array field | $set: { items: [...] } | Rewrites the entire value of the items field |
| Modify an element/sub-field | $inc: { "items.$.quantity": 1 } | Changes only the specified field on the matching element |

**Using $set on the entire items field is not the same as replacing the entire Order**, because other fields such as status and orderNumber remain intact. However, for the array contents, $set replaces the **entire current value of the array** and does not automatically merge with the old version.

## 3. Understand the Atomicity Model Before Choosing a Solution

MongoDB guarantees that **a write operation on a single document is atomic**: a valid update modifying multiple fields of the same document is applied as a single unit, so readers never observe a half-written state from that operation.

However, **atomicity does not mean there are no lost updates** when an application:

1. Reads the document at time T1.
2. Builds a new version based on the data read.
3. Writes the new version at time T2.

Between T1 and T2, another request may have already modified the document. An atomic update at T2 can still overwrite data that the other request just saved.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant M as MongoDB
    participant B as Request B
    A->>M: Read Order, items=[BOOK:2, PEN:1]
    B->>M: Read Order, items=[BOOK:2, PEN:1]
    A->>M: $set items=[BOOK:3, PEN:1]
    B->>M: $set items=[BOOK:2, PEN:2]
    Note over M: Result may lose the BOOK:3 update
~~~

Both $set operations are individually atomic, but **without a version guard condition**, the later operation can overwrite the array contents written by the earlier one.

Meanwhile, two $inc commands targeting specific elements—such as incrementing BOOK and incrementing PEN—can be applied sequentially by MongoDB without having to rewrite the old value of the entire array.

## 4. Replacing the Entire Array with $set

When you want to replace the **entire item list** with a newly confirmed version, you can use $set:

~~~javascript
db.orders.updateOne(
  {
    _id: ObjectId("507f1f77bcf86cd799439011"),
    status: "DRAFT"
  },
  {
    $set: {
      items: [
        { sku: "BOOK-001", quantity: 3, unitPriceMinor: NumberLong("159000") },
        { sku: "PEN-002", quantity: 1, unitPriceMinor: NumberLong("12000") }
      ]
    }
  }
);
~~~

After the update, the **items** field has exactly the two elements from the new array. Fields outside items are not overwritten by this $set command alone. However, if someone else added a third item right before the update, the new array will **drop that third item**.

In Spring Data:

~~~java
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import com.mongodb.client.result.UpdateResult;

public UpdateResult replaceItems(
        MongoTemplate template,
        ObjectId orderId,
        List<OrderItem> replacement) {

    Query query = Query.query(
        Criteria.where("_id").is(orderId)
            .and("status").is("DRAFT")
    );

    Update update = new Update().set("items", replacement);

    return template.updateFirst(
        query, update, OrderDocument.class
    );
}
~~~

Spring Data MappingMongoConverter converts the OrderItem objects in the List into embedded BSON documents. This example assumes OrderDocument uses matching field names in MongoDB and MongoTemplate is configured.

### 4.1. When Is Replacing the Entire Array the Right Intent?

- The user performs a **“Replace the entire cart with the confirmed list”** action.
- There is a requirement to **reorder** all elements.
- A migration process changes the schema for all items in a small array with concurrency controlled.
- The array represents a holistic configuration that must be validated as a single version.

Conversely, if the requirement is simply “increment the quantity of BOOK-001 by one”, replacing the entire array is usually **broader than the required business scope**.

### 4.2. Input Data Validation Is Needed

Before replacing an entire array, validate that:

1. **SKUs are valid** and each SKU appears at most once per the contract.
2. quantity is positive and does not exceed business limits.
3. Unit prices come from a trusted source or are permitted stored snapshots.
4. The Order is still in an editable status.
5. The write request has a concurrent-change detection mechanism if needed.

Do not take the entire items structure from an HTTP request and write it straight into MongoDB without checking ownership, prices, or internal fields.

## 5. Repository.save Can Be a Broader Operation

Another approach:

~~~java
OrderDocument previous = orderRepository.findById(orderId)
    .orElseThrow();

List<OrderItem> newItems = buildNewItems(previous.items());

OrderDocument edited = new OrderDocument(
    previous.id(),
    previous.orderNumber(),
    previous.status(),
    newItems,
    previous.updatedAt()
);

OrderDocument saved = orderRepository.save(edited);
~~~

Here **buildNewItems(...)** is a hypothetical business function that builds the new list. The snippet illustrates read → transform in Java → save. It has no version guard in the current OrderDocument model.

For an existing entity, repository.save typically goes through Spring Data MongoDB's document persistence path and can rewrite many fields of the entity, not just items. If the read copy is missing fields or is stale, saving can cause data loss.

**Do not assume save automatically merges items by SKU.** Spring Data cannot know which SKU is allowed to be overwritten or which version is newer unless the application designs that rule.

When the domain uses **@Version** and optimistic locking, repository.save can detect stale versions according to the version rules. Section 13 covers this protection mechanism.

## 6. Updating the First Matching Element with Positional Operator $

If you only need to increment the quantity of item **BOOK-001**, MongoDB has the positional operator **$** to reference the first array element matching the query condition:

~~~javascript
db.orders.updateOne(
  {
    _id: ObjectId("507f1f77bcf86cd799439011"),
    status: "DRAFT",
    "items.sku": "BOOK-001"
  },
  {
    $inc: { "items.$.quantity": 1 }
  }
);
~~~

In the expression **items.$.quantity**, the **$** stands for the position of the **first** matching element in the items array. The **items.sku** condition in the filter is essential so MongoDB can identify the corresponding element.

If the array contains two items with the same SKU, positional $ only updates the **first matching element** and does not automatically update both. If the business rule states that each SKU appears on only one line item, enforce this invariant when adding items and in tests.

### 6.1. MongoTemplate.updateFirst

~~~java
import com.mongodb.client.result.UpdateResult;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public UpdateResult increaseQuantity(
        MongoTemplate template, ObjectId orderId, String sku) {

    Query query = Query.query(
        Criteria.where("_id").is(orderId)
            .and("status").is("DRAFT")
            .and("items.sku").is(sku)
    );

    Update update = new Update()
        .inc("items.$.quantity", 1);

    return template.updateFirst(
        query, update, OrderDocument.class
    );
}
~~~

This command does not need to read the entire Order before incrementing quantity and does not rewrite the whole array from an old copy. It changes only the quantity field of one item on the matching document.

### 6.2. Why Is $inc Better Than $set for Increment Operations?

Suppose quantity=2. Two concurrent requests both read 2 and both send $set quantity=3; the final result may only be 3. If both send **$inc quantity:1** on the same element, MongoDB applies each update atomically, so the result can be **4** if both succeed.

However, $inc **does not automatically enforce** maximum quantity rules. If inventory only has one product left, you must add an appropriate invariant condition or reservation flow. Using $inc alone does not guarantee no oversell.

### 6.3. Limitations of Positional $

The single positional operator **$** should not be used indiscriminately when the filter involves multiple different arrays or when multiple elements need updating. For nested arrays or multiple matching elements, use **$[]** or **$[identifier]** with arrayFilters depending on MongoDB version support.

**Do not use positional $ as an arbitrary upsert** when no array element matches yet. If there is no matching element, decide whether to add the item or return a business error rather than letting an ambiguous positional path try to create an array.

## 7. Updating All Elements with $[]

The **$[]** operator applies the update to **every element** of an array in the matching document:

~~~javascript
db.orders.updateOne(
  {
    _id: ObjectId("507f1f77bcf86cd799439011"),
    status: "DRAFT"
  },
  {
    $inc: { "items.$[].quantity": 1 }
  }
);
~~~

The example above increments quantity **for every line item** by one, not just BOOK-001. This is only a syntax illustration; real ordering workflows rarely need to increment all quantities unconditionally.

In MongoTemplate:

~~~java
Update update = new Update()
    .inc("items.$[].quantity", 1);

template.updateFirst(
    Query.query(
        Criteria.where("_id").is(orderId)
            .and("status").is("DRAFT")
    ),
    update,
    OrderDocument.class
);
~~~

If you specify **items.$[].quantity**, each element receives the same update on its quantity field. If the array is empty, there are no elements to update. If the array contains elements without a consistent schema or where quantity is not numeric, the operation can fail.

**Distinction:** $[] means every element **within one array of the selected document**; it does not mean updating every document in the collection. To update multiple documents, you must also choose between **updateOne/updateFirst** and **updateMany/updateMulti**.

## 8. Selecting Elements with $[identifier] and arrayFilters

To increment quantity on **every line with sku=BOOK-001**, even if the array has multiple lines with the same SKU, use the **filtered positional operator**:

~~~javascript
db.orders.updateOne(
  {
    _id: ObjectId("507f1f77bcf86cd799439011"),
    status: "DRAFT"
  },
  {
    $inc: { "items.$[line].quantity": 1 }
  },
  {
    arrayFilters: [
      { "line.sku": "BOOK-001" }
    ]
  }
);
~~~

In the path **items.$[line].quantity**, the string **line** is an identifier bound to the filter **line.sku**. MongoDB modifies every items element that satisfies the arrayFilters condition.

Here is how it differs from positional **$**:

| Syntax | Scope Within the Array |
| --- | --- |
| items.$.quantity | First matching element based on positional match from the query |
| items.$[].quantity | All elements in the array |
| items.$[line].quantity + arrayFilters | All elements matching the filter for line |

### 8.1. MongoTemplate with Update.filterArray

Spring Data MongoDB provides a way to declare an array filter in Update:

~~~java
Query query = Query.query(
    Criteria.where("_id").is(orderId)
        .and("status").is("DRAFT")
);

Update update = new Update()
    .inc("items.$[line].quantity", 1)
    .filterArray(
        Criteria.where("line.sku").is("BOOK-001")
    );

UpdateResult result = template.updateFirst(
    query, update, OrderDocument.class
);
~~~

This example uses the **Update.filterArray(CriteriaDefinition)** API in Spring Data MongoDB versions that support filtered positional updates. The name in **line.sku** must match the identifier **line** in the update path.

**Note:** with a query that only filters on _id and status, **matchedCount can be 1 even if no element satisfies arrayFilters**; in that case modifiedCount can be 0. If the business logic requires returning an error when the SKU is absent from the Order, add an **items.sku** condition directly in the Query or design a clear return result.

### 8.2. When Should You Use arrayFilters?

- An array may contain multiple elements matching the same condition.
- You need to update items by category, label, status, or price range.
- There are nested arrays and elements need to be targeted across multiple levels.
- You do not want to replace the whole array from potentially stale Java state.

Do not construct arrayFilters directly from unvalidated client-supplied JSON strings. Bind values from validated parameters, use the framework's Query/Update API, and validate field paths against the defined schema.

## 9. Adding Elements: $push and $addToSet

Modifying an element is different from **adding a new element**. MongoDB has dedicated operators for arrays.

### 9.1. $push: Always Appends an Element

~~~javascript
db.orders.updateOne(
  { _id: ObjectId("507f1f77bcf86cd799439011"), status: "DRAFT" },
  {
    $push: {
      items: {
        sku: "ERASER-003",
        quantity: 1,
        unitPriceMinor: NumberLong("8000")
      }
    }
  }
);
~~~

In MongoTemplate:

~~~java
Update update = new Update().push(
    "items",
    new OrderItem("ERASER-003", 1, 8_000L)
);

template.updateFirst(
    Query.query(Criteria.where("_id").is(orderId)
        .and("status").is("DRAFT")),
    update,
    OrderDocument.class
);
~~~

**$push does not prevent duplicate SKUs automatically.** If the request is sent twice, you may end up with two ERASER-003 elements. If each SKU must be unique within an Order, design a conditional add operation, an idempotency key, or an appropriate data model strategy.

### 9.2. $addToSet: Adds Only If an Identical Element Is Not Present

For a **tags** array of strings:

~~~javascript
db.products.updateOne(
  { sku: "BOOK-001" },
  { $addToSet: { tags: "SPRING" } }
);
~~~

If tags already contains the string SPRING, it is not added again. This is a **set-like operation** for equal elements under BSON comparison rules.

In Spring Data:

~~~java
Update update = new Update()
    .addToSet("tags", "SPRING");
~~~

**Be careful with arrays of objects:** $addToSet compares **the entire embedded document value**; it does not automatically understand that two objects with the same sku represent one logical business item. If price or quantity differs, both objects can coexist even with the same SKU.

### 9.3. Adding Multiple Elements with $each

MongoDB supports:

~~~javascript
db.products.updateOne(
  { sku: "BOOK-001" },
  { $addToSet: { tags: { $each: ["JAVA", "MONGODB"] } } }
);
~~~

In Spring Data:

~~~java
Update update = new Update()
    .addToSet("tags")
    .each("JAVA", "MONGODB");
~~~

$push operations also have an $each variant, and even optional $position, $sort, and $slice modifiers depending on requirements; check MongoDB/Spring Data version support and ordering policy before applying them.

## 10. Removing Elements: $pull and $pop

### 10.1. $pull: Removes Elements Matching a Condition

If the user removes SKU PEN-002 from a draft order:

~~~javascript
db.orders.updateOne(
  {
    _id: ObjectId("507f1f77bcf86cd799439011"),
    status: "DRAFT"
  },
  {
    $pull: {
      items: { sku: "PEN-002" }
    }
  }
);
~~~

**$pull removes all array elements that match the condition**, not just the first matching element. If corrupted data has two lines with the same SKU, both may be removed.

In MongoTemplate:

~~~java
import org.bson.Document;

Update update = new Update().pull(
    "items",
    new Document("sku", "PEN-002")
);

template.updateFirst(
    Query.query(Criteria.where("_id").is(orderId)
        .and("status").is("DRAFT")),
    update,
    OrderDocument.class
);
~~~

### 10.2. $pop: Removes the First or Last Element

If the array is ordered and you need to drop the **last element**:

~~~javascript
db.orders.updateOne(
  { _id: ObjectId("507f1f77bcf86cd799439011") },
  { $pop: { items: 1 } }
);
~~~

The value **1** removes the last element, and **-1** removes the first element. $pop **does not filter by SKU**; therefore it is usually unsuitable for “remove product BOOK-001” if item positions in the array can change.

### 10.3. Difference from $unset

To remove a field from an item while keeping the item itself, you can use **$unset** on the matching element path:

~~~javascript
db.orders.updateOne(
  { _id: ObjectId("507f1f77bcf86cd799439011"), "items.sku": "BOOK-001" },
  { $unset: { "items.$.unitPriceMinor": "" } }
);
~~~

This command **does not remove the item from the array**; it only removes the unitPriceMinor field of the matching item. If the element is required to have a unit price, this operation breaks the invariant and should not be allowed in the application.

In particular, **$unset on an element at an array index** can leave a null value at that position instead of shortening the array; use **$pull** when you want to remove an element from the array.

## 11. Replacing One Field of an Item Instead of the Item or Array

Suppose you need to update the snapshot price of an unconfirmed item:

~~~javascript
db.orders.updateOne(
  {
    _id: ObjectId("507f1f77bcf86cd799439011"),
    status: "DRAFT",
    "items.sku": "BOOK-001"
  },
  {
    $set: {
      "items.$.unitPriceMinor": NumberLong("149000")
    }
  }
);
~~~

This command replaces only **unitPriceMinor** on the first item with the matching SKU, keeping quantity and all other items unchanged.

In Spring Data:

~~~java
Update update = new Update()
    .set("items.$.unitPriceMinor", 149_000L);
~~~

Comparison:

| Command | Result |
| --- | --- |
| $set: { items: newArray } | Replaces the entire items array |
| $set: { "items.$": newItem } | Replaces the entire object of the first matching element |
| $set: { "items.$.unitPriceMinor": newPrice } | Replaces only the price field of the matching element |
| $inc: { "items.$.quantity": 1 } | Increments the quantity on the matching element |

When replacing the **entire embedded object** via items.$, fields from the old item that are absent from the new object are not preserved. If you only want to change one field, target the path to that specific field.

## 12. Nested Paths and Multi-Level Arrays

A complex schema might look like:

~~~javascript
{
  shipments: [
    {
      shipmentCode: "S1",
      packages: [
        { packageCode: "P1", checked: false },
        { packageCode: "P2", checked: false }
      ]
    }
  ]
}
~~~

To set checked=true for package P2 inside shipment S1, you can use two identifiers:

~~~javascript
db.orders.updateOne(
  { _id: ObjectId("507f1f77bcf86cd799439011") },
  {
    $set: {
      "shipments.$[shipment].packages.$[pkg].checked": true
    }
  },
  {
    arrayFilters: [
      { "shipment.shipmentCode": "S1" },
      { "pkg.packageCode": "P2" }
    ]
  }
);
~~~

Using arrayFilters, MongoDB targets elements at **each array level** instead of replacing the entire shipments structure. However, multiple levels of nested arrays make queries, indexes, and updates harder to reason about. If shipments/packages have independent lifecycles and are accessed frequently, re-evaluate embedding versus referencing boundaries.

**Do not use an arbitrary update path passed by the client.** Field names and identifiers must come from controlled code; clients should only supply validated values such as shipmentCode or packageCode.

## 13. Avoiding Lost Updates with Optimistic Locking

Targeted updates reduce the risk of overwriting the entire array, but when business logic requires replacing the whole list, stale versions must be detected.

Spring Data MongoDB supports **@Version**:

~~~java
import java.time.Instant;
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record VersionedOrderDocument(
    @Id ObjectId id,
    String orderNumber,
    String status,
    List<OrderItem> items,
    Instant updatedAt,
    @Version Long version
) {}
~~~

When repository.save performs optimistic locking on an entity with a managed version, Spring Data can detect a stale version and throw **OptimisticLockingFailureException** if the update no longer matches the expected version. An acknowledged write concern must be used, and the framework/driver semantics for the project's version must be preserved.

### 13.1. Version Condition in an Update

Another strategy is putting expectedVersion into the filter:

~~~javascript
db.orders.updateOne(
  {
    _id: ObjectId("507f1f77bcf86cd799439011"),
    status: "DRAFT",
    version: NumberLong("4")
  },
  {
    $set: {
      items: [
        { sku: "BOOK-001", quantity: 3, unitPriceMinor: NumberLong("159000") }
      ]
    },
    $inc: { version: NumberLong("1") }
  }
);
~~~

With version=4, a valid request changes version to 5. Another request based on version=4 gets **matchedCount=0**, allowing the application to return a conflict response and ask the client to reload the data.

The example above illustrates a **MongoDB driver/mongosh raw update**. When using MongoTemplate on an entity with @Version, Spring Data has version management rules during updates; avoid both manually incrementing version in code and letting the framework auto-increment it without verifying the active versioning behavior.

### 13.2. Do Not Confuse Optimistic Locking with Transactions

Optimistic locking checks whether a document is still at the expected version before an update. A multi-document transaction groups writes across different documents into a single commit/rollback unit. A transaction also **does not automatically solve every business race condition** if proper filters or invariants are missing.

If you are only updating different fields within **one Order**, a conditional atomic single-document update is usually simpler than opening a multi-document transaction.

## 14. Checking UpdateResult to Avoid False Success

An update command may **find no document** or **find one without changing anything**. With MongoTemplate:

~~~java
UpdateResult result = template.updateFirst(
    query,
    update,
    OrderDocument.class
);

long matched = result.getMatchedCount();
long modified = result.getModifiedCount();
~~~

These two metrics are different:

| Result | Common Meaning |
| --- | --- |
| matched=0 | No document matched the filter, e.g. Order does not exist, wrong status, or missing SKU |
| matched=1, modified=1 | Document matched and was actually modified |
| matched=1, modified=0 | Document matched, but the update did not change data, e.g. $set with same value or arrayFilters matched no item |

With **updateFirst**, matchedCount is at most 1; with **updateMulti**, multiple documents can be matched. When using an update with arrayFilters and querying only by _id, matched=1 **does not prove any item was modified**.

### 14.1. Enforcing Business Conditions in the Filter

If quantity may only be incremented on a DRAFT Order:

~~~java
Query query = Query.query(
    Criteria.where("_id").is(orderId)
        .and("status").is("DRAFT")
        .and("items.sku").is(sku)
);
~~~

Adding status to the filter makes “the Order is still DRAFT” part of the **atomic write condition**, which is better than reading status first and updating without rechecking.

Do not return “Order not found” for every matched=0. The Order may exist but have changed status, or the SKU may not be in the array. If the API needs to distinguish these errors, use an appropriate check path while understanding that any extra read may observe state after the update has already failed.

## 15. Bounded Increment/Decrement of Quantity

Decrementing quantity by 1 is only valid if the current quantity is greater than 1, or the business logic must choose to **remove the line item when quantity reaches 0**.

A filter with **$elemMatch** binds the sku and quantity conditions to the **same item**:

~~~javascript
db.orders.updateOne(
  {
    _id: ObjectId("507f1f77bcf86cd799439011"),
    status: "DRAFT",
    items: {
      $elemMatch: {
        sku: "BOOK-001",
        quantity: { $gt: 1 }
      }
    }
  },
  {
    $inc: { "items.$.quantity": -1 }
  }
);
~~~

The $elemMatch condition prevents a case where one item has the matching SKU but a low quantity while another item has quantity > 1. The positional operator **$** references the matching array element under the matching criteria.

In MongoTemplate:

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

Criteria eligibleItem = Criteria.where("sku").is(sku)
    .and("quantity").gt(1);

Query query = Query.query(
    Criteria.where("_id").is(orderId)
        .and("status").is("DRAFT")
        .and("items").elemMatch(eligibleItem)
);

Update update = new Update()
    .inc("items.$.quantity", -1);

UpdateResult result = template.updateFirst(
    query, update, OrderDocument.class
);
~~~

The condition and the decrement execute in **a single atomic update on one document**. If it does not match, do not silently set quantity to 0 without an explicit business policy.

**E-commerce system note:** ensuring an item's quantity is non-negative is **different** from preventing Product inventory overselling across competing Orders. Inventory checks typically live on the Product document or a dedicated reservation workflow; if multiple documents must be written together, design an appropriate transaction or coordination protocol.

## 16. Updating Arrays via Reactive Access

With **ReactiveMongoTemplate**, the same Query and Update can be used in a publisher:

~~~java
import com.mongodb.client.result.UpdateResult;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import reactor.core.publisher.Mono;

public Mono<UpdateResult> incrementReactive(
        ReactiveMongoTemplate template, ObjectId orderId, String sku) {

    Query query = Query.query(
        Criteria.where("_id").is(orderId)
            .and("status").is("DRAFT")
            .and("items.sku").is(sku)
    );

    Update update = new Update()
        .inc("items.$.quantity", 1);

    return template.updateFirst(
        query, update, OrderDocument.class
    );
}
~~~

**Mono<UpdateResult>** executes the update only when subscribed to. In WebFlux, do not call **block()** to retrieve the result inside a service/controller, and do not manually subscribe() multiple times: each subscription can re-execute the update, which is especially dangerous with **$inc** because it is not idempotent.

### 16.1. Updating and Reading the New State

If the API needs to return the updated Order, you can use **findAndModify** with the returnNew option:

~~~java
import org.springframework.data.mongodb.core.FindAndModifyOptions;

public Mono<OrderDocument> incrementAndRead(
        ReactiveMongoTemplate template, ObjectId id, String sku) {

    Query query = Query.query(
        Criteria.where("_id").is(id)
            .and("status").is("DRAFT")
            .and("items.sku").is(sku)
    );

    Update update = new Update()
        .inc("items.$.quantity", 1);

    FindAndModifyOptions options =
        FindAndModifyOptions.options().returnNew(true);

    return template.findAndModify(
        query, update, options, OrderDocument.class
    );
}
~~~

If no document matches the query, the publisher may complete **with no Order**. The API layer must handle this case and should not return a false success. findAndModify lets you update and retrieve the post-update document as a single operation on that document, but it does not replace idempotency protection when clients retry.

### 16.2. Avoiding Automatic Retries with $inc

A retry after a timeout can resend an increment update even if the server already applied the first one and the response was lost. If the system requires “each increment command applies only once”, design an appropriate **idempotency key / deduplication / command state**. Never assume that using reactive APIs or transactions automatically makes an $inc command idempotent.

## 17. Array Size, Indexes, and Performance

MongoDB has a BSON document size limit (typically **16 MiB**). An unbounded embedded array can push an Order past that limit or cause high read/update costs.

Signals to evaluate:

- How many elements does the items array typically hold?
- Do APIs usually read the entire Order or just one item?
- Do many requests update different items in the same Order concurrently?
- Does SKU need to be indexed and queried by item?
- Is there a multi-year history requirement that makes the array grow without bound?

### 17.1. Multikey Index

If you frequently search for Orders containing a SKU:

~~~javascript
db.orders.createIndex({ "items.sku": 1 });
~~~

MongoDB uses a **multikey index** for fields inside an array. An index helps locate documents with matching item SKUs, but it incurs maintenance overhead when the array changes. When filters also include status or tenant, evaluate a compound index based on real workload, such as:

~~~javascript
db.orders.createIndex({
  status: 1,
  "items.sku": 1
});
~~~

Do not blindly create many indexes based solely on every field appearing in an update. Indexes optimize the **document lookup** phase, while overall performance also depends on document count, selectivity, and write frequency.

### 17.2. Measuring with explain

~~~javascript
db.orders.find({
  status: "DRAFT",
  "items.sku": "BOOK-001"
}).explain("executionStats");
~~~

Inspect winningPlan, totalKeysExamined, totalDocsExamined, and nReturned. An **explain** on a find query does not fully describe the cost of updating an array, but it shows whether locating the target document is backed by an index.

When updates are slow, also measure write latency, document size, index maintenance, lock/contention, and update frequency on the same document. A per-element $inc usually avoids having the application read/modify/write the whole array, but you cannot conclude every element-level update is faster in all situations.

### 17.3. When Should You Split Documents?

Nesting an array inside Order makes sense when items share the Order's lifecycle and are usually read together with the Order. If a collection has a document with an array of millions of events appended continuously, requiring per-event pagination and independent updates, a **separate collection + reference** model may be more suitable.

Do not split an array just because one update command looks complex; weigh aggregate boundaries, BSON size, access patterns, and business consistency requirements.

## 18. Array Replacement and Concurrency: Comparing Scenarios

| Scenario | Preferred Operation to Consider | Risks to Manage |
| --- | --- | --- |
| Customer replaces entire cart | $set items + version check | Lost update if using stale snapshot |
| Increment quantity of one SKU | $inc items.$.quantity | Duplicate SKUs, retries, and quantity limits |
| Change one field of an item | $set items.$.field | Target the right item without losing other fields |
| Increment every item | $inc items.$[].quantity | Can modify more broadly than expected |
| Modify all items matching a condition | $[identifier] + arrayFilters | Matched document but no modified items |
| Add a new item | $push | Duplicate SKU on repeated requests |
| Add a tag without duplicate values | $addToSet | Compares entire embedded object, not business key |
| Remove items by SKU | $pull | Removes all elements matching the condition |
| Remove the last element | $pop | Depends on array order, does not filter by SKU |
| Update two collections | Transaction or coordination protocol | Single-document atomicity does not span collections |

### 18.1. Is “Replacing the Entire Array” Always Wrong?

No. When the business requirement genuinely defines **the new list as the source of truth**, replacing the entire array can be the right and simplest choice. What matters is validating input data, Order status, current version, and the impact of concurrent requests.

### 18.2. Is “Updating a Single Element” Always Right?

No. If changing one item violates total price, maximum quantity, promotion rules, or order status, updating an individual field can leave related fields out of sync. You may need **a single atomic update with multiple operators** on the same document, an update pipeline, or a recalculation workflow with optimistic locking.

Choose the write scope based on the **business invariants to protect**, not the fewest lines of code.

## 19. Integration Testing with MongoTemplate

Unit tests that merely mock UpdateResult do not verify whether MongoDB understands **items.$.quantity** or whether the converter maps OrderItem correctly. You should write integration tests against a real database, such as MongoDB Testcontainers configured for Spring Boot tests.

A test verifying that **only the selected item increments its quantity**:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import com.mongodb.client.result.UpdateResult;

@DataMongoTest
class OrderArrayUpdateTest {

    @Autowired
    MongoTemplate template;

    @Test
    void incrementsOnlyMatchingItem() {
        OrderDocument inserted = template.insert(
            new OrderDocument(
                null,
                "TEST-" + UUID.randomUUID(),
                "DRAFT",
                List.of(
                    new OrderItem("BOOK-001", 2, 159_000L),
                    new OrderItem("PEN-002", 1, 12_000L)
                ),
                Instant.now()
            )
        );

        ObjectId orderId = inserted.id();
        assertThat(orderId).isNotNull();

        try {
            Query query = Query.query(
                Criteria.where("_id").is(orderId)
                    .and("status").is("DRAFT")
                    .and("items.sku").is("BOOK-001")
            );

            UpdateResult result = template.updateFirst(
                query,
                new Update().inc("items.$.quantity", 1),
                OrderDocument.class
            );

            assertThat(result.getMatchedCount()).isEqualTo(1);
            assertThat(result.getModifiedCount()).isEqualTo(1);

            OrderDocument loaded = template.findById(
                orderId, OrderDocument.class
            );

            assertThat(loaded).isNotNull();
            assertThat(loaded.items()).hasSize(2);
            assertThat(loaded.items().get(0).quantity()).isEqualTo(3);
            assertThat(loaded.items().get(1).quantity()).isEqualTo(1);
            assertThat(loaded.items().get(0).unitPriceMinor())
                .isEqualTo(159_000L);
        } finally {
            template.remove(
                Query.query(Criteria.where("_id").is(orderId)),
                OrderDocument.class
            );
        }
    }
}
~~~

The test uses a dedicated Order per run and cleans up the document in finally. **Do not run against production.** It verifies that BOOK increases from 2 to 3 while PEN keeps quantity=1, and the unit price is preserved.

### 19.1. Additional Important Test Cases

| Test Case | What to Verify |
| --- | --- |
| $set entire array | New items accurately replace the old list |
| $inc positional $ | Only the first matching item is modified |
| $[] | All elements are updated as expected |
| $[line] and arrayFilters | Only elements matching the filter change |
| SKU missing from Order | UpdateResult reflects no changes per the query |
| Order status other than DRAFT | Not updated even if ID and SKU exist |
| Calling $push twice | Risk of duplicates if uncontrolled |
| $addToSet duplicate tag | Does not create duplicate strings |
| $pull by SKU | Removes all matching items |
| Two concurrent $inc requests on the same item | Cumulative result if both succeed |
| Two requests replacing array from stale snapshot | Blocked by version check if required by the system |
| Quantity=1, decrement by 1 with filter quantity>1 | Does not drop to 0 |
| Empty array and document missing items | Define policy and test update behavior |

### 19.2. Inspecting Raw BSON Directly

If behavior looks wrong, inspect the BSON of an Order in the **test database**:

~~~javascript
db.orders.findOne(
  { _id: ObjectId("507f1f77bcf86cd799439011") },
  { orderNumber: 1, status: 1, items: 1 }
);
~~~

Check the values and BSON types of items.quantity and items.unitPriceMinor, and look for duplicate SKUs or missing fields. When Java record field names differ from BSON, verify @Field and the mapping structure.

## 20. Troubleshooting Common Issues

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Incrementing one item loses another item | Replaced whole array from stale data | Use targeted update or version check |
| Positional $ finds no element | Query lacks an items match condition or SKU is wrong | Check filter and actual BSON |
| Two duplicate SKUs but only one item updated | Positional $ selects only the first element | Enforce unique SKU invariant or use arrayFilters |
| All items changed | Used $[] instead of $[line] | Review the update path |
| No item changed even though Order matched | arrayFilters matched no element | Check identifier, field names, and modifiedCount |
| Calling $push twice produces two duplicate items | $push does not deduplicate | Design idempotency/business guard |
| $addToSet still adds object with same SKU | The two embedded documents are not identical | Do not use it as unique-by-sku |
| Removing one item deletes all items with same SKU | $pull removes all matching elements | Define exact data and filter criteria |
| $unset does not shorten the array | Unsetting a position differs from $pull | Use $pull to remove elements |
| Quantity becomes 0 or negative | No filter checking minimum value | Use $elemMatch and conditional update |
| updateFirst matched=1, modified=0 | Update changed no data or arrayFilters matched nothing | Distinguish matchedCount from modifiedCount |
| Stale error on save | @Version detected write conflict | Reload and reconcile the operation |
| Reading partial entity then saving loses fields | Rewrote document from incomplete projection | Use read DTO/projection and targeted field updates |
| Reactive increments quantity twice | Subscribed/retried $inc command twice | Guard idempotency; avoid duplicate manual subscribes |
| Slow operations on large arrays | Large document, index maintenance, contention | Measure metrics, consider splitting into a separate collection |

When investigating, follow this order:

1. Confirm the document has the right _id, status, and items array schema.
2. Clarify whether the intent is **replacing the entire array** or **modifying an element**.
3. Check whether the Query selects the right document and item.
4. Check whether the update path uses **$**, **$[]**, or **$[identifier]**.
5. If using arrayFilters, verify the identifier matches the path.
6. Inspect both matchedCount and modifiedCount; do not conflate them.
7. If concurrent requests exist, check optimistic locking, retries, and idempotency.
8. Reproduce with a test MongoDB fixture; only then examine indexes/explain and contention.

## 21. Practice Exercises

### Exercise 1: Choosing the Right Operation

The API requires **replacing the entire items list** with a user-confirmed list. Should you use $set items or $inc quantity?

**Suggested Answer:** $set items or a replace strategy with a version check, because the business requirement is replacing the complete list. Validate inputs, check Order status, and handle concurrent modifications.

### Exercise 2: Incrementing Exactly One Item

An Order has items BOOK-001 quantity=2 and PEN-002 quantity=1. Write an update to increment BOOK-001 by one while leaving PEN unchanged.

~~~javascript
db.orders.updateOne(
  { _id: orderId, status: "DRAFT", "items.sku": "BOOK-001" },
  { $inc: { "items.$.quantity": 1 } }
);
~~~

**Explanation:** positional $ identifies the first matching item, and $inc updates quantity on the server without rewriting the array.

### Exercise 3: Comparing $ and $[]

An Order has three items. If you run **$inc: { "items.$[].quantity": 1 }**, what happens?

**Answer:** The quantity of **all three items** is incremented by one, because $[] targets every element. If you only want one SKU, use positional $ or arrayFilters.

### Exercise 4: arrayFilters

Write a command to update **all items with sku=BOOK-001**, not just the first element.

~~~javascript
db.orders.updateOne(
  { _id: orderId },
  { $inc: { "items.$[line].quantity": 1 } },
  { arrayFilters: [{ "line.sku": "BOOK-001" }] }
);
~~~

### Exercise 5: Does $addToSet Enforce Uniqueness by SKU?

The array contains {sku:"BOOK-001",quantity:1}. You use $addToSet to add {sku:"BOOK-001",quantity:2}. Will MongoDB automatically recognize these as the same SKU?

**Answer:** No. $addToSet compares elements by the full embedded document value, not by the sku business key. A separate mechanism is needed to guarantee unique SKUs.

### Exercise 6: Removing an Item

To remove every item with SKU PEN-002, use $pop or $pull?

**Answer:** Use **$pull: {items:{sku:"PEN-002"}}**. $pop only removes the first/last element of the array and does not filter by SKU.

### Exercise 7: Lost Update

Requests A and B both read the initial items. A increments BOOK, B increments PEN, and then both use $set on the entire array. Why can a change be lost?

**Answer:** Each request rewrites an array built from a stale snapshot; the later write can overwrite the earlier write's changes. Use targeted updates or optimistic locking with expectedVersion.

### Exercise 8: Quantity Must Not Drop to 0

How do you decrement quantity only when the item has the matching SKU and quantity > 1?

**Hint:** The Query uses **items.$elemMatch** with both sku and quantity > 1, and the update uses **$inc: {"items.$.quantity":-1}**. Both conditions must hold on the same array element.

### Exercise 9: matchedCount Differs from modifiedCount

A command uses arrayFilters for a SKU not present in items, while the _id filter matches the Order. Is matchedCount=1, modifiedCount=0 abnormal?

**Answer:** No. matchedCount indicates the parent document matched; it does not prove an array element satisfied the filter. Check modifiedCount and define error-reporting semantics per business requirements.

### Exercise 10: Reactive Retry

A request increments quantity with $inc; the server applies it, but the response times out. The client retries the same request. Why is this risky?

**Answer:** $inc is not idempotent; the retry can increment quantity a second time. Design idempotency/deduplication instead of assuming retries are always safe.

## 22. Key Principles to Remember

1. **Replacing an entire array and modifying an element express two different intents.** $set items replaces every element; path-based updates target the exact sub-field.
2. **repository.save on a loaded entity can write broadly** and does not automatically merge items by SKU.
3. **Positional $** modifies the first matching element, **$[]** modifies all elements, and **$[identifier]** modifies elements matching arrayFilters.
4. **$inc** fits additive/subtractive quantity changes and avoids lost updates from computing against stale reads, though it does not enforce business bounds on its own.
5. **$push** appends elements, **$addToSet** avoids identical elements, **$pull** removes all matching elements, and **$pop** removes the first/last element by position.
6. **A single update on one document is atomic**, but multi-step read → modify → write flows still require concurrency protection.
7. **@Version or expectedVersion** is useful when replacing arrays from a snapshot; do not assume every query/update is protected the same way as repository.save.
8. **UpdateResult must be inspected.** matchedCount=1 does not necessarily mean an array element was modified.
9. **Multiple documents/collections require a dedicated consistency strategy**, potentially involving transactions and conditional update rules.
10. **Large arrays and indexes have costs**, so choose embedded vs. referenced models based on size, ownership, and access patterns.
11. **Reactive does not make $inc idempotent**; avoid block(), duplicate subscriptions, and blind retries.
12. **Test against real MongoDB** to prove the right elements are modified and unrelated elements remain intact.

Accurately distinguishing **full array replacement** from **element-by-element updates** helps **SPRING_DATA_MONGODB** applications express business intent cleanly, reduce the risk of data loss under concurrent updates, and choose safer, more efficient MongoTemplate, repository, or reactive operations.
