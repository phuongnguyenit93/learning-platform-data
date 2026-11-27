# MongoTransactionManager, @Transactional, and Session Scope in Spring Data MongoDB

## 1. The Problem: A Business Operation Requiring Changes to Multiple Documents Simultaneously

Suppose a Spring Boot application processes orders. When a user confirms an order, the system must perform two actions on MongoDB:

1. Transition the `orders` document status from `PENDING` to `CONFIRMED`.
2. Create an `outbox` document so a worker can publish an order confirmation event.

If the first step succeeds but the second step fails, the system could end up with a confirmed order that has no event to notify other services. A **multi-document transaction** ensures both MongoDB changes **commit** together or **abort** together, provided every operation participates in the **exact same transaction/session**.

~~~text
Client request
      |
      v
CheckoutService.confirmOrder()
      |
      +---- Update orders -------------------+
      |                                      |
      +---- Insert outbox event -------------+--- MongoDB Transaction
                                             |
                                +------------+------------+
                                |                         |
                                v                         v
                            Commit OK                Abort/Rollback
                                |                         |
                                v                         v
                       Both persisted together     No changes persisted
~~~

In Spring Data MongoDB, three concepts are commonly confused:

- `MongoTransactionManager`: Spring's synchronous transaction manager.
- `@Transactional`: declares transaction boundaries and policies on a method.
- `ClientSession`: the driver object that binds operations to the same session; MongoDB transactions are created **on a session**.

This lesson belongs to the **Database Engine Document MongoDB** module, **Spring Data MongoDB** chapter, titled **MongoTransactionManager, @Transactional, and Session Scope**.

### 1.1. What Will You Be Able to Do After This Lesson?

1. Explain why transactions are tied to a `ClientSession` and when multi-document atomicity is needed.
2. Verify replica set, sharded cluster, server version, and driver prerequisites.
3. Declare `MongoTransactionManager` in Spring Boot.
4. Write a `@Transactional` service using `MongoRepository` and `MongoTemplate`.
5. Distinguish method boundaries from session boundaries, commit, abort, and rollback.
6. Understand Spring proxy pitfalls, self-invocation, checked exceptions, and catch-and-swallow.
7. Choose `TransactionTemplate` or session callbacks when explicit control is needed.
8. Explain why raw driver calls, other threads, or reactive flows might not participate in the same transaction.
9. Use `ReactiveMongoTransactionManager` and `TransactionalOperator` for WebFlux/Reactor.
10. Configure readConcern, writeConcern, readPreference, and transaction options.
11. Distinguish retrying an entire transaction from retrying commit when the commit outcome is unknown.
12. Verify real rollback in an integration test running against a replica set.
13. Analyze operational constraints and avoid long-running transactions.
14. Design outbox, idempotency, monitoring, and runbooks for write conflicts or failovers.

**Key takeaway:** Having `@Transactional` on a method does not automatically turn every action in Java code into a system-wide atomic transaction. It only manages the resources and operations that the transaction manager actually controls.

## 2. When Do You Actually Need a Transaction?

MongoDB guarantees **atomicity at the single-document level**, even when updating multiple fields within that document. In many cases, schema embedding eliminates the need for a multi-document transaction.

For example, a shopping cart with an array of items:

~~~javascript
db.carts.updateOne(
  { _id: "cart-001" },
  {
    $set: {
      "items.0.quantity": 3,
      updatedAt: new Date()
    }
  }
);
~~~

This is an operation on a single document, so MongoDB applies it atomically under single-document update semantics. There is no need to open a transaction just to update two fields.

### 2.1. When Should You Evaluate Using a Transaction?

- Moving value between two accounts stored in two documents.
- Updating an order and writing an outbox event across two collections.
- Reserving seats and decrementing inventory with cross-document constraints.
- Writing multiple documents that must be all-or-nothing.
- Enforcing an invariant that cannot be expressed as an atomic update within a single document.

### 2.2. When Should You Avoid Overusing Transactions?

- A single `updateOne` with a sufficiently strict filter already enforces the business condition.
- A single document already holds the entire data aggregate that needs to stay synchronized.
- Multiple reads that do not require snapshot isolation.
- A large ETL or batch job that can be split into idempotent steps.
- A workflow spanning multiple services, HTTP, Kafka, or payment gateways outside MongoDB's control.

Transactions spanning multiple shards also carry higher overhead than transactions confined to a single shard or replica set.

### 2.3. ACID Within MongoDB's Scope

| Property | Practical Meaning |
|---|---|
| Atomicity | Writes within a transaction either all commit or all abort together |
| Consistency | Consistency according to the constraints and logic enforced by the application and enforced indexes |
| Isolation | Uncommitted changes are not visible externally; snapshot level depends on options |
| Durability | Durability level depends on write concern and deployment configuration |

Do not claim that transactions automatically enforce every business constraint if the schema lacks a unique index or deduplication logic.

## 3. Prerequisites Before Trying Transactions

MongoDB multi-document transactions require a supported topology:

| Deployment | Multi-document transaction |
|---|---|
| Standalone `mongod` | No |
| Replica set | Yes, since MongoDB 4.0 with appropriate FCV |
| Sharded cluster | Yes, since MongoDB 4.2 with appropriate FCV |
| MongoDB Atlas | Yes, on deployments/tiers that support transactions |
| Embedded/simulated MongoDB mock | Not equivalent to a real replica set by default |

### 3.1. Using a Replica Set in Lab Environments

A MongoDB container running in **standalone** mode may allow inserts and finds, yet fail when starting a transaction with:

~~~text
Transaction numbers are only allowed on a replica set member or mongos
~~~

This error is not fixed merely by adding `@Transactional`.

### 3.2. Checking with mongosh

On a self-managed node with appropriate privileges:

~~~javascript
db.hello();
~~~

On a replica set, the output typically includes `setName`, `isWritablePrimary`, or `secondary`. On `mongos`, you typically see `msg:"isdbgrid"`.

Check FCV when needed and permitted:

~~~javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
~~~

### 3.3. Compatible Driver and Server Versions

Use the MongoDB Java Driver and Spring Data versions managed by the Spring Boot BOM. Upgrading a MongoDB major version requires checking the compatibility matrix, not just seeing a starter in `pom.xml`.

### 3.4. Connecting to the Right Topology

Example self-managed replica set URI:

~~~text
mongodb://db1.example.test:27017,db2.example.test:27017,db3.example.test:27017/orders?replicaSet=rs0&authSource=admin&tls=true
~~~

Example Atlas SRV URI:

~~~text
mongodb+srv://<user>:<encoded-password>@cluster0.example.mongodb.net/orders?authSource=admin&retryWrites=true&w=majority
~~~

These are placeholders; never put real passwords into lessons or Git. Choose the appropriate `replicaSet` when using a self-managed seed list; `mongodb+srv` has its own discovery mechanism.

## 4. Session and Transaction: A Bounded One-to-Many Relationship

A `ClientSession` represents the client context so the server can identify related operations. Sessions support causal consistency and serve as the foundation for transactions.

~~~text
MongoClient
   |
   +---- ClientSession A
   |        |
   |        +---- Transaction 1: start -> operations -> commit
   |        |
   |        +---- Transaction 2: start -> operations -> abort
   |
   +---- ClientSession B
            |
            +---- Transaction 3: start -> operations -> commit
~~~

One session can participate in multiple transactions **sequentially**, but at any given time there can be at most **one active transaction on that session**.

### 4.1. A Session Does Not Automatically Mean a Transaction

You can use a `ClientSession` to perform causally consistent reads and writes without calling `startTransaction()`. Operations inside a session **do not automatically become an atomic unit** until a transaction is started.

### 4.2. A Transaction Requires Every Operation to Use the Same Session

In the Java Driver, raw operations provide overloads that accept `ClientSession`:

~~~java
collection.insertOne(session, document);
collection.updateOne(session, filter, update);
~~~

If you forget the `session` argument and call the overload without a session, that operation may run **outside** the intended transaction.

### 4.3. Close the Session When Done

Manual sessions must be closed via `close()`, typically with `try-with-resources`. Spring's transaction manager handles the session lifecycle automatically when declarative transactions are used properly.

### 4.4. Lazy Loading After the Session Closes

Some lazy data fetches (such as DBRef lazy loading) may require an active session. If an entity leaves the session scope before lazy data is dereferenced, the operation can fail. Design mapping and lifecycle appropriately rather than keeping sessions open indefinitely just to mask lazy loading.

## 5. Where Does Spring Manage Transactions?

In synchronous Spring Data MongoDB:

~~~text
Caller -> Spring AOP transactional proxy
                    |
                    v
            MongoTransactionManager
                    |
            start ClientSession
            start MongoDB transaction
                    |
           bind session to current thread
                    |
                    v
             Service method body
                  /      \
                 v        v
         MongoRepository MongoTemplate
                 \        /
                  \      /
             MongoDatabaseFactory
                    |
             same bound session
                    |
                    v
             commit / abort
                    |
          unbind / close session
~~~

`MongoTransactionManager` implements Spring's `PlatformTransactionManager`, opens the transaction, binds the `ClientSession` to the **current thread**, and completes/cleans up after the method returns.

`MongoTemplate` retrieves the session bound to the same `MongoDatabaseFactory` so operations participate in the transaction. Repositories use the underlying template/infrastructure and therefore participate when configured synchronously.

### 5.1. @Transactional Does Not Open a Socket Directly

The annotation is processed by Spring's transaction interceptor/AOP. It asks the transaction manager to supply resources, but the annotation itself does not replace the driver, replica set, or MongoDB sessions.

### 5.2. What If No Transaction Manager Is Registered?

According to the Spring Data MongoDB reference, transactional support requires registering `MongoTransactionManager` (or its reactive equivalent). Do not assume merely adding a starter automatically configures the transaction manager for your needs.

### 5.3. Using the Same MongoDatabaseFactory Matters

Two `MongoTemplate` beans using two different `MongoDatabaseFactory`/`MongoClient` instances will not automatically join the same transaction, even if they point to the same hostname/database and run on the same Java thread.

Do not mix repositories from two contexts or factories and assume they are in the "same transaction" just because the method has `@Transactional`.

## 6. Declaring MongoTransactionManager in Spring Boot

With Spring Data MongoDB and MongoDB Java Driver managed by the BOM:

~~~java
package example.orders.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration(proxyBeanMethods = false)
public class MongoTransactionConfig {

    @Bean("mongoTransactionManager")
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory mongoDatabaseFactory) {
        return new MongoTransactionManager(mongoDatabaseFactory);
    }
}
~~~

This is the minimal standard configuration. Spring Boot can auto-configure `MongoClient`, `MongoDatabaseFactory`, and `MongoTemplate`; adding the manager bean enables MongoDB transaction support per Spring Data guidance.

### 6.1. Why Explicit Bean Naming Helps

When an application also uses JDBC/JPA or messaging, multiple `PlatformTransactionManager` beans may coexist. Declaring:

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
~~~

selects the **exact** manager without relying on the environment's default/`@Primary` bean.

### 6.2. Do Not Create a Separate MongoClient in the Manager Configuration

Avoid the following configuration if the application already has an auto-configured client:

~~~java
// Anti-pattern: creating a separate MongoClient solely for the transaction manager.
// This can result in a different MongoDatabaseFactory or unintended connection pool.
~~~

The manager must use the exact same factory used by transactional repositories and `MongoTemplate`.

### 6.3. Spring Boot 3.x vs 4.x: URI Property

With Boot 3.5:

~~~yaml
spring:
  data:
    mongodb:
      uri: "${MONGODB_URI}"
~~~

With Boot 4.x:

~~~yaml
spring:
  mongodb:
    uri: "${MONGODB_URI}"
~~~

The difference lies in the **connection configuration prefix**. The `MongoTransactionManager` class resides in the `org.springframework.data.mongodb` package in modern releases. Verify against your actual Boot/Spring Data version.

### 6.4. Synchronous Dependency

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
~~~

Do not add the reactive starter if you only have synchronous code. Use the Spring Boot BOM to manage versions.

## 7. Document Design for the Order and Outbox Example

Create both collections up front:

~~~javascript
use orders_lab

db.createCollection("orders");
db.createCollection("outbox");

db.orders.createIndex(
  { tenantId: 1, status: 1 },
  { name: "idx_tenant_status" }
);

db.outbox.createIndex(
  { aggregateId: 1, type: 1 },
  { name: "idx_aggregate_type" }
);
~~~

Creating collections and indexes beforehand reduces the risk of first-time collection creation or index DDL happening inside a transaction and keeps schema management controlled in production.

### 7.1. Order Entity

~~~java
package example.orders.domain;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("orders")
public class Order {
    @Id
    private String id;
    private String tenantId;
    private String status;

    protected Order() {
    }

    public Order(String id, String tenantId, String status) {
        this.id = id;
        this.tenantId = tenantId;
        this.status = status;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
}
~~~

### 7.2. OutboxEvent Entity

~~~java
package example.orders.domain;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("outbox")
public class OutboxEvent {
    @Id
    private String id;
    private String aggregateId;
    private String type;
    private Instant occurredAt;

    protected OutboxEvent() {
    }

    public OutboxEvent(String id, String aggregateId, String type,
                       Instant occurredAt) {
        this.id = id;
        this.aggregateId = aggregateId;
        this.type = type;
        this.occurredAt = occurredAt;
    }

    public String getId() { return id; }
    public String getAggregateId() { return aggregateId; }
    public String getType() { return type; }
    public Instant getOccurredAt() { return occurredAt; }
}
~~~

### 7.3. Repositories

~~~java
package example.orders.repo;

import example.orders.domain.Order;
import example.orders.domain.OutboxEvent;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository extends MongoRepository<Order, String> {
}

public interface OutboxEventRepository
        extends MongoRepository<OutboxEvent, String> {
}
~~~

In a real Java project, place each public top-level interface in its own matching `.java` file. The snippet above combines them for presentation.

## 8. @Transactional on a Service: An Observable Example

~~~java
package example.orders.service;

import example.orders.domain.Order;
import example.orders.domain.OutboxEvent;
import example.orders.repo.OrderRepository;
import example.orders.repo.OutboxEventRepository;

import java.time.Instant;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CheckoutService {

    private final OrderRepository orders;
    private final OutboxEventRepository outbox;

    public CheckoutService(OrderRepository orders,
                           OutboxEventRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void confirm(String orderId) {
        Order order = orders.findById(orderId)
            .orElseThrow(() -> new IllegalArgumentException(
                "Order not found: " + orderId));

        if (!"PENDING".equals(order.getStatus())) {
            throw new IllegalStateException(
                "Order is not pending: " + orderId);
        }

        order.setStatus("CONFIRMED");
        orders.save(order);

        OutboxEvent event = new OutboxEvent(
            "order-confirmed:" + orderId,
            orderId,
            "OrderConfirmed",
            Instant.now()
        );
        outbox.save(event);
    }
}
~~~

If `orders.save` succeeds but `outbox.save` throws a runtime exception, Spring's transaction interceptor rolls back the transaction, so the order status is not committed.

### 8.1. Why Place the Transaction Boundary at the Service Layer?

A transaction wraps a **business use case**. Placing `@Transactional` on individual repository methods does not combine multiple repository calls into one transaction. The service method knows which operations need to be all-or-nothing.

### 8.2. Concurrency Limitations of This Example

The code above illustrates atomicity, not a complete concurrency solution:

- Two concurrent requests confirming the same order can race.
- MongoDB may raise a write conflict that causes one transaction to abort.
- A unique event ID prevents duplicate outbox entries but does not replace a retry/idempotency policy.
- Production systems should include conditional state transitions, versioning, or appropriate deduplication.

### 8.3. Transactions Do Not Send Kafka Events

The outbox document is committed inside MongoDB; **publishing** should be handled after commit by a worker/consumer with its own idempotency and retry handling. Do not send HTTP/Kafka messages inside a transaction and assume MongoDB can roll back external side effects.

## 9. Lifecycle of @Transactional

When a method is invoked **through a Spring-managed proxy**:

~~~text
1. Caller invokes CheckoutService proxy
2. Spring selects mongoTransactionManager
3. Manager creates/binds ClientSession
4. Manager starts MongoDB transaction
5. Service invokes repositories/MongoTemplate
6. Calls share the bound ClientSession
7. Method returns normally -> commitTransaction
8. Method throws rollback exception -> abortTransaction
9. Cleanup, unbind, close session
~~~

### 9.1. Commit Happens at the End of the Method, Not After Each save()

When `orders.save` returns successfully inside a transaction, the data is not necessarily visible to clients outside the transaction yet. Only a successful commit establishes the atomic outcome.

### 9.2. A Method Can Return Normally Yet Commit Can Still Fail

The transaction commit occurs when the interceptor finishes the method. Commit errors can occur at that point (network, failover, writeConcern, UnknownTransactionCommitResult). Running to the `return` statement in service code does not guarantee the caller receives success.

### 9.3. An Open Transaction Holds Expensive Resources

Holding a transaction open across sleeps, remote HTTP calls, file uploads, or user waits increases cache and resource pressure, extends lock durations, and raises the risk of abort.

## 10. @Transactional Proxy and Self-Invocation

Spring transaction annotations typically operate through an AOP proxy. **Internal calls on the same object** bypass the proxy.

~~~java
@Service
public class BadCheckoutService {

    public void submit(String orderId) {
        // Calls via 'this', bypassing the transactional proxy:
        confirmInternal(orderId);
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void confirmInternal(String orderId) {
        // Multiple MongoDB operations...
    }
}
~~~

If `submit()` is called from outside without an enclosing transaction, the self-call to `confirmInternal()` will not trigger the transaction advice as expected.

### 10.1. Better Approach: Split Services

~~~text
OrderController
      |
      v
OrderApplicationService
      |
      v
TransactionalCheckoutService proxy
      |
      v
@Transactional confirm()
~~~

~~~java
@Service
public class OrderApplicationService {
    private final CheckoutService checkout;

    public OrderApplicationService(CheckoutService checkout) {
        this.checkout = checkout;
    }

    public void submit(String orderId) {
        checkout.confirm(orderId);
    }
}
~~~

`CheckoutService` is a separate injected Spring bean, so public method invocations go through the proxy in standard configurations.

### 10.2. Private/Final Methods and Proxies

Do not place transaction boundaries on private helper methods expecting a Spring proxy to intercept them. Final methods/classes and JDK vs class-based proxies have different restrictions. Using public service methods invoked through a bean proxy is the cleanest and most testable model.

### 10.3. Constructors and @PostConstruct

Calling a transactional method inside a constructor or too early before the proxy is ready does not guarantee advice application. Data initialization should use an appropriate lifecycle/runner mechanism where the bean proxy and transaction setup are active.

## 11. Rollback Rules: RuntimeException, Checked Exception, and Error

By default, Spring rolls back on `RuntimeException` and `Error`, and **does not automatically roll back on checked exceptions**.

### 11.1. Runtime Exception

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void doWork() {
    // Write A
    throw new IllegalStateException("simulate failure");
    // Write B does not run
}
~~~

When an unchecked exception escapes the proxy, the transaction is aborted.

### 11.2. Checked Exception

~~~java
public class BusinessRuleException extends Exception {
    public BusinessRuleException(String message) {
        super(message);
    }
}
~~~

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager",
    rollbackFor = BusinessRuleException.class
)
public void confirmWithRule(String id) throws BusinessRuleException {
    // Write A
    throw new BusinessRuleException("rule failed");
}
~~~

If you omit `rollbackFor`, a checked exception will **not** trigger a rollback under Spring's default behavior. Explicitly define your rollback policy.

### 11.3. Do Not Use Checked Exceptions Solely to Signal Rollback

Consider separating business validation that happens **before writes** from system failures that happen **after writes**. Validating before opening a transaction reduces resource usage and error-handling complexity.

## 12. Catch-and-Swallow Can Accidentally Commit

Common mistake:

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void unsafeAction() {
    try {
        // Write A
        // Write B -> fails
    } catch (Exception e) {
        // Log only, do not rethrow -> interceptor may commit!
    }
}
~~~

If the exception is swallowed, the method returns normally and Spring may attempt to commit. For certain MongoDB operation errors, the server transaction may already be in an abort-only state; however, you must never rely on that as a business rollback mechanism.

### 12.1. Preferred Pattern: Let the Exception Propagate

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void saferAction() {
    // Write A
    // Write B: if it fails, let the RuntimeException propagate.
}
~~~

### 12.2. When You Must Handle the Error Inside the Method

You can explicitly mark the transaction rollback-only:

~~~java
import org.springframework.transaction.interceptor.TransactionAspectSupport;

try {
    // ... actions
} catch (KnownBusinessException e) {
    TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
    // Only return a response after ensuring it does not claim commit succeeded.
}
~~~

This approach couples your code to the transaction context and Spring's transaction infrastructure. Prefer keeping validation separate and exception flows clear.

### 12.3. UnexpectedRollbackException

If an inner method marks a shared transaction as rollback-only while the outer method completes normally, the outer caller can receive an `UnexpectedRollbackException` at commit time. Do not fix this by suppressing the exception; align propagation, error handling, and the intended business behavior.

## 13. Transaction Propagation: REQUIRED and Its Limits

Propagation values are **Spring transaction manager** concepts, not a 1:1 mapping to "nested MongoDB transactions".

| Propagation | Spring-Level Meaning | MongoDB Notes |
|---|---|---|
| `REQUIRED` | Join existing transaction or create a new one | Usually the appropriate default |
| `SUPPORTS` | Join if one already exists | Does not guarantee a transaction if called standalone |
| `MANDATORY` | Require an already active transaction | Useful to enforce boundaries |
| `NEVER` | Must not run inside a transaction | Fails if the caller is transactional |
| `NOT_SUPPORTED` | Run outside a transaction if manager supports suspend | Verify manager/resource behavior |
| `REQUIRES_NEW` | Require an independent transaction with suspend/resume | Do not assume the Mongo manager supports every case |
| `NESTED` | Savepoint-style nested transaction | MongoDB provides no equivalent nested transaction or savepoint |

### 13.1. REQUIRED Does Not Create a Child Transaction

If `ServiceA.operation()` opens a transaction and calls `ServiceB.save()` marked `REQUIRED`, both normally share the **same** MongoDB transaction/session.

~~~text
A @Transactional(REQUIRED)
    |
    +--> B @Transactional(REQUIRED)
            |
         Same ClientSession
         Same transaction
~~~

### 13.2. Do Not Blindly Use REQUIRES_NEW for Auditing

Do not use `REQUIRES_NEW` expecting guaranteed audit writes even when the outer transaction aborts; with the MongoDB transaction manager, suspension/restart may not behave as expected depending on context. If independent auditing is needed, use separate verified infrastructure and understand it is **not** part of the same atomic unit.

### 13.3. NESTED Does Not Mean a Transaction Inside a Transaction

MongoDB allows only one active transaction per session and has no JDBC-style savepoints for MongoDB transactions. Do not use `Propagation.NESTED` expecting partial rollback of some writes while committing the rest.

### 13.4. Transaction Manager Name

In a service that uses both MongoDB and JDBC:

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
~~~

This annotation does not cover SQL writes managed by `JpaTransactionManager` or HTTP calls. Two independent transaction managers **do not** automatically form a distributed two-phase commit.

## 14. @Transactional(readOnly = true) Does Not Mean "No Session"

In Spring Data MongoDB, `@Transactional(readOnly = true)` can still start a transaction and bind a `ClientSession` to operations. It is not the optimal default for every read-only API.

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager",
    readOnly = true
)
public Order findOrder(String id) {
    return orders.findById(id).orElseThrow();
}
~~~

### 14.1. Do Not Treat readOnly as Write Access Control

`readOnly=true` is a Spring-level transaction hint/configuration; do not use it in place of MongoDB database roles or ACLs. To block writes, grant a read-only user role in MongoDB.

### 14.2. Read Preference Inside Transactions

Transactions containing reads must use `primary` according to MongoDB documentation. Do not expect `@Transactional(readOnly=true)` to automatically route all queries to secondaries.

### 14.3. Does Reading a Single Document Need a Transaction?

Usually no, unless there are explicit consistency requirements. A read-only transaction incurs snapshot/session overhead and should be chosen based on use case needs.

## 15. Transaction Options: Read Concern, Write Concern, Read Preference

MongoDB transaction isolation and durability depend on options:

- `ReadConcern.SNAPSHOT`: uses snapshot consistency subject to support requirements.
- `WriteConcern.MAJORITY`: commit is acknowledged by a majority of nodes; a common choice for durability.
- `ReadPreference.primary()`: required for transactions that perform read operations.
- `maxCommitTime`: limits commit operation duration per driver settings.

### 15.1. Configuring Defaults in MongoTransactionManager

~~~java
package example.orders.config;

import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration(proxyBeanMethods = false)
public class MongoTransactionConfig {

    @Bean("mongoTransactionManager")
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {

        TransactionOptions options = TransactionOptions.builder()
            .readConcern(ReadConcern.SNAPSHOT)
            .writeConcern(WriteConcern.MAJORITY)
            .readPreference(ReadPreference.primary())
            .build();

        return new MongoTransactionManager(factory, options);
    }
}
~~~

This is an **intentional configuration** for a specific class of workload; do not claim every application must use this exact option set.

### 15.2. Distinguishing writeConcern Inside a Transaction

A transaction's write concern applies at commit time per MongoDB semantics; do not assume a separate write concern set on an individual collection operation overrides the commit guarantee.

### 15.3. Snapshot in Sharded Clusters

For multi-shard transactions, `snapshot` read concern is used when a consistent snapshot across shards is required. Other levels do not guarantee the same cross-shard snapshot.

### 15.4. Do Not Use Secondary Read Preference in a Read Transaction

MongoDB documentation requires transactions with reads to use primary, even if Spring Data transaction labels accept broader enum values at the config layer. "Accepted by the parser" does not mean the server supports those semantics in an active transaction.

## 16. @Transactional Labels for Mongo-Specific Options

Supported Spring Data MongoDB versions can read transaction labels to determine options at the transaction boundary.

Example:

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager",
    label = {
        "mongo:readConcern=SNAPSHOT",
        "mongo:writeConcern=MAJORITY",
        "mongo:readPreference=PRIMARY",
        "mongo:maxCommitTime=PT1S"
    }
)
public void confirmWithOptions(String orderId) {
    // MongoDB operations within the same factory/session
}
~~~

### 16.1. Verify Spring Data Version

Transaction labels and `MongoTransactionOptionsResolver` depend on the Spring Data release. Do not copy annotations from modern docs into an older version and assume they are supported.

### 16.2. Outer Transaction Options Win

When an inner `REQUIRED` method joins an already open transaction, labels on the inner method **do not modify** the options of the active transaction. Set consistency and durability options at the boundary that actually starts the transaction.

### 16.3. Annotation Timeout Does Not Replace Server Lifetime Limit

`@Transactional(timeout = 10)` is a Spring transaction setting and does not necessarily govern the entire MongoDB server transaction lifetime as you might assume. The server enforces `transactionLifetimeLimitSeconds` (typically 60 seconds by default), and commit has its own `maxCommitTime`. Check driver, manager, and server semantics.

## 17. TransactionTemplate: Programmatic Boundaries Instead of Annotations

If you want explicit boundaries, use `TransactionTemplate`.

~~~java
package example.orders.service;

import example.orders.domain.Order;
import example.orders.repo.OrderRepository;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class OrderProgrammaticService {
    private final OrderRepository orders;
    private final TransactionTemplate tx;

    public OrderProgrammaticService(
            OrderRepository orders,
            @Qualifier("mongoTransactionManager")
            PlatformTransactionManager manager) {
        this.orders = orders;
        this.tx = new TransactionTemplate(manager);
    }

    public void markConfirmed(String id) {
        tx.executeWithoutResult(status -> {
            Order order = orders.findById(id).orElseThrow();
            order.setStatus("CONFIRMED");
            orders.save(order);
        });
    }
}
~~~

### 17.1. When Is This Appropriate?

- A method has multiple branches and only one section needs a transaction.
- You want to place a retry wrapper around a callback.
- You want to set rollback-only deliberately.
- You want to avoid self-invocation proxy pitfalls within reasonable code scope.

### 17.2. Setting Rollback-Only

~~~java
tx.executeWithoutResult(status -> {
    if (businessRuleFails()) {
        status.setRollbackOnly();
        return;
    }
    // Mongo operations...
});
~~~

Assume `businessRuleFails()` is an application business method. Make sure the return value communicates the rollback to the caller rather than reporting that the order was completed when the transaction did not actually commit.

### 17.3. TransactionTemplate Must Use the Same Manager/Factory

If `TransactionTemplate` is wired with a JDBC manager, `MongoTemplate` will not automatically be wrapped in a MongoDB transaction. Select and inject the right manager.

## 18. Manual ClientSession: When Do You Need Direct Control?

Spring Data's `MongoTemplate.withSession(...)` lets you scope a sequence of operations to a specific session.

Simplified example:

~~~java
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class SessionReader {

    private final MongoClient client;
    private final MongoTemplate template;

    public SessionReader(MongoClient client, MongoTemplate template) {
        this.client = client;
        this.template = template;
    }

    public void readWithSession(String id) {
        try (ClientSession session = client.startSession()) {
            template.withSession(session).execute(ops -> {
                Query query = Query.query(Criteria.where("_id").is(id));
                ops.findOne(query, Order.class);
                return null;
            });
        }
    }
}
~~~

The snippet above **uses a session without calling `startTransaction`**, so it does not create a multi-document atomic transaction.

### 18.1. Manual Transaction with the Driver

~~~java
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

public void writeAtomically(MongoClient client) {
    MongoCollection<Document> left =
        client.getDatabase("orders_lab").getCollection("left");
    MongoCollection<Document> right =
        client.getDatabase("orders_lab").getCollection("right");

    try (ClientSession session = client.startSession()) {
        session.startTransaction();

        try {
            left.insertOne(session,
                new Document("_id", "left-001").append("value", 1));
            right.insertOne(session,
                new Document("_id", "right-001").append("value", 2));

            session.commitTransaction();
        } catch (RuntimeException ex) {
            if (session.hasActiveTransaction()) {
                session.abortTransaction();
            }
            throw ex;
        }
    }
}
~~~

This is a conceptual example that risks duplicate IDs if re-executed. Production code should use proper driver transaction retry APIs/`withTransaction` and idempotent business keys rather than treating this demo snippet as a complete recovery strategy.

### 18.2. Do Not Mix Manual Sessions with @Transactional Uncontrolled

A method annotated with `@Transactional` that also calls `client.startSession()` directly may create a **second independent session**. Raw operations on that new session will not implicitly join the Spring-bound transaction.

### 18.3. getCollection() Is a Native Driver Gateway

`MongoTemplate.getCollection()` returns a native `MongoCollection`, and according to Spring Data docs, direct operations on this gateway may not have the session proxy propagated automatically. When a transaction is required, use `MongoTemplate` operations or explicitly pass `ClientSession` to the appropriate driver overloads.

## 19. Session Scope in Synchronous Spring: ThreadLocal

`MongoTransactionManager` binds the session to the **current thread** via Spring's transaction synchronization and resource binding.

~~~text
HTTP worker thread A
  |
  +-- @Transactional service A
         |
         +-- Repository.insert    -> session S1
         +-- MongoTemplate.update -> session S1
         +-- Repository.find      -> session S1
  |
  +-- return / commit / unbind

Executor thread B
  |
  +-- Mongo operation            -> DOES NOT automatically have session S1
~~~

### 19.1. @Async Does Not Inherit Transactions

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void confirm(String id) {
    orders.save(...);

    asyncWorker.sendNotification(id); // @Async runs on another thread
}
~~~

The asynchronous call may execute before commit or after rollback and **does not share the same thread/session**. Avoid firing side effects from inside a transaction; use an outbox or an after-commit event handler with appropriate semantics.

### 19.2. CompletableFuture / new Thread / ExecutorService

Spawning a new thread inside a transactional method does not propagate the `ThreadLocal` session:

~~~java
CompletableFuture.runAsync(() -> repository.save(...));
~~~

The async operation can run outside the transaction and out of order. Do not write a custom "ThreadLocal copy" to share a `ClientSession` across threads; the MongoDB Java Driver does not permit running operations concurrently on the same transaction/session.

### 19.3. Servlet Request Scope Differs from Transaction Scope

A single HTTP request can invoke multiple services. The transaction boundary covers only the method/call stack managed by the transaction manager—it is **not** automatically equivalent to the entire request or response stream.

### 19.4. Sessions Are Not Safe for Arbitrary Concurrent Use

MongoDB does not support parallel operations inside the same transaction. Do not use `parallelStream` or multiple concurrent futures sharing one session to "optimize" a multi-document transaction.

## 20. Reactive: Do Not Use the Blocking MongoTransactionManager

In WebFlux/Reactor, Spring Data MongoDB provides `ReactiveMongoTransactionManager`.

~~~text
Reactive request publisher
          |
          v
TransactionalOperator / @Transactional
          |
          v
Reactor Context holding transactional resources
          |
          v
ReactiveMongoTemplate / Reactive repository
          |
          v
Reactive MongoDB driver + session
~~~

**Important differences:**

| Execution Model | Transaction Manager | Session Binding |
|---|---|---|
| Synchronous/blocking | `MongoTransactionManager` | Thread-bound |
| Reactive | `ReactiveMongoTransactionManager` | Reactor Context |

### 20.1. Declaring the Reactive Manager

~~~java
package example.orders.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;

@Configuration(proxyBeanMethods = false)
public class ReactiveMongoTxConfig {

    @Bean("reactiveMongoTransactionManager")
    ReactiveMongoTransactionManager reactiveMongoTransactionManager(
            ReactiveMongoDatabaseFactory factory) {
        return new ReactiveMongoTransactionManager(factory);
    }
}
~~~

### 20.2. @Transactional on a Reactive Method

~~~java
@Service
public class ReactiveCheckoutService {
    private final ReactiveOrderRepository orders;
    private final ReactiveOutboxRepository outbox;

    public ReactiveCheckoutService(
            ReactiveOrderRepository orders,
            ReactiveOutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional(transactionManager = "reactiveMongoTransactionManager")
    public Mono<Void> confirm(String orderId) {
        return orders.findById(orderId)
            .switchIfEmpty(Mono.error(
                new IllegalArgumentException("Order not found")))
            .flatMap(order -> {
                order.setStatus("CONFIRMED");

                return orders.save(order)
                    .then(outbox.save(new OutboxEvent(
                        "order-confirmed:" + orderId,
                        orderId,
                        "OrderConfirmed",
                        java.time.Instant.now()
                    )));
            })
            .then();
    }
}
~~~

Here `ReactiveOrderRepository` and `ReactiveOutboxRepository` are interfaces you declare extending `ReactiveMongoRepository<..., String>`, and `Mono` is `reactor.core.publisher.Mono`. Required reactive imports, beans, and dependencies are needed to compile.

### 20.3. Do Not Call block() to Create a "Sync Transaction"

~~~java
// Anti-pattern in a reactive flow:
reactiveRepository.save(order).block();
~~~

Switching to blocking can lose the Reactor Context and cause deadlocks or thread starvation in WebFlux. Reactive transactions must preserve the publisher chain and be subscribed to by the framework.

### 20.4. Reactor Laziness

A method returning `Mono` performs no I/O when called; operations occur upon subscription. The reactive transactional interceptor manages scope through the publisher lifecycle, so you cannot infer open/commit timing purely from the Java line creating the `Mono`.

### 20.5. Synchronous Repositories and Reactive Managers Are Not Interchangeable

Do not mix blocking `MongoRepository` with `ReactiveMongoTransactionManager` expecting a shared session. Match the transaction model to your driver/template/repository stack.

## 21. TransactionalOperator for Reactor

In reactive flows, `TransactionalOperator` lets you define transaction scope without a method proxy.

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

@Service
public class ReactiveAtomicService {
    private final ReactiveMongoTemplate mongoTemplate;
    private final TransactionalOperator operator;

    public ReactiveAtomicService(
            ReactiveMongoTemplate mongoTemplate,
            @Qualifier("reactiveMongoTransactionManager")
            ReactiveTransactionManager manager) {
        this.mongoTemplate = mongoTemplate;
        this.operator = TransactionalOperator.create(manager);
    }

    public Mono<Void> writeTwoDocuments() {
        return mongoTemplate.insert(
                new Document("_id", "a1"), "a")
            .then(mongoTemplate.insert(
                new Document("_id", "b1"), "b"))
            .then()
            .as(operator::transactional);
    }
}
~~~

This condensed snippet uses `org.bson.Document` and `org.springframework.data.mongodb.core.ReactiveMongoTemplate`; reactive dependencies and pre-created collections are required.

### 21.1. Transaction Scope Applies Only to the Wrapped Publisher

`.as(operator::transactional)` wraps only upstream operations in the supplied publisher. An independent `Mono`/`Flux` subscribed outside that chain may fall outside the transaction.

### 21.2. Do Not Manually Subscribe Inside a Service

~~~java
// Anti-pattern: subscribing in a detached stream inside a service.
repository.save(order).subscribe();
return Mono.empty();
~~~

Written this way, the save executes independently, making error/commit tracking difficult. Return the publisher and compose with `then`/`flatMap` so the manager stays in control.

### 21.3. Manual Reactive ClientSession Differs from Reactive Transaction Manager

The Spring Data reference distinguishes session callbacks on `ReactiveMongoTemplate` from managed reactive transactions. Do not try to carry an imperative manager's `ThreadLocal` session into Reactor Context.

## 22. MongoTemplate and SessionSynchronization

`MongoTemplate` exposes a `SessionSynchronization` setting:

| Value | Meaning |
|---|---|
| `ON_ACTUAL_TRANSACTION` | Participates in native MongoDB transactions opened by `MongoTransactionManager` |
| `ALWAYS` | Participates in other Spring transactions as well and may initiate a MongoDB transaction per infrastructure |
| `NEVER` | Does not synchronize with transactional sessions |

In modern Spring Data MongoDB versions, the default is `ON_ACTUAL_TRANSACTION`.

### 22.1. Do You Need to Set ALWAYS When Using MongoTransactionManager?

Usually **no** when already using `MongoTransactionManager` with the matching factory and the default `ON_ACTUAL_TRANSACTION`. `ALWAYS` is intended for other scenarios, such as participating in a non-native MongoDB Spring transaction per documentation.

### 22.2. Do Not Mutate Settings at Runtime

~~~java
// Avoid changing this while multiple threads are active:
template.setSessionSynchronization(SessionSynchronization.ALWAYS);
~~~

Spring Data warns that mutating `MongoTemplate` state at runtime can cause threading and visibility issues. Configure it once before the bean serves traffic.

### 22.3. ALWAYS Does Not Create Distributed XA

Having `MongoTemplate` synchronize with another Spring transaction does not turn MongoDB and JDBC/Kafka into a single global atomic commit. For cross-system consistency, use an outbox, saga, or another pattern suited to your failure modes and semantics.

## 23. Session Scope Across Multiple MongoClients/Factories

Suppose an application has:

~~~text
MongoClient A -> MongoDatabaseFactory A -> MongoTemplate A
MongoClient B -> MongoDatabaseFactory B -> MongoTemplate B
~~~

If `MongoTransactionManager` is built from factory A, operations on Template B do not automatically join transaction A.

### 23.1. Same URI Does Not Mean Same Transaction

Even if A and B target the same deployment, driver sessions are distinct objects and Spring resource binding keys off the factory. Never "assume" matching hostnames are enough.

### 23.2. Multi-Tenant Database Routing

A custom `MongoDatabaseFactory` that selects a database per tenant can complicate session and transaction binding. Ensure the tenant context remains constant throughout the transaction and all calls use the same session/factory. Never switch tenants mid-flight inside an open transaction.

### 23.3. Multiple PlatformTransactionManagers

If you have Mongo, JDBC, Redis, and messaging:

- Name beans explicitly.
- Use `@Transactional(transactionManager="...")`.
- Do not let `@Primary` accidentally determine boundaries.
- Do not assume cross-store atomicity.
- Test scenarios where one store commits while another fails.

## 24. Operations That Remain Outside the Transaction Even Inside the Method

Example:

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void process(String id) {
    orders.save(...);              // MongoDB - can participate in tx
    paymentGateway.charge(...);    // HTTP - NOT part of MongoDB tx
    kafkaTemplate.send(...);       // Kafka - NOT part of MongoDB tx
    auditJdbcRepository.save(...); // JDBC - different manager
}
~~~

MongoDB can abort `orders.save`, yet it cannot undo a completed payment charge or a message already acknowledged by the broker.

### 24.1. Synchronous Transactions Combined with External Side Effects Are Dangerous

Holding a transaction open while calling a payment gateway for several seconds raises timeout, cache, and lock pressure risks. If the MongoDB commit fails after the gateway has charged the customer, the system needs compensation or deduplication.

### 24.2. Outbox Pattern

Instead of sending messages directly:

~~~text
@Transactional:
  - update order
  - insert outbox event

Commit MongoDB

Outbox worker:
  - fetch event
  - publish to broker
  - mark delivered / retry idempotently
~~~

The outbox persists data and publication intent atomically in MongoDB; delivery typically still has **at-least-once** semantics, so consumers must be idempotent.

### 24.3. After-Commit Callbacks Do Not Guarantee Atomic Delivery

Spring offers `@TransactionalEventListener(phase = AFTER_COMMIT)` and transaction synchronizations. They run callbacks only after commit, yet **if the process crashes after commit before sending the message**, the event can be lost. An outbox is more durable for critical event delivery.

## 25. Transaction Retries: Not Every Error Is Safe to Retry

MongoDB uses error labels to help drivers and applications distinguish transient transaction failures from uncertain commit outcomes.

Two key labels:

- `TransientTransactionError`: may require retrying the **entire transaction** from the beginning.
- `UnknownTransactionCommitResult`: commit was sent, but the client does not know whether it succeeded; typically requires retrying the **commit** per the protocol algorithm rather than immediately re-running business writes.

### 25.1. TransientTransactionError

For example, a transaction encounters a write conflict or failover before commit. Handling typically looks like:

~~~text
Attempt 1:
 start tx -> writes -> transient error -> abort
Attempt 2:
 start NEW tx -> re-read state -> writes -> commit
~~~

Retries must have bounded attempt/time limits, jitter/backoff, and invariant checks—never an infinite loop.

### 25.2. UnknownTransactionCommitResult

~~~text
Client sends commitTransaction
        |
        v
Network timeout
        |
        v
Unknown whether server committed
~~~

Do not assume "timeout means rollback". Re-running the whole business flow could emit duplicate outbox events or charges if the first transaction actually committed; retry commit according to driver/manual guidance or reconcile using an idempotent business key.

### 25.3. @Transactional Does Not Automatically Retry All MongoDB Errors

Spring's transaction interceptor handles commit/rollback based on outcomes. It is not a generic MongoDB retry engine for transaction bodies or commit ambiguity.

### 25.4. Retry Wrapper Must Sit Outside the Transaction Boundary

One architecture:

~~~text
Retry orchestrator (outer)
         |
         v
@Transactional service proxy (each attempt = new tx)
         |
         v
MongoDB operations
~~~

If using Spring Retry annotations, verify advice ordering and behavior with an integration test. The clearest approach is an outer retry bean calling a separate transactional service bean—no self-invocation.

### 25.5. Idempotency Is the Business Safety Net

Consider a request confirming an order whose ID is already confirmed. When retrying after an uncertain commit, the system should converge on the final state and unique event key instead of producing duplicate side effects.

## 26. Transaction Lifetime and Performance

MongoDB defaults to a transaction lifetime limit typically of **60 seconds**, controlled by `transactionLifetimeLimitSeconds` on `mongod` (subject to admin policy/tier). Overly long transactions are periodically aborted.

### 26.1. Do Not Perform Non-Database I/O Inside a Transaction

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void badFlow() {
    // MongoDB write A
    // Upload file for 30 seconds
    // Call HTTP for 20 seconds
    // MongoDB write B
}
~~~

Waiting seconds on I/O forces the transaction to hold snapshots and resources longer, raising cache pressure and abort risk.

### 26.2. Large Transactions

Writing too many documents in one transaction creates storage-cache pressure and errors such as:

- `WriteConflict`.
- `TransactionTooLargeForCache`.
- Transaction lifetime exceeded.
- Lock acquisition timeout.
- Commit network/writeConcern timeout.

### 26.3. Sharded Transactions Incur Extra Cost

Transactions touching multiple shards have higher coordination overhead than single-shard transactions. If schema/shard keys allow keeping a business aggregate on a single shard, optimization is usually much simpler.

### 26.4. Design Short Transactions

- Validate inputs beforehand.
- Precompute deterministic values.
- Perform only the MongoDB operations requiring all-or-nothing atomicity.
- Do not call remote services inside the transaction.
- Do not sleep or hold long application locks.
- Enforce timeout/budgets and track metrics.
- Apply retries/backoff with proper semantics.

## 27. Collection/Index DDL in Transactions: Avoid Implicit Collection Creation

Spring Data documentation recommends preparing collections and indexes before executing transactions, because creating collections "on first use" may be incompatible with transaction workflows.

### 27.1. MongoDB Server Version Nuances

Modern MongoDB servers support certain collection/index creation operations inside transactions under specific conditions, for example:

- Not a cross-shard write transaction.
- Index creation is restricted to new/empty collections.
- Explicit DDL inside a transaction requires a suitable read concern (typically `local`).

**However**, Spring Data applications should not rely by default on dynamic DDL inside transactions. Pre-creating collections and indexes reduces risk, prevents unexpected metadata locks, and avoids version/topology edge cases.

### 27.2. Do Not Enable Auto-Index Creation Arbitrarily on Production Startup

Building large indexes during application startup can impact throughput and transaction behavior. Manage schema/index migrations as separate changes, verifying data and duplicate keys before creating unique indexes.

### 27.3. DB Admin Operations Do Not Belong in Normal Transactions

Do not run user creation, replica config, backup/restore, or `explain` inside business transactions. Some operations are unsupported inside transactions by the server, and others have global effects that cannot be rolled back like document writes.

## 28. Count, Geo Queries, and Transactional Semantics

Some helpers behave differently inside transactions.

### 28.1. count vs countDocuments

MongoDB's `count` command reads collection metadata and is unsuitable for transactions; Spring Data's `MongoTemplate.count` switches to an aggregation (`$match + $count`) when an active transaction is detected, per Spring Data docs.

Example:

~~~java
Query query = Query.query(Criteria.where("status").is("OPEN"));
long total = mongoTemplate.count(query, Order.class);
~~~

Inside a transaction, understand that the query executes differently compared to an estimated/metadata count.

### 28.2. Geo Near Limitations

Operators such as `$near` / `$nearSphere` have limitations in certain aggregation count paths. Spring Data docs recommend substituting `$geoWithin`/`$center` or `$centerSphere` expressions where appropriate.

### 28.3. Do Not Rely on Database-Wide Counts to Prove Atomicity

A good rollback test checks **both involved collections** with a failure injected at the right point, rather than merely checking an overall document count.

## 29. Transactions and Spring Tests: Why Tests Easily Mislead

### 29.1. A Standalone Container Is Not Enough

An integration test running only standalone MongoDB can execute repository CRUD yet fail as soon as a transaction opens. MongoDB Testcontainers should run as a replica set (e.g., using the URL from `MongoDBContainer.getReplicaSetUrl()` in the appropriate version).

### 29.2. Property Names by Boot Version

Spring Boot 3.5:

~~~text
spring.data.mongodb.uri
~~~

Spring Boot 4.x:

~~~text
spring.mongodb.uri
~~~

If `@DynamicPropertySource` injects the wrong key, the test may accidentally connect to `localhost`/the default database.

### 29.3. @DataMongoTest Does Not Scan Every Service/Config

`@DataMongoTest` focuses on `MongoTemplate`, `@Document`, and repositories. Configuration or services outside that slice may not be scanned. When testing transactional services, use `@SpringBootTest` or `@Import` the required beans and manager.

### 29.4. @Transactional on a Test Method Can Hide a Missing Commit

If Spring automatically rolls back the test method at the end, querying data **inside the same transaction** may show writes as visible even though commit was never attempted. You need a test that commits for real and reads back from a separate session/transaction.

## 30. Integration Test Verifying Rollback Across Two Collections

A test workflow:

~~~text
1. Seed a PENDING order
2. Call service through Spring proxy
3. Inside service: write order, write outbox, inject exception
4. Transaction aborts
5. Read from a new session:
   - order is still PENDING
   - outbox event does not exist
~~~

### 30.1. Example Adding a Failure-Test Method to the Lab Service

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void confirmThenFailForTest(String orderId) {
    Order order = orders.findById(orderId).orElseThrow();
    order.setStatus("CONFIRMED");
    orders.save(order);

    outbox.save(new OutboxEvent(
        "test-order-confirmed:" + orderId,
        orderId,
        "OrderConfirmed",
        java.time.Instant.now()
    ));

    throw new IllegalStateException("injected failure");
}
~~~

Place this method in `CheckoutService` only for a **test profile/lab**, never expose it as a production endpoint.

### 30.2. Illustrative JUnit Test

~~~java
@SpringBootTest
class CheckoutTransactionIT {

    @Autowired CheckoutService checkout;
    @Autowired OrderRepository orders;
    @Autowired OutboxEventRepository outbox;

    @Test
    void rollbacksBothCollections() {
        String id = "order-test-rollback-001";

        orders.save(new Order(id, "tenant-test", "PENDING"));

        assertThrows(IllegalStateException.class,
            () -> checkout.confirmThenFailForTest(id));

        Order after = orders.findById(id).orElseThrow();
        assertEquals("PENDING", after.getStatus());

        assertFalse(outbox.existsById("test-order-confirmed:" + id));
    }
}
~~~

In a real test class, add JUnit/Spring Test imports, replica-set Testcontainers setup, property injection, fixture cleanup, and test isolation. **Do not** annotate the test method itself with `@Transactional` here if your goal is to observe rollback from outside the transaction.

### 30.3. Testing Successful Commit

Run `checkout.confirm(id)` on a `PENDING` order, then read back the `CONFIRMED` order and matching outbox ID. Continue testing concurrent confirmations, duplicate requests, and transient failures.

### 30.4. Testing When the Second Operation Fails

For example, pre-seed the outbox with a duplicate ID; `outbox.save` may perform a replacement instead of an insert when given the same ID, so testing duplicate-key failures requires `insert` or explicit custom unique constraints. Do not assume `save` always throws a duplicate-key exception.

## 31. Testcontainers Replica Set: Configuration Outline

With compatible Testcontainers/Spring Boot versions:

~~~java
// Structural pseudocode: imports and MongoDBContainer package
// depend on the Testcontainers 1.x/2.x version in your build.

@Testcontainers
@SpringBootTest
class MongoTransactionIntegrationTests {

    @Container
    static MongoDBContainer mongodb =
        new MongoDBContainer("mongo:8.0");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.mongodb.uri",
            mongodb::getReplicaSetUrl
        );
    }
}
~~~

The snippet sets the **Spring Boot 3.5** property. For Boot 4.x, change it to `spring.mongodb.uri`. Add `spring-boot-starter-test`, Testcontainers MongoDB/JUnit dependencies, and an approved MongoDB image/version.

### 31.1. Why Use the Replica Set URL?

The Testcontainers MongoDB module can initialize a replica set on the created container under supported setups. The transaction manager requires a server supporting sessions and transactions, not just port 27017.

### 31.2. What If Testcontainers 2.x Changes Imports/Packages?

Consult the javadocs and modules for your exact major version. Do not copy old imports and assume identical behavior.

### 31.3. Test End-to-End, Not Just Context Load

A "Spring context starts" test only proves beans can be instantiated. You must execute a committing transaction, a rolling-back transaction, and verify state outside the transaction.

## 32. Observing Running Transactions

Transaction issues can manifest as:

- Increasing transaction aborts.
- Rising commit duration p95/p99.
- Write conflicts.
- Long-running transactions.
- WiredTiger cache pressure.
- Driver retries and connection pool waits.
- Lock acquisition timeouts.
- Primary elections and network issues.
- Sharded transaction coordination costs.

### 32.1. serverStatus

In a self-managed or Atlas environment with appropriate privileges:

~~~javascript
const s = db.adminCommand({ serverStatus: 1 });

printjson({
  host: s.host,
  transactions: s.transactions,
  connections: s.connections
});
~~~

Field/metric names depend on the MongoDB server version/tier. Cumulative counters such as commits and aborts require rate calculations and handling process resets.

### 32.2. Current Operations

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      localOps: true
    }
  },
  {
    $match: {
      active: true,
      secs_running: { $gte: 5 }
    }
  },
  {
    $project: {
      opid: 1,
      ns: 1,
      secs_running: 1,
      waitingForLock: 1
    }
  },
  { $limit: 20 }
]);
~~~

`$currentOp` requires privileges and does not automatically expose full commands/PII. Do not run `killOp` indiscriminately whenever a transaction looks slow.

### 32.3. Application Metrics

Consider collecting:

~~~text
mongo_transaction_attempts_total
mongo_transaction_commits_total
mongo_transaction_aborts_total
mongo_transaction_commit_duration_seconds
mongo_transaction_retry_attempts_total
mongo_transaction_unknown_commit_results_total
~~~

These are **illustrative custom-instrumented metric names**, not default Spring/MongoDB fields.

### 32.4. Use Query Shapes Instead of Full Commands

Do not log customer data or credentials to debug transactions. Record the logical operation name, attempt count, duration, error labels, incident ID, and sanitized trace ID.

## 33. Troubleshooting: Classifying Errors Accurately

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Transaction numbers not allowed | Standalone mongod | `db.hello`, replica set |
| @Transactional does not roll back | Missing or wrong manager | Spring beans, logs |
| One repository rolls back, another does not | Different factory/client/session | Bean wiring |
| Self-invocation skips tx | Call on `this` | Separate service proxy |
| @Async write still commits separately | ThreadLocal session not propagated | Tracing/thread |
| Raw driver write runs outside tx | Session omitted in overload | Code path |
| Exception thrown yet data commits | Checked exception / catch-swallow | Rollback rules |
| UnexpectedRollbackException | Inner marked rollback-only | Propagation/error handling |
| TransactionTooLargeForCache | Oversized tx / cache pressure | Server metrics |
| WriteConflict | Concurrent writes / long tx | Trace, retry policy |
| UnknownTransactionCommitResult | Network / commit ambiguity | Error label, reconcile |
| Count command error | Native count unsuitable in tx | `countDocuments`/aggregation |
| Collection creation fails | Auto-create in tx / topology | Pre-create collections |
| readPreference secondary fails | Read transactions require primary | Transaction options |
| @Transactional(readOnly) still opens tx | Session bound by manager | Evaluate if tx is needed |
| Transaction timeout | Server lifetime/commit/locks | Parameters, duration |
| Reactive writes run outside tx | Detached `subscribe` or `block` | Reactor chain/context |
| Multiple transaction managers | Annotation picks wrong manager | Name/Qualifier |
| Test passes yet production rollback fails | Test lacks replica set/real commit | Integration test |
| HTTP side effect does not roll back | Outside MongoDB tx | Outbox/saga |

## 34. Common Pitfall: Same Request Does Not Mean Same Session

Example controller:

~~~java
@PostMapping("/orders/{id}/confirm")
public ResponseEntity<Void> confirm(@PathVariable String id) {
    checkoutService.confirm(id);
    asyncPublisher.publish(id);
    return ResponseEntity.noContent().build();
}
~~~

`checkoutService.confirm` runs its own MongoDB transaction at its method boundary. `asyncPublisher.publish` happens afterward, shares no MongoDB session, and has independent failure semantics.

### 34.1. Sessions Bind to the Manager, Not the URL

One HTTP request can invoke two transactional service calls:

~~~text
Controller
  |
  +--> serviceA.tx()  -> session S1, commit
  |
  +--> serviceB.tx()  -> session S2, commit
~~~

There is no automatic "request-wide transaction" spanning two independent calls. If a single atomic boundary is needed, an outer transactional service **with the proper proxy/factory** must wrap both.

### 34.2. Sessions and the Connection Pool

A session is not a single TCP connection pinned for the lifetime of the application, though transactions carry connection and server-routing requirements. Do not manually pin/close driver connections or manage sessions in the Controller layer when using Spring's transaction manager.

### 34.3. API Response Before Commit?

With a Spring proxy, commit completes before the transactional method returns to the caller, whereas spawning async work or returning a reactive publisher changes execution/commit timing. Never return HTTP 200 "confirmed" before the atomic outcome is actually determined.

## 35. Comparing Transaction Management Approaches

| Approach | Session Management | Pros | Risks / Caveats |
|---|---|---|---|
| `@Transactional` + `MongoTransactionManager` | Spring thread-bound | Clean, readable for services | Proxy/self-invocation, exception rules |
| `TransactionTemplate` | Spring thread-bound | Explicit boundaries | Must pick the right manager |
| `MongoTemplate.withSession` | Developer-supplied | Control over session callbacks | Must close session; manual transactions |
| Java Driver `withTransaction`/manual | Driver | Fine-grained control and retry APIs | Must pass session on every operation |
| `@Transactional` + Reactive manager | Reactor Context | Integrates with WebFlux/Reactor | Publisher chain, subscribe semantics |
| `TransactionalOperator` | Reactor Context | Clear reactive scoping | Detached chains easily escape scope |

### 35.1. Default Choice

Spring MVC applications using `MongoRepository` that need a short atomic business operation should generally start with `MongoTransactionManager` + public `@Transactional` service methods and verify real rollback with tests.

Reactive WebFlux applications should choose the reactive transaction manager/operator; do not introduce the blocking manager into a publisher chain.

### 35.2. When Are Manual Sessions Appropriate?

When you need causal consistency or specialized session-bound operations not directly expressed by Spring's manager. When all-or-nothing writes across multiple repositories are required, declarative transactions are usually clearer.

## 36. Runbook for Production Transaction Incidents

### Scenario: Checkout Errors Spike After Failover

**Step 1 — Impact:** measure failed order rate, p95 latency, user impact, duplicate events, and start time.

**Step 2 — Classify errors:** `TransientTransactionError`, `UnknownTransactionCommitResult`, auth/TLS, `WriteConflict`, or timeout.

**Step 3 — Check topology:** Atlas events/`rs.status`, primary availability, secondary lag, and elections.

**Step 4 — Check runtime:** transaction duration, retries, WiredTiger/cache/locks, pool waits, and server selection.

**Step 5 — Mitigate:** reduce concurrency, pause conflicting batch jobs, preserve idempotency keys. Do not lower `writeConcern` recklessly.

**Step 6 — Verify:** commit success ratio returns to baseline, order/outbox invariants hold, no duplicate side effects.

**Step 7 — RCA:** evidence-backed root cause, refine retry policies/timeouts/failover tests, and update the runbook.

### 36.1. What If UnknownTransactionCommitResult Spikes?

Do not blindly re-run the entire business flow indefinitely. Implement commit retries or reconciliation following driver guidelines and idempotency keys to detect transactions that already committed despite lost responses.

### 36.2. When the Primary Lacks a Majority

Transactions require a healthy MongoDB deployment supporting majority write concerns. Do not weaken `writeConcern` to force writes through without understanding durability implications. Prioritize restoring topology health and safe application state.

## 37. Design Principles for Large Systems

1. **Data modeling before transactions:** If an aggregate can be safely embedded, a single-document atomic update may be simpler.
2. **Use-case boundaries:** A short service method wrapping only the required MongoDB writes.
3. **Consistent session/factory:** Avoid stray `MongoClient` instances outside Spring management.
4. **Idempotency:** Every business request needs a key so retries do not duplicate side effects.
5. **Outbox:** Atomic intent to publish, asynchronous delivery.
6. **Never hold transactions across remote I/O.**
7. **Least privilege:** Database users do not need `root` to run transactions.
8. **Read/write concerns:** Choose according to actual consistency and durability needs.
9. **Keep blocking and reactive semantics separate.**
10. **Test against a real replica set and verify rollback outside the transaction.**
11. **Monitor and alert:** Write conflicts, abort rates, commit latency, unknown commit results.
12. **Maintain runbooks:** Failover, DDL conflicts, timeouts, stale reads, duplicate requests.

## 38. Production Deployment Checklist

### Topology and Configuration

- [ ] MongoDB deployment supports transactions.
- [ ] Replica set/sharded topology and FCV are suitable.
- [ ] Java Driver/Spring Data/Spring Boot versions are compatible.
- [ ] `MongoClient` URI has proper TLS/replica set discovery.
- [ ] Database users follow least-privilege CRUD permissions.
- [ ] Collections and indexes are pre-created for transactional workflows.
- [ ] Baseline transaction duration and throughput are established.

### Spring Transaction Wiring

- [ ] `MongoTransactionManager` is declared.
- [ ] Manager uses the same `MongoDatabaseFactory` as repositories/template.
- [ ] Correct manager is named explicitly when JDBC/JPA coexists.
- [ ] `@Transactional` is placed on public service methods.
- [ ] Invocations pass through the proxy.
- [ ] No self-invocation bypasses transactions.
- [ ] Exception and `rollbackFor` rules are explicit.
- [ ] No catch-and-swallow patterns.
- [ ] Annotation labels/options are tested against the actual version.
- [ ] `NESTED`/`REQUIRES_NEW` are not assumed to act like JDBC savepoints.

### Session and Reactive Scope

- [ ] Do not manually start a second session inside a Spring transaction.
- [ ] Do not call raw driver methods without `ClientSession`.
- [ ] Do not run parallel operations on the same session/transaction.
- [ ] `@Async`/Executors are not assumed to share `ThreadLocal` transactions.
- [ ] Reactive flows use `ReactiveMongoTransactionManager`.
- [ ] No `block()`/`subscribe()` inside a transactional publisher chain.
- [ ] Manual sessions are properly closed.
- [ ] No lazy-loading of session-bound data after session close.

### Performance and Reliability

- [ ] Transactions are kept short, with no remote HTTP/Kafka calls inside.
- [ ] Read concern, write concern, and read preference are chosen intentionally.
- [ ] Bounded retries with backoff are implemented.
- [ ] Transient errors are distinguished from uncertain commits.
- [ ] Idempotency keys and business reconciliation are in place.
- [ ] Outbox pattern is used for critical external event delivery.
- [ ] Commits, aborts, write conflicts, and latency are monitored.
- [ ] No PII or credentials are logged in transaction diagnostics.

### Tests

- [ ] Integration tests run against a replica set.
- [ ] Successful commit across two collections is tested.
- [ ] Rollback after a failure in the second operation is tested.
- [ ] Verification reads occur outside the transaction.
- [ ] Concurrent requests and conflict/retry behavior are tested.
- [ ] Duplicate business requests are tested.
- [ ] Failover/commit ambiguity is tested where supported by environment.
- [ ] CI uses isolated databases.
- [ ] `@DataMongoTest`/`@SpringBootTest` tests verify the right transaction bean loads.

## 39. Practice Exercises

Exercises modifying data should use a **lab MongoDB replica set**. Never run abort, `killOp`, or failover scenarios directly on production just for testing.

### Exercise 1 — Single-Document Atomicity

Why doesn't an `updateOne` modifying multiple fields of one document necessarily require a transaction?

### Exercise 2 — Multi-Document Invariant

Design a workflow updating `orders` and `outbox` that requires all-or-nothing behavior. What happens without a transaction?

### Exercise 3 — Session vs Transaction

A `ClientSession` is opened and three operations are called without calling `startTransaction`. Do they automatically form an atomic unit?

### Exercise 4 — Replica Set

A standalone MongoDB runs repository saves normally, yet transactions fail. Explain why and how to set up a proper lab.

### Exercise 5 — MongoTransactionManager

Write a `@Bean MongoTransactionManager` injecting `MongoDatabaseFactory`.

### Exercise 6 — Same Factory

Two `MongoTemplate` beans use two different factories pointing to the same URI. Are they guaranteed to share one transaction?

### Exercise 7 — Service @Transactional

Add `@Transactional(transactionManager="mongoTransactionManager")` to an order confirmation service and define its boundary.

### Exercise 8 — Runtime Rollback

Throw an `IllegalStateException` after `orders.save` and before commit. Inspect the resulting state outside the transaction.

### Exercise 9 — Checked Exception

A checked `BusinessRuleException` is thrown in a service. When is `rollbackFor` required?

### Exercise 10 — Swallowed Exception

Catch `RuntimeException` and only log it. Why might unwanted data still commit?

### Exercise 11 — Proxy

`submit()` calls `this.confirm()` within the same bean. Why might the annotation on `confirm()` fail to take effect?

### Exercise 12 — Public Method

Why might private or final transactional methods fail to be intercepted by proxies?

### Exercise 13 — REQUIRED

Service A has an active transaction and calls Service B marked `REQUIRED`. How many transactions exist if both share the same manager/factory?

### Exercise 14 — NESTED

Can you partially roll back a transaction using JDBC-style savepoints in MongoDB?

### Exercise 15 — Multiple Managers

An application uses both JPA and MongoDB. How do you ensure `@Transactional` selects the right manager?

### Exercise 16 — Read-Only

Can `@Transactional(readOnly=true)` still open a MongoDB session/transaction? Does it block writes on the server?

### Exercise 17 — Read Preference

Why shouldn't you set `secondary` for a transaction containing reads?

### Exercise 18 — Consistency

Compare `ReadConcern.SNAPSHOT` and `WriteConcern.MAJORITY` in terms of purpose.

### Exercise 19 — Transaction Labels

Write an annotation with `mongo:readConcern=SNAPSHOT` and `mongo:maxCommitTime=PT1S` for a supported Spring Data version.

### Exercise 20 — Programmatic Control

Write `TransactionTemplate.executeWithoutResult` to update two documents.

### Exercise 21 — Manual Session

Use `try(ClientSession session = ...)` and `withSession`; why must the session be closed?

### Exercise 22 — Raw Driver

A `collection.updateOne(filter, update)` call sits inside a method using a manual session. Why might it execute outside the transaction?

### Exercise 23 — ThreadLocal

`@Async` dispatches a MongoDB write on an executor. Does it join the caller's transaction by default?

### Exercise 24 — Reactor Context

Why do reactive transactions use `ReactiveMongoTransactionManager` instead of `ThreadLocal` like imperative flows?

### Exercise 25 — Reactive Subscribe

A service calls `repository.save(doc).subscribe()` and returns `Mono.empty()`. Why might the transaction fail to cover the operation?

### Exercise 26 — TransactionalOperator

Use `.as(operator::transactional)` to wrap two reactive writes in the same chain.

### Exercise 27 — SessionSynchronization

Distinguish `ON_ACTUAL_TRANSACTION`, `ALWAYS`, and `NEVER`.

### Exercise 28 — External Side Effects

A MongoDB transaction aborts after an HTTP payment gateway has already charged the card. Is it automatically refunded? Design compensation/outbox handling.

### Exercise 29 — Commit Ambiguity

When a client receives `UnknownTransactionCommitResult`, should you always re-run the entire business method?

### Exercise 30 — Transient Error

Outline a bounded retry for `TransientTransactionError`, including idempotency and starting a new transaction per attempt.

### Exercise 31 — Transaction Timeout

A transaction runs for 90 seconds while the server's default lifetime limit is typically 60 seconds. Which errors and resources should you monitor?

### Exercise 32 — DDL Inside Transactions

Why should you pre-create collections and indexes even though newer MongoDB server versions conditionally support some DDL?

### Exercise 33 — Count

Why does the native `count` command differ from `MongoTemplate.count` translated into an aggregation inside a transaction?

### Exercise 34 — Integration Test

Design a JUnit test verifying that order + outbox roll back together upon a second-step failure. Why must the test read back outside the transaction?

### Exercise 35 — Testcontainers

Is a standalone container sufficient for testing `MongoTransactionManager`? What kind of replica set URL is needed?

### Exercise 36 — Observability

Select metrics for commit success, aborts, retries, write conflicts, pool waits, and duration.

### Exercise 37 — Concurrent Confirmation

Two requests attempt to confirm the same order. How do you combine unique keys, conditional updates, optimistic locking, and retries to prevent double effects?

### Exercise 38 — Capstone

Design a Spring Boot + MongoDB Atlas API confirming an order with an outbox event, incorporating:

- `MongoTransactionManager` sharing the same factory.
- Transaction scope at a public service boundary.
- `MongoRepository` + `MongoTemplate`.
- Majority write concern and snapshot read concern where appropriate.
- External publisher running post-commit.
- Retries handling transient errors and unknown commit results.
- Idempotency key.
- Testcontainers replica set integration test.
- Observability and incident runbook.

## 40. Summary

A MongoDB transaction in Spring Data is only reliable when you have the **right transaction manager, right session, right scope, and right operations**:

- **MongoTransactionManager** starts transactions and binds `ClientSession` to the thread in synchronous flows. `ReactiveMongoTransactionManager` uses Reactor Context for reactive flows.
- **@Transactional** defines boundaries at a Spring proxy; it does not automatically include `this` self-calls, new threads, separate raw clients, or external services.
- **MongoTemplate and repositories** must share the same `MongoDatabaseFactory`/session. Raw driver calls must pass the session explicitly when operating outside Spring Template management.
- **Rollback** relies on exception propagation and rollback rules; checked exceptions, catch-and-swallow, and self-invocation are common traps.
- **Read/write concerns** and transaction options govern consistency and durability, and transactions performing reads must target primary per MongoDB server rules.
- **Timeouts and retries:** keep transactions short; distinguish transient failures from uncertain commit results using idempotency and bounded retries.
- **External systems:** MongoDB cannot roll back HTTP calls, payment gateways, or Kafka; use outbox/saga and reconciliation.
- **Testing:** run against a real replica set and verify both commits and rollbacks from a separate session; monitoring must track aborts, retries, conflicts, and resource pressure.

A rule of thumb worth remembering: **Transaction scope is not HTTP request scope, session scope is not application-wide scope, and `@Transactional` is not magic covering every kind of I/O.**

## Official References

- [Spring Data MongoDB — Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html)
- [Spring Data MongoDB — MongoTransactionManager API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/MongoTransactionManager.html)
- [Spring Data MongoDB — ReactiveMongoTransactionManager API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/ReactiveMongoTransactionManager.html)
- [Spring Data MongoDB — MongoTemplate API](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-api.html)
- [Spring Data MongoDB — Repositories](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/repositories.html)
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Reactive Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Boot — Data and MongoDB](https://docs.spring.io/spring-boot/reference/data/nosql.html)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Manual — Transactions Production Considerations](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/)
- [MongoDB Manual — Transactions on Sharded Clusters](https://www.mongodb.com/docs/manual/core/transactions-sharded-clusters/)
- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/)
- [MongoDB Java Reactive Streams Driver — Transactions](https://www.mongodb.com/docs/languages/java/reactive-streams-driver/current/write/transactions/)
