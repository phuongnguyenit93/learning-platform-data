# Isolating Databases, Directories, Ports, and Shared Resources

When tests run in parallel or execute asynchronous tasks, multiple tests can access the same database, directory, network port, cache, message broker, or JVM state simultaneously. If two tests modify the same resource without dedicated boundaries, outcomes depend on timing: one test might read another test's data, delete a file in use, or bind to the same port.

In Spring Framework Testing, resource isolation is part of reliable test design. Each test should own its data and resources, assign unique names to shared resources, and release them upon completion. Only serialize execution when a global resource cannot be separated.

## 1. Why do parallel tests easily affect one another?

JUnit Jupiter can run multiple test methods or test classes concurrently. Spring TestContext can also reuse a cached application context across tests. This saves Spring startup time, but it means multiple tests may share the same singleton beans and access the same external services.

Common conflicts:

- Two tests insert the same data row or use the same identifier in a database.
- One test deletes data while another test is reading or updating it.
- Multiple tests create files with the same name in `target/test-output` or a shared temp directory.
- Two test servers attempt to bind to the same fixed port.
- One test alters a system property, locale, or timezone while another test is reading it.
- Multiple tests send messages to the same queue or share a consumer group and consume each other's messages.
- One test modifies mutable state in a singleton bean or static cache used by another test.

A test passing on its own does not prove it is safe when run alongside other tests. Resource boundaries must be designed so execution order and timing do not alter the outcome.

## 2. Principles for designing isolation boundaries

For every resource a test uses, determine who owns it, its sharing scope, and when it is released:

| Resource | Preferred isolation approach | When locking is needed |
|---|---|---|
| Database records | Per-test data, foreign keys, and cleanup by identifier | When an operation must affect the entire database or a shared table |
| Database/schema | Dedicated database or schema per suite/test | When multiple tests reset schemas or run destructive migrations together |
| Directories/files | `@TempDir`, unique filenames | When a test must use a fixed path |
| Network ports | Random OS-assigned port | When a protocol or tool forces a fixed port |
| Cache | Namespaced keys, delete only owned keys | When a test must flush the global cache |
| Queue/topic/consumer group | Dedicated names per test or suite | When separate namespaces cannot be created |
| System property/locale/timezone | Restore previous value in `finally` | When multiple tests access the same JVM state |
| Spring singleton bean | Avoid mutable shared state, create separate instances when needed | When global state cannot be eliminated |

Prefer allocating dedicated resources rather than sharing and attempting to clean up afterward. Dedicated resources reduce order dependencies; cleanup is still necessary to prevent resource leaks after tests finish.

## 3. Isolating database data

### Using separate data for each test

A simple approach is generating unique identifiers for test data. Do not use fixed codes like `TEST-1` if multiple tests may insert into a table with unique constraints simultaneously.

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class CustomerServiceTests {

    @Test
    void createsCustomerWithUniqueTestData() {
        String email = "test-" + UUID.randomUUID() + "@example.test";

        Customer customer = customerService.create("Mai", email);

        assertThat(customer.email()).isEqualTo(email);
    }
}
```

Unique identifiers prevent concurrent tests from overwriting each other's data. If a test creates multiple related records, use the same test identifier as a prefix or correlation field so the exact data group can be queried and cleaned up.

### Cleanup by test identifier

If a test must commit data or invoke a real server, test transaction rollback may not clean up the data. In that case, cleanup by a dedicated identifier is a clear option:

```java
import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class CustomerApiIntegrationTests {

    private String testRunId;

    @BeforeEach
    void createTestNamespace() {
        testRunId = "it-" + UUID.randomUUID();
    }

    @Test
    void createsCustomer() {
        String email = testRunId + "@example.test";
        // Send request to create customer using an email in the test's namespace.
    }

    @AfterEach
    void removeTestData() {
        customerRepository.deleteByEmailStartingWith(testRunId);
    }
}
```

Cleanup must stay scoped to the test's namespace. Avoid `DELETE FROM customers` or `TRUNCATE` on a shared table while other tests might be running. If cleanup fails, let the test or suite fail explicitly instead of silently leaving data behind that affects subsequent runs.

### Understanding transaction rollback properly in Spring Test

Spring TestContext supports `@Transactional` on test methods. By default, test transactions roll back after the test, which is useful when the test directly invokes synchronous services on the same thread:

```java
import org.junit.jupiter.api.Test;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
class CustomerServiceTransactionalTests {

    @Test
    @Transactional
    void createsCustomerInsideTestTransaction() {
        customerService.create("Mai", "mai@example.test");
        // Test transaction is rolled back after the method.
    }
}
```

However, this rollback is not a universal isolation mechanism for all operations:

- Spring transactions are typically bound to the current thread. Tasks run via `@Async`, executors, or schedulers use other threads and do not automatically join the test's transaction.
- With `@SpringBootTest(webEnvironment = RANDOM_PORT)`, HTTP requests are processed on server threads. The test method's transaction does not wrap transactions executed by those requests.
- A service using `REQUIRES_NEW` can commit an independent transaction; rolling back the outer transaction does not undo what was already committed.
- Messages sent to a broker, files written, or HTTP calls to external systems are not rolled back alongside the database transaction.

Therefore, if a test calls an API through a server or launches asynchronous tasks, use isolated per-test data and explicit cleanup. Do not assume adding `@Transactional` to the test cleans up all side effects.

### Dedicated database/schema per suite or test

When tests need to reset data, run migrations, or verify constraints across multiple tables, a dedicated database or schema per test suite can be safer than a shared database. With Testcontainers, you can run a shared suite-level database container while creating separate schemas or data namespaces per test.

A shared container reduces startup cost; it does not automatically isolate records inside the database. If multiple tests run migrations, truncates, or schema changes, separate schemas/databases or serialize those specific operations.

Do not run whole-database reset commands in `@BeforeEach` while other tests share the database. Resetting can wipe out another test's data even if each test has its own transaction.

## 4. Isolating directories and files with @TempDir

JUnit Jupiter provides `@TempDir` to allocate a dedicated temporary directory for a test. You can receive a `Path` via a test method parameter or an annotated field. JUnit manages its lifecycle and deletes the directory by default once the usage scope ends.

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.assertj.core.api.Assertions.assertThat;

class ReportWriterTests {

    @Test
    void writesReportToItsOwnDirectory(@TempDir Path tempDir)
            throws IOException {
        Path report = tempDir.resolve("report.txt");

        Files.writeString(report, "report for this test");

        assertThat(Files.readString(report))
            .isEqualTo("report for this test");
    }
}
```

Each test execution receives its own temporary directory, so two tests both creating `report.txt` will not collide. Prefer passing `Path` into the component under test so it writes to the directory allocated by the test.

If the component accepts a directory via constructor or configuration, pass `tempDir` directly:

```java
@Test
void exportsIntoTemporaryFolder(@TempDir Path tempDir) {
    ReportExporter exporter = new ReportExporter(tempDir);

    Path generated = exporter.export("monthly");

    assertThat(generated).exists();
    assertThat(generated.getParent()).isEqualTo(tempDir);
}
```

Avoid writing test files to a fixed path such as `build/reports/test-output/report.txt` if tests may run concurrently. If you need to test a file with a fixed name, place that name inside `@TempDir`.

`@TempDir` can be placed at the method or class level. Method scope creates a separate directory per test method and is usually the best choice when tests write/delete files. Class scope shares the directory across methods in the class; use it only when methods genuinely need to share fixtures and either do not run concurrently or each method uses its own subdirectory.

## 5. Allocating dynamic network ports

Test servers should not bind to a fixed port like `8080` or `8081`. That port may already be used by another application or a concurrently running test. Let the operating system assign an available port.

With Spring Boot, `RANDOM_PORT` starts the server on a random port and `@LocalServerPort` provides the actual port:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ApiIntegrationTests {

    @LocalServerPort
    private int port;

    @Test
    void respondsOnTheAssignedPort() {
        String baseUrl = "http://localhost:" + port;
        // Send HTTP request to baseUrl.
    }
}
```

If a test starts a mock server directly, use an API supporting port `0` or the library's random port mechanism. For example, `MockWebServer.start()` automatically selects an available port; retrieve the URL from `server.url("/")` instead of assuming a specific port.

Do not manually probe for an apparently free port and then close the socket before the real server binds to it. Between checking and binding, another process can claim the port (a race condition). Let the server itself bind to port `0`, then read the assigned port.

With containers, read the host and mapped port provided by Testcontainers, such as `getHost()` and `getMappedPort(...)`. Do not hard-code the container's internal port as the host port; Docker can map it to a different port.

## 6. Isolating Spring application contexts and singleton beans

Spring TestContext caches application contexts to avoid restarting identical contexts for every test. Tests sharing the same configuration can receive the same singleton bean instances. This helps speed, but requires care when beans contain mutable state.

Example of a bean holding a shared list:

```java
@Component
class RequestHistory {

    private final List<String> requests = new ArrayList<>();

    void add(String request) {
        requests.add(request);
    }

    List<String> all() {
        return List.copyOf(requests);
    }
}
```

If two tests share the context and call `add(...)`, each test can read extra data produced by the other. A better approach is designing beans without test-specific state, passing state via requests, or creating dedicated collaborators in an appropriate scope. If a bean must hold state, provide a controlled reset mechanism and ensure it is not reset while another test is using it.

`@DirtiesContext` marks the context for cache eviction and closes it at the chosen point. It is useful when a test corrupts context configuration or state beyond safe reuse. However, it is not a synchronization lock and does not clean up data in databases, queues, filesystems, or external services. Applying this annotation to every test can slow down the suite without resolving external resource conflicts.

## 7. Using JUnit ResourceLock for global state

Some state cannot easily be allocated per test, such as system properties, default locale, timezone, or static singletons. JUnit Jupiter supports `@ResourceLock` to serialize tests declaring use of the same resource.

Example of a test modifying a system property:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.junit.jupiter.api.parallel.Resources;

import static org.assertj.core.api.Assertions.assertThat;

@ResourceLock(value = Resources.SYSTEM_PROPERTIES,
              mode = ResourceAccessMode.READ_WRITE)
class SystemPropertyTests {

    @Test
    void readsFeatureFlag() {
        String previous = System.getProperty("feature.mode");
        try {
            System.setProperty("feature.mode", "test");

            assertThat(System.getProperty("feature.mode"))
                .isEqualTo("test");
        }
        finally {
            if (previous == null) {
                System.clearProperty("feature.mode");
            }
            else {
                System.setProperty("feature.mode", previous);
            }
        }
    }
}
```

`ResourceAccessMode.READ_WRITE` declares that the test both reads and modifies the resource. Other tests declaring the same resource lock are coordinated by JUnit so they do not run concurrently with the test holding write access. For an application-defined resource, use a custom lock name:

```java
@ResourceLock(value = "shared-test-cache",
              mode = ResourceAccessMode.READ_WRITE)
class CacheResetTests {
    // Test operates on global cache.
}
```

A resource lock only coordinates tests within the corresponding JUnit Jupiter execution. It does not lock tests running in another JVM fork, another Gradle worker, or another CI job. For databases, queues, or filesystems shared across multiple processes, use separate namespaces, resource-layer locks, or separated environments.

If a class must run exclusively relative to all other tests in the same JUnit engine, `@Isolated` can be used at the class level. This is a stronger measure; use it only when the test genuinely affects global state and cannot be isolated by specific resources.

## 8. Configuring parallel execution in JUnit Jupiter

JUnit Jupiter enables parallel execution in `src/test/resources/junit-platform.properties`:

```properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = concurrent
junit.jupiter.execution.parallel.mode.classes.default = concurrent
```

Concurrent scope can be controlled with `@Execution`:

```java
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

@Execution(ExecutionMode.CONCURRENT)
class IndependentServiceTests {
    // Test methods can run concurrently.
}
```

Enable parallel execution only after tests can run independently. If tests still depend on ordering, edit the same file, or reset the same database, turning on concurrency will only make failures happen more often. `@ResourceLock` and `@Isolated` are coordination tools for parts that cannot yet be separated; they do not replace dedicated data design.

Note that build tools can run multiple JVM forks or multiple test tasks simultaneously. JUnit lock configuration within one engine does not coordinate across those JVMs. If shared resources span beyond one process, use unique names per build/test run or a locking mechanism honored by all processes.

## 9. Isolating caches, message brokers, and external services

### Caches

If multiple tests share Redis or a cache service, create namespaced keys such as `testRunId + ":customer:" + customerId`. Cleanup deletes only keys belonging to that namespace. Avoid flushing the entire shared cache because it can delete data belonging to other tests or services.

### Message brokers

With Kafka, RabbitMQ, or similar brokers, use dedicated topics, queues, routing keys, or consumer groups per test/suite when possible. If the broker does not support per-test resources, include a unique correlation ID in messages and only read messages belonging to the current test. Do not use a single shared queue and assume each test receives only the message it just sent.

### Mock servers and test services

Each test should own its own mock server or use a suite-level server with synchronized, resettable expectations. Use dynamic ports, clear response queues after tests, and avoid letting concurrent tests share a mutable mock server without namespacing.

### File resources or object storage

With S3-compatible storage or other storage services, use a dedicated bucket/prefix per test run if the environment allows. Clean up only that prefix after the test. Avoid deleting shared buckets or folders.

## 10. Synchronizing asynchronous tasks without fixed sleep

Resource isolation solves conflicts between tests; synchronization solves tests observing results before asynchronous work finishes. Do not use fixed `Thread.sleep(...)` to guess when a worker has written data. Wait on a bounded condition or use an appropriate reactive testing tool.

Example using Awaitility to wait for a record to appear:

```java
import static org.awaitility.Awaitility.await;

import java.time.Duration;

await()
    .atMost(Duration.ofSeconds(5))
    .untilAsserted(() ->
        assertThat(repository.existsById(orderId)).isTrue()
    );
```

The awaited condition should be tied to the test's own data. If a test waits on a shared record such as `latestOrder`, it can still read another test's result. Timeouts bound the wait duration; they do not make resources isolated.

For Reactor publishers, use `StepVerifier` to assert items and terminal signals. If a test checks side effects produced by a scheduler or `@Async`, wait for the specific side effect with a timeout and clean up data afterward.

## 11. A test pattern combining multiple isolation boundaries

The following example illustrates an integration test with a random-port server, isolated data, and a dedicated temporary directory:

```java
import java.nio.file.Path;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ExportIntegrationTests {

    @LocalServerPort
    private int port;

    @Autowired
    private ExportRepository repository;

    @Test
    void exportsOwnCustomerData(@TempDir Path tempDir) {
        String testId = "it-" + UUID.randomUUID();
        Path output = tempDir.resolve("export.csv");

        try {
            repository.save(new ExportRecord(testId, "Mai"));

            String baseUrl = "http://localhost:" + port;
            // Call export endpoint with testId and write result to tempDir.

            assertThat(output).exists();
            assertThat(repository.existsById(testId)).isTrue();
        }
        finally {
            repository.deleteById(testId);
        }
    }
}
```

In a real test, the HTTP client call and file writing would be implemented against the application's endpoint. Three independent boundaries are established: `RANDOM_PORT` avoids port conflicts, `testId` avoids data collisions, and `@TempDir` avoids file collisions. Because the request runs on a separate server thread, database cleanup is performed explicitly instead of relying on the test method's transaction rollback.

## 12. Pre-parallelism checklist

For each test or test class, verify:

1. Database data has unique identifiers and cleanup does not delete other tests' data.
2. No whole-table or schema resets occur while other tests are using them.
3. Files are written inside `@TempDir` or a uniquely namespaced directory.
4. Servers bind to random ports and tests read the assigned port instead of using fixed ports.
5. Caches, queues, topics, and consumer groups have separate namespaces or explicit synchronization.
6. No mutable state in singleton beans or static fields is mutated concurrently by multiple tests.
7. System properties, locale, timezone, and JVM-wide state are restored; `@ResourceLock` is used when needed.
8. Asynchronous tasks are awaited via bounded conditions rather than fixed `sleep`.
9. All servers, containers, subscriptions, and temporary resources are closed or cleaned up in the test lifecycle.
10. If the build runs multiple JVMs or CI jobs, isolation mechanisms hold across processes, not only within a single JUnit engine.

Parallel tests are stable when each test has clearly owned data and resources. Use transaction rollback for synchronous work inside the test transaction, `@TempDir` for files, dynamic ports for servers, separate namespaces for external services, and resource locks for indivisible global state. Once those boundaries are established, tests can run concurrently without depending on the order or timing of other tests.
