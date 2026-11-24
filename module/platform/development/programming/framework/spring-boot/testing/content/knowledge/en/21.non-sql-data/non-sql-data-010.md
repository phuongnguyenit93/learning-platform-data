# Testing transactional capabilities according to each storage engine

In Spring Boot systems using **non-SQL data**, you cannot simply attach `@Transactional` and expect every storage engine to exhibit the **commit, rollback, isolation, and durability** behavior of a relational database. MongoDB supports multi-document transactions when its topology meets prerequisites. Redis supports `MULTI/EXEC`, `WATCH`, and Lua scripts with specific atomicity and execution ordering, yet **lacks relational-style rollback**. Neo4j provides ACID transactions for graphs. DynamoDB provides a bounded transaction API. Couchbase provides distributed transactions via the appropriate SDK/API. Elasticsearch does not provide ACID multi-document transactions; Cassandra offers LWT/batches and, in certain newer versions/deployments, **Accord transactions** when explicitly enabled.

Therefore, the right question before writing tests is not "did we add the transaction annotation?" but:

1. **Which capabilities does the exact storage engine, version, topology, and client support?**
2. **Is the atomic scope one command, one document, one partition, multiple documents, multiple tables, or the entire system?**
3. **If an error occurs mid-sequence, can earlier executed steps be undone?**
4. **Under concurrent writes or network/primary-node failures, can clients observe ambiguous commit states?**
5. **Which evidence must the test prove, and with which tool/instance close to production?**

This Knowledge lesson provides a **transactional capability matrix by storage engine**, a workflow for designing commit/rollback/conflict/visibility tests, common pitfalls when using Spring Data, and a runnable **Java 17 + Spring Boot 3.5 + MongoDB Testcontainers** project contrasting multi-collection transactions against **non-transactional** operations.

## 1. Understanding "transactions" accurately before testing

Different systems use the word "transaction" for very different guarantees:

| Property | Question to verify | Counter-example |
|---|---|---|
| **Atomicity** | If step two fails, is step one undone? | Redis `MULTI/EXEC` does not roll back earlier executed commands if a later command throws a runtime error |
| **Consistency** | Are business invariants and store constraints upheld at the committed boundary? | A standalone Redis `SET` does not protect monetary sums across multiple keys |
| **Isolation** | Can Client B see intermediate state, cause lost updates, or trigger write skew during Client A's work? | `read committed` does not mean serializable |
| **Durability** | After reporting success, does data survive failover/crash under the configured write concern and replication policy? | `EXEC` succeeding does not automatically mean AOF fsync flushed durably to disk |
| **Scope** | Does the guarantee cover one key, document, partition, transaction request, or multiple resources? | Single-document atomicity does not imply atomicity across two collections |
| **Visibility** | Once a write succeeds, when do queries/searches/subscribers observe the result? | Elasticsearch indexed the doc yet has not run `refresh`, so search still misses it |
| **Idempotency** | Does retrying a request after a timeout duplicate effects? | Inserting an order twice without a business key/conditional check |

**Atomicity does not equal rollback.** A Redis script or atomic compare-and-set executes without interleaving from other clients, yet still **does not revert earlier writes** if the script/transaction hits a runtime error. Conversely, an ACID-capable system supports rollback, yet strictly within the **transaction boundary** actually opened.

**Consistency does not always mean strong consistency.** Eventual consistency allows replicas to observe older states temporarily; server write acceptance does not guarantee every reader or search index sees it immediately. Tests must specify reading from primary vs. replica, consistency/read concern, refreshes, or convergence deadlines.

## 2. Transactional capability matrix by storage system

| Storage engine / API | Guaranteed unit | Multi-object transaction / rollback? | What tests must prove |
|---|---|---|---|
| **MongoDB** | Single document atomic; transactions can span documents/collections on supporting replica set/sharded cluster | **Yes** with session + transaction manager/API and supporting topology | Two collections commit or abort together; mid-step failure; conflict/commit outcome |
| **Redis** `SET`/`INCR` | Single command atomic under Redis server model | Does not group multiple commands into a transaction | Concurrent updates on same key lose no increments via atomic `INCR`; TTL and idempotency |
| **Redis** `MULTI/EXEC`, `WATCH` | Queued commands in `EXEC` run without interleaving; `WATCH` gives optimistic CAS | **No** rollback of already-executed writes if a command inside `EXEC` errors at runtime | `WATCH` conflict aborts queue execution; runtime command error can leave partial effects |
| **Redis** Lua/Functions | Script executes atomically relative to other clients per server rules | Not a SQL rollback transaction | Prevents overselling inside one script; if script errors after writing, never assume auto-rollback |
| **Neo4j** | Transactions over nodes, relationships, and Cypher operations | **Yes ACID**, though default isolation has limits | Create node + relationship, fail and roll back; unique constraints; concurrent updates |
| **DynamoDB** | Single-item writes + conditional writes; `TransactWriteItems` groups multiple items | **Yes** via transaction API within request/Region limits | Condition failure rejects entire transaction; optimistic conflicts; idempotency token |
| **Couchbase** | Atomic single-document ops; multi-document transactions via SDK/transaction service | **Yes** when using the distributed transaction API | Two documents commit/roll back together, retried transaction lambda, conflicts, and query visibility |
| **Traditional Cassandra** | Per-partition/statement atomicity/consistency and batch guarantees; LWT conditional CAS | **Never infer RDBMS-style rollback from `LOGGED BATCH`** | `[applied]` from LWT, conflicts, consistency levels; logged batch is not multi-row isolation |
| **Cassandra Accord** (when version/config supports it) | Can span partitions/tables when transactional mode/API is enabled | **Can** provide multi-operation ACID | Verify engine/transactional mode, test multi-partition atomicity, conflicts/recovery |
| **Elasticsearch** | Per-document index/update with concurrency controls; Bulk reports per-item results | **No default multi-document ACID rollback** | Bulk partial failures, optimistic concurrency `seq_no`/`primary_term`, refresh/search visibility |

**Do not treat this table as a universal promise across every version.** Capabilities evolve across editions, cluster topologies, SDKs, and server releases. For example, Cassandra has long had **LWT/batches**, whereas **Accord** applies only where supported and enabled; never state blindly that "Cassandra never has transactions" or "every Cassandra deployment today has multi-partition ACID".

### Choosing tests by goal

- "Does one valid document insert save accurately?" → single-operation repository test.
- "Do order and outbox writes succeed or fail together?" → **multi-document transaction test on MongoDB/Neo4j/DynamoDB/Couchbase** with the matching API; Redis/Elasticsearch require different designs.
- "Prevent two concurrent requests from buying the last item when stock is 1?" → **concurrency/conditional-write test**, not just a rollback test.
- "Write succeeded yet search cannot find it?" → **visibility/refresh/convergence test**, never conflate with rollback.
- "Email was sent and then the database rolled back?" → **cross-resource workflow test**; no single-store transaction provides magic undo across external side effects.

## 3. Layering transaction tests in Spring Boot

| Test tier | Example | Proves | Does NOT prove |
|---|---|---|---|
| **Unit test** with mock repository | `when(repo.save(...))`, throw on step two | Service calls dependencies in order or translates errors | Whether the server actually rolls back or provides ACID |
| **Data slice** | `@DataMongoTest`, `@DataNeo4jTest`, `@DataRedisTest` | Repository mapping/queries or slice-loaded store APIs | Service proxy transactions unless service/tx manager imported; production topology |
| **Integration test with container** | MongoDB replica set, Redis, Neo4j, Couchbase, Cassandra | Real behavior for the test's server/version and config | Full production cluster durability or failover on a single container |
| **Full Spring Boot context** | `@SpringBootTest` + store container | `@Transactional` service proxy, transaction manager, repository wiring | External systems omitted from the test |
| **Failure/concurrency test** | 2 clients, network drop, duplicate requests, unknown commit | Isolation/conflicts/retries/recovery per scenario | All possible schedules/failover paths if run only once |
| **System/deployment test** | Production-like cluster with auth, replication, and rolling failover | Realistic durability/visibility and configuration | Absolute proof against every conceivable failure |

A `@DataMongoTest` loads `MongoTemplate` yet **does not automatically create `MongoTransactionManager`** the way you might expect. To test `@Transactional` on a service, ensure both the transaction manager bean and Spring proxy exist in the context, typically via `@SpringBootTest` or intentional `@Import`. Likewise, `@DataRedisTest` does not turn Redis commands into SQL transactions.

**Never use H2 to simulate MongoDB transactions.** H2 is a relational engine: rollback tests on H2 only verify H2/JDBC or ORM behavior, never MongoDB sessions, Redis `WATCH`, or Elasticsearch Bulk. Use **the real server/driver or official simulator** matching the exact capability under test.

## 4. MongoDB: multiple documents can commit or roll back together

MongoDB has long guaranteed **single-document** atomicity; multi-document transactions require a **client session, supporting server topology, and transaction API**. With imperative Spring Data MongoDB, register `MongoTransactionManager` and invoke a `@Transactional` public service method through its **Spring proxy**; `MongoTemplate` detects the transaction-bound session and participates automatically.

```text
Spring @Transactional service (proxy)
             |
             v
       MongoTransactionManager
             |
             v
     ClientSession + transaction
             |
         +---+---+
         |       |
         v       v
    orders.insert outbox.insert
         |       |
         +---+---+
             |
       commit / abort
             |
     both visible / neither
```

**Prerequisites:**

1. MongoDB server supports transactions; tests use a **replica set** configured by `MongoDBContainer`, not a non-replica-set standalone `mongod`.
2. Register `MongoTransactionManager` for **imperative `MongoTemplate`**, or `ReactiveMongoTransactionManager` for **reactive templates**. Never mix the two transaction models.
3. Call the service through its Spring bean proxy; never call `this.placeAtomically(...)` internally expecting the default proxy to intercept self-invocation.
4. Use `MongoTemplate`/repository operations sharing the **same `MongoDatabaseFactory`/session**; raw driver calls opening independent sessions fall outside the transaction.
5. **Pre-create collections and indexes** outside transactions to avoid limitations/differences around implicit collection creation inside transactions. Avoid DDL mid-scenario.
6. Test **successful commit**, **exception after the first write**, **DB error on the second write**, and a **non-transactional control case** to prove the transaction actually mattered.

**`@Transactional` does not automatically enlist Redis, Kafka, HTTP clients, or another MongoDB cluster into one transaction.** The Mongo transaction manager governs only its own MongoDB resource, not automatic distributed XA transactions.

### Imperative vs. reactive Mongo

| Code | Transaction manager | Context |
|---|---|---|
| `MongoTemplate`, `MongoRepository`, sync driver | `MongoTransactionManager` | Spring's thread-bound client session |
| `ReactiveMongoTemplate`, `ReactiveMongoRepository`, reactive driver | `ReactiveMongoTransactionManager` | Reactor Context attached to Publisher subscription |

For reactive methods returning `Mono`/`Flux`, subscribe inside the transactional boundary; **never** call `block()` and split commands across separate non-transactional subscriptions. Spring Data provides `TransactionalOperator` to wrap a Publisher, analogous to R2DBC transactions but backed by **`ReactiveMongoTransactionManager`**.

**Durability/isolation:** a transaction committing must be interpreted alongside `writeConcern`, `readConcern`, read preferences, and replication/failover policies. A single-node replica-set test **proves atomicity in that setup**, not multi-node failover or majority durability.

## 5. Complete Java 17 example: MongoDB Testcontainers commit and rollback

We implement a simple order placement workflow: saving an `OrderDoc` in collection `orders` and an `OutboxDoc` in collection `outbox`. **The outbox record is MongoDB data**, not a message already sent to Kafka or email.

If all steps succeed, both documents commit together. If the service throws after inserting the order, the transaction aborts and **neither order nor outbox remains**. Without a transaction, the same error leaves an **orphaned order**. If inserting the outbox fails on duplicate `_id`, the new order must also roll back.

The example uses **Spring Boot 3.5.0**, **Java 17**, **MongoDB 7**, **Testcontainers 1.x (managed by the Spring Boot 3.5 BOM)**, and JUnit Jupiter. **Requires Docker running**. No embedded MongoDB fake or H2; no HTTP server needed.

### 5.1. Project structure

```text
nosql-transaction-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/nosql/
    │   ├── NoSqlTransactionApplication.java
    │   ├── OrderDoc.java
    │   ├── OutboxDoc.java
    │   └── OrderWorkflow.java
    └── test/java/com/example/nosql/
        └── MongoTransactionTest.java
```

### 5.2. Maven `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>nosql-transaction-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-mongodb</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>mongodb</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-data-mongodb` supplies **imperative `MongoTemplate`** in the example; `org.testcontainers:mongodb` from Testcontainers 1.x provides `org.testcontainers.containers.MongoDBContainer`; `junit-jupiter` enables container lifecycle management. **Spring Boot 4/Testcontainers 2.x may change modules/packages**, so check the matching version docs when upgrading instead of copying imports blindly.

### 5.3. Spring Boot application

File **`src/main/java/com/example/nosql/NoSqlTransactionApplication.java`**:

```java
package com.example.nosql;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class NoSqlTransactionApplication {
    public static void main(String[] args) {
        SpringApplication.run(NoSqlTransactionApplication.class, args);
    }
}
```

The root application allows Spring Boot to scan `OrderWorkflow` and Mongo mapping types in the same package. We do not start a web server in tests; only the MongoDB resource and Spring transaction proxy are needed.

### 5.4. MongoDB documents

File **`src/main/java/com/example/nosql/OrderDoc.java`**:

```java
package com.example.nosql;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDoc(@Id String id, String sku) {
}
```

File **`src/main/java/com/example/nosql/OutboxDoc.java`**:

```java
package com.example.nosql;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "outbox")
public record OutboxDoc(
        @Id String id,
        String orderId,
        String eventType) {
}
```

Java `record` provides equality and immutable state. `@Id` maps to `_id`; MongoDB maintains a unique index on `_id` in each collection. Two different collections are **not automatically grouped** into a transaction simply by sharing `MongoTemplate`; the transaction comes from the transaction manager/session and service boundary.

### 5.5. Service with and without transactions

File **`src/main/java/com/example/nosql/OrderWorkflow.java`**:

```java
package com.example.nosql;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderWorkflow {

    private final MongoTemplate mongo;

    public OrderWorkflow(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    @Transactional
    public void placeAtomically(
            String orderId, String sku, boolean failAfterOrder) {
        writeBoth(orderId, sku, failAfterOrder);
    }

    public void placeWithoutTransaction(
            String orderId, String sku, boolean failAfterOrder) {
        writeBoth(orderId, sku, failAfterOrder);
    }

    private void writeBoth(
            String orderId, String sku, boolean failAfterOrder) {
        mongo.insert(new OrderDoc(orderId, sku));

        if (failAfterOrder) {
            throw new IllegalStateException("after-first-write");
        }

        mongo.insert(new OutboxDoc(
                "event-" + orderId,
                orderId,
                "ORDER_PLACED"));
    }
}
```

**Key points to understand:**

- `placeAtomically` is a **public Spring bean method** annotated with `@Transactional`; when **the test calls it through the injected bean**, the proxy starts a transaction. Private helper `writeBoth` executes *inside* that public method's boundary, so both `MongoTemplate` calls join the same session.
- `placeWithoutTransaction` calls the exact same helper **without a transaction**. `MongoTemplate` runs each insert independently; throwing after the first insert leaves the order persisted without an outbox entry.
- When an exception is thrown inside a transactional method, Spring rolls back by default on **unchecked exceptions** such as `IllegalStateException`.
- If the service catches `RuntimeException`, **swallows it**, and returns normally, Spring may commit unless marked rollback-only; tests must reflect that policy.
- This is a **MongoDB** transaction, not a transaction covering sending emails, Kafka, or Redis.

### 5.6. Test configuring MongoDB replica set and transaction manager

File **`src/test/java/com/example/nosql/MongoTransactionTest.java`**:

```java
package com.example.nosql;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

@Testcontainers
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Import(MongoTransactionTest.TxConfig.class)
class MongoTransactionTest {

    @Container
    static final MongoDBContainer MONGO =
            new MongoDBContainer(
                    DockerImageName.parse("mongo:7.0"));

    @DynamicPropertySource
    static void mongoConnection(DynamicPropertyRegistry registry) {
        registry.add("spring.data.mongodb.uri", MONGO::getReplicaSetUrl);
    }

    @TestConfiguration(proxyBeanMethods = false)
    @EnableTransactionManagement
    static class TxConfig {
        @Bean
        MongoTransactionManager transactionManager(
                MongoDatabaseFactory factory) {
            return new MongoTransactionManager(factory);
        }
    }

    @Autowired
    private MongoTemplate mongo;

    @Autowired
    private OrderWorkflow workflow;

    @BeforeEach
    void resetCollectionsOutsideTransaction() {
        // Create collections upfront to avoid DDL inside a transaction.
        if (!mongo.collectionExists(OrderDoc.class)) {
            mongo.createCollection(OrderDoc.class);
        }
        if (!mongo.collectionExists(OutboxDoc.class)) {
            mongo.createCollection(OutboxDoc.class);
        }

        mongo.remove(new Query(), OrderDoc.class);
        mongo.remove(new Query(), OutboxDoc.class);
    }

    @Test
    void successCommitsOrderAndOutboxTogether() {
        workflow.placeAtomically("O-1", "BOOK-1", false);

        assertNotNull(mongo.findById("O-1", OrderDoc.class));
        assertNotNull(mongo.findById("event-O-1", OutboxDoc.class));
        assertEquals(1L, mongo.count(new Query(), OrderDoc.class));
        assertEquals(1L, mongo.count(new Query(), OutboxDoc.class));
    }

    @Test
    void exceptionAfterFirstInsertRollsBackBothCollections() {
        IllegalStateException failure = assertThrows(
                IllegalStateException.class,
                () -> workflow.placeAtomically(
                        "O-2", "BOOK-2", true));

        assertEquals("after-first-write", failure.getMessage());
        assertNull(mongo.findById("O-2", OrderDoc.class));
        assertNull(mongo.findById("event-O-2", OutboxDoc.class));
    }

    @Test
    void sameFailureWithoutTransactionLeavesPartialOrder() {
        assertThrows(
                IllegalStateException.class,
                () -> workflow.placeWithoutTransaction(
                        "O-3", "BOOK-3", true));

        assertNotNull(mongo.findById("O-3", OrderDoc.class));
        assertNull(mongo.findById("event-O-3", OutboxDoc.class));
    }

    @Test
    void duplicateOutboxIdAbortsNewOrderButKeepsExistingEvent() {
        mongo.insert(new OutboxDoc(
                "event-O-4", "OLD", "EARLIER_EVENT"));

        assertThrows(
                DuplicateKeyException.class,
                () -> workflow.placeAtomically(
                        "O-4", "BOOK-4", false));

        assertNull(mongo.findById("O-4", OrderDoc.class));
        OutboxDoc existing =
                mongo.findById("event-O-4", OutboxDoc.class);

        assertNotNull(existing);
        assertEquals("OLD", existing.orderId());
        assertEquals(0L, mongo.count(new Query(), OrderDoc.class));
        assertEquals(1L, mongo.count(new Query(), OutboxDoc.class));
    }
}
```

**Intentional choices in the code:**

- `@Testcontainers` and `@Container` launch MongoDB 7 in Docker. `getReplicaSetUrl` provides the replica-set URI required for transactions. **Never replace it with a standalone MongoDB URI.**
- `@DynamicPropertySource` binds the container URI to `spring.data.mongodb.uri` before Spring Boot builds `MongoClient`.
- `@TestConfiguration` and `@Import` register **`MongoTransactionManager`**; `@EnableTransactionManagement` tells Spring to create proxies for `@Transactional`.
- `@BeforeEach` pre-creates collections and clears data **outside** any transaction. Creating collections inside transactions has version/topology caveats, so pre-creating is cleaner.
- **Test 1:** calls the transactional method via proxy, then checks **both collections** hold their documents.
- **Test 2:** throws after inserting the order and before inserting the outbox; transaction rollback leaves zero documents.
- **Test 3:** triggers the identical failure without the transaction boundary; the order **remains persisted**. This is a critical control test, preventing "false green" results caused by code not writing at all.
- **Test 4:** pre-seeds a conflicting outbox `_id`. MongoDB rejects the second insert with duplicate key; the transaction rolls back the new order while **leaving untouched** the pre-existing outbox document created prior to the transaction.

Never annotate the test methods themselves with `@Transactional`: doing so alters the exact boundary under test (a test-managed transaction interferes with observing committed vs. aborted outcomes). Assertions read data **after the service proxy method returns**, meaning after commit/rollback has completed.

**Expected outcome:** when Docker runs properly, the Mongo container initializes its replica set, and dependencies match, **4 `@Test` methods PASS**. This lesson **was not executed live inside this document**; when applying it, run Maven/IDE tests in your own environment to confirm. A single-node replica-set test does not prove majority fault tolerance or failover of a production cluster.

### 5.7. Running with Maven

From the directory containing `pom.xml`, with Java 17+, Maven, and Docker Engine running with container permissions:

```bash
mvn test
```

Run individually:

```bash
mvn -Dtest=MongoTransactionTest test
```

If the project has Maven Wrapper (`mvnw` generated beforehand), run `./mvnw test` or `mvnw.cmd` on Windows. Maven Surefire/JUnit may print MongoDB/Testcontainers logs depending on versions. With the exact example, expect **Tests run: 4, Failures: 0, Errors: 0** once the image pulls and replica set initializes. No fixed business stdout is printed.

A failure in Test 2 or Test 4 where **the order still exists** signals an issue to investigate in the transaction manager, proxy, Mongo topology/session, or an operation running outside the session — never "fix" it by deleting rows before asserting.

## 6. Redis: `MULTI/EXEC` does not mean rollback on runtime errors

Redis is the classic example of a system having **transaction terminology** without MongoDB/Neo4j rollback semantics.

### `MULTI`, `EXEC`, `DISCARD`, and `WATCH`

```redis
SET quota 5
MULTI
DECR quota
DECR quota
EXEC
GET quota
```

This is an illustrative sequence in `redis-cli`. `MULTI` begins queuing commands; `EXEC` executes queued commands **sequentially without interleaving from other clients**. Given the inputs above and no concurrent client modifying `quota`, the value after `EXEC` is `3`.

If the client calls `DISCARD` **before `EXEC`**, queued commands are dropped without running. However, if a command **fails while `EXEC` executes**, Redis **does not roll back other commands that already succeeded**; tests must inspect both final state and every reply rather than seeing a reply array and assuming atomic rollback.

Example (deliberately including a type-error command):

```redis
SET counter 0
SET text hello
MULTI
INCR counter
INCR text
EXEC
GET counter
GET text
```

State outcome: `counter` becomes `1` even though `INCR text` errors because `text` is not an integer; `text` stays `hello`. This is an **illustrative negative test** refuting the misconception "if `EXEC` hits an error, everything rolls back".

`WATCH` enables **optimistic check-and-set**: Client A runs `WATCH stock`, reads the value, and queues mutations; if Client B modifies `stock` before A calls `EXEC`, A **does not execute** the batch and must handle the null/aborted reply by retrying or reporting a conflict. Proper tests use **two independent connections** and a synchronization barrier to guarantee contention rather than using one connection and assuming concurrency.

### Lua/Redis Functions

To implement "decrement stock only if greater than 0", a Lua script can read-check-write without interleaving on the Redis server, for example:

```lua
local n = tonumber(redis.call('GET', KEYS[1]) or '0')
if n <= 0 then return 0 end
return redis.call('DECR', KEYS[1])
```

This is a **Lua snippet**, invoked via `EVAL`/`EVALSHA` with the right `KEYS[1]`; in clusters, key placement/hash slots must obey multi-key rules. Tests should race **two clients contending** for stock=1 and verify only one wins. However, if a script writes and then triggers a Redis runtime error, **never claim earlier writes automatically roll back**.

For durability, check **AOF/RDB settings, fsync, replication acknowledgements, and failover**. `EXEC` returning success is no substitute for a crash/durability fault-injection test.

### Spring Data Redis

`RedisTemplate` supports transactional commands and `setEnableTransactionSupport(true)` where applicable. Still, a JDBC/Mongo `@Transactional` does not automatically wrap Redis commands into a **multi-resource ACID transaction**. To truly test Redis `WATCH`/`MULTI` behavior, use a **Redis container** with `RedisConnection` or `SessionCallback` on the right connection and assert **both `EXEC` replies and final key states**. Never use `@MockBean RedisTemplate` to prove real rollback behavior.

## 7. Cassandra: LWT, logged batches, and version-dependent Accord

### Lightweight transactions (LWT)

Traditional Cassandra supports compare-and-set via conditional CQL statements:

```sql
INSERT INTO users (tenant_id, user_id, email)
VALUES ('shop-a', 'U-1', 'a@example.com')
IF NOT EXISTS;
```

This is **illustrative CQL**, not SQL/JPA code; it requires a matching Cassandra schema and primary key. The query returns **`[applied]`** status; when the key already exists, a second `INSERT ... IF NOT EXISTS` returns **not applied** without overwriting the original row. LWT uses consensus (Paxos) for compare-and-set/linearizability within its scope, incurring higher latency than regular writes.

Tests must verify **both conditional success and conditional failure**; if the client API returns `[applied]=false` instead of throwing an exception, a test asserting only "no exception thrown" gives a **false pass**.

### Logged batches differ from RDBMS rollback

`BEGIN BATCH ... APPLY BATCH` (logged batch) aims to ensure mutations are logged and eventually applied per Cassandra guarantees, particularly across coordinator failures. Never infer from the word "BATCH" that multiple partitions receive synchronous **isolation + rollback** like a SQL transaction; readers can observe partial progress across partitions depending on version/config. Tests must state whether they are verifying **eventual completion**, **atomic visibility**, or **conditional application**, since each uses different APIs.

### Accord transactions in supporting deployments

Modern Cassandra documentation covers **Accord transactions** for multi-partition/table ACID where supported by version, configuration, and enabled transactional mode. Consequently, statements like "Cassandra never has multi-partition transactions" must be qualified by **specific version and mechanism**. Before relying on multi-table transactions, check your Cassandra release, schema/table options, driver, and `BEGIN TRANSACTION ... COMMIT TRANSACTION` syntax in the corresponding docs. Never copy Accord APIs onto older clusters that only support LWT/batches.

**Cassandra test matrix should cover:** `[applied]` true/false, two clients racing on the same partition, logged batch across partitions during network faults, `QUORUM`/`LOCAL_QUORUM` or `SERIAL`/`LOCAL_SERIAL` read consistency with LWT, and Accord multi-partition tests **only if enabled**.

## 8. DynamoDB: `TransactWriteItems` is a transaction API with clear limits

DynamoDB supports atomic single-item writes and conditional expressions. When multiple items must succeed or fail all-or-nothing, use **`TransactWriteItems`** or `TransactGetItems` rather than two separate `PutItem` calls.

An example transaction request may contain:

```text
TransactWriteItems:
  - Put Order(orderId=O-1), condition attribute_not_exists(orderId)
  - Update Stock(sku=BOOK-1), condition stock >= 1
  - Put Outbox(eventId=event-O-1), condition attribute_not_exists(eventId)
```

This is a **pseudo-request**, not runnable Java/AWS SDK code. If `stock < 1` or `orderId` already exists, the transaction is rejected and **none of the other changes apply**. Tests must not just assert `TransactionCanceledException`; they must read back **order, stock, and outbox** to prove zero partial writes occurred.

Under current DynamoDB API limits, a single `TransactWriteItems` request allows **at most 100 actions and 4 MiB** total item size, within the same AWS account/Region, and cannot target **the same item** twice in one transaction. With global tables, transactions are **not ACID across Regions** during replication; tests reading from a replica Region must not assume atomic global visibility.

**Idempotency:** DynamoDB supports `ClientRequestToken` so retrying the same transaction request never duplicates effects. A high-value test invokes the transaction, simulates a lost response/timeout, retries with **the same token**, and verifies the final state applied exactly once. Never test retries merely with `Mockito.verify(client, times(2))`, which proves nothing about real storage state.

## 9. Neo4j and Couchbase: ACID capable, yet require the right API

### Neo4j graph transactions

Neo4j supports ACID transactions across node, relationship, and Cypher operations. For example: "create two nodes and an `OWNS` relationship, or create nothing". With Spring Data Neo4j or the Neo4j Java Driver, place the transaction boundary properly and inspect the entire graph **after commit/rollback**. Container tests should cover:

- Happy path: both nodes and the relationship exist.
- Exception thrown after creating the first node: no graph fragment remains.
- Unique constraint conflict: transaction rolls back cleanly with no orphaned relationships.
- Concurrency: locking/isolation, lost updates, and retries on transient conflicts.

Neo4j supporting ACID does not imply **serializable isolation by default**; documentation states default isolation is typically read-committed, so invariants needing serializability require explicit locking, constraints, and tests. Never test Neo4j with an in-memory fake and claim real locking was measured.

### Couchbase distributed transactions

Couchbase offers atomic single-document operations and **distributed ACID transactions** across multiple documents/collections via its SDK transaction API. Conceptual Java SDK snippet:

```java
cluster.transactions().run(ctx -> {
    ctx.insert(collection, "order-O-1", orderContent);
    ctx.insert(collection, "outbox-O-1", outboxContent);
});
```

**This is a snippet, not standalone compilable** because `cluster`, `collection`, `orderContent`, and `outboxContent` are undeclared. Unlike imperative `MongoTemplate`, putting `@Transactional` on a Spring service does not automatically prove the Couchbase SDK transaction lambda is used or that every operation joins it.

Couchbase tests must verify **lambda commit/rollback**, conflicts, and transaction retries per SDK/version; because the transactions API may automatically retry the lambda, any **non-Couchbase side effects inside the lambda** (such as sending emails) risk executing repeatedly. Keep idempotency/outbox records decoupled. Cluster configuration, durability, and eventual search/index visibility require separate tests beyond KV transactions.

## 10. Elasticsearch: partial success and refresh are not rollback

Elasticsearch supports single-document indexing/updates with **optimistic concurrency control** via `if_seq_no` + `if_primary_term`. However, the **Bulk API is not an ACID multi-document transaction**: one bulk request can have some items succeed and others fail, with zero automatic rollback of successful items.

Pseudo-bulk example:

```text
Bulk:
  index product-1     -> 201 created
  update product-2    -> 409 version_conflict_engine_exception
  index product-3     -> 201 created

Response: errors=true, inspect items[0..2] separately
```

This is an **illustrative scenario**, not real response JSON from an actual endpoint. Treating a Bulk HTTP status 200 as "the entire batch succeeded" is **wrong**; assert the `errors` flag, each item's status/result, and post-request index/search state.

**Refresh is not commit:** successful index/update operations generally require `refresh` or `refresh=wait_for` before search sees them when the test expects. A search failing immediately after a write usually indicates **near-real-time visibility**, not transaction rollback. Tests should separate:

1. Single-document optimistic version conflicts.
2. Bulk partial success and per-item error handling.
3. Search visibility after refresh/refresh policy.
4. Retries/idempotency when the client does not know which items succeeded.
5. Never assuming Spring `@Transactional` rolls back Elasticsearch indexes when another call fails.

If business logic needs "MongoDB order + Elasticsearch index" kept in sync, use **outbox/CDC/eventual projections** rather than pretending Elastic bulk is part of a Mongo transaction.

## 11. Minimal test cases for any storage engine

Before writing tests, define the target engine's **capability contract**; never expect rollback from an engine that does not support it. A practical matrix:

| Case | Initial state | Action | Final assertion |
|---|---|---|---|
| **Happy commit** | Two empty collections/keys | Write A then B inside the right transaction API | After completion, both A and B exist |
| **Mid-step failure** | Clean state | Write A, throw exception before B | **If store supports rollback:** neither A nor B exists; otherwise assert documented partial effect |
| **DB-level conflict** | B already holds unique key | Write A then write conflicting B | **If store supports rollback:** A absent, existing B unchanged |
| **Concurrent writers** | One slot or stock=1 | Two clients attempt to claim concurrently | Only one succeeds under proper CAS/unique/locking |
| **Timeout/unknown commit** | Fixed operation ID | Send transaction, drop response, then retry | No double charge, no duplicate record |
| **Visibility** | No data | Write, then read via replica/search | Result obeys read concern/refresh deadline, not assumed immediate |
| **Crash/failover** | Replicated cluster | Kill leader during commit/replication | Verify recovery per configured durability guarantee |
| **Cross-store failure** | DB + broker/index | DB write succeeds, broker/index fails | Recovery/outbox/compensation achieves eventual convergence without fake cross-rollback |

For concurrency tests, never rely on `Thread.sleep` hoping two requests collide. Use `CountDownLatch`/`CyclicBarrier`, two distinct connections/clients, and an `ExecutorService`; record **outcomes of both operations** and inspect final server state. Running a concurrency test once still cannot explore every interleaving; run bounded iterations against an appropriate Testcontainers cluster while avoiding flaky timing assumptions.

### Injecting failures in the right places

- **Business exception after the first write:** tests whether the transaction proxy truly rolls back.
- **Constraint/conditional conflict on the second write:** tests server-side abort via real database error paths.
- **Network disconnect at COMMIT:** tests how the app handles **unknown commit outcomes** rather than blindly assuming abort.
- **Process crash before/after ACK:** tests durability under write concern/failover config.
- **Client retry request:** tests idempotency keys and exact side-effect counts.
- **External resource failure:** tests outbox/compensation rather than pretending an unmanaged store joins the atomic boundary.

All fault injection must be **repeatable and observable**, ideally using test-dedicated services/containers. Never crash production or shared databases to "test transactions".

## 12. A single Spring transaction does not span MongoDB, Redis, and Kafka

Treating `@Transactional` as a "universal umbrella" is wrong:

```text
@Transactional
  write MongoDB order   --> MongoTransactionManager
  write Redis cache     --> separate Redis command/Redis transaction
  publish Kafka event   --> separate Kafka producer transaction
  call external HTTP    --> independent server

There is no default distributed atomic rollback across participants!
```

For example, **DB transaction + transactional outbox** fits reliable publishing:

1. Inside **one MongoDB transaction**, write the order and `OutboxDoc`.
2. After commit, a **separate worker** reads the outbox and emits events to Kafka/Redis/search.
3. Consumers use **idempotency keys** to deduplicate; publishers can retry safely.
4. Mark outbox entries as published and run reconcilers/monitoring for stuck records.
5. Test eventual consistency with bounded retries/polling rather than expecting external steps to roll back with the DB.

**An outbox prevents losing the intent to publish**, yet **does not by itself give exactly-once side effects**. Delivery can repeat if ACKs drop, so consumers must be idempotent. For multi-system workflows requiring compensation, use Sagas/compensating actions; compensation **is not ACID rollback**, can itself fail, and needs retries and auditing.

### Separating three distinct guarantees

- **Single-store atomicity:** real transaction API/manager with accurate scope.
- **Reliable cross-store delivery:** outbox/CDC/event stream + idempotency.
- **End-to-end business correctness:** Sagas/validation/reconciliation and end-to-end tests.

When documenting test suites, state explicitly which guarantee each test proves. For instance, `MongoTransactionTest` proves Mongo collections commit/abort together; it does not prove an outbox publisher emitted an event once or that Redis/Elasticsearch projections converged.

## 13. Common pitfalls

| Mistake/misconception | Consequence | Fix |
|---|---|---|
| Putting `@Transactional` on every NoSQL repository | Illusion that all stores roll back like SQL | Verify transaction manager/SDK, scope, and topology |
| Using multi-doc `@Transactional` on standalone MongoDB | Server lacks required transaction topology | Use replica set/sharded cluster and proper session URI |
| Missing `MongoTransactionManager` | `MongoTemplate` ignores Spring transactions | Define manager bean; invoke service through Spring proxy |
| Test instantiates `new OrderWorkflow(mongo)` directly | Bypasses Spring AOP proxy | Inject bean from context; verify server-side rollback |
| `this.placeAtomically()` self-invocation | Internal call bypasses proxy | Redesign bean boundary or invoke through proxy |
| Skipping collection creation before Mongo transaction | DDL/implicit collection creation errors by version/topology | Pre-create collections/indexes outside transactions |
| Unintended transaction on the test method itself | Sees only test-transaction state or rolls back at wrong boundary | Read state after service proxy finishes; keep setup clean |
| Redis `EXEC` hits command error, test expects rollback | Redis never rolls back already-executed runtime writes | Assert each reply and final keys; use atomic scripts/compensation |
| Treating `WATCH` abort as DB rollback exception | Queued commands never ran after aborted `EXEC` | Assert null/aborted `EXEC` and key state; retry CAS |
| Not asserting Cassandra `[applied]=false` | Condition failed yet test stays green | Check LWT result and two-client concurrency |
| Confusing logged batch with multi-partition SQL transactions | False expectation of synchronous isolation/rollback | Test version-specific guarantees; evaluate Accord where available |
| DynamoDB calling two `PutItem`s instead of `TransactWriteItems` | Risks partial writes | Use transaction API and assert all-or-nothing on conflicts |
| DynamoDB transaction acting twice on the same item | Request violates API limits | Redesign conditional updates/transactions |
| Neo4j ACID test lacks failure after first write | Never actually proved rollback | Inject failure and verify zero graph fragments remain |
| Couchbase transaction lambda sends emails | SDK retries can send duplicate emails | Move external side effects outside lambda via outbox/idempotency |
| Treating Elasticsearch Bulk HTTP 200 as total success | Silently misses partial item failures | Inspect `errors` flag and per-item status |
| Thinking invisible Elasticsearch search means rollback | Search index simply not refreshed yet | Separate index ACK from refresh visibility |
| Using mocked repositories as proof of ACID | Mocks are not databases | Write integration tests with real servers/containers |
| Using single Mongo container to claim majority failover | Topology does not represent production clusters | Run separate cluster/failover integration tests |
| Retrying endlessly on unknown commit errors | Double side effects or hung CI | Use idempotency keys, bounded retries, observe commit outcome |
| Skipping cleanup between tests | Order-dependent tests or random duplicate keys | Isolate DBs/containers and run deterministic fixture cleanup |

## 14. Checklist for designing tests around real capabilities

- [ ] Identified the exact **store + version + edition + topology + driver/SDK** under test.
- [ ] Identified whether the guarantee is **single-item**, **multi-item transaction**, **CAS**, or **eventual batch completion**.
- [ ] Distinguished atomicity, isolation, durability, visibility, and idempotency.
- [ ] When multi-write rollback is required, verified the backend supports it and invoked the exact transaction API.
- [ ] Configured and used the Spring transaction manager bean or SDK transaction session.
- [ ] Avoided relying on `@Transactional` to span multiple separate storage systems.
- [ ] Positive tests assert **all** records committed.
- [ ] Negative tests throw **after the first write** and assert exact store state.
- [ ] Tested database-level failures on later steps, not only Java-thrown exceptions.
- [ ] Verified **existing data stays untouched** after transaction abort.
- [ ] Included a **non-transactional control test** when proving transaction effect.
- [ ] When a store lacks rollback, tested **partial success** and recovery/compensation logic.
- [ ] For optimistic locking/conditional writes, tested two contending clients and the failure path.
- [ ] For search/indexes, separated write acknowledgment from **post-refresh visibility**.
- [ ] For timeouts/failover, defined policies for **unknown commit state** and idempotent retries.
- [ ] Used containers/schemas/indexes/capabilities close to production when risks are high.
- [ ] Never used an in-memory fake of a different engine to claim real database guarantees.
- [ ] Verified cleanup/isolation never deletes another parallel CI test's data.
- [ ] Tested event/outbox eventual delivery and deduplication separately rather than inferring from DB commits.
- [ ] Executed tests via the build tool and verified which assertions prove **store capabilities** vs. pure service logic.

**Conclusion:** **There is no single transaction semantic shared across all non-SQL storage engines.** MongoDB, Neo4j, DynamoDB, and Couchbase offer multi-object transactions within defined scopes/conditions; Redis offers atomic commands/`MULTI/EXEC`/`WATCH` without SQL-style rollback; Cassandra offers LWT/batches and Accord depending on version; Elasticsearch offers per-document concurrency and Bulk partial success rather than multi-document rollback. Good tests pick **the right server, right API, right failure boundary, and right post-error state assertions**.

### Official references

- [Spring Data MongoDB — Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html)
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html)
- [MongoDB Java Driver — Integration Testing with Testcontainers](https://www.mongodb.com/docs/drivers/java/sync/current/integrations/testcontainers/)
- [Redis — Transactions, MULTI/EXEC/WATCH, rollback behavior](https://redis.io/docs/latest/develop/using-commands/transactions/)
- [Apache Cassandra — Guarantees, Lightweight Transactions](https://cassandra.apache.org/doc/latest/cassandra/architecture/guarantees.html)
- [Apache Cassandra — Accord Transaction concepts](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/transactions.html)
- [AWS DynamoDB — TransactWriteItems](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_TransactWriteItems.html)
- [AWS DynamoDB — Transaction limits and global tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Constraints.html)
- [Neo4j — Transactional behavior](https://neo4j.com/docs/operations-manual/current/database-internals/)
- [Couchbase — Distributed ACID Transactions](https://docs.couchbase.com/java-sdk/current/concept-docs/transactions.html)
- [Elasticsearch — Document update and optimistic concurrency](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-update)
