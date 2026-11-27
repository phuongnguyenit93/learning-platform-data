# Saving Referenced Documents Separately and Cascade Limitations

## 1. Why Save Referenced Documents Separately?

MongoDB has two common ways to organize related data: **embedding** data inside a single document or **splitting into multiple documents** and maintaining links via a reference value. Embedding fits when data is usually read and updated together and has a lifecycle tied to the parent document. Referencing fits when the related object has an **independent identity, lifecycle, and access permissions**, and may be shared across multiple documents.

For example, an order needs to know which customer placed it. A customer can exist before any order, update their profile independently, and be referenced by many orders. If every order stored a copy of the entire customer profile, updating contact details might require updating many records. Therefore, the **customers** and **orders** model is a natural candidate for cross-collection referencing.

In the **SPRING_DATA_MONGODB** module, this topic relates directly to document mapping, persisting data with **`MongoTemplate`** or **repositories**, query and aggregation design, indexing, transactions, reactive access, testing, and performance diagnostics. The most important point is: **saving a reference does not mean Spring Data MongoDB automatically cascades saves, updates, or deletes to referenced documents**.

After this lesson, you will be able to:

1. Decide when to split documents instead of embedding.
2. Save links using manual IDs, **`@DocumentReference`**, or **`@DBRef`**.
3. Distinguish saving a reference from automatically saving the target document.
4. Build rules for creating, updating, and deleting references without unintended data loss.
5. Recognize **dangling references**, **orphans**, repeated-read risks, and transaction requirements.
6. Design indexes, queries, tests, and monitoring for relationships across collections.

## 2. Running Example: customers and orders

The **customers** collection stores customer profiles:

~~~javascript
// customers
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  displayName: "Lan",
  email: "lan@example.test",
  status: "ACTIVE"
}
~~~

The **orders** collection stores orders and a reference to the customer:

~~~javascript
// orders
{
  _id: ObjectId("507f1f77bcf86cd799439012"),
  orderNumber: "ORD-1001",
  customerId: ObjectId("507f1f77bcf86cd799439011"),
  totalMinor: NumberLong("199000"),
  createdAt: ISODate("2025-05-20T09:00:00Z")
}
~~~

Here, **`customerId`** is a BSON ObjectId field inside the order. The order document stores only the link key, not the full `Customer`. MongoDB does not automatically treat `customerId` as a foreign key like a relational database. The application and operational processes must protect the validity of this link.

~~~mermaid
flowchart LR
    C["customers / Customer"] -->|"_id = C1"| K["ObjectId C1"]
    O["orders / Order"] -->|"customerId = C1"| K
    O -->|"many orders"| O2["Referencing the same customer"]
~~~

**An ID stored in document A does not guarantee document B still exists.** If the `Customer` is deleted, the `Order` retains the old `customerId` unless the application explicitly handles it.

### 2.1. Distinguishing Technical IDs from Business Data

- **`customerId`** is a technical identifier for retrieving `Customer`.
- **`displayName`** and **`email`** belong to `Customer`; changes to them do not necessarily require rewriting every `Order`.
- **`orderNumber`** is the business key of `Order`, which may require its own unique index.
- **`totalMinor`** is the monetary amount in the system's smallest currency unit; this value type is unrelated to how references are stored.

In many systems, an order still needs a **snapshot** of certain purchase-time details, such as recipient name or shipping address. Snapshots serve historical accuracy and should not automatically sync with the live `Customer`. Thus, a single document can store both **`customerId`** as a reference and an embedded **`shippingAddressSnapshot`**.

## 3. Embedding vs. Referencing: Choosing by Data Lifecycle

| Criterion | Embed in parent document | Split documents and reference |
| --- | --- | --- |
| Lifecycle | Component typically belongs exclusively to parent | Target has an independent lifecycle |
| Typical query | Data is usually needed together | Target can be read independently |
| Updates | One document can update atomically | May need to update multiple documents |
| Sharing | Duplicated across parents if embedded repeatedly | Many parents point to one target |
| Scale | Must watch document size limits and growing arrays | Easier to manage larger datasets, though increases reads |
| Deletion | Embedded data disappears when parent is deleted | Target document survives independently unless explicitly deleted |
| Consistency | Fields in one document update atomically | Requires a protocol when modifying multiple documents |

Sensible examples:

- Embed small **items** inside `Order` because line items belong to the order and are usually read together.
- Reference **Customer** from `Order` because customers exist independently and place many orders.
- Reference **Product** from `Order` to link to the live catalog, while still storing **purchase-time name and unit price** in item snapshots so history never changes.

Never assume referencing is always better than embedding. Decisions should start from **access patterns and business boundaries**, then select the mapping mechanism.

## 4. Three Reference Representations in Spring Data MongoDB

Spring Data MongoDB supports several ways to store links between documents:

| Storage approach | Typical BSON in Order | Java layer | Characteristics |
| --- | --- | --- | --- |
| **Manual ID** | `customerId: ObjectId(...)` | `ObjectId customerId` | Simple, transparent; application loads Customer manually |
| Default **`@DocumentReference`** | `customer: ObjectId(...)` | `Customer customer` | Spring Data supports resolving target; usually stores target ID |
| **`@DBRef`** | `customer: { $ref: "customers", $id: ObjectId(...) }` | `Customer customer` | Stores BSON DBRef with collection/ID metadata |

The table illustrates the common case where `Customer`'s ID is a BSON ObjectId. **`@DocumentReference`** also supports custom `lookup` and pointer formatting; when configured that way, the stored value may differ from a plain ID. **`@DBRef`** stores a DBRef structure and must not be confused with a regular ObjectId field.

Common to all three: **saving an `Order` does not automatically create an unpersisted `Customer`**. There is no default cascade-save or cascade-delete for these references as learners coming from some relational ORMs might expect.

### 4.1. No Automatic Foreign Keys

MongoDB does not automatically check that `Customer` exists simply because `Order` has `customerId`. Schema validation can verify that `customerId`'s **data type** is `ObjectId`, but cannot prove a matching record exists in the `customers` collection.

Example of a BSON-type-valid document with a non-existent reference:

~~~javascript
{
  orderNumber: "ORD-404",
  customerId: ObjectId("000000000000000000000001")
}
~~~

The application must decide how to handle this: reject `Order` creation if `Customer` is missing, return a “Customer not found” state, retain historical orders via snapshots, or apply another business-specific strategy.

## 5. Approach 1: Store IDs Manually and Load Target Documents

This option is straightforward, easy to test, and often ideal when the system needs tight control over query count.

### 5.1. Customer Entity

~~~java
package com.example.sales;

import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customers")
public record CustomerDocument(
    @Id ObjectId id,
    String displayName,
    String email
) {}
~~~

### 5.2. Order Entity with customerId

~~~java
package com.example.sales;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id ObjectId id,
    String orderNumber,
    ObjectId customerId,
    long totalMinor,
    Instant createdAt
) {}
~~~

Both root entities have their own collections and IDs. **`customerId`** is not annotated with `@Id` because it is a link key, whereas **`id`** maps to `Order`'s `_id`. When saved, Spring Data MongoDB writes `customerId` as a regular BSON field.

### 5.3. Repositories for Both Aggregates

~~~java
package com.example.sales;

import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CustomerRepository
        extends MongoRepository<CustomerDocument, ObjectId> {
}

public interface OrderRepository
        extends MongoRepository<OrderDocument, ObjectId> {
}
~~~

Example creating and saving each document:

~~~java
CustomerDocument customer = customerRepository.insert(
    new CustomerDocument(null, "Lan", "lan@example.test")
);

OrderDocument order = orderRepository.insert(
    new OrderDocument(
        null,
        "ORD-1001",
        customer.id(),
        199_000L,
        Instant.now()
    )
);

ObjectId customerId = customer.id();
ObjectId orderId = order.id();
~~~

Note the sequence: `Customer` is persisted first and receives an ID, and only then does `Order` store the corresponding `customerId` value. **Calling only `orderRepository.insert(order)` does not save the customer.**

The two operations affect two documents and therefore **do not form an atomic transaction** unless an appropriately configured MongoDB transaction is used. If saving `Customer` succeeds while creating `Order` fails, `Customer` remains in the database—which may be completely normal business behavior.

### 5.4. Reading Order Then Loading Customer

~~~java
import java.util.Optional;
import org.bson.types.ObjectId;

public record OrderDetails(
    String orderNumber,
    String customerName,
    long totalMinor
) {}

public Optional<OrderDetails> loadDetails(ObjectId orderId) {
    Optional<OrderDocument> orderResult = orderRepository.findById(orderId);
    if (orderResult.isEmpty()) {
        return Optional.empty();
    }

    OrderDocument order = orderResult.get();
    CustomerDocument customer = customerRepository.findById(order.customerId())
        .orElseThrow(() -> new IllegalStateException(
            "Order references missing customer: " + order.customerId()
        ));

    return Optional.of(new OrderDetails(
        order.orderNumber(),
        customer.displayName(),
        order.totalMinor()
    ));
}
~~~

The example assumes this method sits in a service with both repositories injected. It performs **two explicit reads** and checks if `Customer` no longer exists. In real applications, the policy for broken references must match business rules: throw a data error, return a historical snapshot, or handle asynchronously.

### 5.5. Querying with MongoTemplate

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public OrderDocument findOrderForCustomer(
        MongoTemplate template, ObjectId customerId) {
    Query query = Query.query(
        Criteria.where("customerId").is(customerId)
    );
    return template.findOne(query, OrderDocument.class);
}
~~~

This queries by the link key. `MongoTemplate` infers the **orders** collection from `OrderDocument`'s `@Document` annotation and does not need to resolve `Customer` to filter. For applications with frequent queries by `customerId`, create a suitable index on that field.

## 6. Approach 2: @DocumentReference

**`@DocumentReference`** lets Spring Data MongoDB hold a reference in a Java object and load the target document via a lookup query. Under common default settings, the value stored in the parent is the **target document's ID**.

Illustrative definition of another Order type:

~~~java
import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.DocumentReference;

@Document(collection = "orders_with_document_reference")
public record OrderWithDocumentReference(
    @Id ObjectId id,
    String orderNumber,
    @DocumentReference CustomerDocument customer,
    Instant createdAt
) {}
~~~

Once the saved `Customer` has an ObjectId, `Order`'s BSON looks like:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439012"),
  orderNumber: "ORD-1001",
  customer: ObjectId("507f1f77bcf86cd799439011"),
  createdAt: ISODate("2025-05-20T09:00:00Z")
}
~~~

Reading `OrderWithDocumentReference` through Spring Data can resolve the reference value into `CustomerDocument`. Remember two points:

1. **The target document must be persisted per application policy.** Attaching a brand-new unsaved `Customer` to `Order` does not mean Spring Data inserts `Customer` automatically.
2. Resolution can emit additional queries. Reading a large list of `Order`s and accessing each `Order`'s `Customer` can cause read counts to surge.

### 6.1. Lazy Loading

You can request deferred reference resolution:

~~~java
@DocumentReference(lazy = true)
private CustomerDocument customer;
~~~

Lazy loading can reduce reads when the application never accesses `Customer`, yet touching the property later triggers a query and can surface errors later. Proxies also have constraints related to Java types, serialization, the module system, and runtime environments. Test thoroughly before broad adoption.

Do not treat `lazy = true` as an automatic cure for the **N+1 queries** problem. If an API still accesses `Customer` on every `Order` in a list, total query count remains high; batch queries or aggregations may be needed.

### 6.2. Custom Lookups

`@DocumentReference` also supports configuring **`lookup`** to link via a business field or custom criteria when special requirements exist. However, linking by a non-`_id` value requires:

- Ensuring uniqueness of the chosen reference key.
- Defining key-change policies and matching indexes.
- Verifying the exact BSON value stored by the parent.
- Testing what happens when the reference can no longer locate the target document.

Do not adopt complex custom lookups merely to mask inconsistent ID design.

## 7. Approach 3: @DBRef

**`@DBRef`** represents references using the MongoDB DBRef format. Example:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.DBRef;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders_with_dbref")
public record OrderWithDbRef(
    @Id ObjectId id,
    String orderNumber,
    @DBRef CustomerDocument customer
) {}
~~~

BSON may represent the reference as:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439012"),
  orderNumber: "ORD-1001",
  customer: {
    $ref: "customers",
    $id: ObjectId("507f1f77bcf86cd799439011")
  }
}
~~~

This illustrates the DBRef representation in `mongosh`; actual components also depend on encoding and target database. Spring Data uses DBRef metadata to locate the referenced document on read.

**`@DBRef` does not automatically enable cascades.** When `Order` has a `@DBRef` to `Customer`, saving `Order` does not save a new `Customer`; deleting `Order` does not delete `Customer`. DBRef also does not mean MongoDB server enforces foreign keys or automatically JOINs on every query.

### 7.1. @DocumentReference or @DBRef?

| Criterion | @DocumentReference | @DBRef |
| --- | --- | --- |
| Default stored data | Usually target ID | DBRef containing collection and ID |
| Dereferencing | Spring Data via lookup | Spring Data via DBRef metadata |
| Default cascade save/delete? | No | No |
| Supports lazy? | Yes, depending on mapping | Yes, depending on mapping |
| Lookup flexibility | Customizable | Tied to DBRef representation |
| Complexity | Can be close to manual IDs | Adds DBRef structure |

For new models, **manual IDs** or **`@DocumentReference`** are generally easier to manage unless compatibility with an existing DBRef system is required. If a project already stores DBRefs, changing annotations **does not automatically convert legacy data** into plain ObjectIds; a migration must be designed.

## 8. What Is Cascading and Its Most Important Limitation

In application development, **cascade** generally refers to an operation on a parent object automatically propagating to related objects: persist, merge/update, or remove. Developers coming from relational ORMs may expect cascading across entity associations. With Spring Data MongoDB, distinguish clearly:

- **Embedded object**: part of the same BSON document. Writing the parent document writes the embedded data inside that same document. Deleting the parent removes embedded data as well, since it is not an independent document.
- **Referenced document**: lives in an independent collection/document. Writing or deleting the parent touches only the parent unless **application code explicitly invokes extra operations** on the target.

~~~mermaid
flowchart TD
    A["Save Order referencing Customer"] --> B["Save Order document"]
    B --> C{"Auto-save Customer?"}
    C -->|"Default: no"| D["Customer exists or not depending on separate operation"]
    E["Delete Order"] --> F["Delete only Order document"]
    F --> G["Customer is preserved"]
~~~

This boundary prevents two opposite bugs:

1. **Believing saving `Order` automatically saves a new `Customer`**, leaving `Order` holding an ID pointing to a nonexistent record.
2. **Implementing an unchecked cascade delete**, causing deletion of a single `Order` to delete a `Customer` used by hundreds of other `Order`s.

### 8.1. Anti-Pattern: Expecting Cascade-Save

~~~java
// Used with the OrderWithDocumentReference entity above.
CustomerDocument notPersisted = new CustomerDocument(
    null, "Mai", "mai@example.test"
);

OrderWithDocumentReference order = new OrderWithDocumentReference(
    null, "ORD-2001", notPersisted, Instant.now()
);

// Wrong intent: do not expect this call to auto-insert Customer.
orderWithRefRepository.insert(order);
~~~

Depending on mapping and ID state, referencing an unpersisted object can throw an error or write an invalid reference value. Never rely on accidental converter behavior. **The right rule is to save or verify `Customer` first**, and only then create the `Order` referencing the existing ID/`Customer`.

### 8.2. Intentional Explicit Saving

~~~java
CustomerDocument customer = customerRepository.insert(
    new CustomerDocument(null, "Mai", "mai@example.test")
);

OrderWithDocumentReference order = new OrderWithDocumentReference(
    null, "ORD-2001", customer, Instant.now()
);

OrderWithDocumentReference savedOrder =
    orderWithRefRepository.insert(order);
~~~

The repositories in the example are dependencies declared and injected into a service. The two `insert` statements are **two explicit operations**, not default cascading. If they must form a single atomic unit, see the transaction section below.

## 9. Why Cascade-Delete Is Very Dangerous for Shared References

Suppose Customer **C1** has three orders **O1**, **O2**, and **O3**:

~~~mermaid
flowchart LR
    O1["Order O1"] --> C1["Customer C1"]
    O2["Order O2"] --> C1
    O3["Order O3"] --> C1
~~~

If logic deleting `O1` also calls `customerRepository.deleteById(C1)`, then `O2` and `O3` will retain references whose target no longer exists. That is usually a severe design flaw.

**Practical rule:** When a target has an independent lifecycle or can be shared, deleting a parent **must never cascade-delete the target** without a proven business invariant and constraint checks.

| Operation | Default reference behavior | Typically sensible policy |
| --- | --- | --- |
| Create `Order` linked to `Customer` | Creates only `Order` | Verify `Customer` exists before writing |
| Edit `Customer` name | Edits only `Customer` | `Order` continues referencing the same ID |
| Delete one `Order` | Deletes only `Order` | Retain `Customer` when independent |
| Delete `Customer` with existing `Order`s | No default foreign-key guard | Reject, soft-delete, or enforce business constraint |
| Delete `Customer` with no `Order`s | Deletes only `Customer` | May allow after checking condition |
| Delete an embedded `OrderItem` | Modifies/removes inside `Order` | Same-document change, not a separate collection delete |

Distinguish **removing an object from a reference array** from **deleting the target document**. Removing a `productId` from an `Order`'s `productIds` list only detaches the link; it is not a command to delete `Product`.

## 10. Dangling References and Orphans: Two Different Situations

A **dangling reference** is a reference from an existing document to a nonexistent target:

~~~javascript
// Order still in orders collection.
{ orderNumber: "ORD-404", customerId: ObjectId("000000000000000000000001") }

// Yet customers has no document with that _id.
~~~

An **orphan document** is a document no longer referenced by any other document when business rules expect it to belong to an owner—for instance, a temporary attachment no longer attached to any order. Being unreferenced is **not always an error**: a `Customer` may have placed zero orders yet still be a valid customer.

Each data type needs its own policy:

- For **`Customer`**, having no referencing `Order`s can be completely normal.
- For an **attachment belonging strictly to one `Order`**, an unlinked attachment may need periodic cleanup.
- For an **audit record**, even after the business entity is deleted, retaining the record may be a compliance requirement.

Thus, there is no universal “if unreferenced, delete it” rule applicable to every collection.

### 10.1. Checking References Manually

With the `customerId` model, you can reconcile `Order` and `Customer` records via aggregation:

~~~javascript
db.orders.aggregate([
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "matchedCustomers"
    }
  },
  { $match: { matchedCustomers: { $size: 0 } } },
  { $project: { orderNumber: 1, customerId: 1 } }
]);
~~~

This pipeline finds `Order`s without a matching `Customer`. It is useful for data audits, though on very large collections it can be resource-intensive. Consider running in batches during off-peak windows and ensuring indexes exist on join fields. `customers` has a default `_id` index; for queries querying `Order` by `customerId`, consider a dedicated index on `orders`.

### 10.2. MongoDB Queries Do Not Automatically Guard References

Operations like `find`, `updateOne`, or `insertOne` can succeed even when `customerId` points to a nonexistent value. Only when application code, audit jobs, or reference resolution logic demands `Customer` does the error surface. Never treat the ability to read `Order` as proof that `Customer` still exists.

## 11. Controlled Link Deletion and Reassignment

### 11.1. Delete Order, Keep Customer

~~~java
public void deleteOrder(ObjectId orderId) {
    orderRepository.deleteById(orderId);
}
~~~

This operates solely on the **orders** collection. It does not require deleting the `Customer` document and needs no cascading because `Customer` has an independent lifecycle.

### 11.2. Reassign Order's Customer

Example with `MongoTemplate` and the `customerId` model:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import com.mongodb.client.result.UpdateResult;

public boolean reassignCustomer(
        MongoTemplate template, ObjectId orderId, ObjectId newCustomerId) {

    if (!template.exists(
            Query.query(Criteria.where("_id").is(newCustomerId)),
            CustomerDocument.class)) {
        throw new IllegalArgumentException("Customer does not exist");
    }

    Query query = Query.query(Criteria.where("_id").is(orderId));
    Update update = new Update().set("customerId", newCustomerId);

    UpdateResult result = template.updateFirst(
        query, update, OrderDocument.class
    );
    return result.getMatchedCount() == 1;
}
~~~

The method illustrates **checking before reassigning**, yet checking existence and updating are two separate operations. Another process could delete `Customer` after the check and before the `Order` update. If strict invariants are required, use transactions/appropriate coordination protocols or disallow deleting referenced `Customer`s rather than relying on a single existence check.

### 11.3. Deleting a Customer Used by Many Orders

One policy is rejecting deletion when orders remain:

~~~java
boolean hasOrders = mongoTemplate.exists(
    Query.query(Criteria.where("customerId").is(customerId)),
    OrderDocument.class
);

if (hasOrders) {
    throw new IllegalStateException(
        "Cannot delete customer referenced by orders"
    );
}

customerRepository.deleteById(customerId);
~~~

This check has a similar **race condition**: another writer could create a new `Order` after `hasOrders` is evaluated but before `Customer` is deleted. In systems requiring strong invariants, all writers and delete flows must follow the same coordination protocol; simply wrapping this snippet in a transaction must still account for preventing concurrent inserts from creating orphans under MongoDB's isolation model.

A common business approach is **soft delete** or setting `status = INACTIVE`, then blocking new `Order` creation for inactive `Customer`s. This preserves order history and keeps lifecycles independent.

## 12. Do Transactions Make Cascading Safer?

MongoDB supports multi-document transactions on supported server configurations. Spring Data MongoDB integrates a transaction manager to group save/delete operations into a transaction:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTxConfig {
    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
~~~

Example of a service creating a `Customer` and first `Order` in the same transaction when business rules require both to succeed or fail together:

~~~java
import java.time.Instant;
import org.springframework.transaction.annotation.Transactional;

@Transactional
public OrderDocument createCustomerAndFirstOrder(
        String customerName, String orderNumber) {

    CustomerDocument customer = customerRepository.insert(
        new CustomerDocument(null, customerName, null)
    );

    return orderRepository.insert(
        new OrderDocument(
            null,
            orderNumber,
            customer.id(),
            0L,
            Instant.now()
        )
    );
}
~~~

The example assumes the method is inside a Spring-managed service, a transaction manager is configured, and the MongoDB deployment supports transactions. Ensure calls go through the Spring proxy so `@Transactional` takes effect. In environments without transaction support or with misconfiguration, the annotation alone does not make two operations atomic.

Transactions group **explicitly coded writes** into a commit/rollback unit. They **do not automatically enable `@DBRef`/`@DocumentReference` cascades**, create foreign keys, or remove the need to coordinate concurrent reference creation/deletion flows.

### 12.1. Do Not Automatically Wrap Every Reference in a Transaction

Multi-document transactions have operational prerequisites and overhead. When `Customer` already exists, a new `Order` is created, and a failed `Order` creation does not need to roll back `Customer`, there is usually no reason to wrap both operations in a transaction.

When emitting events to external systems or synchronizing across services, a MongoDB transaction does not guarantee emails/events were dispatched atomically with the commit. Consider **outbox**, **saga**, or compensating workflows when cross-system consistency is required.

## 13. Performance Diagnostics: N+1, Queries, and Indexes

Suppose an API loads 100 `Order`s and each has a referenced `Customer`. If code runs 100 individual customer lookups after reading the orders, read count rises sharply—a form of **N+1 queries**.

| Read pattern | Typical read count | Key consideration |
| --- | --- | --- |
| Load Orders then `findById` per Customer | 1 + N (before caching/duplicate-ID optimization) | Simple, yet many round trips |
| Load Orders, collect `customerId`s, query customers with `$in` | Typically 2 main queries | Must join results and handle missing IDs |
| `$lookup` aggregation | One server-side pipeline | Needs indexes; watch memory/size/pipeline complexity |
| `@DocumentReference` or `@DBRef` auto-resolve | Depends on mapping and access pattern | Never assume only one query occurs |

### 13.1. Collecting IDs for Batch Reads

With manual `ObjectId` references, a common strategy is:

1. Read the `Orders` page according to filter and page size.
2. Collect distinct **`customerId`** values.
3. Query `Customer`s by the ID set using **`$in`**.
4. Build a **`customerId → Customer`** map.
5. Merge results and handle unresolved references.

Example `MongoTemplate` query fetching `Customer`s by multiple IDs:

~~~java
import java.util.Collection;
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<CustomerDocument> loadCustomers(
        MongoTemplate template, Collection<ObjectId> ids) {
    if (ids.isEmpty()) {
        return List.of();
    }
    return template.find(
        Query.query(Criteria.where("_id").in(ids)),
        CustomerDocument.class
    );
}
~~~

This reduces round trips; still limit page size and ID batch size to avoid oversized queries. When multiple `Order`s share a `Customer`, that `Customer` is fetched only once in the batch.

### 13.2. `$lookup` Aggregation

Example joining `Order` and `Customer` server-side:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      createdAt: { $gte: ISODate("2025-01-01T00:00:00Z") }
    }
  },
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
      orderNumber: 1,
      customerId: 1,
      customerName: "$customer.displayName",
      totalMinor: 1
    }
  }
]);
~~~

**`$lookup`** is a pipeline join, not a cascade, and does not change how references are stored. When using `$lookup`, check output sizes, pre-join filtering, and index usage on the target collection.

### 13.3. Indexes for Link Keys

MongoDB creates an `_id` index for standard collections. In addition, when querying `Orders` by `Customer`, you can create:

~~~javascript
db.orders.createIndex({ customerId: 1, createdAt: -1 });

db.orders.find({
  customerId: ObjectId("507f1f77bcf86cd799439011")
}).sort({ createdAt: -1 }).explain("executionStats");
~~~

A compound index fits when the API frequently filters by `customerId` and sorts by `createdAt`, though actual effectiveness depends on data distribution and query patterns. Use **`explain("executionStats")`** to inspect keys/documents examined, winning plan, and latency. Never assume an index exists on the server solely because an annotation is present in code.

## 14. Referencing a List of Documents

An `Order` may link to multiple `Product`s. Manual ID storage:

~~~javascript
{
  orderNumber: "ORD-3001",
  productIds: [
    ObjectId("507f1f77bcf86cd799439021"),
    ObjectId("507f1f77bcf86cd799439022")
  ]
}
~~~

On the Java side:

~~~java
import java.util.List;
import org.bson.types.ObjectId;

public record OrderProductLinks(
    String orderNumber,
    List<ObjectId> productIds
) {}
~~~

This is a simple link model, yet you must decide:

- Can the same `Product` appear multiple times in `productIds`?
- Does element order carry business meaning?
- Are snapshots of `Product` details at order time needed?
- Can the list grow without bound and make the document too large?
- Is deleting a `Product` allowed while it still appears in historical `Order`s?

For large many-to-many relationships or links carrying their own attributes (such as roles or effective dates), consider a **link collection** instead of an ever-growing ID array. The choice depends on access patterns and business constraints rather than a fixed formula.

### 14.1. Removing a Reference Without Deleting Product

Example:

~~~javascript
db.orders.updateOne(
  { orderNumber: "ORD-3001" },
  {
    $pull: {
      productIds: ObjectId("507f1f77bcf86cd799439021")
    }
  }
);
~~~

`$pull` modifies only the array inside `Order`. The `Product` document with that `_id` still remains in the `products` collection.

## 15. Cascade Limitations in Reactive Access

With **`ReactiveMongoRepository`** or **`ReactiveMongoTemplate`**, referencing principles remain the same: parent and target are separate documents. Reactive code must explicitly orchestrate write order:

~~~java
import java.time.Instant;
import org.bson.types.ObjectId;
import reactor.core.publisher.Mono;

public Mono<OrderDocument> createOrderForCustomer(
        ObjectId customerId, String number) {

    return reactiveCustomerRepository.findById(customerId)
        .switchIfEmpty(Mono.error(
            new IllegalArgumentException("Customer does not exist")
        ))
        .flatMap(customer -> reactiveOrderRepository.insert(
            new OrderDocument(
                null, number, customer.id(), 0L, Instant.now()
            )
        ));
}
~~~

The example assumes two reactive repositories injected into a service. **`flatMap`** guarantees the `Order` insert executes only after reading `Customer` succeeds, yet both operations still **do not automatically share a transaction**. Between the check and write, concurrent modifications can still occur, just like in imperative access.

If reactive transactions are needed, configure **`ReactiveMongoTransactionManager`** and manage transaction context through appropriate reactive mechanisms. Never call `block()` inside a reactive chain simply to force reference operations to run synchronously.

When considering lazy reference resolution in reactive apps, closely inspect I/O and proxy behavior. A convenient mapping does not guarantee non-blocking reference resolution across every context; for flows demanding predictable performance, explicitly use reactive repositories and batch queries.

## 16. Testing Reference Relationships and Cascades

Do not test only that saving an `Order` succeeds. Your test suite should prove links are stored with the right types, read back accurately, and **do not propagate unintended side effects**.

| Scenario | What to verify |
| --- | --- |
| Create `Customer` then `Order` | `Order` stores exact `customerId`; `Customer` loads from ID. |
| Create `Order` with nonexistent `customerId` | Service rejects or handles per contract; never silently treats link as valid. |
| Save `Order` using `@DocumentReference` | Reference field has expected BSON shape; `Customer` is not unexpectedly inserted. |
| Save `Order` using `@DBRef` | BSON contains proper DBRef; saving `Order` does not cascade-save `Customer`. |
| Delete one `Order` | `Customer` is preserved. |
| Attempt to delete `Customer` with `Order`s | Restrict/soft-delete or controlled policy is enforced. |
| Pull `productId` from array | `Product` still exists; only the link changed. |
| Missing `Customer` from legacy data | Read/aggregation path handles dangling reference explicitly. |
| Read many `Order`s | Query count and latency stay within acceptable bounds. |
| Transaction rollback | Writes inside the transaction roll back properly; success is not published prior to commit. |

### 16.1. Example Test for No Cascade-Delete

Example using JUnit 5 and repositories with an isolated test database configuration:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import java.time.Instant;

@SpringBootTest
class OrderReferenceTest {
    @Autowired CustomerRepository customerRepository;
    @Autowired OrderRepository orderRepository;

    @Test
    void deletingOrderDoesNotDeleteCustomer() {
        CustomerDocument customer = customerRepository.insert(
            new CustomerDocument(null, "Test Customer", null)
        );

        try {
            OrderDocument order = orderRepository.insert(
                new OrderDocument(
                    null,
                    "TEST-" + java.util.UUID.randomUUID(),
                    customer.id(),
                    123L,
                    Instant.now()
                )
            );

            orderRepository.deleteById(order.id());

            assertThat(orderRepository.findById(order.id()))
                .isEmpty();
            assertThat(customerRepository.findById(customer.id()))
                .isPresent();
        } finally {
            customerRepository.deleteById(customer.id());
        }
    }
}
~~~

This test verifies that **deleting an `Order` does not delete `Customer`** under the manual ID model. It does not cover mid-delete failures, every reference annotation, or transactions. Add raw BSON fixtures to verify exact `@DocumentReference` and `@DBRef` structures in your project.

## 17. Warnings When Migrating from Embedded to Referenced

Suppose an older version embedded `Customer` inside `Order`:

~~~javascript
{
  orderNumber: "ORD-OLD",
  customer: {
    displayName: "Lan",
    email: "lan@example.test"
  }
}
~~~

The new version moves `Customer` to the `customers` collection and keeps only `customerId`:

~~~javascript
{
  orderNumber: "ORD-NEW",
  customerId: ObjectId("507f1f77bcf86cd799439011")
}
~~~

**Merely changing the Java field from `Customer` to `ObjectId` does not convert legacy BSON.** Migration requires:

1. Identifying whether each embedded `Customer` represents a shared entity or a historical snapshot.
2. Choosing a unique customer identification key before creating target documents; avoid creating duplicate customers for the same person.
3. Writing target `Customer`s and recording returned IDs.
4. Updating `Order`s to the new schema via conditional operations or transactions depending on invariants.
5. Deploying compatible readers while both structures coexist.
6. Verifying data, reconciling references, and dropping the old field only after the rollback window closes.

In particular, **historical snapshots** may need to stay even after a `Customer` reference exists. For instance, the shipping address at checkout must remain intact after the customer edits their current address.

## 18. Common Pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Saving `Order` does not create new `Customer` | Thinking `@DocumentReference` or `@DBRef` auto-cascades saves | Persist `Customer` separately, then save `Order`. |
| Deleting `Order` wipes out `Customer` | Service implements overly broad cascade-delete | Clarify ownership; remove cascades to shared entities. |
| `Order` has `customerId` yet fails to load `Customer` | Broken reference, ID type mismatch, or wrong DB/collection | Check BSON `_id` and `customerId`, and dangling reference policy. |
| Reading `Order` list is very slow | N+1 lookups, lazy resolution, or unindexed queries | Batch fetch, `$lookup`, inspect `executionStats`. |
| Switching `@DBRef` to `@DocumentReference` breaks old reads | Different BSON reference representations | Plan migration or compatible converters. |
| Cannot delete `Customer` despite zero `Order`s | Cleanup policy fails to separate orphans from independent entities | Define lifecycle rules and verify actual data. |
| Checking `Customer` existence still produces broken links | Race between existence check and deletion in another process | Use a consistent protocol, status/tombstone, or appropriate transaction. |
| Reference annotations still allow invalid IDs | MongoDB does not enforce foreign keys | Combine type validation with application existence checks. |
| Reactive pipeline causes unexpected I/O | Auto-resolving lazy references or calling `block()` | Design explicit reactive queries and measure real flows. |

## 19. Practice Exercises

### Exercise 1: Identify What Gets Persisted

Given the code:

~~~java
CustomerDocument customer = new CustomerDocument(
    null, "Lan", "lan@example.test"
);
OrderWithDocumentReference order = new OrderWithDocumentReference(
    null, "ORD-5001", customer, Instant.now()
);

orderWithRefRepository.insert(order);
~~~

**Question:** After inserting `Order`, can you conclude `Customer` now exists in `customers`?

**Answer:** No. `@DocumentReference` does not cascade-save by default. You must save or confirm `Customer` has a valid persisted identity before creating a referencing `Order`.

### Exercise 2: Deleting Parent vs. Target

Three `Order`s point to the same `Customer`. If one `Order` is deleted, should `Customer` be deleted?

**Answer:** Not by default. `Customer` has an independent lifecycle and is still used by the other `Order`s. Deleting an `Order` removes only that `Order`; customer deletion rules belong in a separate business workflow.

### Exercise 3: Finding Dangling References

Build a pipeline to find `Order`s whose `customerId` does not exist in `customers`.

**Hint:** use `$lookup` matching `customerId → _id` and filter for empty `matchedCustomers` arrays; for large datasets, consider performance and scheduled audit windows.

### Exercise 4: Optimizing N+1

An API fetches 100 `Order`s spanning only 12 distinct `customerId`s. How can reads reduce query count?

**Answer:** Collect the 12 unique IDs, query `customers` using `$in`, and map results back to each `Order`. Under suitable conditions, you can also evaluate a `$lookup` aggregation.

### Exercise 5: Choosing Embedding vs. Referencing

An `Order` has 3 line items, each storing the product name and price at purchase time; the `Product` catalog can change names and prices over time. What should you store?

**Hint:** store snapshots of name/price inside each embedded item to preserve history; if links to the live catalog are needed, also store a `productId` reference. Never overwrite historical prices when `Product` changes.

### Exercise 6: Do Transactions Guarantee Foreign Keys?

One service checks `Customer` exists and creates an `Order` inside a transaction. In another service, `Customer` can be deleted. Can you conclude broken references can never occur?

**Answer:** Not sufficient. You must examine the entire protocol for creating/deleting links and concurrency across writers, not merely whether one service has `@Transactional`. Deletion restrictions, soft-delete states, conditional updates, or a consistent coordination mechanism may be needed.

## 20. Key Principles to Remember

1. **A reference is a link between independent documents**; the link itself does not create a foreign key in MongoDB.
2. **Manual IDs, `@DocumentReference`, and `@DBRef`** have different storage representations and resolution mechanisms; choose based on storage contracts and query patterns.
3. **Spring Data MongoDB does not cascade-save or cascade-delete referenced documents by default**. If operations must propagate, design and execute them intentionally.
4. **Deleting a parent should never delete a shared target.** Separate link deletion policies from entity deletion policies.
5. **Dangling references differ from orphans**; handle each based on ownership and lifecycle rules per data type.
6. **Transactions only group explicitly coded operations**; they do not automatically provide cascades, foreign keys, or cross-service consistency.
7. **Reference queries must be measured for performance**. Consider batch fetching, `$lookup`, indexes, and avoiding N+1.
8. **Changing how references are stored is a BSON schema change**. Plan migrations, compatible readers, and historical data tests.
9. **Reactive access must still uphold the same invariants**, even when operations execute through `Mono`/`Flux`.

Understanding how to store referenced documents separately and respect cascade boundaries helps **`SPRING_DATA_MONGODB`** services protect each aggregate's lifecycle, prevent unintended data deletion, and build `MongoTemplate`, repository, transaction, and reactive flows that are controllable, testable, and diagnosable.
