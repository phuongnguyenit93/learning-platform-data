# Write Concern and Transactions in Spring Integration MongoDB

## Learning Objectives

After this lesson, you will be able to:

- Explain MongoDB **write concern** as the **acknowledgment level for write operations** with components `w`, `j`, and `wtimeout`, distinct from query timeouts, poll intervals, and business ACKs.
- Distinguish `w:0` (unacknowledged), `w:1` (primary/standalone ACK), `w:"majority"` (majority of data-bearing voting members per MongoDB rules), and `j:true` (journal flush required); understand impacts of topology, durability, and failover.
- Explain why a **write concern timeout does not automatically roll back**, and when receiving a timeout/lost ACK, the write state may be **unknown**; reuse the same event ID with bounded retries and reconciliation rather than generating a new ID.
- Understand **MongoDB multi-document transactions** built on `ClientSession`, topology prerequisites, and commit/abort vs. single-document atomic updates.
- Configure `MongoTemplate.setWriteConcern(...)` or `WriteConcernResolver` at the right layer without mistaking a template's write concern for a `MessageChannel` property.
- Configure `MongoTransactionManager`/`TransactionTemplate`/`@Transactional` for blocking operations and `ReactiveMongoTransactionManager`/`TransactionalOperator` for reactive operations.
- Integrate transactions with `MongoDbStoringMessageHandler`, `MongoDbMessageSource`, pollers, and `MessageChannel`; distinguish **real MongoDB transactions** from **`PseudoTransactionManager`/transaction synchronization**.
- Understand why a MongoDB transaction **does not automatically commit** Kafka offsets, JMS ACKs, HTTP responses, SFTP file moves, or JDBC transactions on a separate database.
- Design **transactional outbox/inbox**, business idempotency, unique indexes, atomic claim/lease, retry/compensation, and crash recovery.
- Write tests for rollback/commit on a replica set, majority write concern, timeout ambiguity, after-commit callbacks, double consumers, and external publisher failures.

This lesson belongs to the **Adapter MongoDB** chapter in the **SPRING_INTEGRATION_ADAPTERS** module. The module connects external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`, practicing with files, SFTP, HTTP, JMS, AMQP, Kafka, and databases while emphasizing message contracts, error handling, and connection lifecycles. Here, MongoDB serves as a storage system within a **message-processing pipeline**, so three commitments must be separated: **MongoDB acknowledged the write**, **the MongoDB transaction committed**, and **the cross-system business workflow completed**.

> **Version scope:** examples use Java 17+, Spring Boot 3.x, and compatible Spring Data MongoDB/Spring Integration via BOM; packages `MongoDatabaseFactory` and `ReactiveMongoDatabaseFactory` reflect current API names. Configuring transactions requires a supporting MongoDB deployment (typically a replica set or sharded cluster). Local URIs/credentials in examples are not suitable for production.

## 1. Business Problem: Saving an Order and Outbox Event

An API receives an order request. The application wants to:

1. Receive `OrderCommand(orderId, tenantId, amount)` via HTTP/JMS/Kafka or a Spring `MessageChannel`.
2. Write the order document to MongoDB's `orders` collection.
3. Write an **outbox event** to the `outbox_events` collection so another worker publishes to Kafka.
4. Avoid situations where **the order exists without the outbox**, or vice versa.
5. Report the order as recorded **only after the transaction commits**.
6. Never apply the Kafka message twice in terms of **business side effects**, even if the outbox worker crashes and republishes.

~~~mermaid
flowchart LR
  A["HTTP / JMS / Kafka"] --> B["ordersInput channel"]
  B --> C["OrderApplicationService"]
  C --> T["MongoDB transaction"]
  T --> O[("orders")]
  T --> E[("outbox_events")]
  E --> P["Outbox poller"]
  P --> K["Kafka publisher"]
  K --> D["Idempotent consumer"]
~~~

**The issue:** merely setting `writeConcern=MAJORITY` on the order write **does not** combine `insert(order)` and `insert(outbox)` into one transaction. Conversely, a MongoDB transaction across two collections **does not** commit a Kafka publish/ACK. **Write concern**, **transactions**, and **outbox** each play a distinct role.

### 1.1. Possible Observed States

| Milestone | What happened? | What can be concluded? |
|---|---|---|
| `MessageChannel.send()` returns true | Message accepted by channel | **Not guaranteed** MongoDB wrote it, especially in async flows |
| `MongoOperations.insert()` succeeds outside a transaction | Write acknowledged per active write concern | Does not mean the entire business workflow committed |
| `TransactionTemplate.execute()` returns after commit | MongoDB transaction manager completed commit per server response | Does not include Kafka/JMS/HTTP |
| `wtimeout` or network error | Required confirmation was not received | **Cannot assume** the write did not occur |
| Outbox event committed | Event stored durably in MongoDB per write/commit concern | Does not guarantee broker received it |
| Kafka publish ACK succeeds | Broker acknowledged per producer configuration | Does not guarantee consumer processed business logic |
| Consumer business commit | Target side effect succeeded | Requires idempotency when broker redelivers |

## 2. What Is Write Concern?

**Write concern** is the acknowledgment level MongoDB must satisfy before returning a result for a write operation (insert, update, delete, or transaction commit).

Example MongoDB structure:

~~~javascript
{
  w: "majority",
  j: true,
  wtimeout: 3000
}
~~~

- **`w`**: how many members or majority/custom tag condition must acknowledge.
- **`j`**: whether acknowledgment requires the write to be persisted to the **on-disk journal**.
- **`wtimeout`**: time limit for satisfying replication write concern once the operation has run; **not** a total timeout covering all database/driver steps.

Write concern does not answer "**which documents are read**" (that is `ReadConcern`/read preference/query), nor does it answer "**how many documents changed**" (inspect `matchedCount`/`modifiedCount`/duplicate keys/business state).

### 2.1. Key w Levels

| Setting | What MongoDB requires before ACKing | Primary risk |
|---|---|---|
| `{w: 0}` | No server ACK requested for writes | Client cannot tell if server accepted it; validation/write errors may go unnoticed |
| `{w: 1}` | Primary or standalone acknowledges the write | May roll back on failover before replicating sufficiently to secondaries |
| `{w: 2}` | Two eligible members acknowledge (e.g., primary + 1 secondary) | If too few eligible nodes exist, write concern times out |
| `{w: "majority"}` | Majority of **data-bearing** voting members per MongoDB rules acknowledge | Latency/availability depends on topology; can time out |
| `{w: "majority", j: true}` | Majority concern plus journal confirmation per version/config semantics | Does not mean "Kafka ACKed" or "zero data loss under every catastrophe" |

**Never use `w:0` for messages requiring durable delivery/accurate ACKs.** With unacknowledged writes, a caller lacks evidence to know whether a business event was persisted.

### 2.2. Majority Does Not Mean "Just Any Node"

Suppose a replica set has three data-bearing voting members: `Primary P`, `Secondary S1`, `Secondary S2`.

~~~mermaid
sequenceDiagram
    participant App as Integration app
    participant P as Primary
    participant S1 as Secondary 1
    participant S2 as Secondary 2
    App->>P: insert(order), w=majority
    P->>P: apply write/oplog
    P-->>S1: replicate oplog
    P-->>S2: replicate async
    S1-->>P: acknowledge sufficient
    P-->>App: write concern satisfied
~~~

In a three-node data-bearing voting topology, majority typically corresponds to **two** members. In topologies with arbiters, tags, or non-voting members, the calculation follows **MongoDB replication rules**, not simply dividing total nodes by two. Modern MongoDB defaults to `w:"majority"` in most deployments, with exceptions for topologies containing arbiters, and defaults can be overridden by cluster/client/operation settings.

**Never hard-code assumptions like "default is always w:1" or "default is always majority".** Check your actual cluster/driver settings, especially when upgrading MongoDB or changing topology.

### 2.3. What Does j:true Mean?

`j:true` requests acknowledgment only after the write is written to the on-disk journal on applicable members per MongoDB version rules. It reduces data-loss risk on node crashes, yet:

- `j:true` **does not guarantee majority replication** if `w` is low.
- Majority and journaling interact with `writeConcernMajorityJournalDefault` and MongoDB version.
- Modern replica sets often include journal durability in `w:"majority"` by default, but verify your deployment.
- A MongoDB journal ACK **does not prove** downstream Kafka or another database committed.

### 2.4. MongoDB 8.0+ and Read-After-Write on Secondaries

Starting in MongoDB 8.0, majority acknowledgment can be satisfied once members have **durably written oplog entries**; a secondary may **apply** those changes to its local collection asynchronously afterward.

Therefore, right after receiving a `w:"majority"` ACK, an immediate query routed to a secondary without causal consistency may **not yet see the new write**. If a workflow requires read-your-writes, use appropriate read preferences/sessions/causal consistency; never treat a majority write ACK as guaranteeing every secondary is immediately ready to return the document.

## 3. wtimeout: Failing Write Concern Does Not Auto-Rollback

Key point to remember:

> **A `wtimeout` occurring does not mean MongoDB undid the write on the primary.** The write may already have succeeded locally while failing to gather enough replication ACKs before the timeout expired.

Example:

~~~mermaid
sequenceDiagram
    participant A as Spring Integration
    participant P as Mongo Primary
    participant S as Mongo Secondary
    A->>P: insert(evt-101) with w=majority
    P->>P: apply write locally
    Note over S: Network partition or slow replication
    P--xA: writeConcernError / wtimeout
    Note over A: Final outcome is unknown
    Note over P: Write may still exist
~~~

If the app treats every timeout as "document not written" and retries with a new `UUID.randomUUID()`, it can create **two business records**. If it retries with the same business `_id`/unique key, it may hit a duplicate-key error (sometimes proving the earlier write reached the server); still inspect contents and business state rather than swallowing all duplicate-key errors.

### 3.1. Three Distinct Timeouts to Separate

| Timeout | What it bounds | Does timeout auto-rollback? |
|---|---|---|
| `wtimeout` | Wait for write concern replication | **Does not** undo an already-applied write |
| `serverSelectionTimeout` | Driver waiting to pick an eligible server | Does not tell whether a prior write happened |
| Socket/read/network timeout | Driver waiting on I/O or response | Write outcome may be unknown |
| Query max time | Server execution cap, API-dependent | Does not replace transaction rollback semantics |
| `@Gateway(replyTimeout)` | Caller waiting for Spring Messaging reply | Does not cancel/undo a MongoDB write |
| Poller `fixedDelay` | Schedule for invoking source | Not a transaction/write timeout |

In **lost-response** cases, reconcile via unique keys and actual stored data, or retry per official operation protocol with idempotency. **A lost ACK does not mean lost data.**

### 3.2. wtimeout in mongosh

Example write command with explicit write concern:

~~~javascript
use integration_lab

db.runCommand({
  insert: "audit_events",
  documents: [
    { _id: "audit-101", kind: "ORDER_ACCEPTED", orderId: "order-101" }
  ],
  writeConcern: { w: "majority", j: true, wtimeout: 3000 }
})
~~~

Run on a **test** database belonging to a replica set to observe replication policies. Never run this example as a test against production; if the collection/ID already exists, a duplicate-key error may occur. With `wtimeout`, the server can return a write concern error even when the write has been applied.

## 4. Write Concern vs. ReadConcern and ReadPreference

Three commonly confused concepts:

- **WriteConcern**: acknowledgment guarantee for writes/commits.
- **ReadConcern**: consistency/durability guarantee requested by reads (e.g., `local`, `majority`, `snapshot` in appropriate contexts).
- **ReadPreference**: which node serves reads (`primary`, `secondary`, ...).

| Requirement | What to examine |
|---|---|
| Avoid losing recent writes on primary failover | `w:"majority"` and deployment durability |
| Read only majority-committed data | Appropriate `ReadConcern.MAJORITY` |
| Read "your own just-written data" across nodes | Causal consistency/sessions and matching read preference |
| Consistent snapshot inside a transaction | Transaction `snapshot` read concern if supported |
| Subsequent read after write on a thread | Do not assume a transaction without a session/transaction manager |
| Writing from SFTP to MongoDB then HTTP | Define ACKs/compensation outside MongoDB |

Causal consistency with sessions has preconditions on write/read concerns. Never assume a `MongoTemplate.find()` reading from a secondary immediately sees a majority write in every MongoDB version/topology.

## 5. Write Concern vs. Transactions

| Capability | Write concern | MongoDB transaction |
|---|---|---|
| Goal | When the server ACKs a write | Groups operations into one commit/abort unit |
| Single-document update | MongoDB is natively atomic per document | Can be used, though usually unnecessary |
| Two collections `orders` and `outbox_events` | **Not** automatically atomic | Atomic within supporting MongoDB deployment/session |
| Rollback multiple writes on exception | **Not** provided by write concern | Aborts the transaction |
| Choose commit durability level | Applies to individual writes | **Transaction-level write concern** on commit |
| Kafka/JMS/HTTP side effects | Not applicable | **Do not participate automatically** |
| Failover/unknown result | Requires reconciliation | May yield unknown commit result requiring protocol-level retry/reconciliation |
| Cost | Replication ACK latency | Session, transaction locks/resources/commit overhead |

**MongoDB single-document operations are natively atomic** at the document level. If you only need to claim one `NEW` job to `PROCESSING` conditionally, `findAndModify` or conditional `updateFirst` is usually better than opening an unnecessary multi-document transaction.

Transactions are valuable when the application must guarantee **two or more MongoDB operations** commit or abort together, such as inserting an order and an outbox entry.

## 6. Preparing Spring Boot and a Lab MongoDB Replica Set

### 6.1. Maven Dependencies

For Spring Boot 3.x:

~~~xml
<!-- Dependencies section in pom.xml -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-mongodb</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

**No need to pin driver versions manually**; let the compatible BOM manage Spring Data/MongoDB driver/Integration. For reactive only, use `spring-boot-starter-data-mongodb-reactive` and the reactive transaction manager; never inject blocking `MongoTemplate` into a reactive endpoint.

### 6.2. MongoDB Topology

MongoDB multi-document transactions require a supporting deployment (typically a replica set or sharded cluster). **A standalone `mongod` is unsuitable** for testing replica-set transactions, even though single CRUD operations work.

Spring Boot lab:

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://127.0.0.1:27017/integration_lab?replicaSet=rs0
~~~

`rs0` is an illustrative name for an **already-initialized replica set** in the test environment. Never append `replicaSet=rs0` to a production URI unless the cluster actually uses that name.

Inspect topology with `mongosh` on the test deployment:

~~~javascript
rs.status()
db.hello()
db.getMongo().getWriteConcern()
~~~

Some commands are valid only on replica-set members or require specific privileges. If `getWriteConcern()` shows no override, check cluster/server/driver defaults; empty output **does not prove `w:1`**.

### 6.3. Both Collections Must Exist

In test `mongosh`:

~~~javascript
use integration_lab

db.createCollection("orders")
db.createCollection("outbox_events")
db.createCollection("audit_events")

db.orders.createIndex({ tenantId: 1, orderId: 1 }, { unique: true })
db.outbox_events.createIndex({ eventId: 1 }, { unique: true })
~~~

Create collections/indexes **before** transaction tests to avoid relying on implicit creation inside transactions; MongoDB rules for DDL inside transactions vary across versions/topologies, so never treat ad-hoc DDL as a safe part of a business transaction.

### 6.4. Demo Schema

~~~java
package example.mongodbtx;

import java.math.BigDecimal;
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderRecord(
        @Id String id,
        String tenantId,
        String orderId,
        BigDecimal amount,
        String status,
        Instant createdAt) {
}

@Document(collection = "outbox_events")
public record OutboxEvent(
        @Id String id,
        String tenantId,
        String eventId,
        String aggregateId,
        String type,
        String status,
        Instant createdAt) {
}

public record OrderCommand(
        String orderId,
        String tenantId,
        BigDecimal amount) {
}
~~~

Place these records in **separate top-level Java files** in a real project. Use unique business IDs/tenants to avoid duplicates. `@Id` maps to MongoDB `_id`; if monetary precision is critical, configure `@Field(targetType = FieldType.DECIMAL128)` or a custom `BigDecimal` converter and test real round-trip reads/writes.

## 7. Setting Write Concern in the Java Driver and Spring Data

### 7.1. MongoTemplate.setWriteConcern

Spring Data `MongoTemplate` provides the setter:

~~~java
void setWriteConcern(com.mongodb.WriteConcern writeConcern)
~~~

Example configuring a `MongoTemplate` replacing auto-config:

~~~java
package example.mongodbtx;

import com.mongodb.WriteConcern;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.core.MongoTemplate;

@Configuration
public class MongoConcernConfig {

    @Bean
    public MongoTemplate mongoTemplate(
            MongoDatabaseFactory databaseFactory) {

        MongoTemplate template =
                new MongoTemplate(databaseFactory);

        template.setWriteConcern(
            WriteConcern.MAJORITY
                .withWTimeout(3000, TimeUnit.MILLISECONDS));

        return template;
    }
}
~~~

**This is an application template configuration**; you do not need to add it if Boot already provides a `MongoTemplate` with the desired concern. A custom `MongoTemplate` sharing the same factory without custom mappings/converters can alter behavior; in production, keep mapping/converters and connection options consistent.

Without `setWriteConcern`, `MongoTemplate` inherits defaults from the MongoDB driver/database/collection settings. Driver/client URI and server/global defaults also play a role; **never infer behavior from code alone while ignoring deployment settings**.

### 7.2. MongoDB URI with Write Concern

Connection strings accept corresponding options, e.g.:

~~~text
mongodb://db-host-a,db-host-b/integration_lab?replicaSet=rs0&w=majority&journal=true
~~~

This URI is **illustrative**, not a real hostname. Newer driver/MongoDB versions handle timeouts differently; `wtimeoutMS` in connection strings has been deprecated in newer MongoDB docs in favor of `timeoutMS` per supported driver/operation semantics. **Do not treat those timeouts as synonymous**: overall operation timeouts and write-concern wait limits have distinct scopes.

In production, prefer explicit configuration on the driver/template/transaction and verify behavior via integration tests instead of relying on accidental defaults.

### 7.3. WriteConcernResolver per Operation Type

Spring Data provides `WriteConcernResolver` to pick policies by MongoDB action. Example:

~~~java
import com.mongodb.WriteConcern;
import org.springframework.data.mongodb.core.WriteConcernResolver;
import org.springframework.data.mongodb.core.MongoAction;

public final class DomainWriteConcernResolver
        implements WriteConcernResolver {

    @Override
    public WriteConcern resolve(MongoAction action) {
        if ("audit_events".equals(action.getCollectionName())) {
            return WriteConcern.MAJORITY;
        }
        return action.getDefaultWriteConcern();
    }
}
~~~

Register at bean configuration time:

~~~java
template.setWriteConcernResolver(
        new DomainWriteConcernResolver());
~~~

This is an **option for normal write operations outside transactions**. Inside a MongoDB multi-document transaction, write concern must be set **at the transaction level**, not per individual operation inside the transaction. Never use a resolver to try overriding transaction commit policy per operation.

**Never mutate `MongoTemplate` setters per request**: the template is a shared singleton across threads. Choose settings at startup; if different business domains need different policies, use separate templates/factories intentionally or a thread-safe resolver.

## 8. Spring Integration MongoDB Outbound Adapter Inherits Write Concern from Template

`MongoDbStoringMessageHandler` takes a configured `MongoOperations` or `MongoDatabaseFactory` and writes the message payload into a MongoDB collection.

### 8.1. Java DSL with a Configured MongoTemplate

~~~java
package example.mongodbtx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mongodb.outbound.MongoDbStoringMessageHandler;
import org.springframework.expression.common.LiteralExpression;
import org.springframework.data.mongodb.core.MongoTemplate;

@Configuration
@EnableIntegration
public class MongoAuditOutboundFlow {

    @Bean
    public MongoDbStoringMessageHandler mongoAuditWriter(
            MongoTemplate mongoTemplate) {

        MongoDbStoringMessageHandler writer =
                new MongoDbStoringMessageHandler(mongoTemplate);

        writer.setCollectionNameExpression(
            new LiteralExpression("audit_events"));
        return writer;
    }

    @Bean
    public IntegrationFlow auditFlow(
            MongoDbStoringMessageHandler mongoAuditWriter) {

        return IntegrationFlow.from("toMongoAudit")
                .handle(mongoAuditWriter)
                .get();
    }
}
~~~

**What to understand:**

- The handler writes the payload with `MongoOperations.save(...)` semantics and the collection expression.
- There is no separate `writeConcern` property on `MessageChannel` in this flow.
- Write concern follows the `MongoTemplate`/driver used by the handler.
- Passing `MongoDatabaseFactory` to `MongoDbStoringMessageHandler(MongoDatabaseFactory)` creates a separate `MongoTemplate` with potentially different defaults; to enforce a specific policy, pass the configured template.
- If the handler runs synchronously over `DirectChannel`, MongoDB exceptions propagate to the producer; with `QueueChannel`/`ExecutorChannel`, caller `send()` may return before the write completes.
- `save` is not insert-only: an existing `_id` can overwrite the document. Never treat a write ACK as guaranteeing no business duplicates.
- The writer is a **one-way** outbound adapter; for request/reply queries, use the MongoDB outbound gateway or a service calling `MongoOperations`.

### 8.2. Warning on Data Types and Transactions

If the payload came from a partial-projection entity missing some fields, never feed it to the writer's `save` to "update one field": `save` can replace the entire document and erase omitted fields. Use `updateFirst`/`findAndModify` for partial updates conditioned on ID/owner/version.

When multiple MongoDB writes must form a transaction, **place the transaction boundary at the appropriate service/endpoint**. Simply sending two separate messages through the writer does not create a shared transaction: they may execute on separate threads, separate connections, or separate commits.

## 9. MongoTransactionManager: Real MongoDB Transactions

Spring Data MongoDB provides `MongoTransactionManager`, managing `ClientSession` and binding the session to the current thread for `MongoTemplate` sharing the same `MongoDatabaseFactory`.

### 9.1. Creating a Transaction Manager with Options

~~~java
package example.mongodbtx;

import com.mongodb.TransactionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration
public class MongoTransactionConfig {

    @Bean("mongoTransactionManager")
    public MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory databaseFactory) {

        TransactionOptions options = TransactionOptions.builder()
                .readConcern(ReadConcern.SNAPSHOT)
                .readPreference(ReadPreference.primary())
                .writeConcern(WriteConcern.MAJORITY)
                .build();

        return new MongoTransactionManager(
                databaseFactory, options);
    }

    @Bean
    public TransactionTemplate mongoTransactionTemplate(
            MongoTransactionManager mongoTransactionManager) {
        return new TransactionTemplate(
                mongoTransactionManager);
    }
}
~~~

Explanation:

1. `MongoTransactionManager` acquires `ClientSession` from the matching factory.
2. `ReadConcern.SNAPSHOT` gives reads inside the transaction snapshot semantics as supported by MongoDB.
3. `ReadPreference.primary()` is required/appropriate for write transactions.
4. **`WriteConcern.MAJORITY` applies at the **transaction level**, specifically on commit**, not as a per-`insert` write concern inside the transaction.
5. `TransactionTemplate` is an imperative API; it does not take a `Mono` and subscribe automatically.
6. If MongoDB is standalone or a non-transaction-capable cluster, opening/committing transactions will fail.
7. If the project has multiple transaction managers (JDBC, JMS, MongoDB), **specify** the manager explicitly by name/qualifier.

**Note:** if you defined `MongoTemplate` in section 7, both the template and transaction manager must share the **same `MongoDatabaseFactory`**. If an operation runs through a `MongoTemplate` pointing to a different factory, it will execute **outside the transaction you expected**.

### 9.2. Transaction-Level Concern and Per-Operation Restrictions

MongoDB requires **not setting individual write concerns on write operations inside a multi-document transaction**; the transaction-level concern applies at commit.

Therefore:

- Configure `WriteConcern.MAJORITY` in `TransactionOptions` as shown above.
- Never call raw MongoDB collection operations with per-insert `withWriteConcern(...)` inside a transaction.
- Do not assume `MongoTemplate.setWriteConcernResolver` applies different concerns per document inside a transaction.
- If Collection A and Collection B seem to need different concerns in one transaction, revisit the design because **commit carries one transaction-level concern**.
- A transactional commit failing/timing out can produce an **unknown commit result**, requiring retry/reconciliation matching MongoDB driver/server error labels.

### 9.3. MongoDB Transactions Have Costs

Transactions hold sessions, snapshots, and resources while active. Avoid:

- Opening a transaction and waiting minutes for HTTP/SFTP responses.
- Reading huge collections and holding everything inside a transaction.
- Creating many messages and holding a transaction open while an async queue drains.
- Making network calls to Kafka/JMS/HTTP **before** MongoDB commits and assuming those external side effects will roll back if the database aborts.
- Opening multiple transactions across separate database factories/clusters and treating them as one distributed transaction.

Keep transactions **short**, enclosing only the MongoDB operations that genuinely require atomicity.

## 10. @Transactional: Committing Order and Outbox Together

A Java service using synchronous `MongoOperations`:

~~~java
package example.mongodbtx;

import java.time.Instant;
import java.math.BigDecimal;

import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final MongoOperations mongo;

    public OrderApplicationService(MongoOperations mongo) {
        this.mongo = mongo;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void acceptOrder(OrderCommand command) {
        if (command == null
                || command.orderId() == null
                || command.orderId().isBlank()
                || command.tenantId() == null
                || command.tenantId().isBlank()
                || command.amount() == null
                || command.amount().signum() <= 0) {
            throw new IllegalArgumentException(
                    "Invalid order command");
        }

        // Lab: assume tenant authorization occurred before
        // calling this service. Production must enforce real auth.
        Instant now = Instant.now();
        String eventId = "order-accepted:" + command.orderId();

        OrderRecord order = new OrderRecord(
                command.orderId(),
                command.tenantId(),
                command.orderId(),
                command.amount(),
                "ACCEPTED",
                now);

        OutboxEvent outbox = new OutboxEvent(
                eventId,
                command.tenantId(),
                eventId,
                command.orderId(),
                "ORDER_ACCEPTED",
                "PENDING",
                now);

        mongo.insert(order, "orders");
        mongo.insert(outbox, "outbox_events");

        // Do not call kafkaTemplate.send() here.
        // Both MongoDB inserts commit or roll back together.
    }
}
~~~

**Conditions for the transaction to actually activate:**

- The `public` method is **invoked through the Spring proxy** (a Spring-managed bean), not via `this.acceptOrder(...)` from another method on the same object expecting AOP interception.
- Spring transaction management is enabled in Spring Boot configuration.
- `mongoTransactionManager` exists and shares the same factory as `MongoOperations`.
- The MongoDB client connects to a transaction-capable replica set/sharded cluster.
- All MongoDB commands requiring atomicity participate in the same session/transaction.
- Collections/indexes are pre-created; never mix schema/DDL initialization into production request transactions.

### 10.1. What Happens if the Second Insert Fails?

If the `orders` insert succeeds locally inside the transaction, and then the `outbox_events` insert throws a duplicate-key or other exception before commit, the transaction manager **aborts** the transaction; uncommitted writes inside the transaction never become visible as committed writes.

~~~mermaid
sequenceDiagram
    participant I as Spring Integration
    participant S as @Transactional Service
    participant D as MongoDB
    I->>S: acceptOrder(command)
    S->>D: start transaction (session)
    S->>D: insert order
    S->>D: insert outbox
    D-->>S: duplicate key/error
    S->>D: abort transaction
    S-->>I: exception
~~~

This is why rollback must be tested against a MongoDB **replica set** rather than merely mocking `MongoOperations`. Mockito cannot prove two operations roll back together in the storage engine.

### 10.2. @Transactional Differs from High Write Concern

Suppose there is no transaction:

~~~java
mongo.insert(order, "orders");         // ACK majority
mongo.insert(outbox, "outbox_events"); // Throws exception
~~~

The result can be **an order without an outbox entry**. The majority write concern on the first insert **does not roll it back** when the second insert fails.

Conversely, inside a transaction, committing with `w:1` or misconfigured options can weaken durability during replica-set failover. **Atomicity across writes** and **commit acknowledgment/durability** are two orthogonal axes that must be designed together.

### 10.3. Duplicate Business IDs Must Be Handled Explicitly

If a client or Kafka redelivers the same `orderId`:

- A unique `_id`/`(tenantId, orderId)` rejects the duplicate insert.
- The handler should inspect the existing order's state and check whether the payload matches the original request.
- Never swallow every `DuplicateKeyException` as success: the same ID with a different amount is a business conflict.
- Never generate a fresh UUID for the same order request just to "avoid duplicate errors".
- If a caller timed out after commit, the presence of order/outbox by business key enables reconciliation.

## 11. TransactionTemplate: When Programmatic Control Is Needed

When you prefer avoiding `@Transactional` proxies or want explicit failure testing within a clear block, use `TransactionTemplate`.

~~~java
package example.mongodbtx;

import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class ProgrammaticOrderService {

    private final MongoOperations mongo;
    private final TransactionTemplate mongoTx;

    public ProgrammaticOrderService(
            MongoOperations mongo,
            TransactionTemplate mongoTransactionTemplate) {
        this.mongo = mongo;
        this.mongoTx = mongoTransactionTemplate;
    }

    public void saveOrderAndOutbox(
            OrderRecord order, OutboxEvent outbox) {

        mongoTx.executeWithoutResult(status -> {
            mongo.insert(order, "orders");
            mongo.insert(outbox, "outbox_events");
        });
    }
}
~~~

- `executeWithoutResult` finishes only once the callback and transaction manager commit/abort complete.
- Unchecked `RuntimeException`s trigger rollback by default under Spring transaction semantics; checked exceptions require explicit rules depending on usage.
- Never fire an async producer expecting it to await Kafka ACKs inside the transaction.
- `TransactionTemplate` also needs the right manager if the app additionally uses a JDBC transaction manager.

### 11.1. Beware of Spring Proxies and Self-Invocation

This example **does not activate `@Transactional`** when `acceptOrder` is called from another method on the same object:

~~~java
@Service
public class BrokenSelfInvocation {

    public void entry(OrderCommand command) {
        acceptOrder(command); // this-call bypasses proxy.
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void acceptOrder(OrderCommand command) {
        // Do not assume a transaction is active.
    }
}
~~~

This is an **illustrative anti-pattern**, not production code. Separate the transactional service into an injected bean, or use `TransactionTemplate` as in section 11.

## 12. Spring Integration MessageChannel and Transaction Boundaries

An `IntegrationFlow` forwarding `OrderCommand` to the transactional service:

~~~java
package example.mongodbtx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class OrderIntegrationFlowConfig {

    @Bean
    public IntegrationFlow orderCommandsFlow(
            OrderApplicationService service) {
        return IntegrationFlow.from("ordersInput")
                .handle(service, "acceptOrder")
                .get();
    }
}
~~~

Example producer sending to `ordersInput`:

~~~java
Message<OrderCommand> message =
    MessageBuilder.withPayload(
        new OrderCommand(
            "order-101",
            "tenant-a",
            new BigDecimal("125.00")))
        .build();

ordersInput.send(message);
~~~

The producer injects `MessageChannel ordersInput` and imports `MessageBuilder`, `Message`, and `BigDecimal`. The flow calls the service method **through the injected proxy**, allowing `@Transactional` on the service to open the transaction properly.

### 12.1. Synchronous DirectChannel

If the path from producer to handler is synchronous, the service completes or throws within the sender's call stack. **Still, never treat `send()==true` as a universal business ACK**: introducing a transformer/router/async channel in between changes semantics.

If the caller needs the order outcome, design a **request/reply gateway** returning a DTO after commit with clear error mapping. The outbound storing adapter's job is storing payloads, not returning business results like a gateway.

### 12.2. QueueChannel / ExecutorChannel Changes the Boundary

~~~text
Thread A: MessageChannel.send()
    -> QueueChannel accepts in-memory message
    -> returns true

Thread B (later): receives message
    -> @Transactional acceptOrder()
    -> MongoDB commit or rollback
~~~

**Thread A is not inside the transaction opened by Thread B.** An imperative transaction context is normally **thread-bound** and does not propagate across a `QueueChannel`, thread pool, or future.

If a Kafka/JMS source is ACKed as soon as `QueueChannel` accepts the message into RAM, a crash loses work not yet written to MongoDB. Use a durable broker/store or defer ACKs until after transaction commit per endpoint semantics.

### 12.3. Error and Timeout Contracts

- MongoDB errors in a synchronous service can propagate over `DirectChannel` for the caller to handle.
- With asynchronous channels, errors occur on the worker thread and can route to an error channel.
- A caller's reply timeout does not roll back an active MongoDB transaction unless the operation is properly canceled/rolled back.
- A `TransactionTemplate` exception before commit differs from an **unknown commit result** after a timeout; classify them separately.
- When a transaction aborts, upstream must still define retries/backoff and idempotency.

## 13. MongoDbMessageSource Polling, State, and Transactions

The MongoDB inbound channel adapter uses `SourcePollingChannelAdapter` to call `MongoDbMessageSource.receive()` on schedule. The source itself merely emits query results as messages; for multiple MongoDB operations to share a transaction, place `MongoTransactionManager` at a boundary genuinely enclosing those synchronous operations.

`MongoDbMessageSource` queries MongoDB on schedule:

~~~text
Poller -> MongoDbMessageSource.receive()
       -> Query(status=NEW)
       -> Message<List<Document>>
       -> Splitter
       -> business handlers
~~~

A poller with `maxMessagesPerPoll(1)` can receive **one Message holding multiple documents**, not one document. If the query does not alter state, the next poll fetches the same `NEW` documents again.

### 13.1. What Does updateExpression Do?

A MongoDB inbound source can use:

~~~java
MongoDb.inboundChannelAdapter(
        mongoOperations, "{ 'status':'NEW' }")
    .collectionName("inbox_events")
    .entityClass(OrderRecord.class)
    .update(new Update().set("status", "CLAIMED"));
~~~

This is an **illustrative builder** requiring a real poller + flow and matching entity/collection schema. `updateExpression` can prevent retrieved documents from matching the next poll's query, **yet it does not prove downstream committed**.

Warnings:

- App crashes after `CLAIMED` before Kafka ACK → document may get stuck.
- Two workers may query the same `NEW` documents before either updates.
- A `MongoTransactionManager` does not automatically turn query-then-update into an atomic per-document claim across multiple workers unless isolation/concurrency are explicitly designed and tested.
- If the query filter still matches after the update, the document will be re-polled.
- When downstream uses an async channel, the poller's transaction does not span a business handler on another thread.

### 13.2. Poller with Transaction Advice

Spring Integration allows configuring transaction advice and synchronization callbacks on pollers. XML example:

~~~xml
<!-- MongoTemplate, mongoTransactionManager, channels, and
     int/int-mongodb XML namespaces must be validly declared. -->
<int-mongodb:inbound-channel-adapter
        id="mongoWorkPoller"
        channel="inboxMessages"
        mongo-template="mongoTemplate"
        collection-name="inbox_events"
        query="{ 'status':'NEW' }"
        entity-class="example.mongodbtx.OrderRecord">

    <int:poller fixed-delay="5000"
                max-messages-per-poll="1">
        <int:transactional
            transaction-manager="mongoTransactionManager"/>
    </int:poller>
</int-mongodb:inbound-channel-adapter>
~~~

**This configuration illustrates transaction advice.** The transaction wraps the **synchronous work within the poll task scope**, not an async Kafka publish handed off to another thread; it does not automatically guarantee exclusive multi-instance claiming or exactly-once execution.

### 13.3. Single-Document Atomic Claim Beats Read-Then-Update

One option for a MongoDB work queue:

~~~java
package example.mongodbtx;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Repository;

@Repository
public class InboxClaimRepository {

    private final MongoOperations mongo;

    public InboxClaimRepository(MongoOperations mongo) {
        this.mongo = mongo;
    }

    public OrderRecord claimOne(String workerId) {
        Query eligible = Query.query(
            Criteria.where("status").is("NEW"))
            .with(Sort.by(
                Sort.Order.asc("createdAt"),
                Sort.Order.asc("_id")));

        Update update = new Update()
            .set("status", "PROCESSING")
            .set("claimOwner", workerId);

        return mongo.findAndModify(
            eligible, update,
            FindAndModifyOptions.options().returnNew(true),
            OrderRecord.class, "inbox_events");
    }
}
~~~

**Schema adjustment needed:** the example `OrderRecord` class lacks `claimOwner`, so this only illustrates the query/update pattern; use an `InboxWorkItem` entity with owner, lease, attempt, and version in real code. `createdAt` on the demo entity can be sorted when the field exists.

More importantly: `findAndModify` filtering `status=NEW` and updating to `PROCESSING` is **one atomic per-document MongoDB operation**, ensuring only one worker wins the claim on a document at a time (per condition). It still **does not** prove business completion, requiring leases/recovery for dead workers and fencing/versions if a stale owner wakes up.

## 14. PseudoTransactionManager Is Not a MongoDB Transaction

Spring Integration provides:

~~~java
org.springframework.integration.transaction.PseudoTransactionManager
~~~

It is a `PlatformTransactionManager` implementation for **transaction synchronization** when no real database transaction exists. It triggers callbacks:

- `beforeCommit`
- `afterCommit`
- `afterRollback`

**However, it does not commit or roll back MongoDB, Kafka, JMS, or the filesystem.**

### 14.1. Illustrative Transaction Synchronization XML

~~~xml
<bean id="pseudoTransactionManager"
      class="org.springframework.integration.transaction.PseudoTransactionManager"/>

<int:transaction-synchronization-factory id="syncFactory">
    <int:after-commit channel="afterSuccessfulPoll"/>
    <int:after-rollback channel="afterFailedPoll"/>
</int:transaction-synchronization-factory>

<!-- Inside the poller of an inbound adapter with a channel -->
<int:poller fixed-delay="5000">
    <int:transactional
        transaction-manager="pseudoTransactionManager"
        synchronization-factory="syncFactory"/>
</int:poller>
~~~

The `int:poller` portion is a **fragment placed inside an inbound adapter**, not a complete XML configuration. `afterSuccessfulPoll` and `afterFailedPoll` are channels with consumers.

When synchronous processing finishes normally, "after-commit" callbacks run; if an exception occurs within scope, "after-rollback" callbacks run. **This is pseudo-transaction coordination state**, not a MongoDB commit result.

### 14.2. Risk When an afterCommit Callback Sends to Kafka

~~~text
MongoDB transaction COMMITS (orders + outbox)
   -> afterCommit callback sends to Kafka
   -> process crashes before Kafka ACK
   -> on restart, nothing guarantees the callback re-runs
~~~

Even though the callback runs **after** the MongoDB commit, it still has a crash window and is not a durable work queue. For events that must be published, a **transactional outbox** written inside the same transaction and polled by a separate retrying worker is far more durable.

### 14.3. afterRollback Does Not Undo an Already-Sent Request

If a poller processes a File/SFTP item and sends an HTTP call, a pseudo rollback callback can rename the file or log failure. Yet HTTP data already sent cannot automatically be "recalled" just because a callback reported rollback; you need business compensation or idempotent downstreams.

**Callback names do not turn non-transactional sources into transactional resources.**

## 15. Transactional Outbox: Safer Integration Between MongoDB and Kafka/JMS

For MongoDB → broker, a proven durable pattern is:

1. A MongoDB transaction writes **order + outbox event** with a stable business ID.
2. Commit the transaction with an appropriate write concern.
3. The outbox publisher queries `PENDING` entries with limit/sort and claims them atomically with owner/lease.
4. Send to Kafka/JMS and await broker acknowledgment per contract.
5. Mark the outbox entry `SENT` conditioned on owner/version.
6. If a crash happens at any step, a recovery worker retries.
7. Downstream consumers deduplicate by event ID; redelivery never causes duplicate business side effects.

~~~mermaid
sequenceDiagram
    participant API as Order API
    participant TX as Mongo transaction
    participant DB as MongoDB
    participant W as Outbox Worker
    participant B as Kafka/JMS broker
    API->>TX: acceptOrder(order-101)
    TX->>DB: insert orders(order-101)
    TX->>DB: insert outbox(evt-order-101)
    TX->>DB: commit w=majority
    DB-->>API: commit ACK
    W->>DB: atomically claim PENDING event
    DB-->>W: outbox event
    W->>B: publish(eventId)
    B-->>W: broker ACK
    W->>DB: conditional mark SENT
~~~

### 15.1. Two Critical Crash Windows

**Crash before broker ACK:** the outbox stays `PENDING`/`PROCESSING`, its lease expires, and another worker retries. The broker may or may not have received it; **the event ID stays identical**.

**Crash after broker ACK but before marking `SENT`:** the next run may republish the same event. Thus **at-least-once delivery + idempotent consumers** remain mandatory. An outbox **does not** magically create exactly-once effects across broker and target systems.

### 15.2. Choosing IDs and Unique Indexes

- Orders have a stable business ID within tenant scope.
- Outbox events have a stable `eventId`, ideally unique on `(tenantId, eventId)`.
- Source/broker producers reuse the same `eventId` across retries.
- Consumers store dedup/inbox state by that `eventId` with a unique constraint or a transaction alongside the business effect in the target DB.
- Never use Spring's per-delivery `MessageHeaders.ID` as a dedup key.
- If a duplicate key arrives with a different payload, classify it as a **conflict**, never swallow it silently.

### 15.3. ACK Guarantees per System

| System | ACK milestone | Risk if ACKed earlier |
|---|---|---|
| HTTP caller | After MongoDB transaction commits successfully | Client thinks order succeeded while transaction failed |
| Source Kafka consumer | Offset commit policy after durable persistence | Offset committed yet DB write missing |
| JMS session | After business state is durably persisted | Broker won't redeliver when DB fails |
| SFTP/File | After file contents reach durable inbox/broker | File moved/deleted while downstream didn't process |
| Kafka/JMS outbox publisher | After broker producer ACK | Marked `SENT` prematurely when broker lacks event |
| Outbox DB status | After broker ACK, updated conditioned on owner | Crash before update causes duplicate publish, never data loss |

**There is no single global atomic ACK across MongoDB, HTTP, Kafka, and SFTP from `@Transactional` alone.**

## 16. ReactiveMongoTransactionManager and Transactions in Reactor

In reactive MongoDB pipelines, use:

~~~java
org.springframework.data.mongodb.ReactiveMongoTransactionManager
~~~

Instead of thread-locals, reactive transaction context flows via **Reactor Subscriber Context**.

### 16.1. Reactive Transaction Manager with Options

~~~java
package example.mongodbtx;

import com.mongodb.TransactionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

@Configuration
public class ReactiveMongoTransactionConfig {

    @Bean("reactiveMongoTransactionManager")
    public ReactiveMongoTransactionManager reactiveMongoTransactionManager(
            ReactiveMongoDatabaseFactory factory) {

        TransactionOptions options = TransactionOptions.builder()
            .readConcern(ReadConcern.SNAPSHOT)
            .readPreference(ReadPreference.primary())
            .writeConcern(WriteConcern.MAJORITY)
            .build();

        return new ReactiveMongoTransactionManager(
            factory, options);
    }

    @Bean
    public TransactionalOperator mongoTransactionalOperator(
            ReactiveMongoTransactionManager manager) {
        return TransactionalOperator.create(manager);
    }
}
~~~

Requires the MongoDB reactive driver and `spring-boot-starter-data-mongodb-reactive` with a compatible BOM; never inject blocking `MongoTransactionManager` into a reactive pipeline expecting it to manage subscriber context.

### 16.2. TransactionalOperator and Mono

~~~java
package example.mongodbtx;

import org.springframework.data.mongodb.core.ReactiveMongoOperations;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

public final class ReactiveOrderWriter {

    private final ReactiveMongoOperations mongo;
    private final TransactionalOperator tx;

    public ReactiveOrderWriter(
            ReactiveMongoOperations mongo,
            TransactionalOperator tx) {
        this.mongo = mongo;
        this.tx = tx;
    }

    public Mono<Void> persistOrderAndOutbox(
            OrderRecord order, OutboxEvent outbox) {

        Mono<Void> work =
            mongo.insert(order, "orders")
                .then(mongo.insert(outbox, "outbox_events"))
                .then();

        return work.as(tx::transactional);
    }
}
~~~

**Important:**

- Creating a `Mono` does not start the transaction. It executes when the publisher **is subscribed to**.
- Use the same `ReactiveMongoDatabaseFactory` in both the manager and operations.
- Chain MongoDB operations **sequentially**; never run multiple writes concurrently on **the same transactional `ClientSession`**.
- Spring Data MongoDB advises against concurrent `flatMap` operations inside the same MongoDB transaction because the driver requires operations on a session to be serialized. Use `then`/`concatMap` for transactional sequences.
- Never call `subscribe()` inside the service and return `Mono.empty()`; that detaches transaction completion from the caller.
- `TransactionalOperator` covers only MongoDB operations **within the same composed publisher/session**; it does not extend to Kafka/HTTP/JMS.

### 16.3. @Transactional on Reactive Methods

A Spring-managed service can declare:

~~~java
@Transactional(transactionManager = "reactiveMongoTransactionManager")
public Mono<Void> saveReactiveOrder(
        OrderRecord order, OutboxEvent outbox) {
    return mongo.insert(order, "orders")
        .then(mongo.insert(outbox, "outbox_events"))
        .then();
}
~~~

This is a **fragment** inside a `@Service` with an injected `ReactiveMongoOperations mongo`. The method must be invoked via the Spring AOP proxy and **return a `Publisher`** so Spring applies the reactive transaction upon subscription; never call `block()` on the event loop.

### 16.4. ReactiveMongoDbStoringMessageHandler and ACKs

`ReactiveMongoDbStoringMessageHandler` returns a `Mono<Void>` for the write, usually composed into a Spring Integration reactive flow via `FluxMessageChannel`.

Never treat `MessageChannel.send()==true` as a MongoDB transaction ACK: the downstream publisher may not have been subscribed to or finished yet. When using reactive transactions with `TransactionalOperator`, report business success **only after the transaction publisher's terminal signal** per contract.

## 17. MongoDB Commit Concern and Transaction Options

In MongoDB multi-document transactions:

- **Set write concern at the transaction level**, not per individual write.
- On commit, the server applies the transaction-level write concern when returning the ACK.
- `ReadConcern.SNAPSHOT` provides consistent snapshot semantics within the transaction.
- `ReadPreference.primary()` is normally required for write transactions.
- Transaction-level `w:"majority"` ensures commit durability per deployment rules, not an ACK for external systems.

In modern Spring Data MongoDB, `@Transactional` also supports **MongoDB transaction labels** depending on version, e.g.:

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager",
    label = {
        "mongo:writeConcern=MAJORITY",
        "mongo:readConcern=SNAPSHOT"
    })
public void auditedWrite() {
    // MongoDB writes join the session/transaction.
}
~~~

The snippet above is **illustrative for versions supporting transaction labels**; verify your project's Spring Data MongoDB/Spring Framework version and resolver. Otherwise, declare `TransactionOptions` when creating the manager as in section 9.

**Do not layer arbitrary options onto an already-joined transaction** expecting nested method labels to override the outer transaction's concern.

## 18. MongoDB Transaction Limitations and Commit Errors

### 18.1. Prepare Collections/Indexes Before Business Execution

Transactions carry restrictions around DDL, implicit collection creation, topology, and resource budgets; exact behavior varies by MongoDB version. A safe operational practice is **initializing schemas/indexes separately in deployment migrations**, never creating indexes/collections inside request-handling transactions.

### 18.2. Retrying a Transaction Differs from Retrying a Single Insert

MongoDB/drivers attach error labels such as:

- **`TransientTransactionError`**: the transaction failed transiently and may require retrying the **entire transaction**.
- **`UnknownTransactionCommitResult`**: uncertain whether commit succeeded or failed; requires **retrying the commit per driver protocol** or reconciling data.

Never wrap every exception in a blind retry of the whole business method, especially if external HTTP/Kafka/JMS side effects exist. A transaction callback can re-run and duplicate external side effects if placed inside the callback.

### 18.3. Commit Is a Critical Boundary

~~~text
1. startTransaction()
2. insert(order)
3. insert(outbox)
4. commitTransaction()
5. confirm outcome / return to caller
~~~

If an error happens at (2) or (3) before commit, abort rolls back the transaction. If the response is lost at (4), **the commit result may be unknown**—never assume it "rolled back". Use driver retryable-commit semantics and check business keys and outbox state after failover.

### 18.4. Transaction Timeouts, Lock Conflicts, and Write Skew

- Long-running transactions increase resource usage and risk hitting timeouts/resource caps.
- Concurrent transactions modifying the same document trigger write conflicts; use bounded retries.
- Snapshot isolation does not enforce all unique business invariants by itself. Use unique indexes and conditional updates to guard critical invariants.
- Business predicates spanning multiple documents require careful design to prevent concurrency anomalies.
- Journal/majority ACKs add latency; choose SLAs and durability levels based on business requirements.

**Never treat a transaction like a database-wide lock.** Transactions do not serialize all workers globally; you still must design consistency across relevant data boundaries.

## 19. Testing Blocking Transactions on a MongoDB Replica Set

**Never use mocks to prove storage-level transactions.** A Mockito stub can verify a service calls `mongo.insert` in sequence, yet cannot prove MongoDB actually committed or rolled back. You need a **dedicated test replica set**, such as a single-node replica set or Testcontainers MongoDB configured as a replica set.

### 19.1. Testing Rollback Across Two Writes

Example `@SpringBootTest` with `TransactionTemplate` wired to `MongoTransactionManager`, `MongoOperations`, and pre-created collections/indexes:

~~~java
package example.mongodbtx;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class MongoOrderTransactionIT {

    @Autowired
    MongoOperations mongo;

    @Autowired
    TransactionTemplate mongoTransactionTemplate;

    @Test
    void rollsBackOrderAndOutboxTogether() {
        String key = "it-" + UUID.randomUUID();
        String eventId = "evt-" + key;
        Instant now = Instant.now();

        OrderRecord order = new OrderRecord(
            key, "tenant-test", key,
            new BigDecimal("12.50"), "ACCEPTED", now);

        OutboxEvent outbox = new OutboxEvent(
            eventId, "tenant-test", eventId, key,
            "ORDER_ACCEPTED", "PENDING", now);

        IllegalStateException exception = assertThrows(
            IllegalStateException.class,
            () -> mongoTransactionTemplate.executeWithoutResult(status -> {
                mongo.insert(order, "orders");
                mongo.insert(outbox, "outbox_events");
                throw new IllegalStateException("forced rollback");
            }));

        assertEquals("forced rollback", exception.getMessage());

        assertFalse(mongo.exists(
            Query.query(Criteria.where("_id").is(key)),
            OrderRecord.class, "orders"));

        assertFalse(mongo.exists(
            Query.query(Criteria.where("_id").is(eventId)),
            OutboxEvent.class, "outbox_events"));
    }
}
~~~

**Critical check:** if the test mocks `MongoOperations`, `assertFalse(mongo.exists(...))` tests nothing real. Verify Spring Boot Test connects to a real test replica set, never production, and that `TransactionTemplate` uses the MongoDB transaction manager.

### 19.2. Testing Successful Commit

Another test can use the same fixture without throwing an exception:

~~~java
mongoTransactionTemplate.executeWithoutResult(status -> {
    mongo.insert(order, "orders");
    mongo.insert(outbox, "outbox_events");
});

assertTrue(mongo.exists(
    Query.query(Criteria.where("_id").is(order.id())),
    OrderRecord.class, "orders"));

assertTrue(mongo.exists(
    Query.query(Criteria.where("_id").is(outbox.id())),
    OutboxEvent.class, "outbox_events"));
~~~

This is a fragment inside a test method with unique test-ID `order`/`outbox`, imports, and fixtures. After assertions run, **clean up the exact two seeded IDs** in the test database. Never call `dropDatabase()` on a shared database.

### 19.3. Testing Duplicate Event IDs

Call `OrderApplicationService.acceptOrder(...)` twice with the same `orderId` and tenant:

1. The first call commits order and outbox.
2. The second call hits duplicate key or is handled idempotently per your chosen **business policy**.
3. Count `orders` and `outbox_events` to verify only one record exists for that business key.
4. If the second call has a different amount, assert a **conflict** rather than silently treating it as success.
5. Test two concurrent HTTP/Kafka requests to confirm unique constraints and transactions handle the race.

This tests **business idempotency**, not merely `w:"majority"`.

## 20. Testing Reactive Transactions with StepVerifier

With reactive MongoDB, all operations must live inside a **subscribed publisher chain**. Create `OrderRecord`/`OutboxEvent` with unique test IDs, using `ReactiveMongoOperations` and `TransactionalOperator` from the same factory.

### 20.1. Testing Commit

~~~java
import reactor.test.StepVerifier;
import reactor.core.publisher.Mono;

Mono<Void> write =
    mongo.insert(order, "orders")
        .then(mongo.insert(outbox, "outbox_events"))
        .then()
        .as(tx::transactional);

StepVerifier.create(write)
    .verifyComplete();
~~~

Only when `StepVerifier` subscribes and the publisher emits `onComplete` has the transaction manager signaled commit success. Then **read back both collections** and assert both IDs. This snippet is an integration test fragment assuming a reactive MongoDB test instance with `mongo` and `tx` injected.

### 20.2. Testing Rollback

~~~java
Mono<Void> failing =
    mongo.insert(order, "orders")
        .then(mongo.insert(outbox, "outbox_events"))
        .then(Mono.error(
            new IllegalStateException("forced rollback")))
        .as(tx::transactional);

StepVerifier.create(failing)
    .expectErrorMatches(ex ->
        ex instanceof IllegalStateException
            && "forced rollback".equals(ex.getMessage()))
    .verify();
~~~

After failure, run a query **outside the aborted transaction** asserting neither document exists. Never conclude rollback succeeded solely because `StepVerifier` received `onError`; database readback is mandatory in integration tests.

### 20.3. Never Run Parallel Operations on One Session

Inside a transaction, avoid this pattern:

~~~java
// Warning: do not run concurrent flatMap MongoDB operations
// on the same transactional ClientSession expecting driver support.
return Flux.fromIterable(orders)
    .flatMap(order -> mongo.insert(order, "orders"))
    .then()
    .as(tx::transactional);
~~~

Use `concatMap`/`then` when I/O must be serialized:

~~~java
return Flux.fromIterable(orders)
    .concatMap(order -> mongo.insert(order, "orders"))
    .then()
    .as(tx::transactional);
~~~

Never hold a transaction open across an unbounded `Flux`; bound batch sizes and lifetimes. If each event can be persisted independently, split into short transactions per key/job rather than one transaction over the entire stream.

## 21. Testing Write Concern and Unknown Outcomes

### 21.1. Never "Simulate" Durability via setWriteConcern Alone

A unit test:

~~~java
WriteConcern concern = WriteConcern.MAJORITY;
assertNotNull(concern);
~~~

does not prove MongoDB majority-acknowledged anything. Verify against a real topology observing driver/server behavior under controlled permissions and risk.

### 21.2. Failure Injection on a Test Replica Set

Useful test scenarios:

| Test | Environment | Outcomes to distinguish |
|---|---|---|
| `w:1`, primary healthy | Test replica set | Write ACKed at primary |
| `w:majority`, enough members | Test replica set | Write ACKed once concern met |
| `w:majority`, secondary unavailable | **Isolated** replica set only | Timeout / availability error |
| `wtimeout` after primary apply | Controlled fault injection | Never assume write rolled back |
| Driver timeout before ACK | Simulated network fault | Outcome unknown; reconcile same ID |
| Duplicate ID after retry | Unique index | May prove earlier write reached DB |
| Transaction fails before commit | Test DB | Aborts both documents |
| Transaction commit ACK lost | Replica set / fault injection | Unknown commit outcome; retry/reconcile |
| Service crashes after DB commit before Kafka publish | Outbox worker | Outbox remains ready for retry |
| Kafka publish ACK then crash before `SENT` | Broker + DB test | May redeliver same event ID |

Only perform replication failovers or network faults in a **test environment**. Never stop a production primary/secondary to demonstrate a lesson.

### 21.3. Inspecting Outcomes Properly

A write concern timeout is not a signal that "the record definitely does not exist". When the app receives an error:

1. Log request/correlation/business ID, operation type, and error label (never secrets).
2. Never generate a new business ID to retry the same event.
3. If the driver provides safe retryable commit/operation protocols, follow them.
4. Read back with an appropriate query, read concern/session when consistency is required.
5. Verify order/outbox state along with payload/tenant, not just `exists()`, when conflicts are possible.
6. ACK upstream only after durable processing state is established.
7. If state remains indeterminate, route to a **reconciliation queue** instead of continuing as if succeeded.

**Never classify all errors with `onErrorResume(e -> Mono.empty())`** inside a reactive transaction: that converts failure into completion and causes false ACKs.

## 22. Failure Matrix and Recovery Policies

| Failure point | Symptom | Handling |
|---|---|---|
| Bad connection/auth | Driver operation cannot execute | Fix config/secret/role; do not retry forever |
| Standalone lacks transaction support | Error starting/committing transaction | Use a replica-set/sharded test deployment |
| `MongoTemplate` uses different factory from manager | Operations run outside transaction | Trace beans/factories/sessions and fix wiring |
| `WriteConcern w:0` | No reliable write ACK | Do not use for durable business events |
| `wtimeout` | Write may already be applied | Reconcile ID; do not assume rollback |
| Primary step-down | Transient/unknown outcomes | Bounded retries, driver protocol, business keys |
| MongoDB duplicate key | Record with same key already exists | Compare payload/status and classify duplicate vs. conflict |
| Outbox insert fails after order insert | Transaction aborts | Test rollback across both collections |
| MongoDB transaction commit unknown | Client lacks confirmation | Retry commit/reconcile; never blindly replay side effects |
| Very long transaction | Timeouts/lock/resource pressure | Shrink scope, use shorter batches |
| MongoDB write conflict | Transaction aborted | Retry whole transaction if safe/idempotent |
| Kafka send fails after DB commit | Outbox stays `PENDING`/`PROCESSING` | Broker retries, lease recovery |
| Kafka ACKed then worker dies | `SENT` not marked yet | Redelivery with stable event ID |
| JDBC transaction not managed by Mongo manager | Two resources not atomic | Outbox/saga; never assume 2PC |
| `DirectChannel` swapped to `QueueChannel` | Transaction context breaks | Align ACK/transaction on the worker thread |
| `PseudoTransactionManager` misused | No real MongoDB rollback | Use `MongoTransactionManager` for MongoDB transactions |
| `MongoDbMessageSource` re-reads `NEW` | Read-only polling query | Claim/lease/idempotency, proper state updates |
| Two workers claim same document | Read-then-update race | Conditional atomic `findAndModify` |
| Reactive `Mono` unsubscribed | No real write occurs | Framework-managed composition/subscription |
| Reactive parallel `flatMap` in transaction | Driver session contention | `then`/`concatMap`, sequential operations |

### 22.1. Same Exception, Two Interpretations

**`DuplicateKeyException`:** may result from retrying **the exact same already-committed payload**, or another client submitting the same key with a **different payload**. Query the business record and compare contents rather than swallowing all duplicates as idempotent successes.

**`MongoTransactionException` / transaction error labels:** may stem from data, permissions, topology, or transient failover. Never retry forever; classify transient vs. permanent and cap attempts/backoff.

**Write concern errors:** the server-side operation may still persist, requiring reconciliation; never treat every exception as storage rollback.

## 23. Observability: Measuring Real ACKs and Commits

Suggested metrics (do not assume Spring Integration emits these exact names automatically):

| Metric | What it measures |
|---|---|
| `mongo_write_attempt_total` | Number of write attempts |
| `mongo_write_ack_total` | Acknowledged write operations |
| `mongo_write_concern_timeout_total` | `wtimeout` errors |
| `mongo_write_unknown_result_total` | Operations with indeterminate state |
| `mongo_write_latency_seconds` | Write latency until ACK |
| `mongo_transaction_begin_total` | Transactions started |
| `mongo_transaction_commit_success_total` | Successful commit ACKs |
| `mongo_transaction_abort_total` | Aborted/rolled-back transactions |
| `mongo_transaction_commit_unknown_total` | Unknown commit outcomes |
| `mongo_transaction_duration_seconds` | Open transaction duration |
| `mongo_transaction_retry_total` | Controlled retries |
| `mongo_outbox_pending_depth` | Pending outbox events |
| `mongo_outbox_oldest_age_seconds` | Age of oldest `PENDING` event |
| `mongo_outbox_publish_success_total` | Successful broker ACKs |
| `mongo_outbox_publish_error_total` | Failed broker publishes |
| `mongo_outbox_redelivery_total` | Outbox events showing redelivery |
| `integration_business_committed_total` | Downstream business completions |

**Separate** MongoDB write ACKs, transaction commit ACKs, broker publish ACKs, and business completions. A service incrementing `mongo_write_success_total` merely upon handler invocation does not measure durability.

### 23.1. Tracing by Correlation and Business ID

~~~text
order_received       orderId=order-101
mongo_tx_started      orderId=order-101
mongo_order_inserted  orderId=order-101
mongo_outbox_inserted eventId=order-accepted:order-101
mongo_tx_committed    orderId=order-101
outbox_claimed        eventId=order-accepted:order-101
broker_publish_ack    eventId=order-accepted:order-101
outbox_marked_sent    eventId=order-accepted:order-101
consumer_committed    eventId=order-accepted:order-101
~~~

Never log credentials, PANs, secrets, sensitive order details, or raw full payloads. Avoid per-`orderId`/`eventId` metric labels due to extreme cardinality; use tracing/logs with proper retention and PII policies.

### 23.2. Key Alerts

- Rising `wtimeout` counts after a node failover do not mean all writes failed/rolled back.
- Growing outbox backlog may indicate the broker is down while DB transactions commit normally.
- Rising transaction duration can indicate network calls held inside transactions or pool exhaustion.
- Rising duplicate events can reflect the crash window after broker ACK before marking `SENT`; this is why outbox consumers **must expect redeliveries**.
- MongoDB replication lag affects majority ACK latency and read consistency.
- Downstream tracking should use cross-system business keys/trace IDs rather than Spring Message UUIDs.

## 24. Production Security and Operations

### 24.1. Credentials and Privileges

- Use a MongoDB account with read/write access limited to the **exact collections** `orders`/`outbox_events`.
- Collection/index creation and admin operations belong in deployment/migration pipelines, not runtime services unless necessary.
- Load URIs/credentials from a secret manager; never hard-code passwords or log full connection URIs.
- Enable TLS and network controls per environment.
- Authenticate tenants server-side; queries and writes must enforce authorized `tenantId` scope.
- Transactions do not prevent cross-tenant access if the service lacks authorization.
- Unique indexes on business IDs must include tenant scope or namespaced IDs to prevent collisions.

### 24.2. Replica Sets and Durability

- Verify actual topology, majority thresholds, and any arbiter presence.
- Select write concern per **business SLA** balancing latency, durability, and availability.
- Test failovers in isolated environments before rollout.
- Monitor replication lag, journal pressure, client pools, transaction durations, and error labels.
- Configure accurate readiness/liveness probes so an instance is not marked ready when the DB cannot serve the workload.
- Coordinate consistent backups/restores across business collections, outbox, and idempotency state.
- After restore, inspect `PENDING`/`PROCESSING` outbox entries and state drift to prevent lost events.

### 24.3. Release Strategy

When deploying a new version with schema or event-format changes:

1. Ensure consumers understand both old and new versions during rollout.
2. Migrate indexes/collections in a dedicated step, never mid-request inside transactions.
3. Keep outbox `eventId`/`aggregateId` stable across restarts.
4. Keep the transaction manager aligned with the same `MongoDatabaseFactory`.
5. Stop producers/pollers cleanly via lifecycle hooks and drain workers within a deadline.
6. Persist pending work state so new instances resume seamlessly.
7. Do not purge outbox events immediately after broker send without reviewing retention/replay/audit needs.

## 25. Choosing the Right Solution: One Document, Many Documents, or Many Systems?

| Requirement | Solution to consider |
|---|---|
| Transition one job from `NEW` to `PROCESSING` | Atomic single-document **conditional update/`findAndModify`** |
| Write order + outbox in the same MongoDB deployment | **`MongoTransactionManager`** + transaction-level write concern |
| Only configure write ACK level | Appropriate **`WriteConcern`**, no multi-document transaction needed |
| Write messages to MongoDB via Integration outbound adapter | **`MongoDbStoringMessageHandler`** with a properly configured `MongoTemplate` |
| Run callback only after File/SFTP inbound poll finishes | Transaction synchronization; **`PseudoTransactionManager` provides callbacks only**, not DB transactions |
| MongoDB → Kafka with zero lost events | **Transactional outbox** + retries + idempotent Kafka consumer |
| Kafka → MongoDB and commit offset | Durable inbox/transactional state + proper ACK policy; never assume `@Transactional` covers Kafka |
| Update MongoDB + PostgreSQL together | Saga/outbox/compensation or validated distributed design; `MongoTransactionManager` does not manage PostgreSQL |
| Multiple workers polling MongoDB | Atomic claims, leases, owner/version, idempotent processing |
| Atomic multi-write reactive MongoDB | `ReactiveMongoTransactionManager` + `TransactionalOperator`, serialized within session |
| Simply detect updates from MongoDB | Change stream with resume token/checkpoint; does not replace cross-system transactions |

**The answer is not "turn on transactions everywhere".** Open transactions only where MongoDB state genuinely needs atomicity; bridge separate systems using message contracts, durable state, and idempotency.

## 26. Comprehensive Hands-On Lab

Build an **Order API → Spring Integration → MongoDB orders + outbox → Kafka/JMS** system and test durability/rollback on a replica set.

### Part A — Write Concern

1. Set up a MongoDB replica set **for lab/test only**.
2. Create collections and indexes as in section 6.
3. Test `w:1`, `w:"majority"`, and corresponding `j:true` configurations.
4. Compare ACK levels, latency, and topology requirements; never conclude from a single run.
5. Test `wtimeout` under safe fault injection, confirming the write may still exist.
6. Inspect actual cluster/driver defaults instead of guessing.
7. Explain how `ReadConcern.MAJORITY` differs from `WriteConcern.MAJORITY`.
8. Explain why a secondary may not yet have applied a write right after a majority ACK in modern MongoDB.

### Part B — Spring Data MongoDB Transactions

1. Create `MongoTransactionManager` sharing the same `MongoDatabaseFactory` as `MongoTemplate`.
2. Configure `TransactionOptions` with `ReadConcern.SNAPSHOT`, `ReadPreference.primary()`, and `WriteConcern.MAJORITY`.
3. Write `OrderApplicationService.acceptOrder(...)` with `@Transactional`.
4. Insert order and outbox in one transaction; assert both exist after commit.
5. Throw an intentional exception in a **test-only** transaction after both inserts; assert both roll back.
6. Test duplicate business IDs and amount conflicts.
7. Test self-invocation bypassing the Spring proxy to understand transaction boundaries.
8. Test an operation using a `MongoTemplate` on a different factory and analyze the risk of running outside the transaction.

### Part C — Spring Integration Endpoints

1. Create `IntegrationFlow.from("ordersInput").handle(service, "acceptOrder")`.
2. Send an `OrderCommand` from a producer and assert MongoDB commit and `PENDING` outbox entry.
3. Compare `DirectChannel` vs. `QueueChannel` regarding transaction context and when `send()` returns.
4. Configure `MongoDbStoringMessageHandler` using a `MongoTemplate` with appropriate write concern.
5. Test MongoDB inbound polling for `NEW` documents and describe duplicate-read risks.
6. Test `updateExpression` in a separate flow; explain why `CLAIMED` is not yet `DONE`.
7. Use `PseudoTransactionManager` with callbacks to observe that it **does not** roll back MongoDB.

### Part D — Outbox and Failures

1. Write a worker claiming `PENDING` outbox entries via `findAndModify` + leases.
2. Publish a stable `eventId` to a test broker.
3. Simulate broker ACK succeeding then crashing before updating `SENT`: verify retries republish.
4. Add an idempotent consumer keyed by event ID; assert only one business effect occurs.
5. Simulate broker failure before ACK; verify outbox is never falsely marked `SENT`.
6. Bound retries, backoff, and classify transient vs. permanent failures.
7. Apply reconciliation when a transaction commit/write outcome is unknown.

### Part E — Reactive and Operations

1. Create `ReactiveMongoTransactionManager`/`TransactionalOperator` sharing the same `ReactiveMongoDatabaseFactory`.
2. Compose two reactive inserts with `then`, avoiding scattered `subscribe()` calls.
3. Use `StepVerifier` to test commit, rollback, and errors when MongoDB is down.
4. Compare concurrent `flatMap` vs. sequential `concatMap` inside a transaction.
5. Track metrics for transaction begin/commit/abort/unknown, `wtimeout`, and outbox backlog.
6. Design graceful shutdown and recovery with pending outbox events.
7. Write a runbook for replica-set failover, credential rotation, and backup/restore.

**Self-assessment questions:**

- What do write concern `w`, `j`, and `wtimeout` control?
- Is `w:0` suitable for business events that must be persisted durably?
- How does `w:1` differ from `w:"majority"`?
- Does a majority ACK mean every secondary has applied the document?
- Why does a write concern timeout not automatically roll back a write?
- Can `WriteConcern` and `ReadConcern` substitute for one another?
- Why do two inserts with majority ACKs not form a transaction?
- Does a single-document atomic update require a multi-document transaction?
- What are the roles of `ClientSession` and `MongoTransactionManager`?
- At what level is write concern configured inside a transaction?
- Why must `MongoTemplate` and the transaction manager share the same `MongoDatabaseFactory`?
- Why does `@Transactional` self-invocation fail to trigger AOP?
- When switching from `DirectChannel` to `QueueChannel`, how does the transaction scope change?
- Can `PseudoTransactionManager` roll back MongoDB?
- Does an `afterCommit` callback replace a transactional outbox?
- Why does a MongoDB commit not commit Kafka/JMS/HTTP?
- What happens on a crash after broker ACK but before marking `SENT`?
- Why must idempotency keys be stable business IDs?
- When a commit result is unknown, should you generate a new event ID to retry?
- Where does `ReactiveMongoTransactionManager` store the transaction context?
- Why must reactive MongoDB operations inside the same transaction be serialized?
- Can Mockito tests prove real MongoDB rollback?
- Why can long-held transactions degrade throughput?
- When should you use `findAndModify` instead of a multi-document transaction?

## 27. References

- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): definitions of `w`, `j`, `wtimeout`, majority, implicit defaults, and acknowledgment behavior.
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/): transaction scope, concerns/options, commit/abort, and limitations.
- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/): majority/snapshot consistency.
- [MongoDB Manual — Connection String Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/): concern/timeout options and version changes.
- [Spring Data MongoDB Reference — Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): `ClientSession`, `MongoTransactionManager`, `ReactiveMongoTransactionManager`, `TransactionTemplate`/`TransactionalOperator`, and transaction labels.
- [Spring Data MongoDB Reference — Template Configuration](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-config.html): `setWriteConcern`, `WriteConcernResolver`, and defaults.
- [Spring Data MongoDB API — MongoTemplate](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/MongoTemplate.html): `setWriteConcern`, `setWriteConcernResolver`.
- [Spring Data MongoDB API — MongoTransactionManager](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/MongoTransactionManager.html): constructors with `MongoDatabaseFactory`/`TransactionOptions`, session binding.
- [Spring Data MongoDB API — ReactiveMongoTransactionManager](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/ReactiveMongoTransactionManager.html): Reactor Context, reactive sessions, and transaction options.
- [Spring Integration Reference — MongoDB Support](https://docs.spring.io/spring-integration/reference/mongodb.html): inbound/outbound adapters, `MongoDbMessageSource`, `updateExpression`, and transaction synchronization.
- [Spring Integration API — MongoDbStoringMessageHandler](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/outbound/MongoDbStoringMessageHandler.html): factory/template constructors and payload persistence.
- [Spring Integration Reference — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html): poller transaction advice, `beforeCommit`/`afterCommit`/`afterRollback`, `PseudoTransactionManager`, and reactive transactions.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): `DirectChannel`, `QueueChannel`, `ExecutorChannel`, and thread boundaries.
- [Project Reactor — Reference](https://projectreactor.io/docs/core/release/reference/): reactive publisher composition/transaction subscription.
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html): testing `onNext`/`onComplete`/`onError` and rollbacks.
- [MongoDB Manual — findAndModify](https://www.mongodb.com/docs/manual/reference/method/db.collection.findAndModify/): single-document conditional update/claim.
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/): driver retryable write behavior and failure classification.

## Conclusion

**Write concern** answers **how much and what kind of acknowledgment MongoDB requires before ACKing a write**; **transactions** answer **which MongoDB operations must commit or abort together**. `wtimeout` does not prove a write rolled back; `w:"majority"` does not mean Kafka/JMS/HTTP received the event. Inside multi-document transactions, write concern must be specified at the **transaction level**, not per individual insert/update.

In **SPRING_INTEGRATION_ADAPTERS**, use `MongoTemplate` with controlled write concern, `MongoTransactionManager` or `ReactiveMongoTransactionManager` bound to the right factory/session, transaction boundaries aligned with threads/Publishers, and clearly separate `PseudoTransactionManager` from real MongoDB transactions. For flows spanning MongoDB and brokers/files/HTTP, combine **transactional outbox, stable event IDs, conditional claim/lease, idempotent consumers, retry/backoff, monitoring, and reconciliation**. **A MongoDB commit is an important technical step, not an end-to-end exactly-once guarantee for the entire system.**
