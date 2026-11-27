# Single-Document Atomicity and Multi-Document Operations

In MongoDB, **a write operation on a single document is atomic**: all changes made by that operation to the document are applied as a single unit. Conversely, when a business operation modifies **multiple documents**, each individual write remains atomic, but the overall workflow does not automatically become an "all-or-nothing" transaction.

This is the foundation for modeling data and writing code with **Spring Data MongoDB**. You can leverage document-level atomicity with MongoDB update operators, use filter conditions to prevent concurrent race conditions, or use transactions when business consistency spans multiple documents.

## 1. Learning objectives

After this lesson, you will be able to:

- Explain the exact atomicity scope of `insertOne`, `updateOne`, `findOneAndUpdate`, and `updateMany`.
- Use filter conditions alongside `$inc`, `$set`, and other update operators to protect **single-document** invariants under concurrent requests.
- Identify multi-document scenarios that require transactions, and distinguish them from cases where related data should be grouped into one document.
- Implement atomic updates via `MongoTemplate` and transactions via `MongoTransactionManager` with `@Transactional`.
- Distinguish **atomicity**, **isolation**, and **durability**, and identify limits across multiple services or parallel processing.
- Design tests for missing data, mid-workflow failures, and concurrent contention.

## 2. Single-document atomicity scope

The document is MongoDB's primary storage unit; a document can contain scalar fields, nested objects, and arrays. A single update command can modify **multiple fields of the same document**, while outside observers never see an intermediate state of that write command.

For example, an order is stored as:

```json
{
  "_id": "ORD-1001",
  "status": "NEW",
  "payment": { "state": "PENDING" },
  "revision": 0
}
```

Transition the order status in **one** command:

```javascript
db.orders.updateOne(
  { _id: "ORD-1001", status: "NEW" },
  {
    $set: {
      status: "CONFIRMED",
      "payment.state": "AUTHORIZED"
    },
    $inc: { revision: 1 }
  }
);
```

Both `status`, `payment.state`, and `revision` are updated atomically inside document `ORD-1001`. If the document is no longer in status `NEW` at write time, the filter does not match and the operation does not modify that document.

**Distinction to keep in mind:** MongoDB only guarantees atomicity for changes within **the same write command on a single document**. If the application issues three separate `updateOne` calls to edit three fields, there can be a window between calls where some changes are already written and others are not.

### Filter conditions are an essential part of concurrent updates

Consider inventory with `available = 5`. Two customers simultaneously order 4 items:

- If the application reads `available`, computes `available - 4` in memory, and calls `save` without checking a version or condition, there is a risk of **overwriting each other's updates** (lost update).
- If each request executes a single update command with the condition `available >= 4` and `$inc: { available: -4 }`, only one request can succeed in deducting stock. The other request no longer matches the condition.

```javascript
const result = db.inventory.updateOne(
  { _id: "SKU-01", available: { $gte: 4 } },
  { $inc: { available: -4, reserved: 4 } }
);

if (result.modifiedCount !== 1) {
  // SKU not found or insufficient inventory.
}
```

The key point is that **evaluating the condition and modifying the values happen in the same write command**. `$inc` calculates based on the current value on the server; the application does not need to read first and compute the final value. With a filter that does not guard the modified fields, competing writes can still run and overwrite one another: atomicity of each individual write does not automatically solve every concurrency problem.

> **Practical rule:** When an invariant resides within a single document, prefer expressing the invariant with a filter and update operators in **one** statement, then inspect `matchedCount` / `modifiedCount` or the returned result.

## 3. Multiple documents: atomic per item, not automatically atomic as a whole

Suppose the following statement raises prices for all products in a category:

```javascript
db.products.updateMany(
  { category: "books" },
  { $inc: { price: 1000 } }
);
```

Each document is updated atomically. However, **the `updateMany` command as a whole is not a multi-document transaction**. While the operation is running, another query may observe some products with raised prices and others unchanged; if the command fails partway through, already applied changes are not automatically rolled back as a group.

The same applies to standard multi-item write commands, including `bulkWrite`: batching multiple operations into one API call does **not** automatically make all documents atomic together. Options like execution ordering (`ordered` / `unordered`) mainly govern how execution proceeds after an error, not turning the batch into a transaction.

| Operation | Default atomicity scope | What to note |
| --- | --- | --- |
| `insertOne` / `replaceOne` | One document | The entire document is written or not written by that operation. |
| `updateOne` | One document | Can modify multiple fields and array elements of that document simultaneously. |
| `findOneAndUpdate` / `findAndModify` | One document | Finds and updates in one atomic operation; can return the before or after version. |
| `updateMany` | **Each individual** modified document | No automatic rollback across the entire document set. |
| Two consecutive `updateOne` calls | Each command individually | Intermediate state exists between the two commands. |
| Commands inside a valid transaction | Changes belonging to the transaction | Commits or rolls back as a transaction; depends on configuration, deployment, and error handling. |

### Scenario: transferring money between two accounts

Suppose balances live in **two documents**:

```json
{ "_id": "A", "balanceCents": 50000 }
{ "_id": "B", "balanceCents": 20000 }
```

The business flow "transfer 10,000 cents from A to B" consists of:

1. Deduct 10,000 cents from document A.
2. Add 10,000 cents to document B.

If step 1 succeeds and the process stops before step 2, the total money is wrong. The atomicity of each `updateOne` does not ensure both updates succeed or fail together. **Transactions** solve cross-document atomicity requirements within the same MongoDB system.

## 4. Spring Data MongoDB: atomic updates via MongoTemplate

With Spring Data MongoDB, `MongoTemplate` sends filters and update operators directly to MongoDB. Let's use an inventory document:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("inventory")
public class Inventory {
    @Id
    private String id;
    private long available;
    private long reserved;

    public Inventory() {}

    // Getters/setters can be added when the application needs to read or initialize data.
}
```

Inventory reservation service:

```java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    private final MongoTemplate mongoTemplate;

    public InventoryService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public boolean reserve(String sku, long quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be greater than 0");
        }

        Query query = Query.query(
            Criteria.where("_id").is(sku)
                    .and("available").gte(quantity)
        );
        Update update = new Update()
                .inc("available", -quantity)
                .inc("reserved", quantity);

        UpdateResult result =
                mongoTemplate.updateFirst(query, update, Inventory.class);

        return result.getModifiedCount() == 1;
    }
}
```

Invariants are preserved within **one document**: `available` is non-negative; `available + reserved` remains unchanged after reservation, provided all other update paths also follow the business rules.

Notes:

- No multi-document transaction is needed for this **single** `updateFirst` command.
- `modifiedCount == 1` only confirms one document was modified; `0` could mean the SKU does not exist or inventory is insufficient. To return distinct errors, you can perform a follow-up read for messaging, while keeping the success decision anchored to the **atomic update result**.
- Ensure other code paths do not arbitrarily overwrite `available` with stale values; avoid mixing `$inc` with an unprotected "read then `save`" cycle.

### When to use `@Version`?

If business logic must read a document, evaluate complex rules in Java, and then `save` the document back, you can use **optimistic locking**:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("profiles")
public class Profile {
    @Id
    private String id;

    @Version
    private Long version;

    private String displayName;
    private String address;

    // Constructors and getters/setters as needed by the application.
}
```

Spring Data MongoDB uses the version field to detect when a document has been modified by a compatible operation since it was read; saving with a stale version can throw `OptimisticLockingFailureException`. This mechanism is helpful when an operation cannot be expressed purely with conditional `$inc` / `$set`.

For reliable conflict detection, **every participating write path must adhere to the same versioning strategy**, and the write concern must acknowledge writes. `@Version` does not turn two documents into a transaction and does not protect against external applications that deliberately bypass the version check.

## 5. Multi-document transactions in Spring Data MongoDB

To perform operations across multiple documents with "all-or-nothing" semantics, use MongoDB multi-document transactions.

**Deployment prerequisites:** MongoDB must run on a **replica set** or **sharded cluster** that supports transactions; standard standalone MongoDB does not support multi-document transactions. The application must configure the corresponding transaction manager and run commands within the same transaction context.

### 5.1. Configuring MongoTransactionManager

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTransactionConfig {
    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory databaseFactory) {
        return new MongoTransactionManager(databaseFactory);
    }
}
```

In this imperative configuration, Spring uses `MongoTransactionManager` to open and bind a `ClientSession` to the execution thread. `MongoTemplate` or repository operations participate in the transaction when using the matching `MongoDatabaseFactory` and Spring transaction context.

### 5.2. Two updates belonging to the same transaction

Define the account document; use the **smallest currency unit** as an integer so `$inc` has clear semantics and avoids floating-point rounding errors:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("accounts")
public class Account {
    @Id
    private String id;

    private long balanceCents;

    public Account() {}
}
```

Transfer service:

```java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    private final MongoTemplate mongoTemplate;

    public TransferService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    @Transactional
    public void transfer(String fromId, String toId, long amountCents) {
        if (amountCents <= 0 || fromId == null || toId == null
                || fromId.equals(toId)) {
            throw new IllegalArgumentException("Invalid transfer details");
        }

        UpdateResult debit = mongoTemplate.updateFirst(
            Query.query(Criteria.where("_id").is(fromId)
                                .and("balanceCents").gte(amountCents)),
            new Update().inc("balanceCents", -amountCents),
            Account.class
        );
        if (debit.getModifiedCount() != 1) {
            throw new IllegalStateException(
                "Source account does not exist or has insufficient funds");
        }

        UpdateResult credit = mongoTemplate.updateFirst(
            Query.query(Criteria.where("_id").is(toId)),
            new Update().inc("balanceCents", amountCents),
            Account.class
        );
        if (credit.getModifiedCount() != 1) {
            throw new IllegalStateException("Destination account does not exist");
        }
    }
}
```

Within a properly functioning `@Transactional` context, if the destination account is not found, the unchecked exception (`RuntimeException`) causes Spring to roll back the earlier debit as well. If both updates succeed and the transaction commits successfully, both changes belong to one transaction.

**Do not treat the example code as a complete production payment system.** Real money transfers also require a unique business key per request (idempotency key), a transaction ledger, authorization checks, auditing, reconciliation, and safe retry handling.

### 5.3. Key limitations of `@Transactional`

- Placing `@Transactional` **without configuring a suitable MongoDB transaction manager** is not enough to get multi-document transactions like in the example.
- Internal method calls within the same bean (`this.transfer(...)`) generally bypass the Spring proxy and therefore may not trigger the transaction interceptor.
- By default, Spring rolls back on `RuntimeException` and `Error`. To roll back on checked exceptions, configure `rollbackFor` or corresponding rollback rules.
- Calling an external API (such as a payment gateway) inside a transaction **does not enroll the external API into the MongoDB transaction**. When coordinating with events or other systems, consider outbox, saga, and compensating actions.
- For reactive flows, use `ReactiveMongoTransactionManager` and the reactive context (`ReactiveMongoTemplate` / reactive repositories); do not mechanically apply `MongoTransactionManager`'s thread-bound transaction model.

### 5.4. Handling conflicts and commit failures

Transactions can fail due to concurrent updates, network errors, or transient errors. Applications must inspect outcomes and implement **controlled retries** based on the appropriate error types; never assume every transaction automatically retries to success.

In practice, distinguish between:

- Errors indicating the transaction must be **retried from the beginning**; before a new attempt, a fresh transaction context must be created.
- `commitTransaction` outcome **unknown** due to a connection error; do not hastily re-execute the business logic with a new transaction ID, as this risks duplicate execution.
- Business logic requiring idempotency so a repeated request does not trigger an unintended extra transfer.

Do not hold transactions open waiting on user interaction or slow queries. Prepare proper indexes, minimize the number of documents written, and keep transactions short.

## 6. Atomicity vs. isolation and durability

Three properties that are frequently confused:

| Property | Question it answers | Illustration |
| --- | --- | --- |
| **Atomicity** | Is the operation/transaction applied in full or not at all? | A single update to `available` and `reserved` in the same document is never half-written. |
| **Isolation** | How can concurrent operations see and affect one another? | Transactions have a consistent read model and can encounter write conflicts; not automatically equivalent to every SQL isolation level. |
| **Durability** | Does acknowledged data remain safe across crashes or failovers? | Write concern, replica set configuration, and write policies affect whether acknowledged data persists. |

For example, an `updateOne` is always atomic on a document even under a weak write concern; however, **atomic does not mean** the change is guaranteed durable across every failure. When failover resilience is required, choose an appropriate write concern (often considering `majority`), alongside matching read and commit settings.

Transactions provide atomicity across multiple documents, yet how other clients observe data also depends on **read concern, read preference, write concern, and topology**. Do not infer from "transaction" that every read by every client at every point in time is serializable.

## 7. Designing data to leverage single-document atomicity

A key MongoDB design decision is whether to **embed** (embed related data inside one document) or **reference** (link across multiple documents).

Suppose an order must update order status, line items, and total amount as one unit. If the data is moderate in size and typically read/edited together, keeping it in one document allows many rules to be protected by a single update operation.

```json
{
  "_id": "ORD-1002",
  "status": "DRAFT",
  "items": [
    { "sku": "SKU-01", "qty": 2, "unitPriceCents": 12000 },
    { "sku": "SKU-02", "qty": 1, "unitPriceCents": 9000 }
  ],
  "totalCents": 33000
}
```

Conversely, if accounts, products, inventory, and orders have separate lifecycles and are frequently updated by different workflows, forcing everything into one document can cause document bloat, write contention, and awkward queries. When invariants must span multiple documents, use transactions or adjust the business design.

Decision criteria:

| Question | Design direction |
| --- | --- |
| Is the data frequently modified and read together? | Consider embedding to benefit from single-document atomicity. |
| Can the array grow unboundedly? | Avoid unbounded embedding; MongoDB enforces a BSON document size limit (normally 16 MiB). |
| Do entities have independent lifecycles and update frequencies? | Consider splitting documents; if related updates require all-or-nothing semantics, evaluate transactions. |
| Is one document hit by continuous hot writes from many threads? | Evaluate contention, partition the data model, and benchmark realistic loads. |
| Does the workflow span databases/systems outside MongoDB? | MongoDB transactions do not cover external systems; consider an appropriate orchestration pattern. |

**Not every relationship needs a transaction.** Many cases accept eventual consistency, such as syncing an aggregated value for reporting. The decision depends on **business invariants**, not merely the number of collections involved.

## 8. Testing atomicity and transactions

Test both final data outcomes and failure scenarios. An integration test suite should connect to a MongoDB configured as a replica set when testing transactions; running only standalone MongoDB can cause transaction tests to fail right at startup.

### Scenario A — Two concurrent reservation requests for the same stock

Initial data: `available = 5`, `reserved = 0`. Run `reserve("SKU-01", 4)` twice concurrently.

Expected: only **one** request returns `true`; final data is `available = 1` and `reserved = 4`. Verify the non-negative invariant regardless of thread scheduling order.

### Scenario B — Transfer rollback

Initial: `A = 50_000`, `B = 20_000`. Execute `transfer("A", "MISSING", 10_000)`.

Expected: the service throws an error; the transaction rolls back, so A's balance remains `50_000` and B's remains `20_000`. If A was debited, inspect the transaction manager, topology, or how the service is invoked.

### Scenario C — Valid transfer

Execute `transfer("A", "B", 10_000)`.

Expected: A becomes `40_000`, B becomes `30_000`; total balance is unchanged. Run additional concurrent-request scenarios to surface conflicts and verify the application's retry policy.

### Scenario D — Distinguishing updateMany and transactions

Prepare multiple documents, execute `updateMany`, and inject a controlled error in a multi-command workflow. Do not expect a later error to automatically undo the earlier `updateMany` when **there is no transaction**. Run the same workflow inside a transaction to verify rollback boundaries.

### What to observe when diagnosing

- Log **business IDs, matched/modified document counts**, processing duration, and error codes; avoid logging sensitive data.
- Monitor `writeConflict`, transient transaction errors, timeouts, and unusual retry spikes.
- Use `explain` on frequent filter queries; proper indexes reduce execution time and resource cost, even though they do not alter operation atomicity.
- Check field existence and numeric types before using `$inc`; standardize currency or quantity units across services.

## 9. Common misconceptions

**"Is `updateMany` a single statement so it must be atomic across all documents?"**  
No. It updates **each document** atomically, not the entire result set.

**"Is `@Transactional` enough for transactions to work on any MongoDB?"**  
No. You need a transaction manager, a supporting MongoDB deployment, and calls actually passing through the Spring transaction interceptor.

**"Is reading the balance and calling `save` already safe because `save` is an atomic operation?"**  
Not enough. The `save` call itself may be atomic, yet it can still overwrite a newer value written by another thread between your read and your write. Use conditional updates/atomic operators or optimistic locking.

**"Will a MongoDB transaction roll back HTTP calls, Kafka messages, and emails too?"**  
No. A transaction covers only the MongoDB operations participating in that transaction; external systems require separate consistency mechanisms.

**"If we use transactions, do we no longer need conflict handling?"**  
No. Concurrent transactions can encounter write conflicts or transient errors. The application needs appropriate retry and idempotency strategies.

## 10. Self-practice exercises

1. Write an API `POST /inventory/{sku}/reserve` using `MongoTemplate` that rejects `quantity <= 0` and quantities exceeding stock; explain why two concurrent requests cannot both deduct past `available`.
2. A shopping cart stored in a single document contains items and `totalCents`. Propose a way to update both fields atomically; analyze when it should be split into another collection.
3. Create a points-transfer service between two customer wallets; run failure tests when the destination wallet does not exist and inspect both balances after rollback.
4. Explain why a `bulkWrite` batch is not equivalent to a transaction, and describe a case where transactions should be used instead of changing the data model.
5. Analyze a retry scenario when committing a transaction reports an unknown outcome. Design a unique `transferId` to prevent duplicate transfers.

## 11. Summary

- **One write command, one document:** atomic; multiple fields within the document can be modified together.
- **One multi-document update command:** atomic **per document**; no atomicity across the whole set by default.
- **Multiple related operations:** use conditions and update operators if invariants fit inside one document; use MongoDB transactions if invariants span multiple documents and must commit/roll back together.
- **At the Spring Data MongoDB layer:** `MongoTemplate` expresses filters and operators; `@Version` supports optimistic locking; `MongoTransactionManager` combined with `@Transactional` defines transaction boundaries when the environment supports them.
- **In real systems:** concurrency testing, rollback verification, read/write concerns, retries, and idempotency are essential when evaluating workflow correctness.

### Official references

- MongoDB Manual — [Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/).
- MongoDB Manual — [Transactions](https://www.mongodb.com/docs/manual/core/transactions/).
- Spring Data MongoDB — [Client Sessions and Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html).
