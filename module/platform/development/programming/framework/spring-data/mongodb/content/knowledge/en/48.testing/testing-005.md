# Replica Sets in Transaction and Change Stream Tests

## 1. Why Does MongoDB Testing Sometimes Require a Replica Set?

When using **Spring Data MongoDB** to map documents and interact via **MongoRepository**, **MongoTemplate**, **ReactiveMongoRepository**, or **ReactiveMongoTemplate**, simple CRUD tests can run against a standalone MongoDB instance. However, two important groups of features depend on a replica set infrastructure:

- **Multi-document transactions**: a group of operations can be committed or rolled back as a single logical unit. MongoDB transactions require an environment that supports transactions, such as a compatible **replica set** or **sharded cluster**.
- **Change streams**: the application listens for committed changes on a collection, database, or deployment. Change streams rely on the replica set's **oplog**-based change tracking mechanism, or the corresponding infrastructure when connected through **mongos** in a sharded cluster.

Therefore, a repository test that saves one document on standalone MongoDB **does not prove** that business logic using transactions or change streams works. If you run those two features on standalone, the application usually receives an error from the server. Enabling **@Transactional**, adding Reactor dependencies, or tweaking driver retry settings cannot turn a standalone node into a replica set.

In the **Testing** chapter of the **SPRING_DATA_MONGODB** module, we need to know how to spin up a replica set for the test environment, drive transactions from Spring, actively generate change events, and verify actual outcomes.

### Expected Outcomes After This Lesson

1. Explain why transactions and change streams require an appropriate topology.
2. Distinguish a **single-node replica set for integration tests** from a **multi-node replica set for fault-tolerance testing**.
3. Automatically create a replica set using Testcontainers and pass its URI to Spring Data MongoDB.
4. Write tests proving transaction **commit** and **rollback**.
5. Write tests listening for **insert** events through a change stream without dropping events due to subscribing too late.
6. Recognize configuration errors, timeouts, race conditions, and test-environment limitations.

## 2. Topology, Oplog, and How It Works

MongoDB typically appears in the following topologies:

| Environment | Multi-document transactions | Change streams | What is it used to test? |
| --- | --- | --- | --- |
| **Standalone mongod** | Unsupported under this model | Unsupported | Simple CRUD, basic mapping operations |
| **Single-node replica set** | Yes, when supported by MongoDB/driver | Yes | Functional tests for basic transactions and change streams |
| **Multi-member replica set** | Yes | Yes | Testing primary failover, majority writes, replica lag, network faults |
| **Sharded cluster** | Yes, per supported features and versions | Yes, typically via mongos | Cross-shard transactions, cluster-wide change streams, routing |

A **single-member replica set** still has a primary role and an oplog. It suffices for many functional tests because MongoDB treats that node as a member of a replica set. However, it cannot test automatic primary election, losing a node while maintaining quorum, or replication lag across members.

### How Important Is the Oplog?

The **oplog** is an ordered log of operations that replica set members use to replicate changes. Change streams read changes from this mechanism and emit structured events such as **insert**, **update**, **replace**, or **delete**. Matching events are emitted only once changes satisfy MongoDB's acknowledgment rules.

**Transactions** have different semantics: multiple commands execute within the same session/transaction, and committing makes the entire effect of the transaction visible according to consistency rules. Changes inside an **aborted** transaction are not committed data events emitted by a change stream as successful outcomes.

~~~mermaid
flowchart TB
    Test["JUnit integration test"]
    Spring["Spring Data MongoDB<br/>MongoTemplate / Repository"]
    Driver["MongoDB Java Driver"]
    Primary[("mongod<br/>Single-node replica set<br/>PRIMARY + oplog")]
    Tx["MongoTransactionManager<br/>session + commit / abort"]
    Stream["Change stream cursor<br/>watch collection"]
    Test --> Spring
    Spring --> Driver
    Spring --> Tx
    Tx --> Driver
    Driver --> Primary
    Test --> Stream
    Stream --> Driver
    Primary -.->|"Committed changes"| Stream
~~~

The diagram illustrates a simple test environment: the client interacts with a single primary member. In production deployments, there may be multiple nodes and multiple **mongos** routers, but the principles for testing transactions and change streams still rely on real server behavior.

## 3. How to Spin Up a Replica Set for Testing?

### 3.1. Manual Initialization

When you have a dedicated test MongoDB instance, you can start `mongod` with the replica set option, for example:

~~~bash
# Data directory path and startup command vary by operating system.
mongod --dbpath /data/mongo-test --replSet rsTest --bind_ip localhost --port 27017
~~~

Once the process is running, connect with `mongosh` and initiate:

~~~javascript
rs.initiate({
  _id: "rsTest",
  members: [
    { _id: 0, host: "localhost:27017" }
  ]
});

rs.status();
db.hello();
~~~

Wait until the node actually becomes **PRIMARY** before running tests. Example URI when client and `mongod` are on the same machine:

~~~text
mongodb://localhost:27017/spring_mongo_test?replicaSet=rsTest
~~~

**Note:** the hostname advertised by the replica set must be reachable from where the tests run. If a container advertises an internal hostname that the JVM on the host cannot reach, the driver may connect initially and then fail with a **server selection** error. This is one reason to use established libraries to initialize and map the replica set URI when running Docker.

### 3.2. Testcontainers with a Single-Node Replica Set

**Testcontainers** has a MongoDB module that starts MongoDB for tests and exposes a **replica set URL**. This gives the test suite a clean lifecycle and runs locally or in CI with compatible Docker.

Example Gradle dependencies for a Spring Boot 3.x and Testcontainers 1.x project:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:mongodb'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

In Testcontainers 1.x, the class commonly used is **org.testcontainers.containers.MongoDBContainer**. In newer Testcontainers generations, artifact/package names may be reorganized; adjust to match your project's version. The sample below illustrates the Testcontainers 1.x API with MongoDB 7.0 and does not imply every application must pin these exact versions.

~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
class ReplicaSetSmokeTest {

    @Container
    static final MongoDBContainer MONGO =
        new MongoDBContainer(DockerImageName.parse("mongo:7.0"));

    @Test
    void containerExposesReplicaSetUri() {
        String uri = MONGO.getReplicaSetUrl();
        org.junit.jupiter.api.Assertions.assertTrue(uri.startsWith("mongodb://"));
    }
}
~~~

A smoke test only confirms that the container started and the API returned a URI; **the transaction/change stream tests later in this lesson confirm the features actually work**. Never assert only the URI and conclude that the replica set meets all business requirements.

## 4. Configuring Spring Data MongoDB to Use the Container URI

Spring Boot normally provides auto-configuration for `MongoClient` and `MongoTemplate`. For the **Spring Boot 3.x** examples, the URI property is **spring.data.mongodb.uri**. In newer Spring Boot lines, property names or auto-configuration may change; use the property matching your version.

In integration tests, **@DynamicPropertySource** passes the runtime URI generated by Testcontainers into the Spring context:

~~~java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@DynamicPropertySource
static void mongoProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.data.mongodb.uri", MONGO::getReplicaSetUrl);
}
~~~

Key points:

- **MONGO** is a static container started by Testcontainers for the test class.
- **getReplicaSetUrl()** provides connection info suitable for the test replica set, including dynamically mapped host/port.
- Do not guess host port **27017**; Testcontainers typically maps to a different port.
- If the application defines multiple **MongoClient** beans, ensure the client used in transaction tests and the client used for change streams point to the same test deployment according to configuration.

Tests must wait for the container and replica set to finish initializing and avoid sharing the test MongoDB with the real application. Testcontainers manages container lifecycle; readiness checks also require sensible timeouts and verifying specific behaviors.

## 5. Testing Real Transactions with MongoTransactionManager

### 5.1. Why Is @Transactional Alone Not Enough?

In Spring Data MongoDB, **@Transactional** takes effect only when an appropriate transaction manager exists and execution passes through Spring's proxy/transaction management. For synchronous access, **MongoTransactionManager** binds a session to MongoDB operations performed inside the transaction scope.

Prerequisites:

1. The MongoDB server is a replica set or sharded cluster supporting transactions.
2. Spring Data uses the proper **MongoDatabaseFactory** and `MongoClient`.
3. A **MongoTransactionManager** bean exists and transaction management is enabled.
4. Business method calls pass through the Spring bean/proxy rather than instantiating objects directly with **new**.
5. Write operations actually execute through data components that participate in the transaction session.

**Self-invocation** is a common pitfall: a method in the same class directly calling another **@Transactional** method can bypass the proxy and fail to open a transaction as expected.

### 5.2. Illustrative Domain and Repository

Suppose a business flow must write **two ledger entries** in the same batch. If an error occurs after writing the first entry, the transaction must roll back both entries.

~~~java
// LedgerEntry.java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "ledger_entries")
public record LedgerEntry(
    @Id String id,
    String batchId,
    long amount
) {}
~~~

~~~java
// LedgerEntryRepository.java
import org.springframework.data.mongodb.repository.MongoRepository;

public interface LedgerEntryRepository
        extends MongoRepository<LedgerEntry, String> {

    long countByBatchId(String batchId);
}
~~~

~~~java
// LedgerService.java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LedgerService {
    private final LedgerEntryRepository repository;

    public LedgerService(LedgerEntryRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void writePair(String batchId) {
        repository.save(new LedgerEntry(batchId + "-in", batchId, 100));
        repository.save(new LedgerEntry(batchId + "-out", batchId, -100));
    }

    @Transactional
    public void writePairThenFail(String batchId) {
        repository.save(new LedgerEntry(batchId + "-in", batchId, 100));
        repository.save(new LedgerEntry(batchId + "-out", batchId, -100));
        throw new IllegalStateException("Forced business failure");
    }
}
~~~

Two **save** operations on the same document collection clearly demonstrate transaction atomicity. The failure case intentionally throws a runtime exception to trigger rollback under Spring's default rules. For checked exceptions, consider **rollbackFor** or an appropriate rollback policy.

### 5.3. Test-Specific Transaction Manager Configuration

~~~java
// MongoTxTestConfiguration.java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@TestConfiguration(proxyBeanMethods = false)
@EnableTransactionManagement
public class MongoTxTestConfiguration {

    @Bean
    MongoTransactionManager mongoTransactionManager(
        MongoDatabaseFactory mongoDatabaseFactory
    ) {
        return new MongoTransactionManager(mongoDatabaseFactory);
    }
}
~~~

This bean is isolated for testing to make the dependency explicit. In a real application, a transaction manager may already be declared in main configuration; in that case, avoid duplicate bean names or multiple managers that cause Spring to pick the wrong one.

### 5.4. Testing Commit and Rollback on a Real Replica Set

~~~java
// MongoReplicaSetIntegrationTest.java
import static org.junit.jupiter.api.Assertions.*;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@DataMongoTest
@Import({LedgerService.class, MongoTxTestConfiguration.class})
class MongoReplicaSetIntegrationTest {

    @Container
    static final MongoDBContainer MONGO =
        new MongoDBContainer(DockerImageName.parse("mongo:7.0"));

    @DynamicPropertySource
    static void mongoProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.mongodb.uri", MONGO::getReplicaSetUrl);
    }

    @Autowired LedgerEntryRepository repository;
    @Autowired LedgerService service;
    @Autowired MongoTemplate template;

    @BeforeEach
    void ensureCollectionExists() {
        // Create the collection before starting a transaction so we do not
        // depend on implicit collection creation inside a transaction.
        if (!template.collectionExists(LedgerEntry.class)) {
            template.createCollection(LedgerEntry.class);
        }
    }

    @Test
    void successfulTransactionCommitsBothDocuments() {
        String batchId = UUID.randomUUID().toString();

        service.writePair(batchId);

        assertEquals(2, repository.countByBatchId(batchId));
    }

    @Test
    void runtimeFailureRollsBackBothDocuments() {
        String batchId = UUID.randomUUID().toString();

        assertThrows(
            IllegalStateException.class,
            () -> service.writePairThenFail(batchId)
        );

        assertEquals(0, repository.countByBatchId(batchId));
    }
}
~~~

The two tests prove different things:

- **Commit:** when the Spring service call finishes normally, both documents must be visible after the transaction commits.
- **Rollback:** when the service throws inside the transaction, neither document from the batch is persisted.

The tests use a **UUID** per batch to avoid interference from leftover data in the same container. If you need tighter verification, you can query individual IDs before and after the operation.

**Do not place @Transactional on the test method itself** in this example. A transaction opened by the test framework around the test can distort commit observation: after the service returns, writes may still be uncommitted, or the entire test may auto-rollback at the end. The goal here is to verify transactions managed by **LedgerService**.

One more point: compare behavior with and without a properly configured transaction manager. If the manager is missing, the application may silently skip opening a transaction or error depending on configuration. **Reliable evidence is the data state after calling the service**, combined with checking topology and transaction manager, not merely seeing the annotation.

## 6. Testing Change Streams with a Synchronous Cursor

### 6.1. Critical Trap: Only Changes After Opening the Stream Are Received

Change streams normally observe changes occurring **after watching starts** (unless resuming from a valid token or start time). If you insert a document first and then call **watch()**, the test may wait forever without receiving the event.

A reliable test must:

1. Create the collection before opening the stream.
2. Open the stream and **initialize the cursor** before writing the document.
3. Write the document with a unique ID distinguishable from events in other tests.
4. Poll until the matching event appears within a finite deadline.
5. Close the cursor with **try-with-resources**.

Example using **MongoTemplate** to obtain the Java Driver collection and call **watch()**:

~~~java
// Place this method in the test class using @DataMongoTest and
// Testcontainers from section 5.4, with MongoTemplate @Autowired.
import static org.junit.jupiter.api.Assertions.*;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.OperationType;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.bson.Document;
import org.junit.jupiter.api.Test;

@Test
void insertAppearsOnChangeStream() {
    String collectionName = "stream_events";
    if (!template.collectionExists(collectionName)) {
        template.createCollection(collectionName);
    }

    MongoCollection<Document> collection =
        template.getCollection(collectionName);
    String eventId = UUID.randomUUID().toString();

    // iterator() opens the server-side cursor before the write operation.
    try (MongoCursor<ChangeStreamDocument<Document>> cursor =
             collection.watch()
                 .maxAwaitTime(200, TimeUnit.MILLISECONDS)
                 .iterator()) {

        collection.insertOne(new Document("_id", eventId)
            .append("eventType", "ORDER_CREATED"));

        ChangeStreamDocument<Document> matched = null;
        long deadline =
            System.nanoTime() + TimeUnit.SECONDS.toNanos(15);

        while (System.nanoTime() < deadline) {
            ChangeStreamDocument<Document> candidate = cursor.tryNext();
            if (candidate == null) {
                continue;
            }
            if (candidate.getOperationType() == OperationType.INSERT
                && candidate.getDocumentKey() != null
                && eventId.equals(
                    candidate.getDocumentKey()
                        .getString("_id")
                        .getValue()
                )) {
                matched = candidate;
                break;
            }
        }

        assertNotNull(matched, "Expected insert change event");
        assertEquals(
            "ORDER_CREATED",
            matched.getFullDocument().getString("eventType")
        );
        assertNotNull(matched.getResumeToken());
    }
}
~~~

This test method **shares the test class, template field, and container** from section 5.4; when placing it into a project, put the imports at the top of the file and the **insertAppearsOnChangeStream()** method inside that class. The expected event structure is:

~~~javascript
{
  operationType: "insert",
  documentKey: { _id: "test-ID" },
  fullDocument: {
    _id: "test-ID",
    eventType: "ORDER_CREATED"
  },
  _id: { /* resume token */ }
}
~~~

This illustrates the field structure; the change event's **_id** is a **BSON resume token**, unlike the **_id** of the modified document. Never hardcode token values or compare raw token byte order across MongoDB versions.

### 6.2. Why Use tryNext and a Deadline?

- **tryNext()** checks whether a new event arrived during the await/getMore batch; it can return **null** when no event is currently available.
- **maxAwaitTime** bounds how long `getMore` commands wait for new events on the cursor.
- A finite deadline prevents the test from hanging indefinitely if an event never arrives.
- Filtering by **documentKey._id** prevents picking up events produced by another test.

Because this is a real integration test, CI may have higher resource latency than local environments. Set timeouts according to real CI conditions rather than making them too tight and flaky. Do not use arbitrary **Thread.sleep()** calls to “hope the stream is ready,” because sleeping does not prove the server has opened the change stream.

### 6.3. Testing Update, Delete, and Resume

When expanding your tests:

- For **UPDATE**, events typically include **updateDescription**, while **fullDocument** may not contain the complete document unless **fullDocument: updateLookup** or a compatible configuration is requested.
- For **DELETE**, the document is already removed, so do not assume **fullDocument** always holds the old data.
- To resume a stream, persist the **resume token** from a processed event and use **resumeAfter/startAfter** appropriately. Tokens depend on the oplog and its retention window; overly old tokens cannot be resumed.
- Tests for DDL changes or stream invalidation must be designed separately; dropping a collection can terminate or alter stream state.

A single insert test suffices to verify that change streams are enabled in the environment. It does not prove every event type, continuity across primary elections, or retry logic in a real change-stream consumer.

## 7. Change Streams with ReactiveMongoTemplate

If the application uses **reactive access**, Spring Data MongoDB can provide a **Flux** of **ChangeStreamEvent** instead of a synchronous cursor. The API is used like this:

~~~java
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.ChangeStreamOptions;
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import reactor.core.publisher.Flux;

Flux<ChangeStreamEvent<OrderDocument>> updates =
    reactiveMongoTemplate.changeStream(
        "orders",
        ChangeStreamOptions.empty(),
        OrderDocument.class
    );
~~~

This example assumes an existing **reactiveMongoTemplate** and an application-defined **OrderDocument** entity. Your Spring Data version may offer additional builder options on **ChangeStreamOptions**, such as filter conditions or resume tokens.

The difference when testing reactive code is that a **Flux usually starts watching only when subscribed to**. Merely declaring the **updates** variable and calling save is not enough. Writing:

~~~java
reactiveMongoTemplate.save(order).block();
StepVerifier.create(updates.take(1)).expectNextCount(1).verifyComplete();
~~~

causes the subscriber to start **after** the change has already happened; the event may be missed.

For reliable tests, use coordination that ensures the stream is established before the write (or use an appropriate resume token / start time). You can:

- Use a synchronous cursor as in section 6 to verify basic topology and semantics.
- In deeper reactive tests, use a signal confirming subscription **and** that the server-side stream is open, or configure resume/start-at matching the test requirement.
- Use **StepVerifier** to assert data, error/completion, and timeouts after proper coordination. Avoid fixed-duration **thenAwait** as a way to prove the stream is ready.

For **reactive transactions**, you need **ReactiveMongoTransactionManager**, and reactive MongoDB operations must participate in the same reactive transaction context. Do not assume the blocking **MongoTransactionManager** manages transactions for `ReactiveMongoTemplate`. When testing reactive commit/rollback, subscribe to the pipeline and check database state afterward.

## 8. Combining Transactions and Change Streams in One Test

A practical scenario is ensuring a consumer processes **events only from committed transactions**. For instance, a system writes both a ledger entry and an outbox event inside one transaction:

~~~mermaid
sequenceDiagram
    participant Test as JUnit Test
    participant Watch as Change stream
    participant S as Spring service
    participant Mongo as MongoDB replica set
    Test->>Watch: Open stream on outbox
    Test->>S: Call transactional operation
    S->>Mongo: Write ledger + outbox in transaction
    alt Commit succeeds
        S->>Mongo: commit
        Mongo-->>Watch: Emit outbox event
        Watch-->>Test: Receive event, verify payload
    else Rollback
        S->>Mongo: abort
        Note over Watch,Mongo: No committed outbox event emitted
    end
~~~

For the commit case, the test should verify both sides: **the business documents are written** and **the corresponding event appears on the change stream**. For rollback, confirm the documents do not exist and no corresponding event was committed. Avoid using a brief wait to prove an event **never** arrives; negative tests need a finite deadline, exact ID filtering, and clear criteria.

The **outbox pattern** typically requires idempotent consumer handling because event delivery or consumer restarts can deliver an event more than once at the application layer. Integration tests for transactions and change streams do not replace tests for idempotency, checkpointing, and resume tokens.

## 9. Common Errors in Test Environments

| Symptom | Possible cause | Check / resolution |
| --- | --- | --- |
| Transaction fails with **Transaction numbers are only allowed on a replica set member or mongos** | Connected to standalone or wrong endpoint | Inspect **rs.status()**, URI, and running container |
| **$changeStream is only supported on replica sets** | Server is not running as a replica set | Use a compatible replica set or sharded cluster |
| **Server selection timeout**, no PRIMARY found | Replica set uninitiated, election in progress, advertised host unreachable | Inspect **db.hello()**, **rs.status()**, hostname, and replica set URI |
| **@Transactional** runs but data does not roll back | Missing manager, proxy bypassed, self-invocation inside same class, or writes outside session | Inspect transaction config, service injection, and beans using MongoClient |
| Transaction fails on collection/index creation | Implicit collection/index creation inside transaction, or unsupported topology/permissions | Create collections and indexes before transactions in setup |
| Change stream test never receives events | Stream opened after insert, missing subscription, wrong namespace or filter | Open cursor before write; verify collection/ID and timeout |
| Test receives wrong event | Parallel tests sharing collection without filtering by document ID | Use unique collection/ID; filter events precisely |
| UPDATE event lacks fullDocument | Lookup not requested or event semantics differ from insert | Use **fullDocument: updateLookup** when appropriate |
| Resume fails after a long time | Oplog evicted needed history; token is no longer valid | Size oplog retention appropriately or design a resync path |
| Passes locally, fails in CI | Docker unavailable, low resources, short timeout, differing container permissions | Check Docker service, resources, MongoDB logs, and primary readiness timing |

### Useful Commands for Checking Topology

When you have `mongosh` access to the test environment:

~~~javascript
// Replica set member status:
rs.status();

// Server topology and role information:
db.hello();

// Current replica set configuration:
rs.conf();
~~~

In a single-node replica set, verify the node has become **PRIMARY**. Never assume an open TCP port alone means MongoDB is ready for transactions or change streams.

## 10. Structuring Tests for Trustworthy Results

### 10.1. Separate Unit Tests and Integration Tests

Not every test of a service using Spring Data MongoDB needs a container. Pricing rules, validation, and state transitions can be tested with JUnit/Mockito without a database. However, **transactions and change streams are MongoDB server behaviors**, requiring real integration tests to prove.

### 10.2. Avoid Data Interference

Use unique IDs per test, separate collections when needed, or clean data before/after each test. In change stream tests, cleanup can also emit **delete** events; filter by ID and control test ordering. Never share a collection across parallel tests that assume no concurrent operations.

### 10.3. Do Not Confuse Test Framework Rollback with Business Rollback

Spring test libraries can automatically wrap tests in transactions given the right annotations/config. That complicates observing state after a **service commit**. When proving a service's `@Transactional` works, let the service manage its own transaction and read the result after the call completes.

### 10.4. Functional Tests and Fault-Tolerance Tests Have Different Goals

A single-node replica set works well for testing transaction behavior and basic change stream listening. To test **failover** or **resuming after a new primary election**, use a multi-node replica set, realistic network topology, and controlled primary step-downs. Do not infer high availability solely from passing single-node tests.

### 10.5. Never Hold Cursors Open Indefinitely

Change streams are designed to listen long-term; tests must finish. Use **try-with-resources** for synchronous cursors or manage **Disposable/subscription** for reactive streams. Set clear deadlines and helpful error messages on timeout so CI pipelines do not hang.

### 10.6. Measure the Right Target

| Objective | Recommended assertion | Insufficient assertion |
| --- | --- | --- |
| Transaction commit | Both documents visible after service returns | Only checking service threw no exception |
| Transaction rollback | Zero documents from failed batch remain | Only checking an exception was thrown |
| Change stream insert | Received INSERT event with matching documentKey and payload | Only checking cursor was created |
| Resume stream | Consumer restarts, continues from valid token, misses no expected events | Only checking token is non-null |
| Failover | Client operates/recovers as required after primary change | Only checking a replica set exists |

## 11. Test Implementation Checklist

1. **Classify the test:** pure business logic, repository CRUD, transactions, change streams, or failover.
2. **Choose matching topology:** standalone where truly sufficient, single-node replica set for transactions/change streams, multi-node when measuring failover.
3. **Pin compatible versions:** MongoDB server, Spring Boot/Spring Data, MongoDB Java Driver, and Testcontainers must align.
4. **Provision MongoDB automatically:** use Testcontainers or reproducible test provisioning and verify the node is PRIMARY.
5. **Supply the exact URI:** wire the replica set URI into the application's actual `MongoClient`; never hardcode host ports.
6. **Prepare collections/indexes:** run required DDL operations before transactions start.
7. **Test transactions through the proxy:** invoke the Spring-managed service and verify commit and rollback via real documents.
8. **Open change streams before writing:** filter by ID, enforce a deadline, and close cursors/subscriptions on exit.
9. **Run in CI:** verify Docker/network, resources, and timeouts; retain helpful logs on failure.
10. **Expand by risk:** add tests for concurrent updates, resume tokens, consumer restarts, reactive transactions, or multi-node setups when required by the system.

### Self-Check Questions

**1. Can a single-node replica set test transactions?** Yes, when supported by the server/driver version and the node has become PRIMARY. It does not prove failover or multi-node fault tolerance.

**2. Can standalone MongoDB test standard change streams?** No for MongoDB's standard change stream mechanism; a compatible replica set or sharded cluster is required.

**3. Why must a rollback test read data after the service throws an error?** An exception can occur even if the transaction never opened properly. Inspecting the database proves writes before the error rolled back.

**4. Why does calling `watch` after an insert usually miss the event just written?** Change streams observe from the moment watching starts. To read earlier events, you must use a resume token or supported start timestamp.

**5. Is `MongoTransactionManager` required when using Spring `@Transactional` with synchronous MongoDB?** Yes, an appropriate transaction manager is required for Spring to manage MongoDB transactions; the annotation alone does not execute transactions.

**6. Does a reactive consumer that created a `Flux` without subscribing receive change events?** Usually no. You must start the subscription and ensure the stream is active before performing the observed write.

**7. Does a Testcontainers single-node replica set suffice for testing majority writes and primary failover?** No. Evaluating primary changes, quorum, and replication lag requires testing a multi-member topology.

## Conclusion

In **Spring Data MongoDB**, testing **transactions** and **change streams** requires a MongoDB deployment with a compatible topology. A **single-node replica set with Testcontainers** is an effective starting point for reproducible integration tests: Spring receives the exact URI, the transaction manager manages sessions, tests verify **commit/rollback** via document state, and change stream tests verify **events occurring after the stream opens**. When requirements include failover, multiple shards, long-running resume, or complex reactive handling, expand both the topology model and test cases to match the operational behavior you need to prove.
