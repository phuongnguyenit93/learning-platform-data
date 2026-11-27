# Broken References, Data Deletion, and Application Integrity Policies

> **Chapter:** Document References  
> **Module:** `SPRING_DATA_MONGODB` — using Spring Data MongoDB to connect, map documents, operate via `MongoTemplate` or repositories, and design queries, transactions, tests, and data diagnostics.  
> **Objective:** Identify broken references (dangling/orphan references), choose policies when deleting referenced documents, enforce policies at the application layer, detect inconsistent data, and handle concurrent writes.

## 1. Why Can References Between Documents Break?

MongoDB stores data as **documents**. A document can embed all related data (embedding), or store a **reference value** pointing to an independent document in another collection.

For example, the `customers` collection holds customers, and `orders` holds orders:

~~~javascript
// customers
{ _id: "c001", name: "An", status: "ACTIVE" }

// orders
{
  _id: "o001",
  customerId: "c001",
  totalVnd: 250000,
  state: "OPEN"
}
~~~

Here, `orders.customerId` carries the business meaning: “order o001 belongs to customer c001.” However, MongoDB **does not automatically enforce a foreign key constraint** between `customerId` and `customers._id`. You can still:

- Insert an order pointing to `customerId: "c404"` even though customer `c404` does not exist.
- Delete customer `c001` without deleting or updating orders pointing to them.
- Change the schema or BSON type of `customers._id` so lookups no longer match.
- Have two concurrent write flows render an existence check stale.

When a reference has a value yet cannot locate the target object under the data contract, it is called a **dangling reference** (*broken reference*). If a child document remains without a valid parent document, it is also often referred to as an **orphan** in business terms.

An optional reference with a missing field or set to `null` **is not necessarily broken**. It is broken only when business rules **require** that relationship to point to an existing object.

### 1.1. States to Distinguish

| Order state | Interpretation | Handling depends on business rules |
| --- | --- | --- |
| `customerId: "c001"`, customer `c001` exists | Valid reference | Can read customer information |
| `customerId: "c404"`, customer `c404` missing | Dangling reference | Return error, repair link, queue for reconciliation |
| No `customerId` field | Missing reference | Valid if relationship is optional; error if required |
| `customerId: null` | Field present with no target | Per contract: “unassigned” or invalid data |
| `customerId` is BSON `ObjectId`, target `_id` is BSON string | Key type mismatch | Queries fail to match despite identical displayed text |
| Customer has `deletedAt` but still exists | Physically valid reference, logically deleted target | Decide whether orders may still display historical info |

What needs to be designed is **business-level integrity**: a paid order may need to preserve customer history, whereas a “group membership” link may need to be removed immediately when the group is deleted.

## 2. Ways to Store References in MongoDB and Spring Data

### 2.1. Manual Reference: Storing the Target Document's ID

This is a common and transparent choice:

~~~javascript
// customers collection
{ _id: "c001", name: "An", status: "ACTIVE" }

// orders collection
{ _id: "o001", customerId: "c001", totalVnd: 250000 }
~~~

The application queries `orders`, then looks up `customers` by `customerId`. A `$lookup` query can combine data when appropriate. MongoDB recommends manual references for most cases requiring relationships between independent documents.

Pros of manual references: simple BSON fields, easy to index, convenient when checking whether a reference still exists. Cons: the application decides when to look up targets, handle empty results, and maintain integrity.

### 2.2. `@DBRef`: BSON DBRef

Spring Data MongoDB supports the `@DBRef` annotation:

~~~java
import org.springframework.data.mongodb.core.mapping.DBRef;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.MongoId;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document("orders_dbref_example")
public class OrderWithDbRef {
    @MongoId(FieldType.STRING)
    private String id;

    @DBRef
    private CustomerDocument customer;

    protected OrderWithDbRef() { }
}
~~~

DBRef uses a reference structure holding the target collection, ID, and optional database:

~~~javascript
{
  _id: "o001",
  customer: { $ref: "customers_ref_demo_008", $id: "c001" }
}
~~~

When Spring Data loads `OrderWithDbRef`, the framework can resolve `customer` to the target entity, eagerly by default; `@DBRef(lazy = true)` requests lazy loading. Resolution requires a MongoDB read operation and can incur extra round trips.

**Important note:** Spring Data **does not automatically cascade-save** entities referenced by `@DBRef`. Do not assume `orderRepository.save(order)` saves `customer`. Likewise, do not expect deleting an order or customer to cascade-delete related documents: deletion policies must be implemented explicitly in the service layer.

### 2.3. `@DocumentReference`: Spring Data Managed References

`@DocumentReference` allows storing a simple ID instead of a BSON DBRef, or configuring a custom `lookup` on a field other than `_id`:

~~~java
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.DocumentReference;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document("orders_docref_example")
public class OrderWithDocumentReference {
    @MongoId(FieldType.STRING)
    private String id;

    @DocumentReference
    private CustomerDocument customer;

    protected OrderWithDocumentReference() { }
}
~~~

With default `_id`-based lookup, the order's BSON stores the `customer` field as an ID string:

~~~javascript
{ _id: "o001", customer: "c001" }
~~~

Spring Data maps `"c001"` to the document in `CustomerDocument`'s collection. If you need lookups on another key (such as `code`), configure `lookup` while ensuring **the written pointer value and read lookup rule match**. Do not assume every custom object is written properly solely from a query string; some cases require converters or extra configuration.

`@DocumentReference` is not a MongoDB foreign key and **does not cascade-save** either. For reactive access, check specific support limits: current Spring Data MongoDB documentation explicitly states **reading document references via the reactive infrastructure is not supported**; the reliable option in reactive apps is storing IDs and querying targets explicitly via `ReactiveMongoTemplate` or reactive repositories.

### 2.4. Choosing the Right Reference Style

| Organization style | Stored in BSON | Appropriate when | Watch out for |
| --- | --- | --- | --- |
| Embed child document | Child data lives inside parent | Data is always read/updated with parent, reasonable size | Document size limits and syncing duplicated data |
| Manual reference | `customerId: "c001"` | Need control over lookups, existence checks, deletion | Application manages links itself |
| `@DocumentReference` | Usually a simple ID, with customizable lookup | Want reference mapping in imperative Spring Data | Resolution, caching/latency, no cascades |
| `@DBRef` | `{ $ref, $id, $db? }` | Must stay compatible with existing DBRef data or format | Spring Data resolves via driver; not the default for most new systems |

Practical rule: when you simply need a link key and specific deletion business logic, **manual references are usually simpler**. When child data is always read with the parent and fits within one document, consider embedding to avoid cross-collection operations.

## 3. Dataset to Observe Broken References

Use `mongosh` on a practice database. The following examples target collections dedicated to this lesson:

~~~javascript
use spring_data_mongodb_lab

const customers = db.customers_ref_demo_008;
const orders = db.orders_ref_demo_008;

customers.insertMany([
  { _id: "c001", name: "An", status: "ACTIVE" },
  { _id: "c002", name: "Binh", status: "ACTIVE" },
  { _id: "c003", name: "Chi", status: "INACTIVE" }
]);

orders.insertMany([
  { _id: "o001", customerId: "c001", totalVnd: 250000, state: "OPEN" },
  { _id: "o002", customerId: "c404", totalVnd: 150000, state: "OPEN" },
  { _id: "o003", customerId: "c002", totalVnd: 800000, state: "PAID" },
  { _id: "o004", customerId: null, totalVnd: 90000, state: "DRAFT" },
  { _id: "o005", totalVnd: 50000, state: "DRAFT" },
  { _id: "o006", customerId: "c001", totalVnd: 175000, state: "PAID" }
]);

// Improve efficiency when searching orders by customerId.
orders.createIndex({ customerId: 1 });
~~~

Do not re-run the inserts on the same dataset without clearing or using fresh test collections: fixed `_id`s will throw duplicate key errors. Expected results below assume the initial dataset has not been modified.

`o002` is clearly a broken reference: it points to nonexistent `c404`. `o004` and `o005` illustrate null/missing fields; under the business rule “DRAFT orders may omit a customer,” they are **not broken references**. `c003` is a customer with zero orders, which does not mean their data is corrupted.

### 3.1. Direct Two-Step Query

~~~javascript
const order = orders.findOne({ _id: "o002" });
const customer = customers.findOne({ _id: order.customerId });

printjson(order);     // Has customerId: "c404".
printjson(customer);  // null, because c404 does not exist.
~~~

In code, `customer == null` must be handled as a business condition rather than blindly dereferencing `customer.name`. You must also determine whether null/missing `customerId` is valid before treating “every null result as an error.”

## 4. Detecting Broken References with `$lookup`

`$lookup` can join data across two collections to audit links. In this example, both collections reside in the same database and `customerId`/`_id` keys are both BSON strings.

### 4.1. Finding Orders with a `customerId` Yet No Matching Customer

~~~javascript
orders.aggregate([
  // Inspect only orders that actually carry a string ID.
  {
    $match: { customerId: { $type: "string" } }
  },
  {
    $lookup: {
      from: "customers_ref_demo_008",
      localField: "customerId",
      foreignField: "_id",
      as: "matchedCustomers"
    }
  },
  {
    $match: {
      matchedCustomers: { $size: 0 }
    }
  },
  {
    $project: {
      _id: 1,
      customerId: 1,
      state: 1,
      totalVnd: 1
    }
  }
]);
// On initial dataset: only o002 has customerId "c404".
~~~

Why include the first `$match`? When `localField` or `foreignField` is missing, `$lookup` matches against `null` semantics. Filtering upfront separates **references carrying an ID that fails to resolve** from **empty optional relationships**.

`matchedCustomers: { $size: 0 }` checks the output array of `$lookup`. Because `customers._id` is unique, a valid link produces one target document; a broken link yields an empty array.

### 4.2. Classifying Missing, Null, Dangling, and Valid States

For a data quality report, you can classify all rows:

~~~javascript
orders.aggregate([
  {
    $lookup: {
      from: "customers_ref_demo_008",
      localField: "customerId",
      foreignField: "_id",
      as: "matches"
    }
  },
  {
    $project: {
      _id: 1,
      customerId: 1,
      referenceState: {
        $switch: {
          branches: [
            {
              case: { $eq: [{ $type: "$customerId" }, "missing"] },
              then: "MISSING"
            },
            {
              case: { $eq: ["$customerId", null] },
              then: "NULL"
            },
            {
              case: { $eq: [{ $size: "$matches" }, 0] },
              then: "DANGLING"
            }
          ],
          default: "RESOLVED"
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Expected output: `o001/o003/o006 → RESOLVED`, `o002 → DANGLING`, `o004 → NULL`, `o005 → MISSING`.

**Limitation:** this is a point-in-time snapshot at query execution. While the report runs, another writer may insert or delete customers. Audit results do not enforce integrity constraints on subsequent writes.

### 4.3. References Inside Arrays

If a document holds `memberIds: ["c001", "c404"]`, you cannot always compare `matchedCustomers.length === memberIds.length`, because duplicate IDs inside the array skew the count.

One approach is extracting the existing target IDs and computing the set difference:

~~~javascript
// Illustrates one test data variant only.
db.groups_ref_demo_008.insertOne({
  _id: "g001",
  memberIds: ["c001", "c404"]
});

db.groups_ref_demo_008.aggregate([
  {
    $lookup: {
      from: "customers_ref_demo_008",
      localField: "memberIds",
      foreignField: "_id",
      as: "membersFound"
    }
  },
  {
    $project: {
      memberIds: 1,
      missingIds: {
        $setDifference: [
          "$memberIds",
          {
            $map: {
              input: "$membersFound",
              as: "member",
              in: "$$member._id"
            }
          }
        ]
      }
    }
  }
]);
// g001 produces missingIds: ["c404"].
~~~

This assumes `memberIds` is an array of strings with no nulls; if input data is heterogeneous, normalize or filter types before applying `$setDifference`. Do not assume array links always need cascade deletion when a target document is deleted.

### 4.4. Reconciliation Job Performance

- Create indexes on frequently queried fields such as `orders.customerId`. `customers._id` already has a default unique index.
- On very large collections, full-collection `$lookup` scans are expensive; consider batching by `_id`, bounding time ranges, or using events/outbox for early detection.
- Distinguish **truly broken data** from links mid-update by an active transaction or sync process; apply appropriate delay/grace thresholds.
- Never place heavy reconciliation queries on the critical path of individual HTTP requests when indexed ID lookups suffice.

## 5. Policies When Deleting Referenced Documents

Before implementing `deleteById()` or `MongoTemplate.remove()` for a parent entity, define the policy for each relationship type.

| Policy | When deleting a customer with orders | When to use | Risks to handle |
| --- | --- | --- | --- |
| **RESTRICT / BLOCK** | Reject deletion if referencing orders exist | Orders must have a valid customer | Race between check and delete |
| **CASCADE** | Delete related orders before/with the customer | Child documents have no standalone value | Loss of history; multi-document ops left partial |
| **SET NULL / DETACH** | Unset `customerId` or set null on orders, then delete customer | Optional relationship | Schema and UI must handle unassigned state |
| **SOFT DELETE / TOMBSTONE** | Keep customer document, mark as deleted | Audits, historical orders, restoration support | Every business query must filter status properly |
| **RETAIN SNAPSHOT** | Retain historical customer info in orders and allow deleting original per policy | Invoices, receipts, commercial history | Snapshot data must still follow privacy/retention rules |

These are **application-layer policies**, not automatic MongoDB cascade options. Spring Data MongoDB does not emulate relational `ON DELETE CASCADE`/`RESTRICT` for document references.

### 5.1. RESTRICT: Block Deletion While References Remain

Testing in `mongosh`:

~~~javascript
const customerId = "c001";

const linkedOrders = orders.countDocuments({ customerId });
print(linkedOrders); // 2 on initial dataset.

if (linkedOrders === 0) {
  customers.deleteOne({ _id: customerId });
} else {
  print("RESTRICT: customer still has orders, deletion rejected");
}
~~~

Because `c001` currently has `o001` and `o006`, deletion is blocked in the example above.

**Concurrency warning:** checking then deleting are **two separate operations**. Another writer could insert a new order right after `countDocuments` and before `deleteOne`. Hence this demonstrates the policy, not strict RESTRICT guarantees under concurrent writers.

If only one service writes data and business rules tolerate that consistency level, a simple check plus periodic audits may suffice. For strict invariants under concurrent writes, implement a coordination protocol across **all writers** and transactions as shown in section 8.

### 5.2. CASCADE: Delete Dependent Documents

~~~javascript
const customerId = "c003";

// On the initial dataset, c003 has no orders so none are deleted.
const removedChildren = orders.deleteMany({ customerId });
const removedParent = customers.deleteOne({ _id: customerId });

printjson({
  deletedOrders: removedChildren.deletedCount,
  deletedCustomers: removedParent.deletedCount
});
~~~

If applied to a customer with orders, these two operations wipe out historical records. In real deployments requiring atomicity across both collections, use a properly configured MongoDB transaction. For huge child counts, a single multi-document transaction may be too expensive; use an asynchronous stateful workflow with retries and completion tracking.

**Never default to CASCADE for paid invoices/orders** simply because they carry `customerId`. Business requirements and retention regulations dictate which records must survive.

### 5.3. SET NULL / DETACH: Remove Links

~~~javascript
const customerId = "c002";

// Detach all orders pointing to c002.
orders.updateMany(
  { customerId },
  { $unset: { customerId: "" } }
);

// Then delete the customer if business rules permit.
customers.deleteOne({ _id: customerId });
~~~

`$unset` removes the field completely. If the data contract expects the field to remain present as `null`, use `$set: { customerId: null }`. APIs, validation, queries, and reports must all accommodate orders without a customer. Running two separate commands can leave partial state if execution stops mid-way.

### 5.4. SOFT DELETE: Keep a Tombstone

~~~javascript
customers.updateOne(
  { _id: "c001", status: "ACTIVE" },
  {
    $set: {
      status: "DELETED",
      deletedAt: new Date()
    }
  }
);
~~~

Orders can still look up document `c001`, while all business flows must define whether new orders can be placed for deleted customers. If disallowed, order creation must check `status: "ACTIVE"` with a concurrency-safe mechanism.

Tombstoning does not equal data anonymization. If privacy rules require erasing personal data, implement scrubbing/pseudonymization and retention schedules. Never retain all attributes indefinitely merely to preserve references.

### 5.5. Retain Snapshot: Store Historical Data in Orders

~~~javascript
// Example historical snapshot captured at checkout time:
{
  _id: "o100",
  customerId: "c001",
  customerSnapshot: {
    displayNameAtPurchase: "An"
  },
  totalVnd: 250000,
  state: "PAID"
}
~~~

If the customer later changes their name or is deleted, the invoice retains the name used in the transaction. Store **only data truly needed for history**, subject to access controls and retention limits. Snapshots are a data modeling choice and do not automatically ensure cross-collection consistency at creation time.

## 6. Implementing Policies with Spring Data MongoDB

The examples below use manual references so conditions and delete operations are explicit in code. Using explicit string IDs avoids Spring Data auto-converting ObjectId-like `String`s.

### 6.1. Two Simple Entities

~~~java
// CustomerDocument.java
package com.example.references;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document("customers_ref_demo_008")
public class CustomerDocument {
    @MongoId(FieldType.STRING)
    private String id;
    private String name;
    private String status;

    protected CustomerDocument() { }

    public CustomerDocument(String id, String name, String status) {
        this.id = id;
        this.name = name;
        this.status = status;
    }

    public String getId() { return id; }
    public String getName() { return name; }
    public String getStatus() { return status; }
}
~~~

~~~java
// OrderDocument.java
package com.example.references;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document("orders_ref_demo_008")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;
    private String customerId;
    private long totalVnd;
    private String state;

    protected OrderDocument() { }

    public OrderDocument(
            String id, String customerId, long totalVnd, String state) {
        this.id = id;
        this.customerId = customerId;
        this.totalVnd = totalVnd;
        this.state = state;
    }

    public String getId() { return id; }
    public String getCustomerId() { return customerId; }
    public long getTotalVnd() { return totalVnd; }
    public String getState() { return state; }
}
~~~

Here `@MongoId(FieldType.STRING)` enforces a BSON string policy for `_id` on both collections. Real systems may use `ObjectId` for `_id`, in which case reference fields and queries must match that BSON type. A 24-character hex string and an `ObjectId` with the same text **are not** equal in MongoDB.

### 6.2. Repositories Querying by Key

~~~java
package com.example.references;

import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CustomerRepository
        extends MongoRepository<CustomerDocument, String> {
}

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    boolean existsByCustomerId(String customerId);

    long countByCustomerId(String customerId);

    List<OrderDocument> findByCustomerId(String customerId);
}
~~~

`existsByCustomerId()` and `countByCustomerId()` help implement RESTRICT checks; however, by themselves they **do not lock** documents or stop another transaction from inserting a new order. Multi-writer systems require coordination mechanisms as discussed in the concurrency section.

### 6.3. Service Returning Clear Outcomes on Broken References

~~~java
package com.example.references;

import org.springframework.stereotype.Service;

@Service
public class OrderLookupService {
    private final OrderRepository orders;
    private final CustomerRepository customers;

    public OrderLookupService(
            OrderRepository orders, CustomerRepository customers) {
        this.orders = orders;
        this.customers = customers;
    }

    public CustomerDocument customerForOrder(String orderId) {
        OrderDocument order = orders.findById(orderId)
            .orElseThrow(() -> new IllegalArgumentException(
                "Order not found: " + orderId
            ));

        String customerId = order.getCustomerId();
        if (customerId == null) {
            throw new IllegalStateException(
                "Order has no customer reference: " + orderId
            );
        }

        return customers.findById(customerId)
            .orElseThrow(() -> new IllegalStateException(
                "Broken customer reference in order: " + orderId
            ));
    }
}
~~~

The snippet distinguishes: **order does not exist**, **order has no reference**, and **order points to a nonexistent customer**. In real APIs, translate these into properly coded error responses and **never expose sensitive data** in client-facing error messages.

For DRAFT orders allowed to have no customer, the service should return a status DTO or `Optional<CustomerDocument>` instead of throwing on the null branch. This decision stems from the business contract, not repository annotations.

### 6.4. Simple RESTRICT via `MongoTemplate`

~~~java
import com.mongodb.client.result.DeleteResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class RestrictedCustomerDeletionService {
    private final MongoTemplate template;

    public RestrictedCustomerDeletionService(MongoTemplate template) {
        this.template = template;
    }

    public void deleteCustomerIfUnused(String customerId) {
        boolean hasOrders = template.exists(
            Query.query(Criteria.where("customerId").is(customerId)),
            OrderDocument.class
        );

        if (hasOrders) {
            throw new IllegalStateException(
                "Customer has orders; deletion is restricted"
            );
        }

        DeleteResult result = template.remove(
            Query.query(Criteria.where("id").is(customerId)),
            CustomerDocument.class
        );

        if (result.getDeletedCount() != 1) {
            throw new IllegalArgumentException("Customer not found");
        }
    }
}
~~~

This enforces the RESTRICT rule in normal single-flow execution, **not yet race-safe** between check and delete under concurrent writers. The next sections explain these limits and how to strengthen consistency.

## 7. Single-Document Atomicity Does Not Equal Cross-Collection Atomicity

MongoDB guarantees atomicity for **a single write operation on one document**. However, two operations:

~~~javascript
orders.deleteMany({ customerId: "c001" });
customers.deleteOne({ _id: "c001" });
~~~

do not automatically become an atomic cross-collection action. If the first succeeds and the second fails, the remaining state diverges from expectations; the reverse order can leave orphans.

When business rules demand atomic multi-document updates within the same MongoDB deployment, use **multi-document transactions**. MongoDB transactions require a supported topology, such as a replica set or properly configured sharded cluster, and carry higher overhead than single-document writes.

### 7.1. Configuring the Transaction Manager

~~~java
package com.example.references;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration(proxyBeanMethods = false)
public class MongoReferenceTransactionConfiguration {
    @Bean("mongoTransactionManager")
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
~~~

`MongoTemplate` must use the matching database factory to join the same transaction. Ensure required collections already exist before running transaction examples, and configure a replica set/transaction-capable deployment.

### 7.2. Transaction for Detach-Then-Delete

~~~java
package com.example.references;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerDetachService {
    private final MongoTemplate template;

    public CustomerDetachService(MongoTemplate template) {
        this.template = template;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void deleteAndDetach(String customerId) {
        Query customer = Query.query(
            Criteria.where("id").is(customerId)
        );

        if (!template.exists(customer, CustomerDocument.class)) {
            throw new IllegalArgumentException("Customer not found");
        }

        template.updateMulti(
            Query.query(Criteria.where("customerId").is(customerId)),
            new Update().unset("customerId"),
            OrderDocument.class
        );

        var removed = template.remove(customer, CustomerDocument.class);
        if (removed.getDeletedCount() != 1) {
            throw new IllegalStateException("Customer was not deleted");
        }
    }
}
~~~

If an error occurs between operations, the transaction can roll back changes. Nevertheless, **transactions do not provide foreign keys** and do not prevent races with a writer creating a new order outside the coordination protocol; a transaction that merely runs `exists` or `count` can still miss concurrent writes.

Calls to `@Transactional` methods must pass through the Spring proxy; internal self-invocation from another method in the same class may bypass transactions under default proxy settings. For reactive apps, use `ReactiveMongoTransactionManager`/`TransactionalOperator` with `Mono`/`Flux`; never wrap reactive calls inside a synchronous method expecting them to join a transaction automatically.

## 8. Race Conditions: Checking Existence Before Writing Is Not Enough

Consider two concurrent requests:

~~~mermaid
sequenceDiagram
    participant A as Request A: delete customer
    participant DB as MongoDB
    participant B as Request B: create order
    A->>DB: count orders(c001) = 0
    B->>DB: find customer(c001) => exists
    A->>DB: delete customer(c001)
    B->>DB: insert order(customerId=c001)
    Note over DB: New order points to deleted customer
~~~

Each request may have “checked properly” at read time, yet the final state is still a broken reference.

### 8.1. Coordination Protocol Between Writers and Deleters

If the application needs strict RESTRICT, **every order-creation and customer-deletion flow** must obey the same rules. One design using MongoDB transactions forces both operations to **write to the customer document** to create a conflict point when they overlap:

1. Customer has `status: "ACTIVE"` and a numeric `referenceEpoch` field acting as a version or coordination marker.
2. When creating an order, inside a transaction, execute `updateOne` matching `{ _id: customerId, status: "ACTIVE" }` with `$inc: { referenceEpoch: 1 }` on the customer; insert the order only if the update succeeds.
3. When deleting a customer, inside a transaction, conditionally transition `status` from `ACTIVE` to `DELETING` on the **same customer document**; check referencing orders and decide whether to delete or abort.
4. If two transactions attempt to modify the same customer document concurrently, one hits a write conflict and must retry the whole operation per policy.

This is an **application-level protocol**, not a MongoDB foreign key feature. It increases write contention on the customer document if many orders arrive for the same customer. Apply it only when integrity requirements justify the cost; alternatively, choose another data model or suitable state machine.

### 8.2. Pseudocode for Both Coordinated Branches

~~~text
createOrder(customerId, order):
  transaction:
    update customer where id=customerId and status=ACTIVE:
      inc referenceEpoch by 1
    if matchedCount != 1: reject
    insert order referencing customerId
  commit (retry transaction if transient conflict)

deleteCustomerRestricted(customerId):
  transaction:
    update customer where id=customerId and status=ACTIVE:
      set status=DELETING
    if matchedCount != 1: reject
    if countOrders(customerId) > 0: reject and rollback
    delete customer where id=customerId
  commit (retry transaction if transient conflict)
~~~

The crux is that **both branches must participate in the protocol**. An import job inserting orders directly while skipping the `referenceEpoch` update can still create orphans. When multiple services write to a collection, standardize data contracts and write concurrency tests for critical flows.

**Never implement infinite retries.** MongoDB can label transient transaction errors; retries need bounded attempts, appropriate backoff, idempotent behavior, and observability for failures.

### 8.3. When to Use a `DELETING` State

When deleting thousands of child documents, a single transaction can become too large or slow. An alternative:

~~~text
ACTIVE -> DELETING -> DELETED
                  \-> DELETE_FAILED (awaiting retry)
~~~

- Mark the parent `DELETING` via a conditional update.
- All new writers must **reject creating links** to any parent no longer `ACTIVE`.
- Workers delete/detach children in batches, persisting progress with idempotent retries.
- Once verified, transition to `DELETED` or hard-delete per retention policy.

If another writer only reads status without coordinating or writing conditionally, a race window still exists. Design explicit synchronization points; the `DELETING` state is part of the protocol, not a standalone guarantee.

## 9. What Should the Application Do When a Reference Fails to Resolve?

No single behavior is right for every domain. Examples:

| Context | When reference fails to resolve | Suggestion |
| --- | --- | --- |
| Paid order | Still need historical lookup | Display required snapshot; log operational alert |
| Order being created | Cannot confirm customer | Reject confirmation and require assigning a valid customer |
| Group member list | Member does not exist | May omit from list per policy; record audit log |
| Resource authorization | Ownership reference is broken | Deny access by fail-safe default |
| Analytical report | Should not silently drop records | Classify as `UNRESOLVED` with explicit counts |

With `@DBRef`/`@DocumentReference`, never assume lazy resolvers always return `null` identically across types and versions. Depending on mapping, collection, and proxy mechanism, access may emit a query and throw an error. **Design explicit business outcomes**: resolved, optional missing, broken, transient failure.

A service can return a DTO:

~~~java
public record OrderCustomerView(
    String orderId,
    String customerId,
    String customerName,
    String referenceState
) {}
~~~

`referenceState` values should follow a fixed convention such as `RESOLVED`, `OPTIONAL_MISSING`, `BROKEN` so APIs and logs can parse them reliably. In large systems, consider an enum instead of `String` to avoid typos.

## 10. Cleaning Up Broken References and Repairing Existing Data

Detecting an orphan does not authorize automatically deleting or reassigning data. Before running a repair job:

1. Confirm business rules: was the parent actually deleted, or is it a temporary sync lag?
2. Distinguish missing/null `customerId` from a populated ID that fails to resolve.
3. Verify whether `customerId` and `customers._id` share the same BSON type.
4. Check logs, events, or historical records to see if the parent can be restored.
5. Choose the repair action: restore parent, convert to tombstone, detach reference, re-link to correct ID, or delete child per approved policy.
6. Record counts, affected IDs, repair rationale, and retry/rollback capability.

### 10.1. Verify with Queries Before Repairing

~~~javascript
// Inspect exact orders referencing c404.
orders.find(
  { customerId: "c404" },
  { _id: 1, customerId: 1, state: 1, totalVnd: 1 }
);

// Check whether the parent exists.
customers.findOne({ _id: "c404" });
~~~

Never run `deleteMany({ customerId: { $exists: false } })` assuming every order without a customer is an orphan. That could mistakenly wipe out valid DRAFT orders.

### 10.2. Example Repair Under the DETACH Policy

Suppose `o002` has been confirmed eligible to become an unassigned order; update that specific document:

~~~javascript
const result = orders.updateOne(
  { _id: "o002", customerId: "c404" },
  {
    $unset: { customerId: "" },
    $set: { referenceRepairReason: "MISSING_CUSTOMER" }
  }
);

printjson(result); // Check matchedCount, modifiedCount.
~~~

Filtering on both `_id` and `customerId` reduces the risk of overwriting a link someone else just fixed. If the link changed between audit and repair, `matchedCount = 0` signals you to re-inspect rather than forcing a stale update.

If the goal is preserving history without a parent, replace `$unset` with a suitable snapshot or tombstone policy. Never write a fake placeholder like `"UNKNOWN"` into `customerId` if the application could mistake it for a real customer ID.

### 10.3. Periodic Reconciliation and Batch Processing

For large datasets, use a dedicated job:

~~~text
Reconciliation job:
  1. Scan orders by _id or time range in bounded batches.
  2. Filter IDs that are present and of the expected data type.
  3. Match against customer IDs using indexed queries.
  4. Classify true orphans / valid missing / temporarily unsynced.
  5. Log audit results; enqueue cases needing manual decisions.
  6. Repair conditionally and idempotently per policy.
  7. Re-verify and emit metrics.
~~~

Never run unbounded `$lookup` or one-by-one network queries per order on request paths at high volume. Use `$lookup`, batching, or a reconciliation read model; choose based on indexes, latency, and data size.

### 10.4. Monitoring and Alerting

Useful metrics:

- Count of `dangling references` by collection and relationship type.
- Duration from marking parent `DELETING` until cleanup finishes.
- Rejected RESTRICT operations, transaction conflicts, and retries.
- Failed repairs or tasks lingering unusually long in queues.
- Actual deleted/detached document counts versus expected counts.

Never dump full documents containing sensitive fields into logs when only keys and states are needed. When logging IDs, comply with your system's security and traceability policies.

## 11. Testing Integrity Policies

Unit tests using mocked repositories can verify branches like “child exists so block delete,” yet miss BSON type mismatches, `$lookup` behavior, transaction rollbacks, and races between two writers. For critical workflows, run **integration tests** against a MongoDB deployment supporting transactions when testing transactional flows.

### 11.1. Essential Test Cases

| Case | Expected outcome |
| --- | --- |
| Order referencing valid customer | Resolves the matching customer |
| Order referencing nonexistent customer | Returns clear BROKEN status or business exception |
| Order with `customerId: null` or missing field | Handled per optional/required contract |
| IDs across collections have different BSON types | Never silently treated as valid |
| RESTRICT while orders remain | Customer is not deleted |
| RESTRICT when no orders remain | Deletion succeeds per policy |
| DETACH inside transaction encounters error | Cross-collection changes roll back |
| CASCADE with multiple orders | Deletes right targets; verifies counts and limits |
| Two writers create order and delete customer concurrently | Orphan state is never committed if strict consistency is required |
| Reconciliation job runs repeatedly | Does not delete or modify extra out-of-scope data |

### 11.2. Simple RESTRICT Test Example

Assuming a test MongoDB is configured and `RestrictedCustomerDeletionService` from section 6.4 is present:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ReferencePolicyTest {
    @Autowired CustomerRepository customers;
    @Autowired OrderRepository orders;
    @Autowired RestrictedCustomerDeletionService deletionService;

    @Test
    void restrictDeletionWhenOrdersExist() {
        // Fixture must run against an isolated test database.
        orders.deleteById("fixture-o008");
        customers.deleteById("fixture-c008");

        try {
            customers.save(new CustomerDocument(
                "fixture-c008", "Test Customer", "ACTIVE"
            ));
            orders.save(new OrderDocument(
                "fixture-o008", "fixture-c008", 100000, "OPEN"
            ));

            assertThatThrownBy(() ->
                deletionService.deleteCustomerIfUnused("fixture-c008")
            ).isInstanceOf(IllegalStateException.class);

            assertThat(customers.existsById("fixture-c008")).isTrue();
        } finally {
            orders.deleteById("fixture-o008");
            customers.deleteById("fixture-c008");
        }
    }
}
~~~

This test exercises the service from section 6.4 and must run only on an **isolated test database**: fixture setup/teardown deletes those test IDs. It verifies the RESTRICT branch when orders exist, **not** race conditions. Concurrency tests must control timing across two transactions/workers on an appropriate MongoDB topology and assert the final state.

If the app uses `ReactiveMongoRepository`, manual references stored as ID fields still apply. When testing reactive code, subscribe to publishers via `StepVerifier`/reactive chains; writes do not execute merely by constructing a `Mono` or `Flux`.

## 12. Design Case Study: Orders and Customer Profiles

Suppose a system requires:

- Paid orders must retain transaction history.
- Customers can request closing their accounts.
- New orders cannot be created for closed customers.
- Personal data must comply with retention and access controls.

One design approach:

~~~mermaid
flowchart TD
    A["Account closure request"] --> B["Mark customer=DELETING"]
    B --> C{"Historical orders exist?"}
    C -->|Yes| D["Retain required data in order snapshots"]
    C -->|No| E["Eligible for deletion per policy"]
    D --> F["Anonymize/scrub parent per retention"]
    E --> F
    F --> G["Verify references and audit"]
    G --> H["Finalize DELETED status"]
~~~

The system should allow creating orders only when the customer is `ACTIVE`. Deciding between hard delete, tombstone, snapshots, or detailed retention rules must stem from business and legal policies, not the convenience of `deleteById()`.

For other relationships like “document watch tags” or “temporary sessions,” CASCADE or DETACH may fit better. Therefore, **integrity policies must be defined per relationship**, with no single global rule for all document references.

## 13. Common Pitfalls

| Symptom | Possible cause | How to investigate |
| --- | --- | --- |
| `findById(customerId)` returns empty even though UI shows matching IDs | BSON `ObjectId` vs. BSON string; wrong database/collection | Check `$type` of both ID fields and `@Id`/`@MongoId` metadata |
| Deleting customer causes orders to lose details | Hard delete without snapshots/tombstones or handling policy | Review RESTRICT/RETAIN SNAPSHOT/SOFT DELETE |
| Calling `save(order)` does not persist new customer | `@DBRef`/`@DocumentReference` does not cascade-save | Persist customer first and verify actual ID |
| Warnings/errors when accessing lazy references | Resolver runs I/O on property access; proxy, session, or server unavailable | Inspect `@DBRef(lazy=true)`, fetch strategy, and resolver logs |
| `$lookup` flags many “false” orphans | Missing/null fields pulled into join unchecked | Filter present/typed IDs; inspect raw BSON |
| RESTRICT occasionally still creates orphans | Race between count check and order insert | Apply coordination protocol across all writers; test concurrency |
| DETACH/CASCADE completes only halfway | Multi-document ops outside a transaction or non-retryable job | Use proper transactions or idempotent stateful workflows |
| Reconciliation job mistakenly alters DRAFT orders | Lumping null/missing and dangling into one bucket | Classify states and business contracts before repairing |
| Bulk deletion is slow | Scanning `orders` without `customerId` index; huge child count | Add index matching query, batch deletes, measure `explain` |
| Transaction declared yet fails to roll back | Missing `MongoTransactionManager`, wrong factory, self-invocation, or unsupported topology | Review bean/proxy/session config and run integration tests |

## 14. Practice Exercises

### Exercise 1 — Find Broken References

Using the initial dataset from section 3, find orders with a string `customerId` that have no matching customer document.

**Answer:** use an aggregation pipeline with `$match` for `$type: "string"`, `$lookup` into `customers_ref_demo_008`, and filter `matchedCustomers: { $size: 0 }`. Expected result is **o002** with `customerId: "c404"`.

### Exercise 2 — Choose a Deletion Policy

The application must retain paid orders and prevent creating new orders for closed customer accounts. Should you use CASCADE to delete all orders when deleting a customer?

**Reference answer:** No. Consider RESTRICT, SOFT DELETE/TOMBSTONE combined with snapshots of required historical data. All order-creation paths must reject non-ACTIVE customers using a concurrency-safe protocol.

### Exercise 3 — Distinguish Null and Orphan

`o004` has `customerId: null` and `o005` has no `customerId`. Are these two orders orphans?

**Answer:** You cannot conclude without knowing the data contract. If DRAFT orders allow missing customers, both are valid. If every order requires a customer, they violate a required-field constraint, which differs fundamentally from `o002` holding an ID pointing to a nonexistent document.

### Exercise 4 — Delete Only When Unlinked

Write a `mongosh` snippet that checks `orders.countDocuments({ customerId: "c003" })` before calling `customers.deleteOne({ _id: "c003" })`.

**Reference answer:**

~~~javascript
const id = "c003";
if (orders.countDocuments({ customerId: id }) !== 0) {
  throw new Error("Deletion restricted: referenced customer");
}
const result = customers.deleteOne({ _id: id });
printjson(result);
~~~

**Follow-up question:** What gap remains in this snippet? **Answer:** between the count and the delete, another request could insert an order. Writers must coordinate with a transactional or logical locking strategy if strong consistency is required.

### Exercise 5 — Conditional Orphan Repair

It has been confirmed that order `o002` may drop its customer link. Write an update command that avoids overwriting if the reference ID was modified concurrently.

**Answer:**

~~~javascript
orders.updateOne(
  { _id: "o002", customerId: "c404" },
  { $unset: { customerId: "" } }
);
~~~

Check `matchedCount` and `modifiedCount`. If `matchedCount = 0`, reload the order and re-verify rather than forcing the update with a looser filter.

## References

- [MongoDB Manual — Database References](https://www.mongodb.com/docs/manual/reference/database-references/): manual references, DBRefs, and choosing reference representations.
- [Spring Data MongoDB — Using DBRefs and Document References](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/document-references.html): `@DBRef`, `@DocumentReference`, lookup, lazy resolution, and cascading limits.
- [Spring Data MongoDB — Sessions and Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): `MongoTransactionManager`, `ReactiveMongoTransactionManager`, and transaction mechanics.
- [MongoDB Manual — `$lookup`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/): cross-collection joins in aggregation.
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/): multi-document transaction limits and behavior.
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/): difference between single-document atomic operations and multi-operation sequences.
