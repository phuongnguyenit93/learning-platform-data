# Transaction Support Requirements and Transaction Managers

## 1. Context and Objectives

In the **SPRING_BOOT_INTEGRATION** module, Spring Boot connects systems through HTTP clients, databases, caches, message brokers, and Spring Integration adapters. A single business flow might update MongoDB, record a processed event marker, insert an outbox message, or invoke a downstream HTTP endpoint. Ensuring correctness across the flow requires distinguishing **which MongoDB operations commit/roll back together** from **which side effects sit outside the transaction**.

The **MongoDB** chapter highlights an essential topic: **Transaction Support Requirements and Transaction Managers**. Simply adding the Spring Data MongoDB starter and annotating methods with **@Transactional** does not automatically give you multi-document transactions.

After this lesson, you will be able to:

1. Distinguish atomic single-document updates from multi-document/multi-collection transactions.
2. Identify requirements around replica sets, sharded clusters, server versions, `featureCompatibilityVersion`, and `ClientSession`.
3. Configure **MongoTransactionManager** for imperative code and **ReactiveMongoTransactionManager** for reactive pipelines.
4. Write **@Transactional** services, `TransactionTemplate`, and `TransactionalOperator` respecting session boundaries.
5. Design retries, idempotency, outboxes, rollbacks, and reconciliation when commit outcomes are uncertain.
6. Test transactions against a real replica set rather than running CRUD tests on standalone MongoDB.

## 2. Single Documents Are Already Atomic: When Are Transactions Unnecessary?

MongoDB guarantees **single-document write operations are atomic**. Many business entities can be modeled as a single aggregate document, eliminating the need for multi-collection transactions.

Example order document:

~~~json
{
  "_id": "O-204",
  "status": "CREATED",
  "paymentVersion": 6,
  "paidAt": null
}
~~~

A conditional update checks the version and writes the new state in a single atomic operation:

~~~java
Query onlyNewer = Query.query(
        Criteria.where("_id").is("O-204")
                .and("paymentVersion").lt(7L));

Update update = new Update()
        .set("status", "PAID")
        .set("paymentVersion", 7L)
        .set("paidAt", Instant.now());

UpdateResult result = mongoTemplate.updateFirst(
        onlyNewer, update, "orders");

boolean applied = result.getModifiedCount() == 1;
~~~

**MongoTemplate** belongs to Spring Data MongoDB. Imports are omitted to focus on the operation. Because the filter and update execute atomically on one document, two concurrent threads cannot read, compute, and blindly overwrite stale values.

| Need | Recommended Approach |
| --- | --- |
| Updating fields within a single order | One conditional update command |
| Incrementing/decrementing a counter on one document | **$inc** operator with conditional guards if needed |
| Updating two documents or collections together | Consider a multi-document transaction |
| Updating an order and writing an outbox record in MongoDB | Can use a MongoDB transaction |
| Writing MongoDB then publishing to Kafka/HTTP | MongoDB transactions **do not cover** brokers or HTTP |
| Processing millions of records with checkpoints | Small batches, idempotency, and compensation—not one long transaction |

**Design aggregates and unique keys before adding transactions.** Transactions help enforce multi-document invariants, yet add coordination overhead, lock/snapshot contention, and retry complexity.

## 3. MongoDB Requirements for Multi-Document Transactions

### 3.1. Topology and versions

| MongoDB Deployment | Supports Transactions? | Requirements |
| --- | --- | --- |
| **Standalone mongod** | **No** | Successful CRUD does not prove transactions work |
| **Replica set** | **Yes** | MongoDB 4.0+, minimum FCV 4.0 |
| **Sharded cluster** | **Yes** | MongoDB 4.2+, minimum FCV 4.2 |
| **Managed MongoDB** | Depends on topology/tier | Verify actual deployment, privileges, and driver compatibility |

FCV stands for **featureCompatibilityVersion**, not just the Docker image version tag. A single-node replica set initialized with **rs.initiate()** works for local transaction testing, though it lacks the fault tolerance of a multi-node production replica set.

MongoDB transactions are built on **ClientSession**. Every operation in a transaction must execute under that exact session; Spring Data uses a transaction manager to bind the session to participating operations.

Administrative inspection commands:

~~~javascript
rs.status()

db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
})
~~~

**rs.status()** applies to replica set members. For sharded clusters/managed services, use the appropriate topology inspection commands. Never grant admin privileges to application accounts solely to run operational checks.

### 3.2. Connecting and routing to the primary

Example MongoDB URI for a replica set:

~~~text
mongodb://mongo-a:27017,mongo-b:27017,mongo-c:27017/shop?replicaSet=rs-shop&readPreference=primary
~~~

Specifying the exact **replicaSet** helps the driver verify topology and select eligible nodes, especially since transactions require primary routing. Never commit production credentials in URIs or expose them in logs; if runtime URIs carry username/password, protect the whole URI as a secret. Configure TLS and hostname verification appropriately.

Additional prerequisites:

- **ClientSession** supported by the driver and compatible server version.
- User holds read/write permissions on target collections—no arbitrary admin grants.
- Read concern, write concern, and read preference match consistency requirements.
- Transaction duration stays short to avoid holding snapshots/resources too long.
- Collections and indexes are **pre-created before receiving traffic**, avoiding on-the-fly DDL inside transactions.

### 3.3. Limitations not to overlook

- Transactions can hit **write conflicts** when concurrent requests modify the same document.
- Transactions can be aborted by the server if they exceed lifetime or resource limits.
- Operations sharing a `ClientSession` must be coordinated sequentially rather than executed concurrently across threads.
- Sharded transactions incur cross-shard coordination overhead.
- Read concern **snapshot** does not eliminate write conflicts or concurrent update races.

## 4. Spring Boot Auto-Configures MongoDB, Not Automatically a Transaction Manager

With Maven using Spring Boot dependency management:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
~~~

Or Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'
}
~~~

When valid connection settings exist, Boot can create **MongoClient**, **MongoDatabaseFactory**, **MongoTemplate**, and Spring Data repositories. However, under Spring Data MongoDB, **without a `MongoTransactionManager` in the application context, transaction management is not active by default for Mongo operations**. Likewise, reactive APIs require **ReactiveMongoTransactionManager**.

### 4.1. Distinguishing Spring Boot 3.x and 4.x configuration

With **Spring Boot 3.x**, e.g.:

~~~yaml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
~~~

With **Spring Boot 4.x**, connection properties moved under the **spring.mongodb** prefix:

~~~yaml
spring:
  mongodb:
    uri: ${MONGODB_URI}
~~~

These are **two configurations for two major release lines**—never put both expecting the framework to pick one. **MONGODB_URI** is injected via environment or secret manager and may carry **replicaSet**, TLS, and authentication options. Never log raw URIs containing credentials.

### 4.2. Spring's session management flow

~~~mermaid
flowchart TD
    A["@Transactional / TransactionTemplate"] --> B["TransactionInterceptor"]
    B --> C["MongoTransactionManager"]
    C --> D["MongoDatabaseFactory"]
    D --> E["Thread-bound ClientSession"]
    F["MongoTemplate / MongoRepository"] --> E
    E --> G["MongoDB replica set or sharded cluster"]
    H["Reactive @Transactional / TransactionalOperator"] --> I["ReactiveMongoTransactionManager"]
    I --> J["ClientSession in Reactor Context"]
    K["ReactiveMongoTemplate"] --> J
    J --> G
~~~

**MongoTransactionManager** binds transaction context to the thread for synchronous code. **ReactiveMongoTransactionManager** uses Reactor Context; never swap these managers across models. A manually created **MongoTemplate** backed by a different factory, or a driver client opening sessions outside Spring, will not join the registered manager's transactions.

## 5. Declaring `MongoTransactionManager` for Imperative APIs

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration(proxyBeanMethods = false)
@EnableTransactionManagement
public class MongoTransactionsConfiguration {

    @Bean("mongoTransactionManager")
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
~~~

With this configuration:

1. **MongoDatabaseFactory** must be the same factory used by `MongoTemplate`/repositories.
2. **@EnableTransactionManagement** ensures transaction advice is active in the sample config; Spring Boot auto-configures transaction infrastructure when appropriate dependencies/managers exist, while explicit declaration makes verification straightforward.
3. Naming the bean **mongoTransactionManager** allows services to qualify it unambiguously.
4. When a system uses JDBC/JPA or JMS alongside MongoDB, an unqualified **@Transactional** can pick the wrong manager or fail due to ambiguity.

Example service:

~~~java
@Service
public class MongoOrderService {
    private final MongoTemplate mongo;

    public MongoOrderService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void updateBothDocuments(...) {
        // Multiple MongoDB operations executed in the same session.
    }
}
~~~

This skeleton illustrates how to declare a transaction boundary; the next section implements a concrete business case.

### 5.1. Multiple transaction managers do not create a distributed transaction

| Transaction Manager | Managed Resource |
| --- | --- |
| **MongoTransactionManager** | MongoDB session and Mongo operations sharing the same factory |
| **ReactiveMongoTransactionManager** | Reactive MongoDB session inside Reactor Context |
| **JdbcTransactionManager** | Matching JDBC `DataSource` |
| **JmsTransactionManager** | JMS resource per `ConnectionFactory` config |
| **KafkaTransactionManager** | Kafka producer/consumer transactions per contract |

A Mongo transaction cannot roll back a PostgreSQL update or an HTTP call. Calling another **@Transactional** method across beans **does not create XA or two-phase commit** across distinct datastores.

## 6. Example: Recording an Event Receipt and Updating an Order in One Transaction

Suppose a consumer receives a **PaymentCaptured** event and must:

1. Insert a **processed_payment_events** receipt for `eventId` to prevent duplicates.
2. Update the **orders** document to paid status.
3. Roll back both if either operation fails.

### 6.1. Preparing collections

~~~javascript
// Run in migration/setup, never inside business transactions.
db.createCollection("orders")
db.createCollection("processed_payment_events")

// Each _id has a default unique index.
~~~

Collections and indexes must exist before opening transactions. Relying on implicit collection creation on first insert inside a transaction has restrictions depending on MongoDB and Spring Data versions; never depend on it in production.

DTO and receipt:

~~~java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

public record PaymentCaptured(
        String eventId, String orderId, long paymentVersion,
        Instant capturedAt) {
}

@Document("processed_payment_events")
public record ProcessedPaymentEvent(
        @Id String id, String orderId, Instant processedAt) {
}
~~~

Documents in **orders** use **_id = orderId** with fields **status**, **paymentVersion**, and **paidAt**. The code below uses `MongoTemplate` directly for brevity:

~~~java
@Service
public class MongoPaymentProjector {
    private final MongoTemplate mongo;

    public MongoPaymentProjector(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void apply(PaymentCaptured event) {
        if (event.eventId() == null || event.eventId().isBlank()
                || event.orderId() == null || event.orderId().isBlank()) {
            throw new IllegalArgumentException("Invalid event identity");
        }

        boolean processed = mongo.exists(
                Query.query(Criteria.where("_id").is(event.eventId())),
                ProcessedPaymentEvent.class);
        if (processed) {
            return; // Receipt for this event is already committed.
        }

        mongo.insert(new ProcessedPaymentEvent(
                event.eventId(), event.orderId(), Instant.now()));

        UpdateResult result = mongo.updateFirst(
                Query.query(Criteria.where("_id").is(event.orderId())),
                new Update()
                        .set("status", "PAID")
                        .set("paymentVersion", event.paymentVersion())
                        .set("paidAt", event.capturedAt()),
                "orders");

        if (result.getMatchedCount() != 1) {
            throw new IllegalStateException("Order not found");
        }
    }
}
~~~

Imports for `MongoTemplate`, `Query`, `Criteria`, `Update`, `UpdateResult`, `@Service`, and `@Transactional` are omitted. In production, validate **capturedAt** is non-null and schema-compliant; `eventId` must remain stable across retries and redeliveries. Letting **RuntimeException** escape the service tells Spring to roll back both the inserted receipt and order update when transactions are properly configured.

### 6.2. Race conditions and unique keys

Two consumers can both observe **processed=false**. Check-then-insert is **not** an atomic lock. Only the unique index on **_id** prevents two receipts for the same `eventId` from committing. A racing transaction may hit **DuplicateKeyException** or a write conflict; let the failing transaction abort/roll back and handle retry/reconciliation **outside** the transaction boundary.

**Never catch `DuplicateKeyException` mid-transaction and return normally** claiming “duplicate already handled”: the server may have aborted the transaction, or the exception may signal a different error. When redelivery occurs after an earlier receipt committed, the new run sees `processed=true` and safely no-ops; for uncommitted concurrent races, perform bounded retries.

### 6.3. Out-of-order events

If **two different `eventId`s** update the same order, the deduplication receipt alone does not guard against an older event version overwriting a newer one. Add a version predicate directly to the update query:

~~~java
Query onlyNewer = Query.query(
        Criteria.where("_id").is(event.orderId())
                .and("paymentVersion").lt(event.paymentVersion()));

UpdateResult result = mongo.updateFirst(
        onlyNewer,
        new Update().set("paymentVersion", event.paymentVersion())
                .set("status", "PAID"),
        "orders");
~~~

When **matchedCount=0**, distinguish between a missing order, a stale out-of-order event, and data already at a newer version. Treating all zero-match updates as retryable errors causes brokers to redeliver stale messages forever. If legacy documents lack `paymentVersion`, handle via migration or explicit rules.

### 6.4. Commit, ACK, and redelivery

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant L as Listener
    participant TM as MongoTransactionManager
    participant M as MongoDB
    B->>L: PaymentCaptured evt-901
    L->>TM: begin transaction
    TM->>M: ClientSession
    L->>M: insert processed_payment_events
    L->>M: update orders
    alt Mongo commit succeeds
        TM->>M: commitTransaction
        M-->>TM: success
        L-->>B: ACK per adapter
    else Exception occurs
        TM->>M: abortTransaction
        L-->>B: failure / redelivery per policy
    end
~~~

If Mongo commits and the process crashes **before the broker ACK**, the broker redelivers the message. The receipt keyed by `eventId` blocks duplicate Mongo side effects. **Broker ACKs sit outside the Mongo transaction**, so consumers still need idempotency, bounded retries, and dead-letter handling for permanently broken events.

## 7. `TransactionTemplate` and Session Ownership

To scope a transaction around an explicit block of code, use Spring's **TransactionTemplate**:

~~~java
@Configuration
public class MongoTemplateTransactionsConfiguration {
    @Bean("mongoTxTemplate")
    TransactionTemplate mongoTxTemplate(
            @Qualifier("mongoTransactionManager")
            PlatformTransactionManager manager) {
        return new TransactionTemplate(manager);
    }
}
~~~

~~~java
@Service
public class ProjectionBatchService {
    private final MongoTemplate mongo;
    private final TransactionTemplate tx;

    public ProjectionBatchService(
            MongoTemplate mongo,
            @Qualifier("mongoTxTemplate") TransactionTemplate tx) {
        this.mongo = mongo;
        this.tx = tx;
    }

    public void storeRelatedDocuments(
            Document first, Document second) {
        tx.executeWithoutResult(status -> {
            mongo.insert(first, "projection_a");
            mongo.insert(second, "projection_b");
        });
    }
}
~~~

**Document** here is **org.bson.Document** for illustration; production code should use typed DTOs/entities and explicit schemas. Collections are pre-created before running the transaction. If either insert throws, the transaction rolls back so neither commits.

**`TransactionTemplate` must use `MongoTransactionManager`**, never accidentally a JDBC manager. When `MongoTemplate` and the transaction manager share the same factory, Spring manages the `ClientSession` across operations inside the callback.

Spring Data MongoDB also exposes **MongoTemplate.withSession(...)** for manual driver session handling, yet when using Spring's transaction abstraction, do not layer manual **session.startTransaction/commitTransaction** calls on top of `@Transactional`. Mixing manual sessions with `@Transactional` complicates lifecycle and error handling without adding cross-system atomicity.

### 7.1. Proxies and self-invocation

This common mistake causes subtle failures:

~~~java
@Service
class BrokenExample {

    void handle(PaymentCaptured event) {
        apply(event); // Self-invocation; may bypass the transaction proxy.
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void apply(PaymentCaptured event) {
        // ...
    }
}
~~~

Under proxy-based Spring transaction management, calling a method on **the same instance** bypasses `TransactionInterceptor`. Place the transactional method on a separate bean called through the Spring proxy, or use `TransactionTemplate`. Never infer that transactions are running simply because `@Transactional` is present in source code.

## 8. `ReactiveMongoTransactionManager` and Reactor Context

For WebFlux/reactive MongoDB applications, use the reactive starter and reactive transaction manager:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
</dependency>
~~~

Register the manager:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;

@Configuration(proxyBeanMethods = false)
public class ReactiveMongoTransactionsConfiguration {

    @Bean("reactiveMongoTransactionManager")
    ReactiveMongoTransactionManager reactiveMongoTransactionManager(
            ReactiveMongoDatabaseFactory factory) {
        return new ReactiveMongoTransactionManager(factory);
    }
}
~~~

**ReactiveMongoTransactionManager** propagates `ClientSession` through **Reactor Context**, not `ThreadLocal` as imperative `MongoTransactionManager` does; never drop the imperative manager into a reactive pipeline expecting operations to join the transaction.

### 8.1. `@Transactional` on methods returning `Mono`

~~~java
@Service
public class ReactiveMongoPaymentProjector {
    private final ReactiveMongoTemplate mongo;

    public ReactiveMongoPaymentProjector(ReactiveMongoTemplate mongo) {
        this.mongo = mongo;
    }

    @Transactional(
            transactionManager = "reactiveMongoTransactionManager")
    public Mono<Void> apply(PaymentCaptured event) {
        Query receiptQuery = Query.query(
                Criteria.where("_id").is(event.eventId()));

        return mongo.exists(
                    receiptQuery, ProcessedPaymentEvent.class)
                .flatMap(processed -> {
                    if (processed) {
                        return Mono.<Void>empty();
                    }

                    return mongo.insert(new ProcessedPaymentEvent(
                                    event.eventId(),
                                    event.orderId(),
                                    Instant.now()))
                            .then(mongo.updateFirst(
                                    Query.query(Criteria.where("_id")
                                            .is(event.orderId())),
                                    new Update().set("status", "PAID")
                                            .set("paymentVersion",
                                                    event.paymentVersion()),
                                    "orders"))
                            .flatMap(result ->
                                    result.getMatchedCount() == 1
                                    ? Mono.<Void>empty()
                                    : Mono.error(
                                            new IllegalStateException(
                                                    "Order not found")));
                });
    }
}
~~~

This assumes the DTOs, collections, and factory from earlier sections, plus input validation and stale-version checks in real code. A **Mono** is a lazy execution plan: transactions and network calls only execute upon subscription. Calling the method in a test and discarding the publisher proves nothing about transaction execution.

**Never call `subscribe()` manually inside a transactional method and return early.** Detached subscriptions can escape the transaction's Reactor Context, and the method returns while side effects are still running.

### 8.2. `TransactionalOperator`

When scoping transactions programmatically:

~~~java
@Bean("mongoOperator")
TransactionalOperator mongoOperator(
        @Qualifier("reactiveMongoTransactionManager")
        ReactiveTransactionManager manager) {
    return TransactionalOperator.create(manager);
}
~~~

~~~java
Mono<Void> work = reactiveMongoTemplate
        .insert(new ProcessedPaymentEvent(
                "evt-901", "O-204", Instant.now()))
        .then(reactiveMongoTemplate.updateFirst(
                Query.query(Criteria.where("_id").is("O-204")),
                new Update().set("status", "PAID"),
                "orders"))
        .then()
        .as(mongoOperator::transactional);
~~~

With **.as(mongoOperator::transactional)**, upstream operators join the transactional operator's context. Publishers created in separate subscriptions or invoked after the operator will not participate in that transaction.

### 8.3. Do not run concurrent operations on a single session

The MongoDB driver requires operations inside a transaction to execute sequentially as permitted by the session. Never use concurrent **`flatMap`** writes on **the same `ClientSession`**:

~~~java
// Avoid parallel writes inside a single transaction:
Flux.fromIterable(events)
        .flatMap(event -> reactiveMongoTemplate.insert(event));

// For small batches executed sequentially within one transaction:
Flux.fromIterable(events)
        .concatMap(event -> reactiveMongoTemplate.insert(event));
~~~

These expressions illustrate execution ordering only, not a full transaction setup. For large volumes, split work into **small checkpointed, idempotent transactions** rather than holding one session open across an entire stream.

**Never call `block()` on the WebFlux event loop**, and never assume synchronous `MongoTemplate` shares the `ClientSession` managed by `ReactiveMongoTransactionManager`.

## 9. Read Concern, Write Concern, and Transaction Options

MongoDB transactions support options controlling visibility and commit behavior:

| Option | Role | Consideration |
| --- | --- | --- |
| **readConcern** | Consistency visibility for reads | **snapshot** suits many transactional read workloads |
| **writeConcern** | Write/commit acknowledgment requirement | **majority** improves durability over single-replica acknowledgment |
| **readPreference** | Driver node routing policy | Transactions require routing to an eligible primary |
| **maxCommitTime** | Bounds commit execution time | Expiration does not always prove the commit failed |
| **transaction lifetime** | Server-side lifetime limit | Overly long transactions get aborted |

Spring Data MongoDB supports transaction labels in versions providing **MongoTransactionOptionsResolver**:

~~~java
@Transactional(
        transactionManager = "mongoTransactionManager",
        label = {
                "mongo:readConcern=SNAPSHOT",
                "mongo:writeConcern=MAJORITY",
                "mongo:maxCommitTime=PT2S"
        })
public void processPayment(PaymentCaptured event) {
    // Mongo operations participating in the same transaction.
}
~~~

If your Spring Data version does not support these option labels, configure **TransactionOptions** directly on `MongoTransactionManager` or the appropriate API. Never invent arbitrary labels expecting them to configure MongoDB.

**`readConcern=snapshot` does not eliminate write conflicts.** A transaction can read a consistent snapshot and still abort if another transaction writes to the same document. Guard with unique indexes, version predicates, and bounded retries.

**`@Transactional(readOnly=true)`** can still open a `ClientSession`/transaction depending on the manager; avoid wrapping every simple read query in a transaction unnecessarily.

## 10. Operational Limits of MongoDB Transactions

### 10.1. Keep transactions short

MongoDB enforces **transactionLifetimeLimitSeconds**. A common default across deployments is **60 seconds**, though actual limits depend on server or managed service configuration. Expired transactions abort, and long-running ones hold snapshots/locks that amplify write conflicts.

Never hold a Mongo transaction open while:

- Waiting on slow downstream HTTP calls or long `Retry-After` delays.
- Waiting for broker confirmations, human approvals, or multi-minute async jobs.
- Scanning millions of documents or holding cursors open arbitrarily.
- Performing backoff retries inside the open transaction.

Prepare inputs and validate before starting the transaction; perform quick atomic Mongo writes; send notifications or publish broker messages after commit via an outbox/recovery pattern.

### 10.2. Collections and indexes must be pre-created

Never rely on Spring Data creating a collection on first insert **inside a transaction**. DDL inside transactions has version, topology, and integration constraints; ensure collections and indexes are provisioned beforehand via migrations or controlled bootstrapping.

~~~javascript
// Pre-provisioning outside transactions:
db.createCollection("orders")
db.createCollection("processed_payment_events")
db.createCollection("outbox_events")
db.outbox_events.createIndex({ status: 1, createdAt: 1 })
~~~

Real migrations must check existence so they re-run safely; these commands show the goal rather than a complete idempotent production script.

### 10.3. Do not use transactions as a bulk throughput mechanism

Multi-document transactions incur coordination and oplog overhead, especially across shards. They do not speed up bulk ingestion. Each BSON document still obeys document size limits, and transactions obey server runtime/memory caps.

For heavy ingestion, use small batches, atomic upserts, checkpoints, bounded retries, and reconciliation; if invariants span a large workflow, model explicit stateful workflows rather than keeping one transaction open for minutes.

## 11. Errors, Retries, and Uncertain Commit Outcomes

Transactions can fail when starting a session, reading, writing, or committing:

~~~mermaid
flowchart TD
    A["Begin transaction"] --> B["Write document A"]
    B --> C["Write document B"]
    C --> D["commitTransaction"]
    B -->|"Exception"| E["abort/rollback"]
    C -->|"Write conflict/duplicate"| E
    D -->|"Commit confirmed"| F["Next step/ACK"]
    D -->|"Uncertain outcome"| G["Check error labels / reconcile"]
    G --> H{"Recovery"}
    H -->|"Retry commit per driver protocol"| I["Verify commit outcome"]
    H -->|"Retry whole transaction if safe"| A
~~~

### 11.1. Error classification

| Category | Meaning | Policy |
| --- | --- | --- |
| Standalone unsupported error | Topology lacks transaction support | Fix deployment; do not retry business logic |
| **TransientTransactionError** | Potentially transient transaction failure | Retry the **entire transaction** when operations are idempotent |
| **UnknownTransactionCommitResult** | Unknown whether commit succeeded | Follow commit-retry/reconciliation protocol; do not immediately fire new side effects |
| `DuplicateKeyException` | Unique receipt/index violation | Distinguish idempotent duplicate from race/conflict |
| Write conflict | Concurrent update contention | Bounded backoff/retry; shorten transaction duration |
| Validation/mapping error | Invalid DTO/schema | Fix data/code; never retry endlessly |
| Network/timeout | Operation outcome may be uncertain | Inspect phase, error labels, and authoritative state |

The driver attaches **error labels** to exceptions; Spring Data translates some errors to **DataAccessException**. Inspect root causes and driver labels and test with your exact library versions. **`@Transactional` alone does not supply a safe retry policy for all failures**.

### 11.2. Retry at the right boundary

If writing B inside a transaction hits a transient error, retrying only write B outside the aborted transaction breaks the invariant. Typically you roll back the failed transaction and retry the **entire business method** inside a fresh transaction. If the **commit result is unknown**, re-running the whole business flow blindly can create duplicates: use unique receipts, state lookups, or commit retries per driver guidance.

**Never catch `RuntimeException` and return normally inside `@Transactional`.** If the transaction is still active, Spring may commit partial writes made before the error; if the server already aborted, the subsequent commit fails confusingly. Let exceptions propagate out of the boundary to roll back, or explicitly mark rollback-only.

### 11.3. Checked exceptions and rollback rules

Under standard Spring configuration, unchecked exceptions (`RuntimeException`/`Error`) roll back by default; checked exceptions require explicit configuration if they should trigger rollback:

~~~java
@Transactional(
        transactionManager = "mongoTransactionManager",
        rollbackFor = ExternalContractException.class)
public void process(...) throws ExternalContractException {
    // Skeleton illustrating rollback rules.
}
~~~

**ExternalContractException** is an application-defined exception type. Rollback policies can be customized at framework/application level and should always be verified with tests.

## 12. MongoDB Transactions and Broker/HTTP Integration

A Mongo transaction **does not cover** Kafka, RabbitMQ, JMS, HTTP, Redis, or JDBC merely because the code sits inside a `@Transactional` method.

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void saveAndPublish(...) {
    mongoTemplate.insert(...);
    kafkaTemplate.send(...); // Not part of the MongoDB transaction.
    // An HTTP call also does not roll back when Mongo rolls back.
}
~~~

This is **boundary pseudocode**, not production code. If the broker receives the event yet Mongo fails to commit, downstreams observe an event for nonexistent data. If Mongo commits and the process dies before publishing, the event is lost.

### 12.1. Transactional outbox in MongoDB

A common pattern is **updating business documents and inserting an outbox document in the same Mongo transaction**, while a separate relay forwards outbox records to the broker:

~~~mermaid
flowchart TD
    A["Business command"] --> B["Mongo transaction"]
    B --> C["Update order"]
    B --> D["Insert outbox event"]
    C --> E{"Mongo commit"}
    D --> E
    E -->|"Committed"| F["Outbox relay"]
    F --> G["Kafka/RabbitMQ/JMS"]
    F -->|"Publish error"| H["Retry, backoff, checkpoint"]
    H --> F
    G --> I["Idempotent consumer"]
~~~

Outbox document:

~~~java
@Document("outbox_events")
public record OutboxEvent(
        @Id String eventId,
        String eventType,
        String aggregateId,
        Instant createdAt,
        String status) {
}
~~~

Service snippet illustrating the in-transaction writes:

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void markPaidAndQueueEvent(PaymentCaptured event) {
    UpdateResult result = mongo.updateFirst(
            Query.query(Criteria.where("_id").is(event.orderId())),
            new Update().set("status", "PAID"),
            "orders");

    if (result.getMatchedCount() != 1) {
        throw new IllegalStateException("Order not found");
    }

    mongo.insert(new OutboxEvent(
            event.eventId(),
            "OrderPaid",
            event.orderId(),
            Instant.now(),
            "PENDING"));
}
~~~

This uses **`eventId` as the outbox `_id`** to simplify uniqueness protection, while real applications also enforce version/out-of-order rules and idempotency. The relay must handle the case where **publishing succeeds yet updating `SENT` fails**, which causes duplicate publishes; consumers must deduplicate by `eventId`.

MongoDB **change streams** can help relays detect newly committed outbox documents on replica sets/sharded clusters, yet resume tokens, disconnects, replays, and duplicates must still be handled; change streams do not magically provide exactly-once broker delivery.

### 12.2. When PostgreSQL or Redis are also involved

`MongoTransactionManager` manages only the corresponding Mongo session. A JDBC transaction manager manages only its `DataSource`. When workflows span multiple backend types, use **outbox/inbox, sagas, idempotency, retries, checkpoints, and reconciliation** instead of assuming a single `@Transactional` provides distributed XA.

## 13. Testing Transactions on a Real Replica Set

Mocking `MongoTemplate` or running against standalone MongoDB cannot verify multi-document rollback. In Spring Boot, integration tests should use a real replica set, such as the **Testcontainers MongoDB module**.

Example for Spring Boot **3.x** with Testcontainers + JUnit 5:

~~~java
@Testcontainers
@SpringBootTest
class MongoPaymentTransactionIT {

    @Container
    static MongoDBContainer mongo =
            new MongoDBContainer("mongo:7.0");

    @DynamicPropertySource
    static void mongoUri(DynamicPropertyRegistry properties) {
        properties.add(
                "spring.data.mongodb.uri",
                () -> mongo.getReplicaSetUrl("shop"));
    }

    @Autowired
    MongoTemplate template;

    @Autowired
    MongoPaymentProjector projector;

    @BeforeEach
    void prepare() {
        if (!template.collectionExists("orders")) {
            template.createCollection("orders");
        }
        if (!template.collectionExists("processed_payment_events")) {
            template.createCollection("processed_payment_events");
        }
        template.getCollection("orders").deleteMany(new Document());
        template.getCollection("processed_payment_events")
                .deleteMany(new Document());
    }

    @Test
    void receiptIsRolledBackWhenOrderIsMissing() {
        PaymentCaptured event = new PaymentCaptured(
                "evt-001", "missing-order", 1L, Instant.now());

        assertThrows(IllegalStateException.class,
                () -> projector.apply(event));
        assertFalse(template.exists(
                Query.query(Criteria.where("_id").is("evt-001")),
                ProcessedPaymentEvent.class));
    }
}
~~~

JUnit, Testcontainers, Spring Test, BSON, Mongo, and `Instant` imports are omitted. Configure Testcontainers/JUnit test dependencies and a working Docker runtime in CI; **mongo:7.0** is an example image that should be pinned and updated periodically. **MongoDBContainer** supplies a transaction-ready replica set URI; verify `getReplicaSetUrl(...)` against your Testcontainers version.

With **Spring Boot 4.x**, update the test property to **spring.mongodb.uri**. The **`@DataMongoTest`** slice focuses on templates/repositories and may skip custom service beans or transaction configurations; use **`@SpringBootTest`** or **`@Import`** when testing real `@Transactional` services.

### 13.1. Test matrix

| Scenario | What to Prove |
| --- | --- |
| Replica set + right manager | Both writes commit or roll back together |
| Standalone MongoDB | Multi-document transactions cannot be treated as working |
| Missing order | Receipt insert rolls back |
| Repeated event with same `eventId` | Unique receipt prevents duplicate side effects |
| Two concurrent consumers | Race resolved via unique keys and retry/reconciliation |
| Older version arriving after newer version | Order version does not regress |
| Unchecked/checked exceptions | Rollback behaves per configured policy |
| Write conflict | Bounded retries without duplicating side effects |
| Unknown commit result | Does not assume failure; recovers via receipt lookup |
| Reactive publisher emits error | Transaction rolls back with zero leftover writes |
| Broker redelivery after Mongo commit | Business state remains idempotent |
| Outbox relay crash after publish | Consumer still deduplicates |
| Mongo failover/network outage | Errors are not swallowed and ACKs are not sent early |

In reactive tests, always **subscribe** to verify effects:

~~~java
StepVerifier.create(reactiveProjector.apply(event))
        .verifyComplete();
~~~

Merely constructing a `Mono` without subscribing never starts the transaction. On error tests, use **`expectError(...)`** and query collections afterward to prove rollback rather than only asserting the exception.

## 14. Observing and Operating MongoDB Transactions

| Metric / Signal | Meaning |
| --- | --- |
| **transaction started/committed/aborted** | Commit and rollback rates |
| **transaction duration p95/p99** | Slow transactions risking lifetime abort |
| **write conflict / duplicate key** | Contention and idempotency hits |
| **unknown commit result** | Requires reconciliation rather than assuming rollback |
| **connection pool pending / timeout** | Pool held too long or overloaded |
| **Mongo command latency** | Unindexed queries/updates or slow primary |
| **outbox pending / oldest age** | Relay stalled after Mongo commit |
| **broker redelivery / duplicate event** | Impact of ACK failures and at-least-once delivery |

These names are **recommended metric concepts**, not all auto-provided by Spring Boot. Spring Boot Actuator, Micrometer, MongoDB driver/server exporters, and Spring Integration tracing expose different subsets. Never put **`eventId`, `orderId`, `tenantId`, or password-bearing MongoDB URIs** into high-cardinality metric tags.

A helpful trace outline:

~~~text
Message delivery evt-901
  → Mongo transaction begin
     → insert processed_payment_events
     → update orders
  → Mongo commit success
  → broker ACK
~~~

Distinguish **Mongo commit** from **broker ACK** in logs/traces. When broker redelivery occurs after a lost ACK, duplicate metrics rise even though the Mongo transaction committed earlier.

In production, monitor long-running transactions, indexes, `currentOp`, primary failover health, pool pressure, and appropriately access-controlled Mongo logs. Never enable full payload/credential logging just to debug.

## 15. Common Mistakes

**“MongoDB always needs `@Transactional` to write safely.”** Single-document operations are already atomic; conditional single-document updates often suffice.

**“Adding `spring-boot-starter-data-mongodb` automatically gives me Mongo transactions.”** Not enough. A Mongo transaction manager must be configured and the topology must support transactions.

**“Standalone CRUD passing is enough to test transactions.”** False. Multi-document transaction tests require a replica set or sharded cluster.

**“`@Transactional` automatically picks Mongo even when a JDBC manager exists.”** Not guaranteed; qualify the manager explicitly and test against the real context.

**“`MongoTransactionManager` rolls back HTTP or Kafka too.”** False. It manages only Mongo operations participating in that session.

**“`exists` then `insert` prevents duplicates safely under concurrency.”** You need a real unique key and race handling.

**“Catching `DuplicateKeyException` inside a transaction and returning normally is safe.”** The transaction may already be aborted; handle conflicts outside the boundary or per protocol.

**“Snapshot reads eliminate write conflicts.”** No; a transaction still aborts if two writes collide on the same document.

**“Reactive transactions use `ThreadLocal` like imperative ones.”** False. Reactive sessions propagate via Reactor Context and subscriptions.

**“Retrying the entire business flow on commit timeout is always safe.”** The commit may have succeeded before timing out; distinguish unknown commit results and enforce idempotency.

**“Long transactions batch millions of documents more efficiently.”** They usually amplify lock/snapshot pressure, aborts, and pool exhaustion.

**“Creating collections inside a transaction on first write is always reliable.”** Depends on version/topology; pre-create schemas beforehand.

**“Once Mongo commits, the broker definitely received the event.”** True only with an explicit integration protocol; normally you need an outbox/recovery mechanism.

## 16. Pre-Deployment Checklist

1. Identify which invariants genuinely span **multiple documents**; prefer single-document atomic updates when sufficient.
2. Verify MongoDB topology, version/FCV, privileges, read/write concerns, and TLS.
3. Never rely on standalone MongoDB to validate production transactions.
4. Use the right MongoDB properties for Spring Boot 3.x vs. 4.x and configure `replicaSet` explicitly.
5. Register **MongoTransactionManager** or **ReactiveMongoTransactionManager** with the matching factory.
6. Qualify transaction manager names explicitly if the service mixes Mongo/JDBC/JMS.
7. Place boundaries on services via Spring proxies/`TransactionTemplate`/`TransactionalOperator`, avoiding self-invocation.
8. Pre-create collections and indexes, especially unique receipt/outbox keys.
9. Keep transactions brief; never wait on HTTP, brokers, or backoff delays inside them.
10. For reactive flows, never manually `subscribe()`, `block()`, or run concurrent operations on the same session.
11. Retry based on error labels and budgets, distinguishing transient errors from unknown commit outcomes.
12. Protect side effects using `eventId`, versioning, idempotency, and outbox/inbox.
13. Test rollback on a real replica set, adding concurrency, redelivery, and post-commit crash tests.
14. Monitor transaction latency, aborts, write conflicts, pool pressure, and outbox backlogs without leaking secrets.

**Conclusion:** MongoDB multi-document transactions protect a group of operations within **the same MongoDB session** when supported by the server and managed properly by Spring. They are a vital tool, yet never substitute for **good data modeling, idempotency, outboxes, conditional retries, real testing, and observability** across the full integration flow.

## References

- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/): transaction support, topologies, FCV, and atomicity.
- [MongoDB Manual — Transactions Production Considerations](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/): runtime limits and resource considerations.
- [MongoDB Manual — startTransaction](https://www.mongodb.com/docs/manual/reference/method/session.starttransaction/): `ClientSession`, retries, and commits.
- [Spring Data MongoDB — Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): `MongoTransactionManager`, `ReactiveMongoTransactionManager`, `TransactionTemplate`, `TransactionalOperator`, and option labels.
- [Spring Boot — Working with NoSQL Technologies](https://docs.spring.io/spring-boot/reference/data/nosql.html): MongoDB client, properties, and auto-configuration.
- [Spring Boot 4 Migration Guide — MongoDB properties](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): migration to the `spring.mongodb` prefix.
- [Spring Boot 3.5 — Auto-configured Data MongoDB Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): scope of the `@DataMongoTest` slice.
- [Testcontainers — MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/): `MongoDBContainer` and replica sets in integration tests.
