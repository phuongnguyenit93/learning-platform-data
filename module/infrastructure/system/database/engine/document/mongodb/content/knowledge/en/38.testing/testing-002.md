# Provisioning MongoDB with Testcontainers Using Feature-Appropriate Topologies

## 1. Why Is One MongoDB Container Not Enough for Every Test?

A Java project has four groups of tests:

- Tests for `insertOne()`, `find()`, indexes, and aggregation.
- Tests for transferring funds between two accounts using a **multi-document transaction**.
- Tests for **change streams** to emit events when new documents arrive.
- Tests for whether the application finds a **new primary** when the old primary stops, and whether it can read from a **secondary**.

If every test uses a standalone MongoDB instance, transactions and change streams can be rejected. If everything moves to a **single-node replica set**, transactions and change streams can run, yet **there is no secondary to verify read preferences and no other member to elect a primary when the sole node stops**.

The challenge of this lesson is not simply “starting MongoDB with Docker.” The goal is to **choose the simplest topology that satisfies the requirements of the feature under test**, and then configure the Java Driver, Spring Boot, and CI environment accordingly.

### 1.1. Expected Outcomes

After this lesson, you will be able to:

1. Choose between **standalone**, **single-node replica set**, **multi-node replica set**, **sharded cluster**, and **MongoDB Atlas Local** based on the feature to test.
2. Use Testcontainers Java, JUnit 5, and the Java Sync Driver to run isolated MongoDB instances in integration tests.
3. Declare **Testcontainers 2.x** dependencies correctly and recognize differences from older 1.x examples.
4. Use `MongoDBContainer.withReplicaSet()` and `getReplicaSetUrl()` for transaction and change stream tests.
5. Connect Spring Boot via `@DynamicPropertySource` or `@ServiceConnection` without hardcoding Docker mapped ports.
6. Understand multi-node replica set configuration, internal hostnames, seed lists, and Docker networking.
7. Organize test data, state resets, container lifecycles, parallel tests, and cleanup to avoid flaky tests.
8. Design feature tests: transaction rollback, change stream resume, read preference, elections, retryable writes, sharding, and search.
9. Standardize Docker/CI, version pinning, diagnostics, timeouts, and production-simulation boundaries.

### 1.2. Example Scope

Examples use **Java 17+**, **JUnit Jupiter**, and **MongoDB Java Sync Driver**. Dependencies are illustrated with **Testcontainers Java 2.0.x** and MongoDB image 7.0.x. In a real project, pin specific versions verified to be compatible.

**Important:** Testcontainers 2.0 moved the MongoDB module to Maven coordinates `org.testcontainers:testcontainers-mongodb` and class `org.testcontainers.mongodb.MongoDBContainer`. Many 1.x articles still use `org.testcontainers:mongodb` and `org.testcontainers.containers.MongoDBContainer`. Do not mix the two when copying code.

## 2. What Does Testcontainers Do, and What Does It Not Do?

Testcontainers is a Java library that controls a Docker-compatible container runtime to provide dependent services for tests.

```text
JUnit 5 / Spring Boot Test
          |
          v
    Testcontainers Java
          |
          +-- create isolated container
          +-- start / inspect / wait
          +-- expose dynamically mapped ports
          +-- report host + connection URI
          +-- capture logs / stop / clean up
          |
          v
     MongoDB container(s)
          |
          v
       Java MongoClient
          |
          v
     Assertions / teardown
```

### 2.1. Strengths

- No need to install MongoDB directly on a developer's machine.
- The exact same MongoDB image is chosen locally and in CI.
- Tests provision the infrastructure they need rather than relying on a shared database.
- Host ports are allocated dynamically, reducing collisions across concurrent test suites.
- Simulates most behaviors of a **real MongoDB server** instead of merely mocking repositories.
- Easy control over versions, startup, cleanup, and integration into the test lifecycle.

### 2.2. Limitations

- Testcontainers **does not automatically choose the right topology** for your business requirements.
- A standard `MongoDBContainer` **does not automatically provide three voting members or a sharded cluster**.
- A single-node replica set cannot test majority propagation, elections, or reads from a real secondary.
- Local containers do not fully simulate multi-region latency, IAM, private endpoints, or all Atlas-managed features.
- Requires a working container runtime with sufficient CPU/RAM/disk locally and in CI.

### 2.3. This Is Integration Testing, Not a Replacement for Unit Tests

Unit tests for domain logic may need no Docker at all. Testcontainers is valuable when you need to confirm:

- Driver BSON encoding/decoding.
- Query filters, aggregations, indexes, and unique constraints.
- Transaction semantics.
- Database validation, error codes, and real server behavior.
- Change streams and replica set configuration.
- Spring Data MongoDB interaction with a real MongoDB server.

Do not spin up a MongoDB container just to test a `calculateTotal()` function that never touches the database.

## 3. Topology Matrix by Feature

| What to test | Standalone | Single-node replica set | Multi-node replica set | Sharded cluster | Atlas Local |
|---|---|---|---|---|---|
| Basic CRUD, filters, aggregation | Yes | Yes | Yes | Yes | Yes, within supported scope |
| Unique/TTL indexes / schema validation | Yes | Yes | Yes | Yes, with sharding constraints | Yes |
| Multi-document transactions | No on standalone | **Yes** | **Yes** | Yes, with sharded transactions | Depends on local deployment/features |
| Change streams | No on standalone | **Yes** | **Yes** | Yes | Per image support |
| Retryable writes under replica-set protocol | Insufficient RS conditions | Yes | Yes | Yes | Per topology |
| Secondary read preference with data | No | **No** | **Yes** | Yes with appropriate shard replicas | Does not replace multi-member automatically |
| Real failover and election | No | **No** | **Yes** | Yes on appropriate shard/config RS | Not by default |
| Replication lag across nodes | No | No secondary | Yes | Yes | Not by default |
| Majority acknowledgment across multiple nodes | No | Majority is only one member | **Yes** | Yes per replica sets | Depends on topology |
| Shard key, targeted/scatter queries | No | No | Not enough | **Yes** | Does not replace sharded cluster |
| `mongos` routing/balancer | No | No | No | **Yes** | No |
| Local Atlas Search/Vector Search | Not by default | Not by default | Not by default | Not built-in | **Primary purpose** |
| Internal X.509/TLS/member auth | Must be configured | Must be configured | Must be configured | Must be configured | Depends on mode |

**How to read the table:** “Yes” means the topology provides the necessary foundation to design a test, not that any arbitrary test automatically covers all cases. A single-node replica set still needs an appropriate wire version, MongoDB version, and driver for the feature under test.

### 3.1. Quick Selection Rules

```text
Testing only CRUD/indexes/aggregation?
  -> Standalone or default MongoDBContainer.

Testing transactions/change streams?
  -> Single-node replica set is the starting choice.

Testing secondary reads, voting, failover, replication lag?
  -> Replica set with multiple data-bearing members.

Testing shard keys, mongos routing, distributed transactions?
  -> Sharded cluster with config server + mongos + shards.

Testing local Atlas Search / Vector Search integration?
  -> MongoDBAtlasLocalContainer (matching version and supported scope).
```

### 3.2. Pick the Fewest Nodes **Sufficient to Prove What You Are Testing**

You do not need a 9-container cluster for a filter test. Conversely, if the requirement is “the application keeps writing after the primary dies,” a single-node replica set **is meaningless as a failover test**, even though transactions run on it.

## 4. Preparing the Java, Docker, and JUnit Environment

### 4.1. Required Components

- A JDK compatible with the Testcontainers, driver, and Spring Boot versions in use.
- Maven or Gradle.
- A container runtime supported by Testcontainers that can pull MongoDB images.
- JUnit Jupiter.
- Java MongoDB Sync Driver or Spring Data MongoDB starter.
- CI with a Docker-compatible runtime and appropriate image pull/network policies.

### 4.2. Checking the Local Container Runtime

Example from a developer terminal:

```bash
docker version
docker info
docker pull mongo:7.0
```

These are **setup reference commands**, not commands required while writing documentation. Docker Desktop is not mandatory if another runtime supported by Testcontainers is available.

### 4.3. Never Use a Production Database

Testcontainers must connect to a **container started by the test**, never pulling a URI from `MONGODB_PROD_URI` or a production environment secret. A misconfigured URI pointing to the wrong environment can cause the test suite to destroy real data.

### 4.4. Check Versions Before Copying Code

With Testcontainers **1.x**, older examples typically use:

```java
import org.testcontainers.containers.MongoDBContainer;
```

With Testcontainers **2.x**:

```java
import org.testcontainers.mongodb.MongoDBContainer;
```

Do not attempt to compile 2.x samples against 1.x JARs or vice versa.

## 5. Gradle Dependencies: Testcontainers 2.x

Example `build.gradle` for a standard Java application:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.mongodb:mongodb-driver-sync:5.6.0'

    testImplementation platform(
        'org.testcontainers:testcontainers-bom:2.0.5'
    )
    testImplementation 'org.testcontainers:testcontainers-mongodb'
    testImplementation 'org.testcontainers:testcontainers-junit-jupiter'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.13.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**The versions above are illustrative milestones** for declaring coordinates/BOMs; align them with the Spring Boot BOM and the actual chosen versions. In practice, you can let Spring Boot dependency management govern Testcontainers/JUnit/driver versions and override only with clear justification.

### 5.1. Why Use a BOM?

`testcontainers-bom` keeps modules such as MongoDB, JUnit Jupiter, and core on compatible versions, avoiding:

```text
testcontainers-mongodb 2.0.x
testcontainers-junit-jupiter 1.20.x
mismatched transitive core
```

Mixing versions like this easily causes classpath errors.

### 5.2. The Driver Is a Separate Dependency

`testcontainers-mongodb` manages the container; **it does not automatically add the MongoDB Java Driver to your application**. With the Spring Boot Data MongoDB starter, the driver is usually pulled in transitively; plain Java needs `mongodb-driver-sync` explicitly.

### 5.3. Distinguish Dependency Scopes

Testcontainers dependencies belong in `testImplementation`; do not package Testcontainers core or Docker control libraries into production runtime artifacts just for the application to connect to a database.

## 6. Corresponding Maven Dependencies

```xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>testcontainers-bom</artifactId>
      <version>2.0.5</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-mongodb</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-junit-jupiter</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.mongodb</groupId>
    <artifactId>mongodb-driver-sync</artifactId>
    <version>5.6.0</version>
  </dependency>
</dependencies>
```

This is a **dependency fragment**, not a complete `pom.xml`. A project still needs appropriate JUnit/JDK/test plugin configuration; versions may be managed by another BOM.

## 7. JUnit 5 and `@Testcontainers` / `@Container`

A sample test class using Jupiter's lifecycle:

```java
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.mongodb.MongoDBContainer;
import org.testcontainers.utility.DockerImageName;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
class MongoStarts412Test {

    @Container
    static MongoDBContainer mongo =
        new MongoDBContainer(DockerImageName.parse("mongo:7.0"))
            .withReplicaSet();

    @Test
    void mongoIsRunning() {
        assertTrue(mongo.isRunning());
    }
}
```

### 7.1. Static Container

`static @Container` is typically started **once per test class** and stopped after the class's test methods finish. Suitable when tests share a database with clear data isolation rules.

### 7.2. Instance Container

An instance-field `@Container` is managed per test method. This improves isolation at the cost of higher startup overhead.

### 7.3. Testcontainers JUnit 5 Extension and Parallelism

Testcontainers documentation notes that the JUnit Jupiter extension is primarily tested with **sequential test execution**; parallel tests require an explicit sharing/ownership design rather than assuming container fields and mutable data are thread-safe.

### 7.4. Testing “Is Running” Is Not Enough

`mongo.isRunning()` only proves Docker container state; **it does not confirm the feature under test**. Useful tests must call MongoDB and assert query results, transactions, or change stream behavior.

## 8. Standalone MongoDB: When to Use `GenericContainer`?

If you want to verify **true standalone** behavior, do not assume `MongoDBContainer` creates a standalone instance; the MongoDB module has version-dependent replica set logic.

Generic container example:

```java
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.utility.DockerImageName;

GenericContainer<?> standalone =
    new GenericContainer<>(DockerImageName.parse("mongo:7.0"))
        .withExposedPorts(27017)
        .withCommand("mongod", "--bind_ip_all");

standalone.start();

String uri = String.format(
    "mongodb://%s:%d/?directConnection=true",
    standalone.getHost(),
    standalone.getMappedPort(27017)
);
```

### 8.1. What Does Standalone Help Test?

- CRUD, BSON codecs, filters, projections.
- Basic aggregation, update operators.
- Unique indexes, TTL mechanics, collation.
- Schema validation.
- Server exception handling.

### 8.2. Standalone Is Insufficient for Multi-Document Transactions

A real transaction command on standalone can be rejected because multi-document transactions require a supported deployment (replica set/sharded cluster).

### 8.3. URIs Must Use Mapped Ports

Do not write:

```text
mongodb://localhost:27017
```

unless you **intentionally** publish a fixed port. Testcontainers normally assigns a dynamic host port, so use `getHost()` and `getMappedPort(27017)`.

### 8.4. Do Not Use Standalone to Represent a Production Replica Set

If production uses majority write concern, session transactions, or change streams, testing exclusively on standalone can miss critical bugs.

## 9. Single-Node Replica Set: Sufficient Topology for Transactions

Diagram:

```text
JUnit 5 / Java Driver
        |
        v
Testcontainers mapped endpoint
        |
        v
MongoDBContainer
  mongod --replSet ...
  rs.initiate()
  single member becomes PRIMARY
        |
        v
    local.oplog.rs
```

### 9.1. Supported Features

A single-node replica set enables:

- Multi-document transactions in a supported deployment.
- Change streams and oplog-based behavior.
- Sessions and the retryable write protocol.
- Certain write/read concern semantics.
- Testing multiple commands in one transaction against real MongoDB.

### 9.2. What Is **Not** Simulated

- No secondary to read from.
- No replication lag between primary and secondary.
- No election to another node when the primary dies.
- Majority consists of **only one member**; it does not prove durability across multiple replicas.
- Cannot test responses to network partitions between voting members.

### 9.3. Connecting Properly

`MongoDBContainer.withReplicaSet()` initializes replica set mode via the Testcontainers 2.x API. After the container starts, retrieve the URI with `getReplicaSetUrl()`.

**Do not manually append `replicaSet=rs0` or rewrite the hostname/port in the URI when the helper already provides one.** The replica set name and advertised address handling are managed by the module.

## 10. Complete Java Integration Test: Reading/Writing on a Single-Node Replica Set

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.mongodb.MongoDBContainer;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
class ProductRepository412IT {

    @Container
    static MongoDBContainer mongo =
        new MongoDBContainer(DockerImageName.parse("mongo:7.0"))
            .withReplicaSet();

    static MongoClient client;
    static MongoCollection<Document> products;

    @BeforeAll
    static void setup() {
        client = MongoClients.create(mongo.getReplicaSetUrl());
        products = client.getDatabase("it_products_412")
            .getCollection("products");
    }

    @AfterAll
    static void cleanup() {
        if (client != null) {
            client.close();
        }
    }

    @Test
    void shouldInsertAndFindProduct() {
        products.insertOne(
            new Document("_id", "P412-1")
                .append("name", "Demo keyboard")
                .append("price", 350000));

        Document found = products.find(
            new Document("_id", "P412-1")).first();

        assertNotNull(found);
        assertEquals("Demo keyboard", found.getString("name"));
        assertEquals(350000, found.getInteger("price"));
    }
}
```

### 10.1. Notable Points

1. `@Container static` manages the lifecycle for the test class.
2. `withReplicaSet()` selects the appropriate topology.
3. `getReplicaSetUrl()` provides the endpoint and dynamic port after startup.
4. Database name `it_products_412` isolates the test namespace.
5. `MongoClient` is closed after the test class finishes.

### 10.2. Avoid Shared Test Data Without Cleanup

This test assumes a fresh container for the class. If reusable containers are enabled or a long-lived singleton is shared across classes, `_id = "P412-1"` can collide on subsequent runs. When sharing containers, use an alternative data isolation strategy.

### 10.3. Test the API Rather Than Only Container Status

Assertions verify that documents are actually written/read and that the Java Driver operates against real MongoDB.

## 11. Testing Transactions: Success and Rollback

### 11.1. Why Do Transactions Require a Replica Set?

MongoDB supports multi-document transactions on appropriate replica set/sharded topologies; standalone does not execute this transaction type.

A single-node replica set is the lightest choice to confirm **atomic commit/abort across multiple documents**. It does not simulate network failures or multi-node majority behavior.

### 11.2. Java Intentional Rollback Test

```java
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

@Test
void shouldAbortTwoDocumentTransaction() {
    MongoCollection<Document> accounts = client
        .getDatabase("it_accounts_412")
        .getCollection("accounts");

    accounts.insertMany(java.util.List.of(
        new Document("_id", "A").append("balance", 100),
        new Document("_id", "B").append("balance", 50)
    ));

    try (ClientSession session = client.startSession()) {
        session.startTransaction();

        accounts.updateOne(
            session,
            new Document("_id", "A"),
            new Document("$inc", new Document("balance", -20)));

        accounts.updateOne(
            session,
            new Document("_id", "B"),
            new Document("$inc", new Document("balance", 20)));

        // Intentionally abort to verify atomic rollback.
        session.abortTransaction();
    }

    assertEquals(100, accounts.find(
        new Document("_id", "A")).first().getInteger("balance"));

    assertEquals(50, accounts.find(
        new Document("_id", "B")).first().getInteger("balance"));
}
```

**Note:** The test method above assumes it resides inside a test class where `client` was initialized as in section 10; the `it_accounts_412` namespace must be fresh or seeded/cleaned up with control.

### 11.3. Commit Test

Another test should call `session.commitTransaction()` and assert that both balances updated, the total sum is conserved, and no partial state remains.

### 11.4. Do Not Infer Failover Safety from a Rollback Test

To test `UnknownTransactionCommitResult`/`TransientTransactionError` during an election, you need a **multi-node topology** or another sufficiently realistic fault-injection strategy; losing the sole node in a single-node setup cannot elect a new primary.

## 12. Testing Change Streams: Event Sources Need an Oplog

Change streams rely on the oplog of a replica set or sharded cluster to track changes. Tests on standalone will lack the required conditions.

### 12.1. Test Flow

```text
Create single-node replica set
      |
      v
Open change stream on collection
      |
      v
Insert document into collection
      |
      v
Read event from stream
      |
      v
Assert operationType=INSERT and document key
```

### 12.2. Java Sync Driver Example

```java
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.OperationType;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import java.util.concurrent.TimeUnit;
import static org.junit.jupiter.api.Assertions.*;

@Test
void shouldReceiveInsertChangeEvent() {
    MongoCollection<Document> events = client
        .getDatabase("it_changes_412")
        .getCollection("events");

    try (MongoChangeStreamCursor<ChangeStreamDocument<Document>> cursor =
             events.watch()
                 .maxAwaitTime(1, TimeUnit.SECONDS)
                 .cursor()) {

        events.insertOne(
            new Document("_id", "E412-1").append("kind", "CREATED"));

        ChangeStreamDocument<Document> change = null;
        long deadline = System.nanoTime()
            + TimeUnit.SECONDS.toNanos(10);

        while (System.nanoTime() < deadline && change == null) {
            change = cursor.tryNext();
        }

        assertNotNull(change, "No change stream event received");
        assertEquals(OperationType.INSERT, change.getOperationType());
        assertNotNull(change.getDocumentKey());
    }
}
```

### 12.3. Avoid the “Opening Watcher Too Late” Race

In the driver, `watch().cursor()` runs the subscription/aggregation, yet opening the stream and writing must be ordered **carefully**. If a test opens the stream after the insert without an appropriate `resumeAfter/startAtOperationTime`, the event may fall outside the observed window.

### 12.4. Bounded Timeouts

Never call `cursor.next()` to wait indefinitely in a test. `tryNext()` with `maxAwaitTime` and a deadline ensures the test terminates cleanly if no event arrives.

### 12.5. One Event Does Not Prove Failover Resume

Verifying resume tokens, reconnects, oplog windows, and duplicate event handling requires dedicated tests; single-node setups remain useful for basic consumer logic.

## 13. Spring Boot Integration Tests with `@DynamicPropertySource`

### 13.1. Why Is a Dynamic URI Needed?

Host ports change every time Testcontainers starts a container. Hardcoding `spring.data.mongodb.uri=mongodb://localhost:27017` is incorrect.

Spring Framework provides `@DynamicPropertySource` to register properties from the container **once the endpoint is allocated**.

### 13.2. Spring Data MongoDB Example

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.mongodb.MongoDBContainer;
import org.testcontainers.utility.DockerImageName;

import org.bson.Document;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@Testcontainers
class SpringMongo412IT {

    @Container
    static MongoDBContainer mongo =
        new MongoDBContainer(DockerImageName.parse("mongo:7.0"))
            .withReplicaSet();

    @DynamicPropertySource
    static void mongoProps(DynamicPropertyRegistry registry) {
        registry.add("spring.data.mongodb.uri", mongo::getReplicaSetUrl);
        registry.add("spring.data.mongodb.database",
            () -> "spring_it_412");
    }

    @Autowired
    MongoTemplate mongoTemplate;

    @Test
    void shouldQueryWithSpringMongoTemplate() {
        Document value = new Document("_id", "SP412")
            .append("status", "READY");
        mongoTemplate.insert(value, "snapshots");

        Document result = mongoTemplate.findById(
            "SP412", Document.class, "snapshots");

        assertNotNull(result);
        assertEquals("READY", result.getString("status"));
    }
}
```

### 13.3. What to Verify

- Test includes the `spring-boot-starter-data-mongodb` dependency.
- Spring Boot version consumes `spring.data.mongodb.uri` via the expected mechanism.
- The container is running before Spring initializes the real client.
- No other property or bean accidentally overrides the connection.
- Test properties contain no production credentials.

### 13.4. Spring Context Caching and Container Lifecycle

Spring can cache the application context across test classes. If a cached context holds a MongoClient pointing to a previous class's stopped container, the next test class can receive a **stale connection string**.

Solutions: use a singleton container whose lifecycle is managed across classes, bound context reuse, or explicitly configure appropriate test context isolation. Do not enable `@DirtiesContext` on every test needlessly, as context startup cost is high.

## 14. Spring Boot `@ServiceConnection`

With Spring Boot supporting **Testcontainers service connections** (Spring Boot 3.1+ with appropriate setup), you can write:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.mongodb.MongoDBContainer;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class SpringMongoServiceConnection412IT {

    @Container
    @ServiceConnection
    static MongoDBContainer mongo =
        new MongoDBContainer(DockerImageName.parse("mongo:7.0"))
            .withReplicaSet();

    @Test
    void contextStarts() {
        // Spring MongoDB auto-configuration uses connection details
        // derived from the running MongoDB Testcontainer.
    }
}
```

### 14.1. Additional Dependency

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
}
```

Spring Boot derives the appropriate `MongoConnectionDetails` from `MongoDBContainer`. When a service connection is active, connection details **may take precedence over properties**; understand how the framework interacts with custom MongoClient beans.

### 14.2. `@ServiceConnection` or `@DynamicPropertySource`?

| Option | Advantage | When to consider |
|---|---|---|
| `@DynamicPropertySource` | Explicit per property, flexible | Need custom database/URI settings |
| `@ServiceConnection` | Less boilerplate, Boot-integrated | Auto-configuration fits the project |
| Custom `MongoClient` test bean | Direct control over settings | Specialized driver/test setup |

Do not simultaneously declare all three mechanisms and lose track of which bean or URI is actually used.

### 14.3. Tests Need More Than contextLoads

`contextStarts()` is a configuration smoke test; add assertions that actually exercise repositories, transactions, or streams to prove the feature works.

## 15. Inspecting Topology Before Running Feature Tests

Never rely blindly on the class name `MongoDBContainer`. Use a MongoDB command to confirm:

```java
import org.bson.Document;

Document hello = client.getDatabase("admin")
    .runCommand(new Document("hello", 1));

System.out.println("hello.setName=" + hello.getString("setName"));
System.out.println("hello.isWritablePrimary=" +
    hello.getBoolean("isWritablePrimary"));
```

### 15.1. Replica Set Assertions

```java
assertNotNull(hello.getString("setName"));
assertEquals(Boolean.TRUE,
    hello.getBoolean("isWritablePrimary"));
```

`setName` is present when the server belongs to a replica set. `isWritablePrimary` reports the role in the hello response; during an election window it may not yet be true, so wait for proper readiness instead of a fixed `Thread.sleep`.

### 15.2. `replSetGetStatus`

When authorized:

```java
Document status = client.getDatabase("admin")
    .runCommand(new Document("replSetGetStatus", 1));
```

A single-node replica set expects one member in `members` with role primary after initialization.

### 15.3. What Should Not Be Asserted?

Do not assert a container's **mapped port** against a hardcoded literal. Do not assert that an election completes within exactly 3 seconds across every CI host. Do not parse unstable mongosh text output as a protocol when the MongoDB driver provides structured JSON/BSON fields.

## 16. Readiness: More Than Waiting for Port 27017 to Open

```text
Container started
    |
    v
Port 27017 listening
    |
    v
MongoDB process ready for commands
    |
    v
Replica set initiated
    |
    v
PRIMARY elected
    |
    v
Transactions/change streams can run
```

### 16.1. An Open Socket Does Not Mean Features Are Ready

`Wait.forListeningPort()` only proves the TCP port accepts connections; **it does not prove `rs.initiate()` has finished**.

### 16.2. Use the Module Helper

`MongoDBContainer.withReplicaSet()` handles setup according to Testcontainers' implementation. Do not arbitrarily override `withCommand()`, startup scripts, or wait strategies without understanding its internal initialization logic.

### 16.3. For Hand-Built Topologies

You must:

1. Start the `mongod` processes.
2. Call `rs.initiate()` once on an appropriate member.
3. Wait for primary election.
4. Wait for secondaries to be recognized and reach the proper state.
5. Connect the driver via a URI that **the client can actually resolve**.

Do not use `Thread.sleep(5000)` and assume every CI node is fast enough.

## 17. Test Data: Seeding, Isolation, and Teardown

### 17.1. Tests Must Be Independent and Repeatable

A test doing:

```java
products.insertOne(new Document("_id", "P1"));
```

can fail with `E11000 duplicate key` if another test left `P1` in the database.

### 17.2. Strategies

| Strategy | Advantage | Risk |
|---|---|---|
| Fresh container per class | Strong isolation | Slower startup |
| Fresh DB per class | Shared container, separate namespace | Needs cleanup and metadata management |
| Fresh collection per test | Easy reset for small datasets | Easy to forget indexes/schemas |
| Unique IDs per test | Fewer collisions | Can still drift from shared state |
| Transaction rollback at end | Clean for certain patterns | Does not cover all operations/side effects |
| Database cleanup after test | Easy to understand | Mid-test/cleanup failures can leave stale state |

### 17.3. Never Drop an Unowned Database

Only call `dropDatabase()` on a test database **created specifically for the test and guaranteed not to contain another suite's data**. Verify ownership before any destructive cleanup.

### 17.4. Seed Before Assertions

Example:

```java
MongoCollection<Document> products =
    client.getDatabase("it_seed_412").getCollection("products");

products.insertMany(java.util.List.of(
    new Document("_id", "P10")
        .append("category", "audio").append("price", 100000),
    new Document("_id", "P20")
        .append("category", "audio").append("price", 200000),
    new Document("_id", "P30")
        .append("category", "books").append("price", 150000)
));
```

Write category filter and price sort tests matching the expected results. Do not reuse these IDs if data is shared across classes without a reset.

### 17.5. Seed via Java Instead of Depending on Shell Versions

MongoDB Docker images can differ in `mongosh` availability and flags. For Java integration tests, seeding with the Java Driver after container readiness is usually easier to control than mounting one-shot JS scripts into `docker-entrypoint-initdb.d`.

## 18. Indexes, Validation, and TTL: Appropriate Topology Without Overkill

### 18.1. Unique Index

```java
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;

orders.createIndex(
    Indexes.ascending("tenantId", "requestId"),
    new IndexOptions().unique(true));
```

Test inserting two orders with the same `tenantId/requestId` and expect MongoDB to return a duplicate key error.

### 18.2. Schema Validation

```javascript
db.createCollection("inventories", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["sku", "available"],
      properties: {
        sku: { bsonType: "string" },
        available: {
          bsonType: ["int", "long"],
          minimum: 0
        }
      }
    }
  }
});
```

Test that documents missing `sku` or having `available < 0` are rejected. A standalone container suffices for this case.

### 18.3. TTL

The TTL monitor runs asynchronously; tests should not assert “document disappears after exactly 100 ms.” Use an appropriate deadline and test TTL semantics separately. **Do not make the whole suite wait on the TTL monitor** when you can unit test expiry policy and run one small integration test for the behavior.

### 18.4. Create Indexes Before the Workload

Seed data and create indexes in the intended order. For unique indexes, seeding duplicates before creating the index will cause the index build to fail, which differs from asserting duplicate inserts after the index exists.

## 19. Testing Aggregation with BSON-Accurate Data

A mocked repository can miss differences such as:

- `Decimal128` vs `double`.
- `ObjectId` vs `String`.
- `Date` and timezones.
- `null` vs missing fields.
- Array operators and multikey semantics.
- Collation and case sensitivity.

### 19.1. Aggregation Example

```javascript
db.sales412.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$productId",
      revenue: {
        $sum: { $multiply: ["$price", "$quantity"] }
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { revenue: -1 } }
]);
```

### 19.2. Test Outputs with Explicit Ordering

An aggregation `$group` stage does not guarantee result order without `$sort`. Do not assert on arbitrary ordering merely because your local machine currently returns a stable order.

### 19.3. Version Feature Gates

If a pipeline uses a stage or operator only available in newer MongoDB releases, select the minimum compatible image version and test the compatibility matrix. **The MongoDB image version is part of the test contract.**

## 20. Separating Transaction Logic Tests from Failover Tests

### 20.1. Two Distinct Objectives

Transaction test:

```text
Given two accounts
When one transaction updates both
Then commit changes both or abort changes none
```

Sufficient topology: **single-node replica set**.

Failover test:

```text
Given A PRIMARY and B/C SECONDARY
When A becomes unavailable
Then B or C is elected PRIMARY
And Java Driver resumes eligible operations
```

Mandatory topology: **multi-node replica set with a valid majority**.

### 20.2. Separating Suites

```text
src/test/java/
  repository/
    CrudIT.java
    TransactionIT.java
    ChangeStreamIT.java

src/failoverTest/java/ (or dedicated source set/tag)
    ElectionIT.java
    SecondaryReadIT.java
    RetryOnFailoverIT.java
```

These paths are project organization examples; a `failoverTest` source set does not exist out of the box unless configured in Gradle/Maven.

### 20.3. Why Not Run Failover Tests on Default Fast CI?

Multi-node startup, network setup, and elections take longer. They can run under a dedicated tag, nightly build, or merge gate while keeping unit/integration tests fast for per-commit feedback.

## 21. Multi-Node Replica Set: Minimal Architecture

Diagram of three data-bearing members:

```text
               Docker network: mongo-it-net

        +----------------+      +----------------+
        | mongo-a        |      | mongo-b        |
        | alias=mongo-a  |      | alias=mongo-b  |
        | mongod         |      | mongod         |
        | --replSet rsIT |      | --replSet rsIT |
        +----------------+      +----------------+
                 \                  /
                  \                /
                   \              /
                  +----------------+
                  | mongo-c        |
                  | alias=mongo-c  |
                  | mongod         |
                  | --replSet rsIT |
                  +----------------+
                           |
                           v
                 Containerized test runner
                 same network:
                 mongodb://mongo-a:27017,
                 mongo-b:27017,
                 mongo-c:27017/?replicaSet=rsIT
```

### 21.1. Why Are Three Members Needed?

With three voters, majority is 2. When primary A drops, B and C can still elect a new primary if eligible and caught up. With one node, stopping the sole node leaves zero members to hold an election.

### 21.2. Why Prefer Data-Bearing Members?

If the goal is testing **secondary reads, replication lag, and failover**, using three data-bearing members provides clearer signals than one primary, one secondary, and one arbiter. An arbiter votes but holds no data or oplog.

### 21.3. Never Claim “Three Containers = Replica Set”

Three independent `mongod` processes are still three standalone processes unless you:

1. Start them with the same replica set name.
2. Ensure internal network connectivity between them.
3. Call `rs.initiate()` or apply a valid configuration.
4. Wait for election/catch-up.

### 21.4. Multi-Node Is More Complex Than the Default Module

Testcontainers' MongoDB module documentation also notes considering dedicated multi-node helpers. Do not create one `MongoDBContainer` and assume it spawns three voting members.

## 22. Docker Networking and MongoDB Advertised Addresses

### 22.1. Two Network Spaces

Inside the Docker network:

```text
mongo-a:27017
mongo-b:27017
mongo-c:27017
```

Docker resolves these **network aliases** between containers on the same network.

On the host running JUnit:

```text
localhost:<randomMappedPortA>
localhost:<randomMappedPortB>
localhost:<randomMappedPortC>
```

The host JVM **does not by default** resolve `mongo-a` as a Docker network hostname.

### 22.2. The MongoDB Driver Also Learns Hosts from `hello`

MongoDB replica set config:

```javascript
{
  _id: "rsIT",
  members: [
    { _id: 0, host: "mongo-a:27017" },
    { _id: 1, host: "mongo-b:27017" },
    { _id: 2, host: "mongo-c:27017" }
  ]
}
```

The driver connects to a seed host and reads the member hostnames advertised by the replica set. If the host JVM cannot resolve `mongo-b`, it can fail topology selection or fail to locate the primary despite open mapped ports.

### 22.3. Why Can `localhost:mappedA,mappedB,mappedC` Fail?

```text
mongodb://localhost:49123,localhost:49124,localhost:49125
  ?replicaSet=rsIT
```

The driver discovers membership `mongo-a/b/c:27017` and attempts to connect to those internal addresses. If the host JVM cannot resolve or reach them, the connection fails.

**The seed list does not rewrite the hostnames advertised by the server.**

### 22.4. Two Valid Strategies

1. **Run the Java test/application runner inside the same Docker network**, using a URI with container aliases/ports.
2. If the JVM must run on the host, design **bidirectional addressing/proxying/host mapping** so the hostnames in the replica set config are reachable by all members **and** the JVM. Test DNS/routing across Linux, macOS, Windows, and CI.

Never pass `directConnection=true` and treat it as a replica set failover test: the driver is pinned to a single node and bypasses the discovery mechanism under test.

## 23. Building Three `mongod` Nodes with `GenericContainer`

This snippet **illustrates infrastructure initialization**. It starts three servers, a Docker network, and initializes the replica set via `mongosh`; the multi-node Java driver test must run on a network able to resolve `mongo-a/b/c`.

```java
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.Network;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.utility.DockerImageName;
import java.time.Duration;

public final class ThreeNodeMongoInfrastructure412
        implements AutoCloseable {

    private final Network network = Network.newNetwork();
    private final DockerImageName image =
        DockerImageName.parse("mongo:7.0");

    public final GenericContainer<?> a = node("mongo-a");
    public final GenericContainer<?> b = node("mongo-b");
    public final GenericContainer<?> c = node("mongo-c");

    private GenericContainer<?> node(String alias) {
        return new GenericContainer<>(image)
            .withNetwork(network)
            .withNetworkAliases(alias)
            .withExposedPorts(27017)
            .withCommand(
                "mongod", "--replSet", "rsIT", "--bind_ip_all")
            .waitingFor(Wait.forListeningPort())
            .withStartupTimeout(Duration.ofMinutes(2));
    }

    public void start() throws Exception {
        a.start();
        b.start();
        c.start();

        String init =
            "rs.initiate({_id:'rsIT',members:[" +
            "{_id:0,host:'mongo-a:27017'}," +
            "{_id:1,host:'mongo-b:27017'}," +
            "{_id:2,host:'mongo-c:27017'}" +
            "]})";

        var result = a.execInContainer(
            "mongosh", "--quiet", "--eval", init);

        if (result.getExitCode() != 0) {
            throw new IllegalStateException(
                "rs.initiate failed: " + result.getStderr());
        }

        // Must wait for election + secondaries ready; see next section.
    }

    @Override
    public void close() {
        c.stop();
        b.stop();
        a.stop();
        network.close();
    }
}
```

### 23.1. Why Use GenericContainer?

`MongoDBContainer` targets simple/single-node MongoDB use cases; creating three instances of it can cause each to initialize its own **independent** replica set per module implementation rather than forming one unified replica set.

For custom multi-member setups, use `GenericContainer` or a vetted multi-node helper to control `--replSet`, `rs.initiate`, and networking.

### 23.2. What This Code Does **Not** Do Yet

- Does not wait for B/C to become `SECONDARY`.
- Does not configure authentication/TLS/internal cluster auth.
- Does not run the Java test runner inside the Docker network.
- Does not handle retries if one node starts slowly.
- Does not provide a readiness gate sufficient for failover assertions.

This is a **building block**, not a complete reusable production-grade test harness.

### 23.3. Do Not Call `rs.initiate()` Multiple Times

Only initialize a replica set when unconfigured. With reusable containers or persistent data volumes, check status before calling again to avoid “already initialized” errors or inconsistent configs.

## 24. Waiting for Primary and Secondaries by Condition, Not `sleep`

### 24.1. Structured `replSetGetStatus` Command

From a shell inside member A:

```javascript
db.getSiblingDB("admin").runCommand({
  replSetGetStatus: 1
});
```

Expected across three members:

```text
one PRIMARY
two SECONDARY
health=1 for all
```

### 24.2. Awaitility Example on the Java Test Harness Side

```java
import static org.awaitility.Awaitility.await;
import java.time.Duration;

await()
    .atMost(Duration.ofMinutes(2))
    .pollInterval(Duration.ofSeconds(1))
    .until(() -> {
        var r = infrastructure.a.execInContainer(
            "mongosh", "--quiet", "--eval",
            "let s=rs.status();" +
            "if (s.members.length!==3 || " +
            "s.members.filter(m=>m.stateStr==='PRIMARY').length!==1 || " +
            "s.members.filter(m=>m.stateStr==='SECONDARY').length!==2 || " +
            "s.members.some(m=>m.health!==1)) quit(2);"
        );
        return r.getExitCode() == 0;
    });
```

### 24.3. Why Are Condition-Based Waits Better?

`Thread.sleep(5000)` may pass on a fast laptop yet fail on a heavily loaded CI runner. With a condition-based wait, tests proceed as soon as ready and fail with clear messages on timeout.

### 24.4. Do Not Apply a “Three Secondaries” Checklist to Other Topologies

A three-node replica set needs **1 primary + 2 secondaries**, not 3 secondaries. If there are arbiters, delayed, or hidden members, readiness conditions must match **expected roles** rather than hardcoding one formula for every cluster.

## 25. Connecting a Runner in the Same Docker Network

One strategy to avoid hostname issues:

```text
+--------------------------------------------+
| Testcontainers Docker network              |
|                                            |
| mongo-a:27017   mongo-b:27017 mongo-c:27017|
|        \            |            /         |
|         \           |           /          |
|          Java test runner container        |
|          can resolve all aliases           |
+--------------------------------------------+
```

The runner can be:

- A container built from the project's Java test code.
- A CI job running **inside the same network** as the MongoDB containers.
- A test helper container to verify connectivity/driver behavior with proper runtime setup.

URI used by the runner:

```text
mongodb://mongo-a:27017,mongo-b:27017,mongo-c:27017/
  ?replicaSet=rsIT&retryWrites=true
```

Write the real URI on **one line**; the line break above is for readability only.

### 25.1. Checking Aliases with mongosh from a Sidecar

A helper container with `mongosh` on the same network can run:

```bash
mongosh "mongodb://mongo-a:27017,mongo-b:27017,mongo-c:27017/?replicaSet=rsIT" --quiet --eval "db.hello().isWritablePrimary"
```

Do not treat `mongosh` succeeding inside a sidecar as proof that the JVM **on the host** can also resolve the aliases; they live in different network namespaces.

### 25.2. If JUnit Must Run on the Host

You can build a test harness using reverse proxies, port forwarding, or host mappings so **all advertised hostnames** are reachable from both the host and member-to-member networks. That is an advanced option requiring explicit resolution handling on Docker Desktop, Linux, and CI—not merely creating mapped ports.

### 25.3. Failover Tests Must Use Discovery

The driver connection URI must specify the right replica set name and multiple reachable members. `directConnection=true` invalidates tests of automatic primary discovery.

## 26. Testing Secondary Read Preference

### 26.1. Requires at Least One Data-Bearing Secondary

On a single-node replica set there is only a primary; a `find` using `ReadPreference.secondary()` cannot locate a secondary.

### 26.2. Java Test on a Multi-Node Topology

```java
import com.mongodb.ReadPreference;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

MongoCollection<Document> secondaryCollection =
    client.getDatabase("rs_read_it_412")
        .getCollection("products")
        .withReadPreference(ReadPreference.secondary());

Document value = secondaryCollection
    .find(new Document("_id", "P412")).first();
```

Here `client` must connect to a **multi-node replica set with a reachable secondary**, not the singleton `MongoClient` from the single-node example.

### 26.3. Read Concern and Replication

`secondary()` permits reading data that may lag behind the primary. Tests should not assert “the secondary immediately sees the write just executed” without waiting for replication or using causal consistency/sessions/appropriate read concerns.

### 26.4. Do Not Use `secondaryPreferred()` to Prove a Secondary Was Used

`secondaryPreferred()` falls back to the primary when no eligible secondary is available. A test using it can pass without ever reading from a secondary.

To verify which host actually received the command, use command monitoring/tracing or explicit server selection and topology-based assertions.

## 27. Failover Testing: Purposeful Operations in Multi-Node Setups

### 27.1. Objective

```text
Given 3-voter replica set
And Java client configured for discovery
When primary becomes unavailable
Then another member becomes PRIMARY
And eligible operations eventually succeed
```

### 27.2. Tests Must Not Assume Who Becomes the New Primary

When A is lost, either B or C can be elected depending on state, priority, and replication progress. If a test expects **specifically B** without configuring priorities and conditions, it can be flaky.

### 27.3. Identify the Primary from Real State

Before fault injection:

1. Read `rs.status()`/`hello` through an appropriate client.
2. Identify the host currently acting as primary.
3. Confirm both secondaries have caught up and quorum exists.
4. Set a clear test deadline and collect evidence.

Only then perform a planned stepdown or stop the actual primary in the test environment.

### 27.4. Never Call `a.stop()` Just Because a Was Once Primary

After the initial election, `a` might already be a secondary. The test must inspect actual cluster state before injecting faults.

### 27.5. Two Approaches

**Planned stepdown:** use `rs.stepDown()` conditionally and observe client recovery.

**Unexpected primary failure:** stop/kill the container currently acting as primary (in the lab) and observe election by the two remaining members. This is closer to real failure but requires reliable teardown and capacity.

### 27.6. Assertions to Measure

- A new primary appears within the deadline.
- The application experiences transient errors within expected bounds and then recovers.
- The driver does not require restarting the entire application.
- Retryable operations are handled properly.
- No duplicate business writes occur.
- Majority writes succeed after failover.

## 28. Testing Replication Lag and Majority Write Concern

### 28.1. Single-Node Is Insufficient

With one voting member, `w:"majority"` is satisfied by that sole member. It does not prove replication to another host.

### 28.2. Multi-Node Optime Observation

```javascript
const s = rs.status();
printjson(s.members.map(m => ({
  name: m.name,
  state: m.stateStr,
  optimeDate: m.optimeDate,
  health: m.health
})));
```

In a multi-node test, you can observe progress after a write and check secondary catch-up using condition-based polling.

### 28.3. Majority Loss Tests

To verify behavior when majority is lost:

- You need a multi-node cluster with a clearly understood voting config.
- Injecting network faults can trigger write concern timeouts or loss of primary.
- Distinguish “write not applied” from “write applied but failed to satisfy write concern.”
- Never run on shared/staging/production clusters.

### 28.4. Sleep-Based Tests Are Poor Practice

```java
Thread.sleep(1000); // Does not prove replication reached B/C.
```

Polling `optime`, document state via read preferences, and using deadlines is far more meaningful.

## 29. Fault Injection with Docker Stop Differs from Network Partitions

### 29.1. Stopping a Container

In a lab environment:

```java
// Conditional pseudocode: container 'primaryNode'
// must be identified from real topology before calling.
primaryNode.stop();
```

Simulates **process/host unavailability**. It does not necessarily match a packet-loss scenario.

### 29.2. Network Partition

```text
          A PRIMARY
          /       \
         /         \
        B  ----X---- C
```

Network partitions take many forms:

- A is isolated from B/C.
- A can reach B but not C.
- Client can reach A, yet A lacks majority.
- A link has packet loss/latency without failing completely.

Simulating these may require **Toxiproxy** or equivalent network-control tools; not every failure mode can be replaced by `container.stop()`.

### 29.3. Know Simulation Limits

Disconnecting two containers may differ from real cloud-region, disk, or Kubernetes service outages. Scenarios should document the fault model and what was **not** tested.

### 29.4. Never Run Chaos Testing on Real Databases

Stop/kill/network-partition operations must only target clusters completely owned by the test. Never aim fault injection at shared staging or production MongoDB.

## 30. Using Toxiproxy for Controlled Network Faults

Toxiproxy lets you inject latency, bandwidth limits, or connection failures into a connection path via a **proxy**.

```text
Java Client (runner)
       |
       v
Toxiproxy
       |
       v
MongoDB node
```

### 30.1. Faults That Can Be Simulated

- Abrupt connection drops.
- Controlled latency increases.
- Bandwidth throttling.
- Mid-command network disconnects.
- Certain half-open/stalled behaviors via supported toxics.

### 30.2. Replica Set Pitfall

If you only proxy the **seed URI** while MongoDB advertises `mongo-a/mongo-b/mongo-c` directly, the driver may **bypass the proxy** after topology discovery and connect straight to the nodes. Then the test never injects faults into the path the driver actually uses.

To test failover reliably through proxies:

1. Configure advertised addresses to route through appropriate proxies.
2. Ensure all addresses/ports are reachable from the runner.
3. Verify via CommandListener/SDAM events that client traffic goes through the proxies.
4. Only then enable toxics and assert.

### 30.3. Do Not Assert Only That an Exception Appeared

A more useful network-fault test asserts **recovery behavior**, preserved business idempotency, retry budgets, and time-to-success.

## 31. Sharded Cluster: When Is It Mandatory to Spin Up?

A sharded cluster consists of:

```text
                    Java Driver
                        |
                        v
                    mongos
                   /  |   \
                  /   |    \
                 v    v     v
        +----------+ +----------+
        | Shard A  | | Shard B  |
        | RS       | | RS       |
        +----------+ +----------+
                 \     /
                  \   /
                   v v
          Config Server Replica Set
```

### 31.1. Features Requiring a Sharded Topology

- Testing shard keys and write routing.
- Evaluating targeted vs scatter/gather queries.
- Testing unique index constraints on sharded collections.
- Testing cross-shard transactions.
- Testing certain `$lookup`/`$merge` behaviors on sharded collections.
- Change streams on a sharded deployment.
- Handling `mongos` routing/failures and topology changes.

### 31.2. Why Two MongoDBContainers Do Not Create Sharding

Two `MongoDBContainer` instances simply create two test MongoDB instances per module implementation; they **lack config servers, shard registrations, `mongos`, and collection sharding metadata**.

### 31.3. A Sharded Cluster Can Require Many Containers

Depending on needs, an isolated test may require:

```text
Config RS: config-1 (minimal for lab) or 3 nodes
Shard A: 1-node RS or multiple data-bearing members
Shard B: 1-node RS or multiple data-bearing members
mongos: 1 router
runner: test process / container
```

Sharded deployments have strict configuration/initialization requirements; minimum valid node counts and config server rules depend on version. Never put a single-node config server into production.

### 31.4. Do Not Spin Up a Full Sharded Cluster for Every Repository Test

A repository querying solely by `_id` can be tested on a single-node replica set; dedicated sharding behavior tests should live in an appropriate suite despite heavier startup costs.

## 32. Sharded Setup with Testcontainers Compose

### 32.1. Why Consider Compose?

A topology with a config server replica set, two shard replica sets, `mongos`, and init scripts can be expressed more cleanly via **Docker Compose** or a specialized test fixture image than hundreds of lines of `GenericContainer`.

Testcontainers supports Compose integration to start services according to the test lifecycle.

### 32.2. Components to Initialize

```text
1. Start config server mongod nodes with --configsvr --replSet
2. Initiate config server replica set
3. Start shard mongod nodes with --shardsvr --replSet
4. Initiate shard replica sets
5. Start mongos with --configdb configRS/hosts
6. Wait for mongos readiness
7. Run sh.addShard(...)
8. Enable sharding / shard collections with correct indexes
9. Run test through mongos
```

### 32.3. Tests Must Go Through `mongos`

To verify routing, the Java test must connect to **mongos**. Connecting straight to a shard primary and querying bypasses the layer under test.

### 32.4. Endpoints Still Must Resolve Properly

If containers run inside a Docker network, shard/config names resolve internally. The runner/JVM must have a reachable path to `mongos`; if server discovery exposes additional hostnames, check network semantics too.

### 32.5. 1.x vs 2.x Differences

Testcontainers Java changed some module coordinates and classes between 1.x and 2.x; when using `ComposeContainer`, read the docs for your **pinned version** instead of copying old imports/dependencies into a new environment.

## 33. Sharding Test: Creating a Collection and Checking the Shard Key

An example executed via `mongos` once the sharded cluster is ready:

```javascript
sh.enableSharding("orders_it_412");

db.getSiblingDB("orders_it_412").orders.createIndex({
  tenantId: 1,
  orderId: 1
});

sh.shardCollection(
  "orders_it_412.orders",
  { tenantId: 1, orderId: 1 }
);
```

### 33.1. Assertions

- `sh.status()` or corresponding metadata reflects that the namespace is sharded.
- Queries containing the shard key are routed appropriately.
- Queries missing the shard key are not blindly assumed to be targeted.
- Unique index constraints are verified according to shard key/version rules.
- Cross-shard transactions are tested only when multiple shards hold suitably distributed data.

### 33.2. Calling `sh.shardCollection()` Alone Is Not Enough

A successful admin command proves the namespace is configured as sharded, yet testing **routing** requires sufficiently varied data distribution/query predicates and inspecting explain output or shard metrics.

### 33.3. Never Alter Sharding for Tests on a Shared Database

Only operate on namespaces and clusters owned by the test; `sh.enableSharding` and `sh.shardCollection` modify cluster metadata.

## 34. Atlas Search and Vector Search: Yet Another Topology

MongoDB Atlas Search / Atlas Vector Search are search capabilities with **search engine integration**; a plain `mongo:7.0` container does not provide them out of the box.

Testcontainers Java provides **`MongoDBAtlasLocalContainer`** using the `mongodb/mongodb-atlas-local` image to create a supported local Atlas Search/Vector Search environment.

### 34.1. Example

```java
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.mongodb.MongoDBAtlasLocalContainer;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@Testcontainers
class AtlasLocal412IT {
    @Container
    static MongoDBAtlasLocalContainer atlas =
        new MongoDBAtlasLocalContainer(
            DockerImageName.parse(
                "mongodb/mongodb-atlas-local:7.0.9"));

    @Test
    void shouldProvideConnectionString() {
        assertNotNull(atlas.getConnectionString());
    }
}
```

### 34.2. Atlas Local URI

`getConnectionString()` returns the dynamic host/mapped port and may include `directConnection=true`. Do not rewrite it into a replica set URI unless the image/container advertises that topology.

### 34.3. Do Not Treat Atlas Local as Identical to Atlas Cloud

The local environment does not by default replicate:

- Atlas control plane, organization/project RBAC.
- Private endpoints and cloud IAM/networking.
- Every vector search feature/version behavior.
- Resource sizing and distributed scaling.
- Managed Atlas backups/PITR/alerting.

### 34.4. Real Tests Need Search Indexes

Merely checking `atlas.isRunning()` does not test search. You must create a valid index, wait until the index is ready, seed documents, run `$search` or `$vectorSearch`, and assert results.

### 34.5. Image Versions

The Atlas Local image has version/feature constraints; pin a version aligned with real server/search integration and verify image compatibility before deploying the suite.

## 35. Why Can Single-Node Transaction Tests Appear “Too Easy”?

### 35.1. Majority on One Node

```text
Single node RS:
  voters=1
  majority=1
```

Write concern `majority` follows replica set semantics, yet here it does not require replicating data to another physical node.

### 35.2. No Real Lag

An application using `ReadPreference.secondary()` in production can observe stale data. A transaction test on a single-node primary does not cover this scenario.

### 35.3. No Elections

If the sole node stops, the driver cannot discover a new primary until that node returns; recovery via another server is never tested.

### 35.4. Logic Tests Still Hold Value

Do not dismiss single-node tests: they are highly valuable for transaction atomicity, BSON types, validation, and aggregation. **Just do not ascribe to them guarantees the topology cannot produce.**

## 36. Authentication and Authorization in Testcontainers

### 36.1. Simple Containers Usually Lack Auth

Many MongoDB Testcontainers examples start local MongoDB **without authentication enabled** to focus on query/transaction behavior.

This does **not** mean production applications do not need auth.

### 36.2. Testing Authentication Requires Deliberate Setup

With the official MongoDB Docker image in a lab:

```java
GenericContainer<?> securedMongo =
    new GenericContainer<>(DockerImageName.parse("mongo:7.0"))
        .withExposedPorts(27017)
        .withEnv("MONGO_INITDB_ROOT_USERNAME", "testroot")
        .withEnv("MONGO_INITDB_ROOT_PASSWORD", "local-test-only-secret");
```

The official image initializes a root user via those environment variables under appropriate startup conditions. Use **test-only credentials** and never commit production secrets.

### 36.3. Auth on a Replica Set Is More Complex

Enabling auth across multiple members requires handling **internal member authentication**, keyfiles/X.509, permissions, and `rs.initiate()` ordering. Do not simply attach username/password env vars to `MongoDBContainer.withReplicaSet()` and assume the helper handles every step.

### 36.4. RBAC Testing

A useful security test:

1. Create a user with read permission on database A.
2. Confirm `find` in A succeeds.
3. Confirm writes are rejected per role.
4. Confirm access to database B is denied.
5. Never use the root user as the application identity under test.

### 36.5. Never Run the Secured Sample Credentials in Production

Hardcoded example credentials are valid only for disposable test environments. Real systems must use secrets management and least-privilege roles.

## 37. TLS, Certificates, and Hostnames in Topology Tests

### 37.1. When Must TLS Be Tested?

- The application mandates `tls=true`.
- Certificate rotation.
- Client certificate authentication.
- Hostname verification.
- Multi-node deployments with certificate SANs matching member hostnames.

### 37.2. Adding `tls=true` Alone Is Not Enough

The MongoDB server must also be configured with TLS and valid certificates. The test container must mount certs/keys with proper permissions, configure the CA/truststore for the client, and match hostnames to SANs.

### 37.3. Multi-Node Also Needs Internal Auth

When using X.509 or keyfiles for inter-member authentication, those requirements are part of the topology—not merely Java client settings.

### 37.4. Never Disable Hostname Verification

Do not work around SAN errors by setting `tlsAllowInvalidHostnames` or bypassing the truststore just to make tests pass. Instead, issue test certificates with accurate SANs for the hostnames used in the test network.

### 37.5. Security Tests Should Form a Dedicated Suite

Most CRUD tests do not need to stand up a CA/PKI in every test class. Keep a dedicated suite for TLS/auth protocols while simpler suites use a lighter MongoDBContainer.

## 38. Container Lifecycle: Using JUnit Properly

### 38.1. Per-Method

```java
@Container
MongoDBContainer mongo = new MongoDBContainer("mongo:7.0")
    .withReplicaSet();
```

The container is recreated for each test method in the corresponding Jupiter setup. This provides strong isolation with higher startup overhead.

### 38.2. Per-Class

```java
@Container
static MongoDBContainer mongo = new MongoDBContainer("mongo:7.0")
    .withReplicaSet();
```

One container serves all test methods in the class; requires seeding/cleanup.

### 38.3. Suite-Wide Singleton

Some projects use a singleton container across multiple classes to reduce startup time. In that case:

- Do not mix `@Container` lifecycle management with a manually managed singleton.
- Do not close the container while another Spring context still holds a live MongoClient.
- Assign distinct database names and clear cleanup ownership.
- Ensure proper shutdown/cleanup on JVM exit.

### 38.4. Test Parallelism

When running in parallel:

- Use unique test IDs/databases.
- Never let one test drop a collection another test is using.
- Never let one test step down or stop a cluster while another test runs CRUD on it.
- Ensure pool/shared container capacity is sufficient.
- Verify JUnit Testcontainers extension parallel support/semantics for your version.

## 39. Reusable Containers: Benefits and Risks

Testcontainers offers **reusable containers** in certain versions, though the documentation marks it experimental.

### 39.1. Benefits

On a developer's machine, avoids starting a fresh MongoDB instance on every test run.

### 39.2. Risks

- State persists across runs.
- Old indexes/collections affect assertions.
- Newer test code reuses a database from an older version.
- Cleanup does not occur as with disposable containers.
- Harder to diagnose flaky failures.

### 39.3. Do Not Enable Automatically in CI

CI should favor **ephemeral, repeatable tests**. Only use reuse with clear conventions and reliable state-reset mechanisms. Do not treat `withReuse(true)` + host configuration as universally optimal.

### 39.4. Never Use Reuse to Mask Startup Problems

If a MongoDB container initializes its replica set unreliably on cold start, reusing an already-running container can hide readiness bugs. Test the cold-start path separately.

## 40. CI/CD: Docker Runtime and Resources

### 40.1. What Does a CI Job Need?

- A Docker-compatible daemon/runtime accessible to Testcontainers.
- Permissions to create/start/stop containers and networks.
- Enough disk space for MongoDB images and temporary data.
- Enough RAM/CPU for `mongod`, especially with multiple nodes.
- Network access to an image registry or mirror.
- Runner/container lifecycle cleanup.

### 40.2. GitHub Actions, GitLab CI, Jenkins...

Each platform exposes the Docker socket/daemon differently. Never assume `/var/run/docker.sock` always exists on a runner.

### 40.3. Docker-in-Docker

If the test process runs inside a container using Docker-in-Docker or a bind-mounted host socket, understand:

- `DOCKER_HOST` and how Testcontainers discovers the daemon.
- The hostname/mapped ports visible to the JVM.
- Docker network isolation.
- Resource and security implications of privileged mode.
- Cleanup if the runner is killed.

**Do not expose a privileged Docker socket to untrusted workloads** just to run integration tests.

### 40.4. Image Pulls

Pin appropriate MongoDB image tags and use a registry mirror/cache if CI hits rate limits. Avoid `mongo:latest` because an upstream MongoDB server upgrade can change test behavior overnight.

### 40.5. Image Digests

Pinning digests guarantees byte-for-byte image reproducibility, though it requires a periodic security-update and rebuild process. Even when pinning specific version tags, note that tags can be republished.

## 41. Testcontainers Ryuk and Cleanup

Testcontainers generally provides a resource reaper/cleanup mechanism to remove containers and networks after tests finish.

### 41.1. Why Does It Matter?

Without cleanup:

- Containers remain running, consuming RAM/disk.
- Orphaned networks accumulate.
- Mapped ports/connections linger unexpectedly.
- CI runner disks fill up.

### 41.2. Do Not Arbitrarily Disable Cleanup

In CI environments whose policies restrict cleanup sidecars, configure per Testcontainers documentation with a reliable alternative resource-cleanup mechanism. Do not blindly disable Ryuk/resource reaper to “fix an error” while introducing resource leaks.

### 41.3. Teardown Must Handle Test Failures Too

With manual `GenericContainer.start()`, use try-with-resources/`finally` or JUnit lifecycles to stop/close. If one node fails to start, previously started nodes must still be cleaned up.

### 41.4. Do Not Delete Docker Resources Outside Test Scope

Never run `docker system prune -a` on a shared CI host just because a MongoDB suite failed. Clean up only containers/networks owned by Testcontainers.

## 42. Startup Failures: Locating the Right Failure Layer

| Symptom | Common cause | Check |
|---|---|---|
| Cannot connect to Docker daemon | Runtime/socket/permission | Docker info, CI runtime |
| Image pull failed | Network/registry/rate limit | Registry credentials/cache |
| Mongo container exited | Command/image/volume/permission | Container logs |
| Port opened but RS not ready | Election/init incomplete | `hello`/`rs.status` |
| `rs.initiate` hostnames unreachable | Network aliases/DNS | Internal connectivity |
| JVM cannot select primary | Advertised hosts unresolved | `hello.hosts`/URI |
| Transaction not supported | Standalone or wrong topology | `hello.setName` |
| Change streams unavailable | No replica set/sharded deployment | Oplog/topology |
| Atlas Search stage unavailable | Wrong image/search engine | Atlas Local config/index |
| Passes locally, fails in CI | CPU/RAM/startup timeout/path | Timing/resource metrics |
| Unexpected duplicate key | Data leak between tests | Seed/cleanup/unique keys |

### 42.1. Inspecting Container Logs

```java
String logs = mongo.getLogs();
System.out.println(logs);
```

Only print logs in test environments with fake data; MongoDB output can contain connection info, usernames, or query metadata.

### 42.2. Do Not Print Only a Stack Trace

On failure, capture:

- Image name/tag.
- Testcontainers module version.
- Docker runtime version.
- Container exit code and log tail.
- MongoDB `hello`/`rs.status` if reachable.
- Network aliases, advertised hosts, and redacted URI.
- Startup/readiness timestamps.

### 42.3. Do Not Rely on Long Sleeps as the Sole Fix

Increasing `Thread.sleep(30000)` may mask a race while slowing the suite down and still failing on slower CI runners. Use readiness conditions with justified deadlines.

## 43. Docker Networking: Common Misconceptions

### 43.1. Host Port Differs from Container Port

```text
Inside container:
  MongoDB listens 27017

On test host:
  MongoDB mapped to 49123 (example)
```

`getMappedPort(27017)` returns the host port. Do not confuse internal `27017` with the port Java uses on the host.

### 43.2. `localhost` Inside a Container Is Not the Host's localhost

If the Java application runs **in its own container**, `localhost` points to the Java container itself, not the MongoDB container.

### 43.3. Docker Network Aliases Only Work Inside That Network

`mongo-a` resolves inside a custom Docker network, not necessarily from the host JVM or another network.

### 43.4. Replica Sets Advertise Hosts

Even when a seed URI connects, the driver discovers hosts from MongoDB and may discard the initial seed endpoint. Multi-node connectivity must resolve **every advertised address**.

### 43.5. Never Use `directConnection=true` to Prove Failover

Direct mode targets a single member, useful for diagnostics, yet bypasses the topology discovery mechanism under test in failover scenarios.

## 44. Database Version Matrix in Integration Tests

### 44.1. Why Test Multiple Server Versions?

An application may support MongoDB 7.0 and 8.0, which can differ in operators and index behaviors; a newer driver may also talk to an older supported server.

### 44.2. Suggested Matrix

| Suite | MongoDB image | Topology | Features |
|---|---|---|---|
| Basic CRUD IT | Lowest supported server version | Single-node RS | Queries/indexes |
| Transaction IT | Supported versions | Single-node RS | Commit/abort |
| Change Stream IT | Target version | Single-node RS | Watch/resume |
| Failover IT | Production version | Three-node RS | Election/retry |
| Sharding IT | Production version | Sharded cluster | Routing/transactions |
| Search IT | Compatible Atlas Local image | Atlas Local | `$search`/`$vectorSearch` |

### 44.3. Pin Images and Test Feature Compatibility

Do not just swap the image string if a feature also depends on `featureCompatibilityVersion` (FCV), storage engine, image support, Java driver version, or TLS/auth config.

### 44.4. Do Not Run Every Combination on Every Commit

One option:

- Per PR: CRUD + transaction + change stream on one primary version.
- Nightly: expanded version matrix and multi-node/sharding tests.
- Pre-production upgrade: dedicated compatibility/failover/rollback drills.

### 44.5. Testcontainers Pinning Matters Too

Testcontainers 1.x and 2.x changed module names/packages. Upgrading the MongoDB image separately from upgrading Testcontainers Java makes regression triage clearer.

## 45. Topology-Specific Datasets

### 45.1. Standalone

Seed enough documents to test indexes, filters, type handling, collation, and TTL.

### 45.2. Single-Node RS

Seed multiple collections to test transaction commit/abort; seed stream events with clear identities and timestamps.

### 45.3. Multi-Node RS

Seed enough data to test secondary reads and read-after-write under lag; use unique business request IDs to catch retry duplicates.

### 45.4. Sharded Cluster

Seed keys with intentional distribution. If every document happens to land on one shard, a “cross-shard transaction test” might actually touch only one shard.

### 45.5. Atlas Search

Seed documents with text/vector fields matching the index definition and wait for the index to become ready. Do not assert exact tie-breaking scores if the algorithm has ties or non-deterministic behavior without explicit ordering criteria.

## 46. Preventing Flaky Tests: Readiness, Timeouts, and State

### 46.1. Startup Flakiness

```text
Laptop: mongod ready in 2 sec
CI:     mongod ready in 15 sec
```

If a test hardcodes a 3-second sleep, it will fail in CI.

### 46.2. Election Flakiness

Elections take variable time; assertions must check state within a deadline rather than expecting an exact duration.

### 46.3. Change Stream Flakiness

Stream consumers must subscribe at the right time, read events with bounded timeouts, filter by identity, and handle duplicate/resume semantics.

### 46.4. TTL Flakiness

The TTL monitor is asynchronous; assert eventual deletion with an appropriate timeout or avoid running TTL waits in every class.

### 46.5. Data-Sharing Flakiness

Two tests creating `_id = "P1"` in a shared collection will collide. Use unique IDs/DB names and controlled cleanup.

### 46.6. Parallel JUnit Flakiness

Parallel tests concurrently stopping primaries or dropping shared collections are unsafe. Isolate topology-mutating tests into an exclusive suite or give each its own cluster.

## 47. Measuring Test Runtime and Optimizing Cost

### 47.1. Breakdown

```text
T_total =
  Docker environment detection
  + image pull
  + container start
  + MongoDB readiness / election
  + seed/index setup
  + assertions
  + teardown
```

### 47.2. Targeted Optimizations

- Pin/cache images in CI.
- Split suites by topology.
- Share static containers across multiple tests when data isolation is solid.
- Avoid dropping and recreating excessive indexes on every method.
- Use Awaitility/condition-based waits instead of fixed sleeps.
- Schedule sharding/failover tests appropriately.

### 47.3. Never Optimize by Removing the Real Database

Turning transaction integration tests into mocks runs faster, yet forfeits the exact semantics you need to prove. Stratify tests instead of deleting critical integration coverage.

### 47.4. Do Not Turn Tests into Performance Benchmarks

Laptop and CI host performance fluctuates. `assert duration < 25ms` is prone to flakiness. Performance tests need dedicated benchmark infrastructure; integration tests primarily assert correctness and availability within reasonable windows.

## 48. Pre-Test Topology Selection Checklist

### 48.1. Feature Questions

1. Does the test use multi-document transactions?
2. Does the test use change streams/resume tokens?
3. Does the test use real secondary read preferences?
4. Does the test involve elections/failover/network partitions?
5. Does the test require multi-node majority write concern?
6. Does the test involve sharding/mongos/shard keys?
7. Does the test involve Atlas Search/Vector Search?
8. Does the test cover auth/TLS/X.509 behaviors?

### 48.2. Infrastructure Questions

1. Is the container runtime ready?
2. Are Testcontainers/Driver/MongoDB versions compatible?
3. Is the MongoDB image pinned?
4. Do CI RAM/disk/network suffice?
5. Does startup readiness match the feature?
6. Are all advertised hosts reachable from the test runner?
7. Is data isolated across classes/runs?
8. Does cleanup run even when tests fail?

### 48.3. Evidence Questions

1. Do assertions prove behavior rather than only container.isRunning()?
2. Do assertions avoid non-deterministic timing or ordering?
3. Are logs/traces captured on startup failure?
4. Are key failure modes covered by test cases?
5. Is there a plan to separate heavy tests?

## 49. Example Scenario: Money Transfer Transaction

### 49.1. Problem

Transfer 30 units from account A to B. Requirement: either both balances change or neither changes.

### 49.2. Topology

A **single-node replica set** is sufficient to test atomic transaction commit/abort.

### 49.3. Test Cases

- Commit succeeds: A decreases by 30, B increases by 30.
- Exception inside the transaction body triggers abort.
- Constraint failure prevents commit.
- No intermediate state is visible after abort.

### 49.4. What Is Not Tested Yet

- Primary election mid-commit.
- Unknown commit result due to network failure.
- Replication and majority acknowledgment across data-bearing nodes.

Those cases require separate multi-node/fault tests.

## 50. Example Scenario: Event-Driven Order Service

### 50.1. Problem

When an order transitions `CREATED` → `PAID`, a change-stream worker updates a read model.

### 50.2. Topology

**Single-node replica set** for basic emit/consume testing; **multi-node replica set** if proving resume across failover is required.

### 50.3. Test Cases

1. Open watcher.
2. Update order.
3. Assert update event.
4. Check resume token is persisted.
5. Restart consumer and resume from the exact position.
6. Assert handler idempotency if an event is reprocessed.

### 50.4. Easy-to-Miss Bugs

- Watcher subscribes after the event occurred.
- Polling without a deadline.
- Resume token not persisted.
- Non-idempotent event handler.
- Oplog truncated before consumer resumes.

## 51. Example Scenario: API Keeps Working After Primary Failure

### 51.1. Problem

The Java driver must discover a new primary when the current primary stops.

### 51.2. Topology

**Three-data-bearing-member replica set**, voting majority 2/3, with a driver URI able to resolve all advertised hosts.

### 51.3. Test Cases

1. Wait for one primary, two secondaries, and healthy replication.
2. Send baseline writes with request IDs.
3. Identify the actual primary.
4. Stop the primary or trigger a planned stepdown in the lab.
5. Poll for a new primary within a deadline.
6. Send/retry eligible writes after failover.
7. Verify no duplicate IDs exist.
8. Verify the former primary rejoins as secondary and catches up upon restart.

### 51.4. Do Not Hardcode “A Is Primary”

The initial election may choose A, B, or C. Always stopping A might mean you are only testing “losing a secondary.”

### 51.5. Applications Can Observe Unknown Outcomes

If a write was sent before a network fault, a lost response can leave the outcome uncertain. Driver retryable writes have specific semantics; the HTTP API still needs business idempotency.

## 52. Example Scenario: Testing Shard Keys and Cross-Shard Transactions

### 52.1. Problem

Multi-tenant orders are distributed across shards; routing and transactions across collections/shards must be verified.

### 52.2. Topology

**Sharded cluster** with at least two shards and mongos. A single-node replica set is insufficient.

### 52.3. Test Cases

- Collection sharded by the proper key.
- Inserts distributed across multiple shard ranges/chunks per test setup.
- Queries containing the full shard key route properly.
- Queries missing the shard key have scatter semantics measured/understood.
- Cross-shard transaction commit/abort preserves MongoDB atomicity.
- Unique indexes obey shard key constraints.

### 52.4. Challenges

Initializing config servers, shards, mongos, data distribution, and container networking is complex. Use a maintained/dedicated fixture rather than scattering admin commands across every repository test.

## 53. Anti-Patterns to Avoid

| Anti-pattern | Consequence | Replacement |
|---|---|---|
| Using standalone for transactions | Wrong topology | Single-node RS |
| Using standalone for change streams | No valid oplog stream | Replica set/sharded |
| Single-node RS for failover | No secondary to elect new primary | Three-node RS |
| Single-node RS for secondary reads | No data-bearing secondary | Multi-node RS |
| Treating one-node `w:majority` as multi-copy replication | False durability conclusions | Multi-voter test |
| Creating three independent `MongoDBContainer` instances and calling it one RS | Not the same replica set | GenericContainer + init/fixture |
| Hardcoding `localhost:27017` | Dynamic mapped ports | getReplicaSetUrl/getMappedPort |
| Using Docker aliases in host JVM | Host cannot resolve | Containerized runner/proxy |
| Using `directConnection=true` for failover | Bypasses SDAM replica-set behavior | Full replica set URI |
| Using `Wait.forListeningPort()` as proof primary is ready | Race condition | Condition-based topology wait |
| Hardcoding `Thread.sleep(3000)` | Flaky CI | Poll with deadline |
| Test asserting only container.isRunning | Does not test database feature | Real DB operations |
| Enabling MongoDB auth env vars with helper without checking RS init | Startup failure | Dedicated secured fixture |
| Disabling TLS validation in tests | Hides certificate bugs | Valid test CA/SAN |
| Enabling reusable containers without cleanup | Data leaks | Isolation/disposable CI |
| Creating a new MongoClient per query | Connection storm / slow | Long-lived client |
| Forgetting to close MongoClient/cursor | Resource leaks | Lifecycle/try-with-resources |
| Calling `dropDatabase()` with wrong URI | Data loss | Test-owned namespace guard |
| Using production credentials | Security risk | Disposable test secrets |
| Replaying test data without independent IDs | Duplicate keys/flaky | Stable fixtures + reset |
| Testing TTL down to the exact second | Flaky due to TTL monitor | Eventually assertion |
| Subscribing change stream too late | Missed events | Subscribe before write |
| Testing failover without identifying actual primary | Stops a secondary by mistake | Inspect topology first |
| Letting parallel tests mutate shared topology | Cross-test interference | Exclusive fixture |
| Checking only MongoDB image version, ignoring FCV | Feature mismatch | Version/FCV matrix |
| Running sharded suite for all CRUD tests | Unnecessarily slow CI | Split topology suites |
| Treating Atlas Local as full Atlas Cloud | Misses control-plane differences | Scope Atlas tests |
| Logging full commands/PII | Data exposure | Redact/sanitize |
| Disabling Ryuk/cleanup unconditionally | Orphaned resources | Reliable cleanup |
| Exposing unrestricted privileged Docker socket | Security risk | Scoped runner/runtime |

## 54. Hands-On Exercises

### Exercise 1 — Topology Selection

Given seven features: CRUD, unique indexes, transactions, change streams, secondary reads, failover, and `$vectorSearch`. Choose the minimum suitable topology and explain each choice.

### Exercise 2 — 2.x Dependencies

Write Gradle test dependencies for `testcontainers-mongodb` and `testcontainers-junit-jupiter` using the BOM. Explain why the MongoDB Java Driver is declared separately.

### Exercise 3 — Migration 1.x → 2.x

A test uses `org.testcontainers.containers.MongoDBContainer` and `org.testcontainers:mongodb`. Update it to the corresponding 2.x API and module coordinates.

### Exercise 4 — Dynamic Ports

The MongoDB container listens internally on 27017, while the host mapped port is 49211. Write Java code retrieving the proper connection string via the helper, and explain why 27017 must not be hardcoded on the host.

### Exercise 5 — Standalone

Configure `GenericContainer` for `mongod --bind_ip_all` without `--replSet`. Verify CRUD succeeds and transactions are rejected per version.

### Exercise 6 — Single-Node Replica Set

Create `MongoDBContainer.withReplicaSet()`, use `getReplicaSetUrl()`, run `hello`, and confirm `setName` is non-null.

### Exercise 7 — Transaction Commit

Create two accounts, update both in a transaction, commit, and assert the total balance remains unchanged.

### Exercise 8 — Transaction Abort

From the same fixture, call `abortTransaction()`; assert both documents remain unchanged. Explain why failover recovery is still unproven.

### Exercise 9 — Change Streams

Open a stream before inserting an event; wait with a bounded timeout and assert the operation type. Which race conditions make this test flaky?

### Exercise 10 — Spring DynamicPropertySource

Write a Spring Boot integration test using `@DynamicPropertySource` to wire the MongoDB Testcontainers URI into `spring.data.mongodb.uri`.

### Exercise 11 — ServiceConnection

Convert the Spring Boot test to `@ServiceConnection`. List the required extra dependency and explain when a custom MongoClient bean can alter expected auto-configuration.

### Exercise 12 — Container Lifecycle

Compare `static @Container`, instance `@Container`, and a suite-wide singleton in terms of startup time, isolation, and cleanup.

### Exercise 13 — Docker Network Aliases

Explain why `mongo-a:27017` resolves inside a Docker network yet does not resolve by default from the host JVM.

### Exercise 14 — Replica Set Advertised Hosts

A replica set is configured with `mongo-a/b/c:27017`, while the host JVM seeds with localhost mapped ports. Why does the driver still fail server selection after reading `hello`?

### Exercise 15 — Manual Replica Set

Start three `GenericContainer` instances with the same `--replSet rsIT`, run `rs.initiate`, and use a condition wait to confirm one primary and two secondaries.

### Exercise 16 — Read Preference

Write a `ReadPreference.secondary()` test on a multi-node RS. Why can `secondaryPreferred()` pass without ever reading from a secondary?

### Exercise 17 — Election

Among three voters, stop the actual primary, wait for election, and verify writes. Explain why you must not hardcode “container A is always primary.”

### Exercise 18 — Majority Semantics

Why does `w:"majority"` in a single-node RS not prove data was replicated across the network?

### Exercise 19 — Toxiproxy

Design a network partition test using proxies. How do you verify Java Driver traffic does not bypass the proxy via advertised hosts?

### Exercise 20 — Sharded Cluster

Diagram a topology with a config server RS, shard A RS, shard B RS, and mongos. Note initialization order and where the Java Driver should connect.

### Exercise 21 — Shard Key

For an orders collection keyed by tenantId/orderId, create the shard key and design tests for targeted queries, scatter queries, and unique constraints under a sharded topology.

### Exercise 22 — Atlas Local

Create a `MongoDBAtlasLocalContainer`, describe creating an Atlas Search index, and run a `$search` pipeline. Why is plain `mongo:7.0` insufficient?

### Exercise 23 — Authentication

Create a read-only user on a test database, verify reads succeed, and verify writes are denied. Why should root never be granted as the application identity?

### Exercise 24 — TLS

Create a test CA and server cert with SAN matching the hostname. When the JVM connects via an alias not in the SAN, what happens? Why not enable allowInvalidHostnames?

### Exercise 25 — TTL and Eventual Assertions

Test TTL document deletion without asserting immediately after 1 second. Describe an appropriate polling deadline/timeout.

### Exercise 26 — CI Runtime

A GitLab job reports it cannot find a Docker runtime. Draft a checklist covering Docker socket/daemon, permissions, image pulls, networking, and cleanup.

### Exercise 27 — Data Isolation

Two test classes share a singleton MongoDB container and both insert `_id=P1`. Propose at least three ways to avoid collisions and state their trade-offs.

### Exercise 28 — Version Matrix

A project supports MongoDB 7 and 8. Design smoke/transaction/change-stream/sharding suites across a version matrix, noting FCV dependencies.

### Exercise 29 — Failure Diagnosis

The container is running and the port is open, yet Java throws `MongoTimeoutException: no primary`. Draft a runbook distinguishing incomplete RS initialization from unresolved hostnames.

### Exercise 30 — Capstone

Design an integration test strategy for a Java service featuring:

1. CRUD and schema validation.
2. Order-placement transactions.
3. Change streams updating a read model.
4. Failover/primary switchover.
5. Secondary read preference.
6. Search/vector search.
7. Sharded routing for multi-tenancy.

Select the topology per suite, dependencies, readiness criteria, data isolation, CI schedule, timeouts, observability, and stop conditions.

## 55. Feature-Based Test Design Workflow

### Step 1 — List Behaviors to Prove

```text
CRUD accurate?
Transaction atomic?
Stream receives events?
Replica set failover?
Secondary read staleness?
Sharded routing?
Atlas Search?
```

### Step 2 — Choose the Smallest Adequate Topology

Standalone for simple behavior without RS requirements; single-node RS for transactions/streams; multi-node RS for elections/lag; sharded cluster for mongos/shard keys; Atlas Local for search integration.

### Step 3 — Pin Runtime and Versions

Testcontainers BOM, JUnit, MongoDB Driver, MongoDB image, Spring Boot version, and FCV if relevant.

### Step 4 — Provision via the Right API

`MongoDBContainer` for the MongoDB module, `GenericContainer` for standalone/custom members, `MongoDBAtlasLocalContainer` for local search, Compose/helpers for multi-service topologies.

### Step 5 — Resolve Networking Before Assertions

Confirm advertised hostnames are reachable from both the Java test runner and member-to-member networks. Never hack around it by forcing `directConnection=true` on failover tests.

### Step 6 — Wait for Feature-Appropriate Readiness

TCP open → database ready → replica set primary/secondaries → indexes/streams/search ready. Never assume one step suffices for all.

### Step 7 — Seed, Test, Reset

Test-owned namespaces/IDs, data isolation, deterministic seeding, clear assertions, and safe teardown.

### Step 8 — Inject Faults with Control

Only when the topology is valid; identify the actual primary, enforce timeouts, collect telemetry, and clean up.

### Step 9 — Read Evidence on Failure

Container logs, `hello`, `rs.status`, Docker runtime details, redacted URI, server selection errors, stack trace, and timeline.

### Step 10 — Separate CI Lanes

Fast runs on PRs; heavy multi-node/sharding/search/failover suites scheduled per policy to keep reliability high and feedback loops reasonable.

## 56. Summary

**One MongoDB container cannot represent every MongoDB topology.** Testcontainers delivers repeatable infrastructure, yet test authors must pick configurations based on the feature:

- **Standalone:** sufficient for ordinary CRUD/indexes/aggregation, insufficient for replica-set-only features.
- **Single-node replica set:** suitable for transactions, change streams, sessions, and the retryable-write protocol, yet lacks secondaries and real failover.
- **Multi-node replica set:** required for elections, secondary reads, lag, majority acknowledgment across multiple data-bearing nodes, and client recovery.
- **Sharded cluster:** mandatory when testing shard keys, `mongos` routing, and sharded transactions.
- **MongoDB Atlas Local:** used for local Atlas Search/Vector Search within image-supported scope, without replacing full managed Atlas Cloud.

**The hard part of multi-node testing is usually networking, not starting three containers.** Replica sets advertise member hostnames via `hello`; Docker aliases and host mapped ports inhabit different spaces. To test real failover, the runner must resolve/reach all advertised hosts and use full replica set discovery.

**A good test verifies behavior, not just startup.** Wait for readiness with conditions; assert transaction commit/abort, stream events, server selection, secondary reads, and routing appropriately; isolate data between tests; use deadlines and capture logs on failure.

**Optimize suites through stratification, not by faking topology.** Simple tests run fast on `MongoDBContainer`; multi-node/sharding/search suites run separately as needed. The outcome is integration testing that stays faithful to real MongoDB, avoids flakiness, and runs reliably in CI.

## 57. References

- [Testcontainers Java — MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/): `MongoDBContainer`, `MongoDBAtlasLocalContainer`, and 2.x dependencies.
- [Testcontainers Java — JUnit 5 Integration](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Testcontainers`, `@Container`, static/instance lifecycle.
- [Testcontainers Java — Networking and Communicating with Containers](https://java.testcontainers.org/features/networking/): mapped ports, networks, aliases, and host access.
- [Testcontainers Java — Wait Strategies](https://java.testcontainers.org/features/startup_and_waits/): readiness and startup timeouts.
- [Testcontainers Java — Docker Compose Module](https://java.testcontainers.org/modules/docker_compose/): multi-service orchestration.
- [Testcontainers Java — Reusable Containers](https://java.testcontainers.org/features/reuse/): risks and reuse mode.
- [MongoDB Java Sync Driver — Integration Testing Using Testcontainers](https://www.mongodb.com/docs/drivers/java/sync/current/integrations/testcontainers/): Java and Spring Boot examples.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): `@ServiceConnection` and `@DynamicPropertySource`.
- [Spring Framework — DynamicPropertySource](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): dynamic property configuration.
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/): topology prerequisites and transaction semantics.
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/): oplog, resume tokens, and deployment support.
- [MongoDB Manual — Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/): voting, majority, and failover.
- [MongoDB Manual — Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/): primary/secondary semantics.
- [MongoDB Manual — Sharding](https://www.mongodb.com/docs/manual/sharding/): mongos, shards, config servers, and shard keys.
- [MongoDB Atlas — Atlas Search](https://www.mongodb.com/docs/atlas/atlas-search/): search architecture and indexes.
- [MongoDB Atlas — Vector Search](https://www.mongodb.com/docs/atlas/atlas-vector-search/): vector search indexes and queries.
