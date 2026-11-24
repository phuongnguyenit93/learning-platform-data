# Dedicated Databases, Schemas, Topics, Queues, and Namespaces

## 1. The Problem: Parallel Tests Sharing Resources

In a Spring Boot system, two tests can be completely independent in Java code yet still contend over the same **database**, **schema**, **Kafka topic**, **consumer group**, **RabbitMQ queue/exchange**, **Redis keys**, **S3 prefix**, or **Kubernetes namespace**. When run one by one, everything may pass. When the full suite runs on CI, the following issues appear:

- Test A deletes every row in a table while Test B is asserting on data it just inserted.
- Two tests use the same key `order-1` in the same database/schema, causing duplicate-key violations or reading the wrong result.
- Kafka Test A consumes a message published by B; two consumers using the same `group.id` split partitions and cause the other test to miss its message.
- Two RabbitMQ tests share a queue named `test.queue`; A's consumer grabs B's message, or A's teardown deletes the queue B is still using.
- A Redis test runs `FLUSHDB`/`FLUSHALL`, wiping caches belonging to every other suite.
- A test creates its own schema, yet the app still uses a datasource with `search_path=public`, so every write continues landing in the same table.
- A test uses `@Transactional`, but an HTTP request, async task, or message listener runs on a separate thread/transaction; side effects are not rolled back with the test method.
- Two CI jobs share the same Kafka broker/RabbitMQ vhost with identical topic/queue names; running locally works fine, running concurrently collides.
- Teardown runs `DROP SCHEMA ... CASCADE`, deletes a Kubernetes namespace, or wipes a cloud bucket too broadly; one test job accidentally destroys another job's resources.

This lesson belongs to **Isolation and Parallel Execution**, titled **"Dedicated Databases, Schemas, Topics, Queues, and Namespaces"**. The goal is not merely appending a UUID suffix to every name, but establishing **ownership rules**, resource lifecycles, read/write/delete scopes, and ways to verify isolation when multiple tests actually execute in parallel.

The main example uses **Java 17+**, **Spring Boot 3.3.5**, **JUnit Jupiter**, **Testcontainers PostgreSQL 16**, and `JdbcTemplate`. Sections on Kafka/RabbitMQ/Redis/S3/Kubernetes include standalone APIs/snippets, marked as **extensions** since they are not in the minimal PostgreSQL Gradle project.

### Learning Outcomes

1. Distinguish database-per-suite, schema-per-class, and namespace-key-per-method.
2. Generate a `runId` that is safe, unique, and valid for each system's syntax.
3. Connect `PostgreSQLContainer` using `@Testcontainers`, `@Container`, and Spring Boot `@ServiceConnection`.
4. Ensure SQL queries always filter by `test_namespace` and cleanup deletes only owned data.
5. Understand why `@Transactional`, `@DirtiesContext`, `@Sql`, and `@BeforeEach` do not isolate all external side effects.
6. Isolate Kafka topics, consumer groups, retry/DLT topics, offsets, and transactional IDs.
7. Isolate RabbitMQ queues, exchanges, bindings, and vhosts when needed; choose `exclusive`/`auto-delete` appropriately.
8. Isolate Redis keys with prefixes/TTLs and avoid wiping an entire shared datastore.
9. Organize CI/parallel JUnit lifecycles, resource locks, failure cleanup, and orphan scavenging.
10. Distinguish isolation of **test input**, **processing**, **output**, and **infrastructure**.

## 2. Isolation Levels: Stronger Means Higher Resource Cost

| Level | Example | Pros | Limits |
| --- | --- | --- | --- |
| Dedicated process/container | `PostgreSQLContainer` per test class | Very few collisions across classes | High startup time/resource cost |
| Dedicated database | `it_db_abc...` on one PostgreSQL server | Isolates tables/schemas/migrations | Requires DB create/drop privileges; still shares server capacity |
| Dedicated schema | `it_abc...` in the same database | Separates object names; schema-level migrations | Must configure search_path/Flyway/JPA properly to avoid connection leakage |
| Dedicated row namespace | `test_namespace` in shared tables | Cheap, well-suited for parallel methods | Every query/write/cleanup must filter by namespace |
| Dedicated logical resource | Kafka topic, Rabbit queue/exchange | Prevents tests from stealing each other's messages | Broker metadata, quotas, deletion, and consumer config must be managed |
| Dedicated prefix | Redis key `it:runId:...`; S3 `it/runId/...` | No need to create a new datastore | Prefix deletion must respect ownership and use TTL |
| Infrastructure namespace | K8s namespace + labels | Isolates deploys/services/configs and RBAC | Operational cost; a namespace is not an absolute security boundary |

**A real project often combines multiple layers:** a dedicated PostgreSQL container for a test class, with each test method inside using a row namespace; a Kafka broker Testcontainer shared across the suite while topics and groups are unique per scenario; RabbitMQ using dedicated queues/exchanges; Redis using key prefixes with TTL.

### Four Questions Before Choosing

1. Does the test alter **global schemas**, migrations, or server settings? If so, row namespaces are insufficient.
2. Does the test have always-on consumers or async workers? If so, separate routing/subscriptions and await completion before cleanup.
3. Does CI run multiple forks, modules, machines, or pull requests concurrently? If so, an in-JVM `1,2,3` counter is not unique enough.
4. Do you have permissions to create/delete real resources? If not, prefer test-owned prefixes/groups in a dedicated environment or use Testcontainers.

## 3. Resource Naming Must Be Both Unique and Valid

UUID v4 generated per test run has an extremely low collision probability; using **32 lowercase hex characters** builds stable names without slashes, spaces, or quote characters. Still, systems differ on naming constraints:

| Type | Example | Notes |
| --- | --- | --- |
| PostgreSQL schema | `it_012345...` | Max 63 bytes for default identifiers; lowercase + underscore |
| PostgreSQL row namespace | `run_012345...` | SQL parameter value, not an identifier |
| Kafka topic | `it.orders.012345...` | Do not collide with Kafka internal topics; short name, alphanumeric/dot/hyphen |
| Kafka consumer group | `it.consumer.012345...` | Dedicated group to avoid sharing partitions/offsets |
| Rabbit exchange | `it.exchange.012345...` | Avoid reserved prefix `amq.` |
| Rabbit queue | `it.queue.012345...` | Dedicated queue, intentional lifecycle/auto-delete |
| Redis key prefix | `it:012345...:` | Never run `FLUSHALL` on shared Redis |
| S3/object prefix | `it/012345.../` | Prefix is an object key segment, not a bucket security boundary |
| Kubernetes namespace | `it-012345...` | DNS label lowercase/hyphen; dedicated quotas/RBAC and labels |

**Unique names alone are not absolute isolation.** If a reader scans the entire database, a consumer subscribes to `it.orders.*`, or cleanup deletes all topics starting with `it.`, tests still interfere with one another. Every read, write, subscribe, and cleanup path must use the exact namespace and ownership.

## 4. Resource Lifecycle and Ownership

```text
CI run / test class / test method
           |
   Generate runId (unique)
           |
   Allocate exact resources
   - DB/container/schema or row namespace
   - topic + group
   - exchange + queue + binding
   - cache prefix / object prefix
           |
   Prepare fixture -> start consumer -> wait ready
           |
   Execute -> await bounded results -> assertions
           |
   Stop listeners/consumers
           |
   Cleanup ONLY resources owned by runId
           |
   Close clients/containers, record orphan cleanup if needed
```

Principles:

- Every resource has a clear **owner** (`runId`, CI build ID/label, TTL).
- **Create before use**; never assume a topic/schema/queue exists from a previous run.
- **Observe readiness**: broker partition assignment, Rabbit queue binding, DB migrations finished, K8s Ready status.
- **Delete after consumers stop**; avoid cleaning up while workers are still processing.
- **Cleanup in `finally`/`@AfterEach`/`@AfterAll`** so cleanup still runs when assertions fail.
- If a process is hard-killed, lifecycle hooks will not run: rely on TTLs, labels, and orphan garbage collection in test environments.
- Never delete resources outside your run's prefix/label.
- Never embed secrets/PII in topic/namespace names, logs, or exception messages.

## 5. Runnable Project: Java 17 + Boot 3.3.5 + PostgreSQL Testcontainers

This example runs a `PostgreSQLContainer` **dedicated to the test class**, while every test method writes rows into the same `it_orders` table using a **separate row namespace**. These are two intentional isolation layers:

- **Class/suite isolation:** Testcontainers provides a dedicated database instance, reducing interference with other applications.
- **Method isolation:** `test_namespace` accompanies every record and every query/cleanup; parallel methods never see each other's rows.

Directory tree:

```text
isolation-test-lab/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/isolation/
│   ├── IsolationApplication.java
│   ├── IsolationNames.java
│   └── OrderStore.java
└── src/test/
    ├── java/com/example/isolation/
    │   ├── IsolationNamesTest.java
    │   └── OrderStoreIsolationTest.java
    └── resources/
        ├── application-test.yml
        ├── schema.sql
        └── junit-platform.properties
```

**Prerequisites:** A Docker/Podman-compatible Testcontainers environment configured; PostgreSQL image pullable; CI capable of starting containers. Without Docker, network integration tests **must not silently fall back to H2** or be reported as PASS.

## 6. Gradle Dependencies

### settings.gradle

```groovy
rootProject.name = 'isolation-test-lab'
```

### build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

- `spring-boot-starter-jdbc`: `JdbcTemplate`, DataSource, and JDBC transaction support.
- `postgresql`: PostgreSQL JDBC driver.
- `spring-boot-starter-test`: JUnit Jupiter, AssertJ, Spring TestContext.
- `spring-boot-testcontainers`: `@ServiceConnection` support in Spring Boot 3.3.
- `org.testcontainers:junit-jupiter`: JUnit Testcontainers extension and `@Container`.
- `org.testcontainers:postgresql`: `PostgreSQLContainer`.
- `junit-platform-launcher`: Gradle/JUnit Platform compatibility.

Do not pin the Testcontainers version manually in this project; Spring Boot 3.3.5 dependency management selects a compatible release. Testcontainers PostgreSQL requires a running Docker daemon/engine, not a local PostgreSQL server installation.

## 7. Application Root

`src/main/java/com/example/isolation/IsolationApplication.java`:

```java
package com.example.isolation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IsolationApplication {

    public static void main(String[] args) {
        SpringApplication.run(IsolationApplication.class, args);
    }
}
```

Because the project only includes the JDBC starter, the app does not open a Servlet server. `@SpringBootTest` loads the repository and real DataSource in tests; no HTTP endpoints or scheduled tasks alter rows unexpectedly.

## 8. IsolationNames: Single Source of Safe IDs Across Resource Types

`src/main/java/com/example/isolation/IsolationNames.java`:

```java
package com.example.isolation;

import java.util.Objects;
import java.util.UUID;

public final class IsolationNames {

    private IsolationNames() {
    }

    public static String newRunId() {
        return UUID.randomUUID()
                .toString()
                .replace("-", "");
    }

    public static Names forRunId(String runId) {
        Objects.requireNonNull(runId, "runId");

        if (!runId.matches("[0-9a-f]{32}")) {
            throw new IllegalArgumentException(
                    "runId must be 32 lowercase hex characters");
        }

        return new Names(
                "it_" + runId,
                "run_" + runId,
                "it.orders." + runId,
                "it.consumer." + runId,
                "it.exchange." + runId,
                "it.queue." + runId,
                "it:" + runId + ":",
                "it/" + runId + "/",
                "it-" + runId);
    }

    public record Names(
            String postgresSchema,
            String rowNamespace,
            String kafkaTopic,
            String kafkaConsumerGroup,
            String rabbitExchange,
            String rabbitQueue,
            String redisPrefix,
            String objectPrefix,
            String kubernetesNamespace
    ) {
    }
}
```

`forRunId(...)` accepts only **32 lowercase hex characters**, so generated names contain no quotes, whitespace, unexpected slashes, or arbitrary SQL punctuation. Notably, `postgresSchema` is 35 characters long (3 + 32), well under PostgreSQL's default 63-byte identifier limit.

**Never concatenate raw user input into schema/SQL identifier names.** SQL parameter bindings like `?` apply only to **values**, not directly to table/schema names. If schemas must be created dynamically, enforce an allowlist/safe generator as shown here and grant restricted privileges to the test DB user.

### Why Not Use currentTimeMillis() for Names?

In parallel tests or across CI processes, milliseconds can collide and thread scheduling does not guarantee uniqueness. Random UUID v4 avoids timestamp dependence. If CI run traceability is needed, attach `runId` as a separate test report/log label; never stuff branch names or emails into resource names due to invalid characters, PII, and length limits.

### Multiple Name Formats from One runId

Using one `runId` helps trace and clean up a single scenario. Yet each resource type uses a distinct prefix to prevent confusion:

```text
runId                 0123456789abcdef0123456789abcdef
postgresSchema        it_0123456789abcdef0123456789abcdef
rowNamespace          run_0123456789abcdef0123456789abcdef
kafkaTopic            it.orders.0123456789abcdef0123456789abcdef
kafkaConsumerGroup    it.consumer.0123456789abcdef0123456789abcdef
rabbitExchange        it.exchange.0123456789abcdef0123456789abcdef
rabbitQueue           it.queue.0123456789abcdef0123456789abcdef
redisPrefix           it:0123456789abcdef0123456789abcdef:
objectPrefix          it/0123456789abcdef0123456789abcdef/
kubernetesNamespace   it-0123456789abcdef0123456789abcdef
```

This is an **illustrative example from a fixed runId**, not stdout captured from Gradle. When `newRunId()` is called, values differ on every run.

## 9. OrderStore: Always Query and Clean Up by Namespace

`src/main/java/com/example/isolation/OrderStore.java`:

```java
package com.example.isolation;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderStore {

    private final JdbcTemplate jdbc;

    public OrderStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void save(
            String namespace,
            String orderId,
            String state) {

        jdbc.update("""
                INSERT INTO it_orders
                    (test_namespace, order_id, state)
                VALUES (?, ?, ?)
                """, namespace, orderId, state);
    }

    public long count(String namespace) {
        Long value = jdbc.queryForObject("""
                SELECT COUNT(*)
                FROM it_orders
                WHERE test_namespace = ?
                """, Long.class, namespace);

        return value == null ? 0L : value;
    }

    public String state(
            String namespace,
            String orderId) {
        return jdbc.queryForObject("""
                SELECT state
                FROM it_orders
                WHERE test_namespace = ?
                  AND order_id = ?
                """, String.class, namespace, orderId);
    }

    public int deleteNamespace(String namespace) {
        return jdbc.update("""
                DELETE FROM it_orders
                WHERE test_namespace = ?
                """, namespace);
    }
}
```

Most importantly, this is not just about using `UUID`—it is that **every query path passes the namespace**. If Test A and B both save `order_id="ORDER-1"` under different namespaces, the composite primary key allows both to coexist without conflict.

`deleteNamespace` uses `WHERE test_namespace = ?`. It **never** executes an unconditional `DELETE FROM it_orders`, never `TRUNCATE`s, and never deletes another test's data. Bind parameters are safely handled for values by JDBC.

### When Is a Row Namespace Not Enough?

If production code runs `SELECT * FROM it_orders` without filtering by namespace, fixing only the sample repository leaves a risk of misreading rows. Multi-tenant systems need genuine tenant isolation (RLS, tenant-scoped repositories, schema-per-tenant...). In an integration test, verify **all** read/write/delete paths of the subject under test, not just a single sample repository.

For migrations/DDL, a namespace column **does not isolate** schema changes or global sequences; use a dedicated schema/container/database.

## 10. Test-Only SQL Schema and Profile

`src/test/resources/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS it_orders (
    test_namespace VARCHAR(80) NOT NULL,
    order_id VARCHAR(64) NOT NULL,
    state VARCHAR(40) NOT NULL,
    PRIMARY KEY (test_namespace, order_id)
);

CREATE INDEX IF NOT EXISTS idx_it_orders_namespace
    ON it_orders (test_namespace);
```

`src/test/resources/application-test.yml`:

```yaml
spring:
  main:
    web-application-type: none
  sql:
    init:
      mode: always
```

`spring.sql.init.mode=always` ensures Spring Boot runs `schema.sql` against the test PostgreSQL instance, not only when the DataSource is considered embedded. Real systems can use Flyway/Liquibase instead of `schema.sql`; **do not run multiple schema initialization mechanisms concurrently** on the same objects without clear ordering/ownership.

**Use the demo table only in test databases.** Never enable `spring.sql.init.mode=always` with a destructive script against a production datasource. With Flyway, apply migrations to the proper test database/schema and run real production migrations when catching migration compatibility issues.

## 11. Enabling JUnit Parallelism in a Controlled Way

`src/test/resources/junit-platform.properties`:

```properties
# Integration tests using @Testcontainers/@Container must run sequentially in JUnit.
# Concurrent access by two writers is still verified via ExecutorService inside one @Test.
junit.jupiter.execution.parallel.enabled=false
```

The runnable configuration above **disables JUnit parallelism** because the example uses the Testcontainers JUnit Jupiter extension (`@Testcontainers`/`@Container`), which currently only supports sequential execution. Putting `@Execution(CONCURRENT)` on a class using that extension or enabling concurrent methods/classes suite-wide can cause container lifecycle races and unsupported outcomes. The lesson still proves concurrent access using two `ExecutorService` tasks inside a `@Test` method running sequentially at the JUnit layer.

For pure JUnit tests not using this extension, parallelism can be configured in a separate isolated suite; `Gradle maxParallelForks`, modules, and CI jobs can also increase concurrency at other layers. Do not make parallel execution of the Testcontainers extension a default runnable configuration.

### Parallel Execution Does Not Mean Race-Free

Having a separate namespace per test prevents row collisions, yet an app can still harbor static mutable singletons, unnamespaced caches, shared temp files, Kafka consumer groups, fixed ports, or server-side global state. Enable parallelism only after confirming each dependency is isolated or locked.

## 12. @SpringBootTest + PostgreSQLContainer + @ServiceConnection

`src/test/java/com/example/isolation/OrderStoreIsolationTest.java`:

```java
package com.example.isolation;

import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@ActiveProfiles("test")
@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class OrderStoreIsolationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    OrderStore store;

    // Default JUnit PER_METHOD: each test gets its own instance/list.
    private final List<String> ownedNamespaces =
            new CopyOnWriteArrayList<>();

    private String ownedNamespace() {
        String ns = IsolationNames
                .forRunId(IsolationNames.newRunId())
                .rowNamespace();
        ownedNamespaces.add(ns);
        return ns;
    }

    @AfterEach
    void cleanupOwnedRows() {
        // Only delete rows belonging to the current test method.
        for (String ns : ownedNamespaces) {
            store.deleteNamespace(ns);
        }
    }

    @Test
    void identicalOrderIdsInDifferentNamespacesDoNotClash() {
        String first = ownedNamespace();
        String second = ownedNamespace();

        store.save(first, "ORDER-1", "NEW");
        store.save(second, "ORDER-1", "PAID");

        assertEquals("NEW", store.state(first, "ORDER-1"));
        assertEquals("PAID", store.state(second, "ORDER-1"));
        assertEquals(1L, store.count(first));
        assertEquals(1L, store.count(second));
    }

    @Test
    void cleanupOfOneNamespaceDoesNotDeleteAnother() {
        String first = ownedNamespace();
        String second = ownedNamespace();

        store.save(first, "ORDER-2", "READY");
        store.save(second, "ORDER-2", "READY");

        assertEquals(1, store.deleteNamespace(first));
        assertEquals(0L, store.count(first));
        assertEquals(1L, store.count(second));
    }

    @Test
    void duplicateOrderIdWithinSameNamespaceIsRejected() {
        String ns = ownedNamespace();

        store.save(ns, "ORDER-3", "NEW");

        assertThrows(
                DataIntegrityViolationException.class,
                () -> store.save(ns, "ORDER-3", "NEW"));

        assertEquals(1L, store.count(ns));
    }

    @Test
    void concurrentWritersCannotSeeEachOthersRows()
            throws Exception {
        String first = ownedNamespace();
        String second = ownedNamespace();

        ExecutorService pool =
                Executors.newFixedThreadPool(2);

        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        Callable<Void> writeFirst = () -> {
            ready.countDown();
            if (!start.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("start timed out");
            }
            for (int i = 0; i < 20; i++) {
                store.save(first, "A-" + i, "READY");
            }
            return null;
        };

        Callable<Void> writeSecond = () -> {
            ready.countDown();
            if (!start.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("start timed out");
            }
            for (int i = 0; i < 20; i++) {
                store.save(second, "B-" + i, "READY");
            }
            return null;
        };

        try {
            Future<Void> left = pool.submit(writeFirst);
            Future<Void> right = pool.submit(writeSecond);

            assertTrue(ready.await(5, TimeUnit.SECONDS));
            start.countDown();

            left.get(15, TimeUnit.SECONDS);
            right.get(15, TimeUnit.SECONDS);

            assertEquals(20L, store.count(first));
            assertEquals(20L, store.count(second));
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
```

**There are 4 `@Test` methods** in this class. They require Docker/Testcontainers and real PostgreSQL. `@ServiceConnection` lets Boot inject JDBC connection details from `PostgreSQLContainer` into the application context without hard-coding JDBC port, username, or password. `@Container` hands container lifecycle management to the JUnit Testcontainers extension.

### Why @DirtiesContext(AFTER_CLASS)?

The Testcontainers extension normally stops the static `@Container` after the test class, yet the Spring TestContext cache can hold the old `ApplicationContext`/DataSource for a subsequent test class. `@DirtiesContext(classMode=AFTER_CLASS)` guarantees the context is not reused after this class completes. It **does not** automatically delete rows, topics, or queues in an external system: that remains the job of explicit cleanup.

### Why Not @Transactional on the Test Class?

Test-managed `@Transactional` rolls back the transaction on the test thread, whereas Kafka consumers, Rabbit listeners, `@Async` tasks, or HTTP requests run on different threads/transactions and are not rolled back with it. In the demo, a test transaction is not wrapped around all work; each method uses a namespace and explicit cleanup. When testing repository transaction semantics specifically, write a dedicated test with explicit commit/rollback expectations.

### Limitations of @AfterEach Cleanup

`@AfterEach` runs when normal assertions fail, but does not run if the JVM is hard-killed or the CI runner loses power. Test-owned namespaces inside an ephemeral container vanish when the container is removed; with shared brokers/cloud services, you need **TTLs, labels, and a sweeper** to handle orphan resources.

In `concurrentWritersCannotSeeEachOthersRows`, `shutdownNow()` sends an interruption but does not wait to confirm every task stopped immediately if a future times out; production-grade test helpers should `awaitTermination` or cancel/join futures before cleanup. The sample waits for both futures to succeed on the normal path; timeout/failure paths must be handled carefully if expanded into a stress suite.

## 13. Unit Tests for Namespace Naming and Independence Properties

`src/test/java/com/example/isolation/IsolationNamesTest.java`:

```java
package com.example.isolation;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class IsolationNamesTest {

    private static final String A =
            "0123456789abcdef0123456789abcdef";

    private static final String B =
            "fedcba9876543210fedcba9876543210";

    @Test
    void generatedRunIdIsSafeLowercaseHex() {
        String runId = IsolationNames.newRunId();

        assertTrue(runId.matches("[0-9a-f]{32}"));
    }

    @Test
    void postgresSchemaIsShortAndSqlIdentifierSafe() {
        String schema =
                IsolationNames.forRunId(A).postgresSchema();

        assertTrue(schema.matches("[a-z][a-z0-9_]*"));
        assertTrue(schema.length() <= 63);
    }

    @Test
    void kafkaAndRabbitResourcesUseDistinctPrefixes() {
        IsolationNames.Names names =
                IsolationNames.forRunId(A);

        assertTrue(names.kafkaTopic().startsWith("it.orders."));
        assertTrue(names.kafkaConsumerGroup()
                .startsWith("it.consumer."));
        assertTrue(names.rabbitQueue().startsWith("it.queue."));
        assertTrue(names.rabbitExchange()
                .startsWith("it.exchange."));
        assertNotEquals(
                names.rabbitQueue(),
                names.rabbitExchange());
    }

    @Test
    void redisS3AndKubernetesNamesUseSafePatterns() {
        IsolationNames.Names names =
                IsolationNames.forRunId(A);

        assertTrue(names.redisPrefix().startsWith("it:"));
        assertTrue(names.redisPrefix().endsWith(":"));
        assertTrue(names.objectPrefix().startsWith("it/"));
        assertTrue(names.objectPrefix().endsWith("/"));
        assertTrue(names.kubernetesNamespace()
                .matches("[a-z0-9]+(-[a-z0-9]+)*"));
    }

    @Test
    void runIdCannotContainInjectedSqlOrPathCharacters() {
        assertThrows(
                IllegalArgumentException.class,
                () -> IsolationNames.forRunId(
                        "x; DROP SCHEMA public CASCADE"));
    }

    @Test
    void twoRunIdsProduceDifferentNamespaces() {
        assertNotEquals(
                IsolationNames.forRunId(A).rowNamespace(),
                IsolationNames.forRunId(B).rowNamespace());
        assertNotEquals(
                IsolationNames.forRunId(A).kafkaTopic(),
                IsolationNames.forRunId(B).kafkaTopic());
    }
}
```

This class has **6 `@Test` methods** requiring no Docker; the main project totals **10 test methods** (4 integration + 6 unit). These tests verify only the naming contract, not that corresponding schemas/topics/queues exist in reality.

### Avoid Testing Uniqueness via Timing

`twoRunIdsProduceDifferentNamespaces` uses **two distinct fixed input runIds**; it is deterministic. `generatedRunIdIsSafeLowercaseHex` checks the format of the UUID-derived string without relying on a specific random value. Given UUID v4's probability distribution, we do not claim "mathematically impossible collision", yet it is a practical choice for test runs.

## 14. How to Run, Environment Prerequisites, and Expected Outcomes

If the repository includes the Gradle Wrapper:

```bash
./gradlew test --tests 'com.example.isolation.IsolationNamesTest'
./gradlew test --tests 'com.example.isolation.OrderStoreIsolationTest'
./gradlew test
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
```

If no Wrapper exists yet but a compatible Gradle is installed:

```bash
gradle test
```

JUnit reports are typically found at:

```text
build/reports/tests/test/index.html
build/test-results/test/
```

**Neither Gradle nor Docker was executed while authoring this lesson.** The source contains 10 `@Test` methods with the assertions described, but **we cannot claim all 10 tests PASS** without running the suite and inspecting real reports. If CI lacks Docker permissions, integration tests fail immediately during container setup; never mislabel that as a SQL isolation logic bug.

### What Does the Project Verify?

| Group | Tested | Not yet tested |
| --- | --- | --- |
| RunId/naming | Format, prefix, distinction between two IDs | Kafka broker/K8s API accepting real resources |
| PostgreSQL | Per-class Testcontainer, namespaced rows, unique key | Schema-per-class provisioning and multi-schema migrations |
| Method-level isolation | Same order ID across namespaces, owner-only delete | Production multi-tenant security |
| Parallel access | 2 workers writing 20 rows per namespace concurrently | Heavy load, chaos, long-term contention |
| Cleanup | Owner-specific SQL delete | Kill -9 cleanup, shared cloud resources |
| Kafka/Rabbit/Redis/S3 | Architectural patterns in later sections | Not included in runnable Gradle dependencies |

## 15. Three Ways to Isolate PostgreSQL: Database, Schema, and Rows

### 15.1. Database-per-Suite

A dedicated `PostgreSQLContainer` as in the project is easy to understand: each class gets its own database instance, and tables/migrations are not shared with other suites. Downsides are startup time, memory, and Docker limits. With 100 test classes running concurrently, 100 containers can slow down or crash CI.

You can run one container **for a test module** with a dedicated database per class. Yet when moving to a shared container, you need valid schema/database namespaces, proper schema migrations, and cleanup; do not move a `static` field to a global singleton and assume isolation remains intact automatically.

### 15.2. Schema-per-Class

Create a dedicated schema, such as `it_0123456789abcdef0123456789abcdef`, for each test class. When provisioning via JDBC:

```java
String schema =
        IsolationNames.forRunId(runId).postgresSchema();

try (Connection connection = adminDataSource.getConnection();
     Statement statement = connection.createStatement()) {

    statement.execute("CREATE SCHEMA \"" + schema + "\"");
}
```

**This is an extension snippet, not part of the main runnable project**: it requires `runId`, `adminDataSource`, and `java.sql.Connection/Statement` imports already configured; the schema must be created **before** the app DataSource/Flyway/JPA creates objects. Because `schema` comes from allowlisted UUID hex characters, there is no SQL injection or unexpected identifier quoting.

After creation, configure the test class's **dedicated DataSource** with the appropriate schema: e.g., PostgreSQL JDBC `currentSchema`, Hikari `schema`, or connection-init SQL, matching the connection pool used. With Flyway/Liquibase, configure target schemas/default schema, migrations, and history tables properly; with JPA, configure the default schema/tenant routing accordingly.

**The `search_path` trap:** calling `SET search_path=...` once on connection A does not mean connection B from the Hikari pool uses that schema. Moreover, a connection returned to the pool can retain session state if not properly reset, causing another test to target the wrong schema. Prefer a dedicated datasource/pool per schema and verify actual `current_schema()` right inside the integration test.

### 15.3. Row Namespace-per-Method

If all tests can share a schema, add `test_namespace` to composite PKs/WHERE clauses as in the main project. This is a cheap option for parallel tests. Still, watch out for:

- `TRUNCATE it_orders` still wipes every test namespace.
- Any query missing `WHERE test_namespace = ?` still reads other tests' data.
- A unique key on `order_id` alone without the namespace still collides.
- Global sequences, triggers, or singleton caches may still be shared.
- `@BeforeEach` cleanup via `DELETE FROM it_orders` is unsafe.
- If a service uses connection pooling and a `ThreadLocal` tenant context, propagate that context across HTTP/async tasks.

### Quick Comparison

| Requirement | Approach to Choose |
| --- | --- |
| Testing DDL/migrations/schema structure | Dedicated database/schema |
| Testing multi-threaded business queries | Row namespace in tables, if supported by code |
| Testing multi-tenant behavior | Real tenant isolation tests, not just swapping test IDs |
| Testing transaction rollback on PostgreSQL | Real PostgreSQL test DB and commit/rollback assertions |
| Optimizing cost across many test methods | Shared container + per-method namespace |
| Requiring complete cleanliness per class | Fresh database/container, accepting the cost |

## 16. @Transactional Does Not Replace Resource Isolation

`@Transactional` on a JUnit method can roll back JDBC writes made inside the **same test-managed transaction**; this is convenient for single-threaded repository tests. However, it **cannot** roll back:

- Messages already published to Kafka or RabbitMQ.
- HTTP calls handled on a different thread/server.
- Spring Batch job/step transactions.
- `@Async` listeners running on another executor.
- Redis writes via a client not participating in the JDBC transaction.
- Objects on S3/blob storage.
- Schema/table DDL depending on DB/transaction semantics.
- A service invoked over HTTP against a real server that commits on its own.

Therefore, think of **transaction scope** and **resource scope** separately. For integration tests involving async/external operations, use dedicated test DBs/schemas/namespaces and matching cleanup; do not slap on `@Rollback` and assume data cannot leak.

### @Sql and Cleanup Scripts

`@Sql` is handy for setting up fixtures via SQL in a test DB. However, a `DELETE FROM orders` in an after `@Sql` script still affects all tests sharing that table. If a script performs cleanup, parameterize it by namespace or use a schema/database owned exclusively by the test. `@SqlConfig(transactionMode=ISOLATED)` controls the script's transaction mode, **not** automatic namespace isolation.

## 17. Spring TestContext Cache, @DirtiesContext, and @DynamicPropertySource

Spring TestContext caches `ApplicationContext` instances across classes with equivalent configurations to cut startup costs. This speeds up suites, but poses risks when a bean holds the URL of a shut-down Testcontainer or when dynamic properties change across classes.

Key points:

1. `static @Container` is managed per test class by the JUnit Testcontainers extension; there is no guarantee the container stays alive when a cached context is reused in another class.
2. `@ServiceConnection` configures DataSource connection details from the container; when switching to a different container, the context must refresh according to its lifecycle.
3. `@DirtiesContext(AFTER_CLASS)` prevents context reuse after the class, **not replacing DB cleanup**.
4. `@DynamicPropertySource` injects dynamic endpoints into the Spring Environment when not using service connections; it must also align with the context lifecycle, not act as a JVM-global variable mutated between methods.
5. If a container is a **shared singleton** across classes/modules, manage its lifecycle in a test fixture with clear ownership and ensure cached contexts/properties never point to stale endpoints.
6. Never let `spring.kafka.bootstrap-servers`/`spring.rabbitmq.addresses` point to a production broker in a test profile.
7. Another CI job may run in a different process, so Spring's context cache does not provide cross-process isolation.

**Note:** Overusing `@DirtiesContext` slows down the suite. When row namespaces are safe and containers live for the proper scope, you do not need to mark every method dirty. Use it when Spring bean state/contexts genuinely need resetting, not as a fake "Kafka topic cleaner".

## 18. Kafka: Need Both Dedicated Topic and Dedicated Consumer Group

Kafka has two distinct operational namespaces:

- **Topic**: stores records/partitions; tests sharing a topic see the same data log.
- **Consumer group**: controls partition assignment and committed offsets for a group of consumers. Two tests using the same group may split partitions or trigger rebalances against each other; two different groups on the same topic can both read the log according to their offset policies.

Hence, for parallel tests that must **never touch each other's messages**, isolate **both topic and group** whenever possible.

```text
Test A:
  topic = it.orders.runA
  group = it.consumer.runA
  producer A --> topic A --> consumer A

Test B:
  topic = it.orders.runB
  group = it.consumer.runB
  producer B --> topic B --> consumer B
```

The names above are schematic and not for direct production use. In the project's naming utility, both topic and group are generated from `IsolationNames.forRunId(...)` using the hex `runId`.

### Creating Topics via AdminClient at Test Runtime

The following Java sample requires `spring-kafka` or `org.apache.kafka:kafka-clients`, a test Kafka broker, and Apache Kafka Admin API imports; it is **not part of the runnable PostgreSQL project**:

```java
String topic =
        IsolationNames.forRunId(runId).kafkaTopic();

try (AdminClient admin = AdminClient.create(
        Map.of(
            AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
            bootstrapServers))) {

    admin.createTopics(
            List.of(new NewTopic(topic, 1, (short) 1)))
        .all()
        .get(10, TimeUnit.SECONDS);
}
```

This snippet requires `runId`, `bootstrapServers`, `AdminClient`, `AdminClientConfig`, `NewTopic`, `List`, `Map`, and `TimeUnit`. Replication factor 1 fits a **single-broker test**, not a production cluster. After consumers stop/close, the test can call `deleteTopics(...)` on **that exact topic** and await/poll deletion; Kafka topic deletion can be asynchronous or restricted by broker policy.

### @KafkaListener and Dynamic Topics

`@KafkaListener(topics = "...")` typically resolves topic names when the Spring context/consumer container is created. You cannot simply mutate a property after context initialization and expect the listener to switch to a new topic for the next test method.

Safe approaches:

- Create the dedicated topic **before** the listener container starts.
- Bind topic and group names into a test-specific Spring context at initialization; or use a programmatic `ConcurrentMessageListenerContainer` with test-specific properties.
- With `@EmbeddedKafka`, remember the broker may be shared across tests; isolate topics/groups rather than assuming "embedded" automatically isolates every test.
- Wait for listener partition assignment before publishing, instead of fixed sleeps.
- Use correlation IDs/test-specific headers when asserting consumed messages.
- Clean up only topics/consumer groups created by the test.

**Remember auxiliary topics:** retry topics, DLT/DLQ, and Kafka Streams changelog/state-store topics must also have separate prefixes/ownership. For transactional producers, `transactional.id` must also be unique to avoid producer fencing between tests.

### Offsets and auto.offset.reset

A new group with no committed offsets typically obeys `auto.offset.reset` (`earliest`/`latest`). With a fresh topic and an unassigned consumer, publishing before the listener is ready when using `latest` can cause the test to miss records. Use bounded readiness checks and explicit offset policies rather than guessing with `Thread.sleep(200)`.

## 19. RabbitMQ: Queues, Exchanges, Bindings, and Vhosts

RabbitMQ routing relies on **exchanges**, **routing keys**, **queues**, and **bindings**. A test that changes only the routing key while sharing a queue can receive another test's message if bindings cover both keys. Separate queues and exchanges/bindings when tests need independence.

### Spring AMQP Snippet for Dedicated Resources

Requires `spring-boot-starter-amqp`, a test RabbitMQ broker, and configured `RabbitAdmin` and `RabbitTemplate`; this is an **extension snippet**, not part of the runnable PostgreSQL project:

```java
IsolationNames.Names names =
        IsolationNames.forRunId(runId);

DirectExchange exchange =
        new DirectExchange(names.rabbitExchange(), false, false);

Queue queue =
        new Queue(names.rabbitQueue(), false, false, false);

rabbitAdmin.declareExchange(exchange);
rabbitAdmin.declareQueue(queue);
rabbitAdmin.declareBinding(
        BindingBuilder.bind(queue)
                .to(exchange)
                .with("events"));

try {
    rabbitTemplate.convertAndSend(
            exchange.getName(),
            "events",
            "order-created");

    Object received = rabbitTemplate.receiveAndConvert(
            queue.getName(), 5000);

    assertEquals("order-created", received);
} finally {
    rabbitAdmin.deleteQueue(queue.getName());
    rabbitAdmin.deleteExchange(exchange.getName());
}
```

This is a sample integration flow with a **non-durable** queue/exchange and manual cleanup; it needs injected `rabbitAdmin`, `rabbitTemplate`, JUnit assertions, and Spring AMQP imports. It assumes the broker is ready, resource declarations succeed, and the user has permission to delete those resources. If a test has running asynchronous consumers, **stop consumers before deleting the queue**; the direct polling example above does not compete with another listener on the queue.

### When Is AnonymousQueue Appropriate?

`AnonymousQueue` or `RabbitAdmin.declareQueue()` can create a queue with an auto-generated name that is **non-durable, exclusive, and auto-delete** per its semantics. It fits a temporary consumer in integration tests. However, when a test aims to verify durable queues/bindings/persistence, an exclusive auto-delete queue will **not validate** real production behavior. Nor does it mean the queue disappears immediately after each message: auto-delete normally depends on consumer/connection lifecycles.

### Is a Dedicated Vhost Better?

A RabbitMQ **virtual host** separates the namespace of queues/exchanges/permissions. If a test suite has permission to create vhosts, it can provision `/it-<runId>`. Yet provisioning/cleaning up vhosts requires management APIs/elevated permissions and consumes resources; for many small tests, unique queues/exchanges inside a **CI-dedicated vhost** are usually sufficient.

Never share the `/` vhost with production, and never delete an entire vhost just because one test failed. A vhost is an administrative boundary that tests should not create/delete arbitrarily on a shared broker they do not own.

## 20. Redis: Use Prefixes and TTL, Never FLUSHALL

Redis logical database indexes are generally **not** strong enough isolation across environments (Redis Cluster supports only DB 0; clients may share the same index). On a shared Redis test instance, attach a namespace to **every key**:

```text
it:0123456789abcdef0123456789abcdef:order:ORDER-1
it:0123456789abcdef0123456789abcdef:session:USER-1
it:fedcba9876543210fedcba9876543210:order:ORDER-1
```

Same business key, different namespace → two distinct Redis keys.

A pattern with Spring Data Redis (snippet; requires `RedisTemplate<String,String>`, not in the main Gradle build):

```java
String prefix =
        IsolationNames.forRunId(runId).redisPrefix();

String key = prefix + "order:ORDER-1";

redisTemplate.opsForValue().set(
        key, "READY", Duration.ofMinutes(5));

String value =
        redisTemplate.opsForValue().get(key);

assertEquals("READY", value);
```

The **5-minute TTL** here is a test-fixture safety limit, not a default business cache TTL. Cleanup can scan prefix `it:<runId>:*` using `SCAN` with bounded batching, then delete **only keys matching exact ownership**. Never run `KEYS *` on large Redis instances, never run `FLUSHALL`/`FLUSHDB` on a shared instance, and never delete `it:*` if multiple CI jobs share that prefix root.

### Redis Streams/Consumer Groups

When using Redis Streams, isolate the **stream key**, consumer group, and pending entries. Changing only a cache key prefix while keeping a shared `events` stream and `test-group` consumer group still causes contention and cross-reading. Name streams/consumers using `runId` or use a dedicated Redis container for the test suite.

## 21. Object Storage: Dedicated Bucket or Dedicated Prefix?

For S3/MinIO/Azure Blob, you can choose:

- **Bucket/container per suite**: stronger isolation, but often hits quota/global name uniqueness limits, slow provisioning, and complex permissions.
- **Prefix per run**: shared test bucket with keys under `it/<runId>/`.
- **Object version/etag per test**: may be needed for concurrency/race tests.

An object key snippet:

```java
IsolationNames.Names names =
        IsolationNames.forRunId(runId);

String key = names.objectPrefix()
        + "reports/report.json";
```

Never write objects to a global `reports/report.json` when suites run in parallel. During cleanup, **list and delete only objects under the run's prefix**, accounting for pagination and versioned objects/delete markers. An unfiltered `deleteObjects` can wipe other users' data. Keep a dedicated test bucket with policies denying production credentials wherever possible.

Do not share a bucket/prefix with production and hope test cleanup is safe just because the filename is `test.json`.

## 22. Kubernetes Namespaces and Their Limits

For e2e tests deploying services/brokers, a dedicated Kubernetes namespace per `runId` separates resource names and many config objects.

Example from `IsolationNames.forRunId(runId).kubernetesNamespace()`:

```text
it-0123456789abcdef0123456789abcdef
```

Attach labels like `test-run=<runId>`, `managed-by=ci`, `expires-at=<timestamp>`, along with resource quotas. On cleanup, delete only the namespace created by that run after verifying the owner label/ID; never execute namespace deletion against shared system/production namespaces.

**A namespace is not automatic full security:** you still need NetworkPolicies, RBAC, quotas, service accounts, secret policies, storage class boundaries, and unique cluster-wide resource names. Tests can still collide on CRDs, ClusterRoles, ingress hostnames, PVs, or DNS names despite separate namespaces.

### Options Without Namespace-Creation Permissions

If CI only has permission to deploy inside one shared test namespace, use resource name prefixes, labels, service accounts/resource quotas, and exact-label cleanup. Never delete all pods matching `app=test` if multiple runs share that label; include the test run ID in the selector.

## 23. Testcontainers Reuse and Resource Ownership

Testcontainers supports several lifecycle styles:

- **Static `@Container` field:** container typically lives across test methods in a class and stops after the class.
- **Instance `@Container` field:** creates a container per test method—stronger isolation, higher startup cost.
- **Manual singleton container:** can be reused across classes, but the developer must manage its lifecycle, the Spring context cache, and static mutable state.
- **Reusable containers feature:** should not be enabled by default in shared CI unless cleanup/isolated state is guaranteed.

If a container is shared, isolate databases/schemas/namespaces inside it. "Every test shares one PostgreSQL container" is not inherently unsafe, provided every form of shared mutability is controlled.

### Distinguishing CI Job Isolation from Local Test Isolation

A CI pipeline can run multiple **Gradle forks** or shard jobs. A `static` field lives only within its JVM and cannot distribute identity across processes. UUID-derived `runId`s work across processes; static-field counters do not. A cloud broker may be shared across Git branches, so namespaces must include run ownership or be globally unique rather than just a class name.

## 24. Parallel Execution: @Execution, @ResourceLock, and @Isolated

JUnit Jupiter supports `@Execution(CONCURRENT)` for tests with independent state. For global resources that cannot be isolated (e.g., `System.setProperty`, a fixed filesystem path, or a legacy fixed-port mock server), use `@ResourceLock` or `@Isolated` to serialize:

```java
@ResourceLock(value = "legacy-shared-queue")
@Test
void legacyQueueTest() {
    // Structural snippet.
}
```

Import `org.junit.jupiter.api.parallel.ResourceLock` and place the method in a test class with appropriate setup. If multiple tests touch the same resource, every one of them must declare the lock key consistently; one test omitting the lock still creates a race.

`@Isolated` can be placed on a test class that cannot run concurrently with other tests in the JVM. **It does not lock resources across JVMs or across CI jobs**. For cross-process shared resources, use namespaces, distributed locking, or dedicated infrastructure.

### Why Not Lock Everything?

Serializing the entire suite hides races and slows down CI. Prefer fixing resource ownership/isolation; reserve locks for resources that cannot be separated in the short term, documenting the reason and refactoring plan.

## 25. Readiness: Creation Does Not Mean Consumers Are Ready

With a DB, schema creation/migrations must finish before querying. With Kafka, topic creation completing does not mean listeners have been assigned partitions. With Rabbit, declaring a queue does not guarantee bindings/consumer lifecycles are complete.

A reliable test sequence:

1. Generate `runId`.
2. Create topic/queue/schema.
3. Configure consumer/listener for the exact topic, group, and queue.
4. Start the listener container.
5. Wait for readiness with a timeout (e.g., Kafka partition assignment/consumer state, Rabbit consumer registration, app health).
6. Publish/send test data.
7. Await **consumption/business effect** with a timeout, not just producer send acknowledgment.
8. Stop listeners and wait for processing to become quiescent.
9. Clean up only owned resources.

**Never use `Thread.sleep(1000)`** to guess when a consumer is ready. When async events flow, assert acknowledgments/outputs by correlation ID; if Test B runs simultaneously, routing/group config must make it impossible for B to consume A's events.

## 26. Migrations with Dedicated Schemas: Specific Pitfalls

When using Flyway/Liquibase with a dedicated schema per test class:

- Create the schema **before** Flyway/Liquibase runs.
- Configure target schemas/default schema and the metadata history table in the proper namespace.
- Avoid migrations creating global objects in `public` or shared extensions/roles.
- Verify JPA/Hibernate default schema, JDBC `search_path`, and Flyway schema all point to **the exact same schema**.
- Do not share a singleton datasource and switch `search_path` per test method if the pool reuses connections.
- Ensure migration scripts never execute `DROP SCHEMA public CASCADE` or wipe unrelated objects.
- For PostgreSQL schema-per-suite, use a role with permissions restricted to the provisioned test database/schema.
- Clean up by owner schema, checking allowlists and permissions before `DROP SCHEMA ... CASCADE`; that statement destroys tables/functions/views in the targeted schema.
- When running migrations concurrently across multiple schemas in the same database, test lock/history policies, transaction boundaries, and extension/global DDL conflicts.

### Do Not Hide Migration Bugs Behind H2

H2 syntax and isolation differ from PostgreSQL. For tests involving PostgreSQL-specific JSONB, advisory locks, sequences, or transactional DDL, a PostgreSQL Testcontainer is far more valuable than in-memory H2. Conversely, Docker is unnecessary for pure unit tests of namespace naming.

## 27. Kafka Retry/DLT and Transactional IDs

Isolating the main topic is insufficient if a retry framework generates secondary topics by convention:

```text
it.orders.<runId>
it.orders.<runId>-retry
it.orders.<runId>-dlt
```

These names are merely an educational pattern, not a guarantee that Spring Kafka creates those exact suffixes in every version; when using `@RetryableTopic`, configure suffixes, attempts, and DLT policies per your actual Spring Kafka release. Retry/DLT topics must use the same `runId` and be cleaned up by exact name.

With Kafka producer transactions, **`transactional.id` prefixes** must not be shared by two independent concurrent producers; Kafka can fence one producer when another uses the same transactional ID. Likewise, Kafka Streams' `application.id` determines consumer groups and internal topics; it must be unique per isolated test suite.

### Safe Kafka Cleanup

- Close producers/consumers/listener containers first.
- Delete the **exact** main/retry/DLT topics created.
- Wait for broker metadata updates with bounded polling if subsequent assertions require the topic to be gone.
- Do not assume deleting a topic immediately deletes consumer group offsets or every internal resource.
- If topic deletion is forbidden, use a dedicated broker container or TTL/scavengers in the test environment; never create thousands of unbounded topics on a shared CI broker.

## 28. RabbitMQ: Avoiding Unintended Fan-Out and Queue Contention

In RabbitMQ, multiple consumers on **the same queue** typically split messages via competing-consumer semantics. Two tests sharing a queue receive interleaved messages with no guarantee who gets which message.

To keep two tests **independent**, use two separate queues or vhosts. To test **pub/sub broadcast**, create a dedicated exchange and two dedicated queues with explicit bindings. Tests must match the exact semantics:

| Goal | Configuration |
| --- | --- |
| One test receives its own exact message | Queue per test, routing key/binding per test |
| Two consumers share work | Same queue, same test scope, assert distribution per policy |
| Fan-out to two listeners | One fanout exchange, two dedicated queues within the same test |
| Error to DLQ | Main queue + DLX + DLQ in the same run namespace |
| Test reconnect/exclusive queue | Server-named/exclusive queue; lifecycle tied to connection |
| Multiple CI jobs without interference | Unique vhost or exchange+queue names per run |

**Never call `rabbitAdmin.purgeQueue("test.queue")` on a shared queue** during test setup because purging deletes other tests' messages. Do not use a fixed queue name in `@RabbitListener(queues="test.queue")` when multiple scenarios share the same app context; if dynamic queues are needed, bind properties into a test-specific context or start listener containers programmatically.

## 29. Cleanup Must Never Cause Cross-Test Deletion

| Resource | Dangerous Cleanup | Ownership-Based Cleanup |
| --- | --- | --- |
| PostgreSQL | `TRUNCATE orders`; `DROP SCHEMA public` | `DELETE ... WHERE test_namespace = ?` or drop generated test schema |
| Kafka | Delete all topics matching an overly broad prefix | Delete exact topic names for `runId` |
| RabbitMQ | Purge fixed queue or delete shared exchange | Delete declared queue/binding/exchange of the run |
| Redis | `FLUSHALL`/`FLUSHDB` | TTL + scan/delete exact run prefix |
| S3 | Delete shared bucket/prefix | Delete only owned object prefix; account for versions |
| Kubernetes | Delete shared namespace | Delete exact generated namespace after label verification |
| Temp files | `rm -rf /tmp` or shared folder | Unique temp directory per test, recursive delete only owned path |
| Metrics/logs | Clear global registries | Per-test registry/log capture or namespaced assertions |

### Two-Step Rule Before Destructive Deletes

1. **Validate target:** identifier must match the test-generated prefix/schema/namespace and belong to a test environment.
2. **Validate ownership:** metadata/labels/run records match the owner; never delete resources owned by another run.

For any `DROP ... CASCADE`, bucket deletion, or Kubernetes namespace deletion, enforce permission guardrails and auditing. Avoid running routine tests with admin/root credentials when restricted privileges suffice.

## 30. Test Data and Observability Also Need Isolation

Resource isolation is not just for storage:

- **Filesystem:** `@TempDir` creates a separate folder per test; never write to a shared `/tmp/output.csv`.
- **Clock:** avoid mutating global `TimeZone.setDefault` or `System.setProperty` in parallel tests; inject a `Clock` bean.
- **Random:** inject a fixed seed when test logic demands deterministic output; UUIDs remain valid for resource uniqueness.
- **Micrometer:** give each test its own `SimpleMeterRegistry` or test-specific tags/cleanup plan; never clear another test's global registry.
- **Spring Security:** avoid global mutable auth contexts; understand `SecurityContextHolder`'s thread-local behavior.
- **Caches:** prefix/namespace keys; never wipe the entire Caffeine/Redis cache across a shared context.
- **Log capture:** separate records by correlation ID/`runId`; never assert logs by checking only the global last line.
- **Test fixtures:** primary keys, external invoice numbers, and webhook event IDs must not be reused statically across parallel runs.
- **Schedulers:** disable startup schedulers unless explicitly testing scheduling; background jobs can read/delete another test's state if sharing a namespace.

When a build splits test modules, each module needs compatible resource naming conventions without collisions. Centralize test ownership conventions in a test helper library rather than copy-pasting arbitrary hard-coded prefixes everywhere.

## 31. CI Strategy: Balancing Speed and Isolation

Suites can be divided into three tiers:

| Tier | Example | Policy |
| --- | --- | --- |
| Unit | `IsolationNamesTest`, pure services | High parallelism, no Docker needed |
| Small integration | JDBC + one PostgreSQL container, Kafka listeners | Per-class/container/namespace, timeouts and cleanup |
| E2E/chaos | Multiple brokers/services/K8s | Dedicated namespace or quota-controlled environment, limited parallelism |

Do not spin up 32 Docker containers just because a machine has 32 CPU threads. PostgreSQL startups, Kafka partition metadata, Rabbit connections, and Redis memory all consume resources. Cap concurrency by CI quotas; measure suite runtime and flake rates before and after raising parallelism.

### Gradle Forks

`maxParallelForks` runs multiple test JVMs concurrently. Each JVM has its own static state and context cache; they **do not share a counter**. Namespaces must be unique across processes, making UUID v4 safer than a `test-1` suffix. If CI sharding runs multiple jobs simultaneously, maintain per-run identity as well.

### When Not to Use Parallel Execution

A migration integration suite altering global DB schemas, cluster-wide RBAC tests, or chaos tests stopping a shared broker should typically run **serially in a dedicated environment**. `@Isolated` is scoped to one JUnit process and provides no locking across CI jobs.

## 32. Common Pitfalls

| Symptom | Cause | Fix |
| --- | --- | --- |
| Passes alone, fails in parallel | Shared row/topic/queue/resource | Create dedicated namespace and assert owner filtering |
| Unique key violation between tests | PK omits namespace | Composite key or DB/schema per test |
| Rows from another test appear in results | Query lacks namespace predicate | Mandatory tenant/test scoping on every read |
| `@AfterEach` deletes neighboring test's data | Overly broad cleanup | Delete by exact `runId`/prefix |
| Dedicated PostgreSQL schema yet writes go to `public` | DataSource `search_path`/Flyway mismatch | Configure pool/schema from startup and assert `current_schema()` |
| Kafka test misses messages | Shared group/rebalance, consumer not ready, `latest` offset | Unique topic+group; wait for assignment |
| Kafka sees duplicate/stale records | Reused fixed topic/group | Unique topic, group, correlation |
| Rabbit queue deleted while Test B runs | Shared queue name and lifecycle | Queue/exchange per run |
| Unexpected Redis cache misses | Another test's `FLUSHDB` | Unique prefix, TTL, no global flush |
| Context keeps old container JDBC URL | Static container stopped while context cached | `@DirtiesContext` or align lifecycles |
| `@Transactional` does not roll back HTTP/Kafka | Separate thread/transaction | Explicit cleanup and integration assertions |
| `@DirtiesContext` slows CI without fixing broker collision | Resetting the wrong layer | Isolate broker resources |
| Flaky Kafka topic deletion | Async deletion/broker policy | Bounded polling, stop consumers first |
| Parallel tests overwrite same System property | JVM-global mutable state | Inject config or `ResourceLock` |
| Invalid characters in namespace name | Raw branch name/input used | Sanitize/allowlist generated IDs |
| K8s delete destroys colleague's namespace | Owner label unverified | RBAC + exact generated name |
| E2E suite hits quotas | Too many containers/topics | Cap parallelism, cleanup + resource budget |

## 33. QA Checklist Before Merging

- [ ] Is the test isolation scope defined: per method, class, suite, process, or CI job?
- [ ] Are all resources named with a unique/safe `runId`?
- [ ] Do schema names satisfy PostgreSQL identifier length/character rules?
- [ ] Does database/schema provisioning complete before migrations/app startup?
- [ ] With pooled connections, does every connection see the intended schema?
- [ ] When using row namespaces, do all `SELECT`/`UPDATE`/`DELETE` queries include the namespace predicate?
- [ ] Do unique constraints/indexes include the namespace where needed?
- [ ] Does teardown delete only owner-owned resources?
- [ ] Do `@AfterEach` and exception/failure paths execute cleanup?
- [ ] Are orphan resources handled when CI is killed?
- [ ] Are `FLUSHALL`/`TRUNCATE`/`DROP public` avoided in shared environments?
- [ ] Are `@Transactional` limitations with async/brokers/HTTP understood?
- [ ] Is `@DirtiesContext` used only when context refresh is needed, never as broker cleanup?
- [ ] Are both Kafka topics and consumer groups isolated?
- [ ] Are Kafka retry/DLT/transactional IDs isolated if used?
- [ ] Are Kafka consumers ready before publishing?
- [ ] Do Rabbit queues/exchanges/bindings/vhosts have separate owners?
- [ ] Do temporary Rabbit queue semantics match what is being tested?
- [ ] Do Redis keys/streams have prefixes/TTLs and safe cleanup?
- [ ] Do S3/bucket objects use dedicated prefixes and exact-scope deletion?
- [ ] Are Kubernetes namespace labels/RBAC/quotas designed?
- [ ] Are JUnit parallelism and Gradle forks factored into total concurrency?
- [ ] Are global System properties/Clocks/metrics/temp files isolated?
- [ ] Does Testcontainers static container lifecycle align with Spring context caching?
- [ ] Are Docker/CI resource limits accounted for?
- [ ] Is there an actual concurrent test verifying no cross-reading occurs?
- [ ] Have the suite/CI and real reports been checked before claiming tests PASS?

## 34. Hands-On Exercises

1. Run `IsolationNamesTest` without Docker and verify generated IDs are valid.
2. Run `OrderStoreIsolationTest` with PostgreSQL Testcontainers.
3. Intentionally remove `WHERE test_namespace = ?` from `OrderStore.count` and observe which test catches it.
4. Intentionally change the PK to `order_id` alone and observe collision across two namespaces.
5. Change `cleanupOwnedRows` to an unconditional `DELETE FROM it_orders` in a sandbox and run in parallel to see the hazard.
6. Add a second test class with its own `PostgreSQLContainer`; observe resources and context lifecycle.
7. Try a single shared PostgreSQL container with a separate schema per class; assert `SELECT current_schema()` per class.
8. Add Flyway migrations per class schema and verify the history table lands in the right place.
9. Add a Kafka Testcontainer and create two topic+consumer group pairs for two `runId`s.
10. Intentionally share `group.id` and observe rebalances/partition competition.
11. Add retry/DLT topics per `runId` and clean up only owned topics.
12. Create a RabbitMQ queue/exchange per `runId`, publish/consume/clean up the exact resources.
13. Use `AnonymousQueue` and inspect its lifecycle when the consumer disconnects.
14. Add a Redis Testcontainer; write two keys with the same business ID under two prefixes.
15. Delete only one run's prefix and verify the other run's data remains.
16. Write two objects with the same filename under two S3 prefixes and clean up one run.
17. Create a test K8s namespace with labels and quotas, and clean up with owner validation.
18. On a pure JUnit suite **not using the Testcontainers JUnit extension**, try enabling 4 JUnit threads and measure failures/resources; keep the `@Testcontainers` example sequential.
19. Try `@ResourceLock` to serialize a legacy global resource and explain why it does not lock across JVMs.
20. Simulate killing CI mid-run and design an orphan sweeper that deletes only expired test-owned resources.
21. Measure test time before and after raising parallelism; pick a level with real net gain.
22. Run a scenario with `@Async`/message listeners and verify cleanup occurs only after processing completes.

## 35. References

- [Spring Boot 3.3 — Testcontainers](https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html): `@ServiceConnection` and integration with Spring Boot-managed connections.
- [Spring Boot 3.3 — Database Initialization](https://docs.spring.io/spring-boot/3.3/how-to/data-initialization.html): `spring.sql.init.mode=always`, `schema.sql`, migrations.
- [Testcontainers for Java — JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Testcontainers`, `@Container`, and lifecycle; see warnings on parallel execution of the extension.
- [Testcontainers PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/): `PostgreSQLContainer`.
- [Spring Framework — TestContext Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): context reuse.
- [Spring Kafka Reference — Topic Configuration](https://docs.spring.io/spring-kafka/reference/kafka/configuring-topics.html): `KafkaAdmin` and `NewTopic`.
- [Apache Kafka AdminClient API](https://kafka.apache.org/documentation/): topic creation/deletion, consumer groups/offsets.
- [Spring AMQP — Broker Configuration](https://docs.spring.io/spring-amqp/reference/amqp/broker-configuration.html): `RabbitAdmin`, queues, exchanges, bindings, temporary/anonymous queues.
- [RabbitMQ — Virtual Hosts](https://www.rabbitmq.com/docs/vhosts): vhosts as broker namespaces.
- [Spring Data Redis Reference](https://docs.spring.io/spring-data/redis/reference/): `RedisTemplate`, key prefixes, and TTL.
- [JUnit 5 — Parallel Execution](https://junit.org/junit5/docs/current/user-guide/#writing-tests-parallel-execution): `@Execution`, `@ResourceLock`, `@Isolated`.
- [Gradle — Testing in Java Projects](https://docs.gradle.org/current/userguide/java_testing.html): forks and test reports.
- [Kubernetes — Namespaces](https://kubernetes.io/docs/concepts/overview/working-with-objects/namespaces/): resource name scope, labels, and supplementary RBAC/NetworkPolicy.
- [JUnit Jupiter User Guide](https://junit.org/junit5/docs/current/user-guide/): test lifecycles/assertions.

## 36. Conclusion

**Resource isolation is the prerequisite for meaningful parallel testing.** A UUID or `@Transactional` alone will not cover everything: you must choose the right boundary (database, schema, row namespace, Kafka topic and consumer group, RabbitMQ queue/exchange, Redis key prefix, object storage prefix, or Kubernetes namespace), propagate that identity through **every operation**, and clean up **only the resources you created**.

With Spring Boot 3.3.5, Testcontainers `@ServiceConnection` provides real PostgreSQL without hard-coding endpoints, while `test_namespace` combined with a composite primary key lets multiple test methods share a table without stepping on each other. Kafka requires isolating both topics **and groups** along with retry/DLT; RabbitMQ requires queue/exchange/binding and vhost discipline; Redis requires avoiding global flushes; K8s requires labels/RBAC/quotas. JUnit parallelism, Gradle forks, and Spring's context cache determine whether that isolation holds across the entire suite and CI.

The main code illustrates **10 test methods** (6 unit naming + 4 PostgreSQL integration), yet only after running real Gradle/Docker and inspecting JUnit reports can you state how many tests PASS. Protect ownership, readiness, resource lifetimes, and cleanup before raising concurrency so CI becomes faster without losing reliability.