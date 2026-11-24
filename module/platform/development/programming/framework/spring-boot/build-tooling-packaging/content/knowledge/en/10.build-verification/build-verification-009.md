# Managing Test Resources and Processes So Builds Never Hang

## 1. Lesson Objectives

When running `mvn test`, `mvn verify`, or `gradle test`, a build can **fail to finish** even without compilation or assertion errors. Sometimes a test waits indefinitely on a socket, database, or async result; sometimes **all tests PASS yet the test JVM never exits** because a thread or child process remains alive; other times the build tool is downloading dependencies, waiting on a lock, waiting on a container, or aggregating reports.

In Spring Boot projects, this happens more frequently because integration tests can launch an `ApplicationContext`, embedded servers, connection pools, message consumers, scheduled tasks, Testcontainers, and external services.

The goal is **systematic prevention, detection, and remediation**, not merely setting an aggressively short timeout and ignoring failures.

After this lesson, you will be able to:

- Distinguish slow tests, deadlocks, hung I/O operations, and **forked JVMs failing to exit after tests finish**.
- Design tests with deadlines that close `ExecutorService`, sockets, files, HTTP connections, and `AutoCloseable` resources.
- Use JUnit Jupiter `@Timeout`, `Future.get(timeout)`, and default timeout configuration without assuming interrupts can kill arbitrary blocking calls.
- Constrain test processes via Maven Surefire/Failsafe and the Gradle `Test` task to prevent CPU/RAM oversubscription.
- Write Spring Boot integration tests using random ports and managing `ApplicationContext`/Testcontainers lifecycles properly.
- Capture thread dumps and build reports **before forcibly terminating**, identifying live threads and held resources.
- Layer deadlines across tests, worker processes, and CI jobs so builds always produce an observable outcome.

**Context:** Java 17+, JUnit Jupiter, Maven/Gradle, Spring Boot 3.x. The Maven hands-on example uses Spring Boot `3.5.16` and Maven Surefire `3.5.5` as concrete released versions; real projects must choose versions compatible with their Boot/JDK line.

## 2. First: "Hanging" Has Several Distinct Causes

A console screen unchanged for a few minutes **is not enough** to conclude a process is hung. Identify **which stage is stalled**.

| Symptom | Likely cause | What to inspect |
| --- | --- | --- |
| No test-start messages yet | Downloading artifacts/plugins, resolving dependencies, compiling, Gradle lock, starting daemon | Build logs with `--info`/`-X`, repositories, CPU/network |
| Running a test, log stops at HTTP/DB | I/O missing timeout, lock, slow SQL query, unready server | Test name, client timeouts, thread dump, service logs |
| Test waiting on `Future.get()` or latch | Incomplete task, deadlock, thread pool starvation | Worker stack traces, executor queues, deadlines |
| Prints "Tests run: ... Failures: 0" yet Maven does not exit | Non-daemon threads, shutdown hooks, forked JVM not exiting | Thread dump of the **forked test JVM**, Surefire reports |
| Gradle `:test` still running after last test | Test worker not exiting, unfinished task/finalizer, daemon processing | Gradle `--info`, test worker PID, thread dump |
| CI times out while local runs pass | Excessive parallelism, insufficient CPU/RAM, slow services, clock/timing/env differences | Resource metrics, concurrency, env, logs, and reports |
| Flaky behavior: passes sometimes, hangs others | Fixed ports, shared files/data, race conditions, missing readiness wait | Port/test isolation, retries, and scheduling |
| Test process vanishes with fork-crashed message | OOM, `System.exit`, JVM crash or killed process, not necessarily a hang | `hs_err_pid*.log`, heap usage, fork dumps |

An effective diagnostic model separates four layers:

1. **Timeout inside an operation**: HTTP connect/read, JDBC acquire, `Future.get`.
2. **Timeout on a test/lifecycle method**: JUnit `@Timeout`.
3. **Timeout on a process running multiple tests**: Surefire fork or Gradle `Test` task.
4. **Timeout on the entire pipeline/job**: CI provider or process supervisor.

All four layers **complement** each other; no single layer fully replaces the others.

## 3. Java Resource Lifecycle: Close Where You Open

### 3.1. Common Hang-Causing Resources

| Resource type | Creation | Proper termination |
| --- | --- | --- |
| `AutoCloseable` files/sockets/JDBC streams | `Files.newInputStream`, `Socket`, `Connection` | `try-with-resources`, or explicit lifecycle close |
| `ExecutorService` | `Executors.newSingleThreadExecutor()` | `shutdown()`, `awaitTermination()`; `shutdownNow()` when needed |
| Manually created thread | `new Thread(...).start()` | Stop flag/interrupt, `join(timeout)`, avoid infinite loops |
| Temporary HTTP server | Embedded server, `HttpServer`, `ServerSocket` | `stop`/`close`, wait for shutdown |
| Spring `ApplicationContext` | `@SpringBootTest` or manual `SpringApplication.run` | Spring TestContext cache, or `close` for manually created contexts |
| External container | Testcontainers, Docker Compose, child process | Manage test/app lifecycle properly and stop/cleanup |
| Connection pool, scheduler, consumer | Spring-managed bean or manually created | `@PreDestroy`/bean destroy callback; close when context actually closes |
| `ThreadLocal`, mutable static state | Static fields or reused thread pools | Clear state after tests, call `remove()` as appropriate |

Principles:

- **Clear ownership:** whoever creates a resource is responsible for closing it, or transfers ownership via an API with an explicit contract.
- **Cleanup lives in `finally`/`try-with-resources` or `@AfterEach`/`@AfterAll`**, never only at the end of the "happy path."
- **Do not equate "test assertions finished" with "all resources stopped."**
- **Do not kill every JVM on the machine** when only one test worker is stuck; locate the exact PID first and capture evidence.

### 3.2. try-with-resources

In Java 17, `AutoCloseable` ensures resources are released even when exceptions occur:

~~~java
package com.example.build;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class FileReadExample {
    private FileReadExample() {}

    public static long countBytes(Path path) throws IOException {
        try (var input = Files.newInputStream(path)) {
            long count = 0;
            byte[] buffer = new byte[4096];
            int n;
            while ((n = input.read(buffer)) != -1) {
                count += n;
            }
            return count;
        }
    }
}
~~~

This is a complete Java 17+ class without `main`. It returns the actual byte count when reading succeeds; if the file is missing or unreadable, it throws `IOException` and closes the opened stream.

**Limitation:** `try-with-resources` guarantees `close` is called along exit control flow, yet **cannot unblock** a `read()` call that never returns. For network I/O, configure explicit connect/read/request timeouts.

### 3.3. ExecutorService in Java 17

Do not write `try (ExecutorService executor = ...)` in projects locked to Java 17: in Java 17, `ExecutorService` **does not implement `AutoCloseable`**. The consistent Java 17 pattern is `shutdown`/`awaitTermination` in `finally` or test teardown.

A bounded cleanup pattern:

~~~java
executor.shutdown();
if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
    executor.shutdownNow();
    if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
        throw new IllegalStateException("Executor did not stop");
    }
}
~~~

This is a **snippet inside a method** with an `ExecutorService executor` (which may declare `throws InterruptedException`); it is not a complete Java file. `shutdownNow()` only **requests interruption** of running tasks and cannot guarantee stopping tasks that ignore interrupts or block in native I/O. If threads truly refuse to stop, tests/builds must fail and process/CI timeouts handle recovery.

Never retain unbounded shared static thread pools across tests without clear ownership and lifecycle.

## 4. Preventing Unbounded Waits at the Source

### 4.1. Futures, Latches, and Synchronization Primitives

Calls such as `future.get()`, `latch.await()`, and `thread.join()` without **a deadline** can wait forever if a task never finishes.

Prefer:

~~~java
String value = future.get(2, TimeUnit.SECONDS);
boolean completed = latch.await(2, TimeUnit.SECONDS);
worker.join(2000);
~~~

These three lines are **API snippets** assuming declared variables. `Future.get(timeout)` throws `TimeoutException` if incomplete; `CountDownLatch.await(timeout)` returns `false` on expiry; `Thread.join(timeout)` stops waiting on expiry without proving the worker exited, so check `worker.isAlive()` afterward.

For async workflows polling readiness, always maintain a **total deadline**, a reasonable delay between checks, and a clear failure message. Never write `while (!ready) { Thread.sleep(100); }` without a bound.

### 4.2. HTTP Connect and Request Timeouts

Java 17 includes `java.net.http.HttpClient`. Standalone helper example:

~~~java
package com.example.build;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class BoundedHttpClient {
    private BoundedHttpClient() {}

    public static String get(String url)
            throws IOException, InterruptedException {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build();

        HttpRequest request = HttpRequest.newBuilder(URI.create(url))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<String> response =
                client.send(request, HttpResponse.BodyHandlers.ofString());
        return response.body();
    }
}
~~~

This is a valid Java 17+ class using the JDK HTTP API without Spring Web dependencies. It returns only the response body on success; it **has no fixed stdout** and does not assume endpoints are always up. `connectTimeout` bounds connection setup, `HttpRequest.timeout` bounds the request, while DNS/OS/native operations and special environments may behave differently. For other clients/frameworks (RestClient, WebClient, JDBC), configure timeouts using that client's actual API.

### 4.3. Databases and Connection Pools

When tests use a database, never let the pool wait too long or indefinitely for connections. Example with HikariCP when Spring Boot configures a Hikari DataSource:

~~~properties
spring.datasource.hikari.connection-timeout=3000
spring.datasource.hikari.validation-timeout=1000
~~~

Both values are in **milliseconds** per Hikari settings: roughly 3 seconds max for connection acquisition and 1 second for validation. They **are not** timeouts for running SQL queries. Query timeouts, JDBC driver socket/read timeouts, and transaction timeouts are separate layers configured per database/driver/framework.

If tests use stubs/mocks, do not spin up a full database and connection pool just to test pure calculation logic.

### 4.4. Servers/Sockets Waiting on `accept`

`ServerSocket.accept()` is blocking. Bound it via `setSoTimeout` and close the socket when done. Never hardcode port `8080` or `5432` across parallel tests when services can allocate dynamic ports.

In Spring Boot HTTP integration tests, prefer `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` whenever an embedded HTTP server is actually needed. This is a **test scope** setting, not a production server port configuration.

## 5. Sample Maven Project Verifying Timeouts and Cleanup

The complete example below **compiles and runs tests** with Java 17+, Maven 3.9+, and repository access for Spring Boot/JUnit dependencies. No Docker, database, or external HTTP server is required to run the baseline tests.

### 5.1. File Layout

~~~text
bounded-build/
├── pom.xml
├── mvnw                  # If generated via Spring Initializr / Maven Wrapper
├── mvnw.cmd
└── src/
    ├── main/java/com/example/build/
    │   └── BoundedBuildApplication.java
    └── test/
        ├── java/com/example/build/
        │   ├── BoundedExecutorTest.java
        │   └── ApplicationContextTest.java
        └── resources/
            └── junit-platform.properties
~~~

You can generate a Maven Spring Boot project via Spring Initializr with Java 17, Maven, `spring-boot-starter`, and `spring-boot-starter-test`, then replace the source files accordingly. If creating the tree manually without a wrapper, use `mvn` instead of `./mvnw`.

### 5.2. Complete `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>bounded-build</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.5</version>
                <configuration>
                    <forkCount>1</forkCount>
                    <reuseForks>true</reuseForks>
                    <forkedProcessTimeoutInSeconds>900</forkedProcessTimeoutInSeconds>
                    <forkedProcessExitTimeoutInSeconds>30</forkedProcessExitTimeoutInSeconds>
                    <argLine>-Xmx512m</argLine>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Explaining `maven-surefire-plugin`:

- `forkCount=1`: one forked test JVM at a time for this module; in a multi-module Maven reactor or with Maven `-T`, total processes may be higher.
- `reuseForks=true`: reuses the fork across multiple test classes; saves startup time while risking accumulated state or thread leaks from earlier tests.
- `forkedProcessTimeoutInSeconds=900`: limits **the lifetime of one forked test process**, not "900 seconds per test method." If a normal suite in one fork legitimately exceeds 900 seconds, this is too low: base it on real measurements.
- `forkedProcessExitTimeoutInSeconds=30`: after tests finish, gives the fork at most ~30 seconds to complete shutdown. **Distinct** from timeouts while tests are running.
- `argLine=-Xmx512m`: sets max heap for the forked test JVM; size it to fit CI container memory alongside other processes rather than treating it as universal.

**Important:** Surefire timeouts do not automatically clean up databases, containers, or threads cleanly. They provide a safety boundary for the fork; on expiry, the test process is killed and the build fails. Base budgets on benchmarks instead of copying sample numbers blindly across projects.

When using Spring Boot starter parent, many plugin versions and test dependencies are already managed. The example pins Surefire `3.5.5` intentionally to make configuration explicit; real projects should review compatibility instead of overriding team-managed plugin versions needlessly.

### 5.3. Main Spring Boot Application

Create `src/main/java/com/example/build/BoundedBuildApplication.java`:

~~~java
package com.example.build;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BoundedBuildApplication {

    public static void main(String[] args) {
        SpringApplication.run(BoundedBuildApplication.class, args);
    }
}
~~~

This is the complete Java class for the example module. With no Spring Web starter, the app does not start an HTTP server or bind port 8080 during `@SpringBootTest`.

### 5.4. JUnit: Bounded Future and Guaranteed Executor Cleanup

Create `src/test/java/com/example/build/BoundedExecutorTest.java`:

~~~java
package com.example.build;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class BoundedExecutorTest {

    private final ExecutorService executor =
            Executors.newSingleThreadExecutor();

    @AfterEach
    void tearDown() throws InterruptedException {
        executor.shutdownNow();
        assertTrue(executor.awaitTermination(2, TimeUnit.SECONDS),
                "Executor did not terminate after 2 seconds");
    }

    @Test
    @Timeout(value = 5, unit = TimeUnit.SECONDS)
    void resultArrivesBeforeDeadline() throws Exception {
        Future<Integer> answer = executor.submit(() -> 40 + 2);
        assertEquals(42, answer.get(1, TimeUnit.SECONDS).intValue());
    }
}
~~~

All classes are imported and compile under Java 17+ with `spring-boot-starter-test` on the test classpath.

**Expected outcome:** one passing test; the `Future` returns **42**. This test **does not print 42 to stdout**; Maven/JUnit display test execution details depending on provider and version. The timeouts catch regressions when code changes.

There are three layers of protection:

1. `Future.get(1, TimeUnit.SECONDS)` bounds **waiting for the result**.
2. `@Timeout(5s)` bounds the duration of the **test method** via JUnit.
3. `@AfterEach` calls `shutdownNow` and waits up to 2 seconds; if the worker does not cooperate, the test fails and the fork process timeout acts as a backstop.

`shutdownNow` does not guarantee every task stops immediately. In real code, tasks should handle `InterruptedException` properly and avoid accidentally swallowing the interrupt flag.

### 5.5. JUnit + Spring: Context Startup Test

Create `src/test/java/com/example/build/ApplicationContextTest.java`:

~~~java
package com.example.build;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ApplicationContextTest {

    @Test
    @Timeout(30)
    void applicationContextStarts() {
        // Test passes if the Spring context initializes successfully.
    }
}
~~~

**Important note:** `@Timeout` on a **test method** is not a hard timeout for work happening **before the method is invoked**. Spring TestContext may initialize the `ApplicationContext` during extension/lifecycle callbacks before entering the test method, so a hung startup may not be bounded as expected by this method annotation. Therefore, configure timeouts for I/O and dependency startup, JUnit lifecycle/extensions where appropriate, and test process/CI timeouts.

In this project, `@SpringBootTest` uses a mock web environment by default and starts no real web server. When testing real HTTP endpoints in a project with a web starter, use `webEnvironment = RANDOM_PORT` and configure HTTP client timeouts.

### 5.6. Default JUnit Timeouts

Create `src/test/resources/junit-platform.properties`:

~~~properties
junit.jupiter.execution.timeout.test.method.default = 30 s
junit.jupiter.execution.timeout.beforeeach.method.default = 30 s
junit.jupiter.execution.timeout.aftereach.method.default = 30 s
junit.jupiter.execution.timeout.beforeall.method.default = 60 s
junit.jupiter.execution.timeout.afterall.method.default = 60 s
junit.jupiter.execution.timeout.mode = enabled
~~~

JUnit Jupiter reads this file from the **test runtime classpath**. These values are starting points; many integration tests need higher budgets per real SLOs. `@Timeout` directly on a method or class overrides defaults when needed.

You can set `junit.jupiter.execution.timeout.default = 30 s` for all testable and lifecycle methods and override selectively; the example specifies each stage explicitly to distinguish them.

**Timeouts are not an absolute thread-killing mechanism:** in same-thread mode, JUnit interrupts the running thread, yet code stuck in uninterruptible calls can keep running. Meanwhile `@BeforeAll`, Spring extensions, and shutdown hooks have their own lifecycles. Hence you still need JVM fork and CI job limits.

During breakpoint debugging, short timeouts can trigger false failures. JUnit offers `junit.jupiter.execution.timeout.mode=disabled_on_debug` if your team wants timeouts disabled when a debugger is attached; never change CI settings to mask hangs.

### 5.7. Running on Linux/macOS and Windows

Linux/macOS when the project has a Maven Wrapper:

~~~bash
./mvnw clean test
./mvnw -Dtest=BoundedExecutorTest test
./mvnw verify
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd clean test
.\mvnw.cmd "-Dtest=BoundedExecutorTest" test
.\mvnw.cmd verify
~~~

If the project was created manually without a Wrapper, replace `./mvnw` or `.\mvnw.cmd` with `mvn`. `verify` runs prior phases including `test`; when Failsafe is bound, `verify` also runs integration tests.

**Where to read Surefire results:** `target/surefire-reports/` holds text/XML reports and diagnostic files if created by the test provider or forked process. Inspect the last class/test showing progress rather than looking only at `BUILD SUCCESS`/`BUILD FAILURE`.

## 6. Why `@Timeout` Is Not Enough

Four common situations arise:

1. **I/O ignoring interrupts:** the test thread is interrupted, yet the network client/driver does not abort as expected. Client timeout APIs and process limits are needed.
2. **Work occurring outside the test method:** `@BeforeAll`, Spring context startup, extension callbacks, process shutdown, or Docker readiness run before/after the body. Place timeouts at the right lifecycle, startup/readiness, and CI layers.
3. **Spawning non-daemon threads:** the test method returns and assertions pass, yet a live thread keeps the JVM alive. Fix resource ownership and cleanup; Surefire's `forkedProcessExitTimeoutInSeconds` acts as a last line of defense.
4. **Unmanaged external processes/containers:** Java tests finish while child processes still hold ports or files; subsequent jobs can hang or fail. Close them via lifecycle hooks and CI job cleanup.

### 6.1. Deadlocks and Thread Pool Starvation

Conceptual deadlock example: thread A holds lock X and waits for Y; thread B holds Y and waits for X. A thread dump reveals `BLOCKED` threads and lock ownership. Another form of **thread starvation**: an executor has only 1 worker, and the running task calls `get()` waiting on a second task submitted to **the exact same executor**. The second task can never be scheduled.

Never "fix" deadlocks or starvation merely by raising thread counts: fix task dependencies, eliminate nested blocking `get()`, or design async flows that do not block a worker waiting on another task.

### 6.2. Do Not Use `Thread.stop` or `System.exit` to Fix Tests

`Thread.stop` is deprecated and unsafe because it can corrupt shared state invariants. `System.exit` inside a test kills the forked JVM, causing Surefire/Gradle to report unexpected process termination, losing reports, and breaking CI. Use controlled cancellation/interruption and proper resource closing.

### 6.3. Making Every Thread a Daemon Is Not a General Solution

Marking worker threads as daemons allows the JVM to exit, yet a running daemon thread can be terminated mid-flight before flushing logs, committing transactions, or cleaning up files. Choose **ownership + graceful shutdown + timeout** rather than turning all threads into daemons.

## 7. Spring Boot Tests and `ApplicationContext` Lifecycle

Spring Boot tests normally use the **Spring TestContext Framework**, which caches `ApplicationContext` instances across test classes with equivalent configurations. This cuts startup overhead while introducing lifecycle nuances.

### 7.1. Does `@SpringBootTest` Always Start a Server?

No. `@SpringBootTest` defaults to `MOCK` web environment: when a web stack is present, it creates a mock web environment **without starting an embedded HTTP server**. When you actually need to test HTTP requests over TCP, use:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HttpIntegrationTest {
    // Test executes an HTTP request with timeout against the dynamically assigned port.
}
~~~

This is an illustrative class snippet, **not a complete test**. A real project needs the web starter and a configured test client. `RANDOM_PORT` avoids fixed-port collisions across build/test workers, though you must still set connect/request timeouts on the HTTP client.

`DEFINED_PORT` can collide in CI if multiple test JVMs share 8080 or a fixed `server.port`. Use dynamic ports unless specifically required.

### 7.2. Bean Lifecycles, Executors, and Clients

If an executor, scheduler, or connection pool is a **Spring bean**, Spring invokes its destroy callback when the `ApplicationContext` closes—provided the bean and destroy method are properly configured. However, **context caching can keep a context alive across multiple test classes**, so never assume `@AfterEach` means all Spring beans have shut down.

Conversely, executors, HTTP clients, and sockets created **directly inside a test** must be closed by `@AfterEach`/`@AfterAll` or try-with-resources rather than expecting Spring to clean them up.

Never scatter `@DirtiesContext` everywhere just to "reset to be safe": it evicts the Spring context from the cache and forces re-initialization, potentially slowing down the entire suite dramatically. Use it only when a test genuinely mutates context state in a way that cannot otherwise be reset.

### 7.3. Testcontainers and Docker

When integration tests use Testcontainers, distinguish:

- Containers tied to a **JUnit extension** (e.g., `@Testcontainers` + `@Container`), typically stopped with the test class/method lifecycle.
- Containers **managed by Spring** (container beans or matching integration hooks), which can live alongside the cached `ApplicationContext`.
- Manually started containers/processes: you must register stop/close hooks, especially on test failure or timeout.

A classic trap: a cached Spring context still holds a datasource pointing to a container that a JUnit extension already stopped when its class finished. Later tests reusing that context fail to connect or hang in readiness retries. If a context shares a container's lifetime, manage lifecycles consistently per Spring Boot guidance; never keep unmanaged static containers outside the framework without accounting for context caching.

**Never wait indefinitely for containers.** Wait for container health/readiness with a realistic timeout; on failure, save Docker/service logs and target only container IDs owned by the job rather than stopping all containers on a shared runner.

### 7.4. Transactions and Teardown

In Spring tests, `@Transactional` on a test method normally rolls back the transaction on **the test thread** after execution. When an HTTP integration test uses `RANDOM_PORT` or `DEFINED_PORT`, server-side requests execute on a separate thread whose transactions **are not rolled back** by the test client's transaction. Thus explicit test data cleanup or isolated databases/schemas are required.

If DB cleanup uses the same congested connection pool, teardown itself can hang. Ensure proper connection timeouts and data/transaction isolation.

## 8. Maven Surefire: Forks, Timeouts, and Reports

### 8.1. What Is a Forked Test JVM?

Maven Surefire can run tests in one or more **separate JVMs** rather than inside the Maven JVM. This isolates classpaths, memory, and lifecycles. Key parameters:

| Surefire parameter | Meaning | Risk if misconfigured |
| --- | --- | --- |
| `forkCount` | Number of concurrent test JVMs forked **per module** | Setting too high causes CPU/RAM/port contention |
| `reuseForks` | Whether to reuse forks across test classes or spawn fresh ones | Reuse can accumulate leaks; disabling reuse slows startup |
| `forkedProcessTimeoutInSeconds` | Time limit for **one forked JVM** | Too low kills valid suites; 0 means unlimited |
| `forkedProcessExitTimeoutInSeconds` | Timeout while fork exits after finishing tests | Masks leaks if relying on kill instead of cleanup |
| `argLine` | JVM arguments for the fork, e.g., `-Xmx`, diagnostics | Excessively large heap triggers CI OOM |
| `systemPropertyVariables` | JVM system properties passed to tests | Risks exposing secrets if hardcoded |

**Do not confuse `forkedProcessTimeoutInSeconds` with per-test timeouts.** When `reuseForks=true`, a single fork may execute many test classes; a limit of a few dozen seconds can kill a healthy suite. Use test-level `@Timeout` for individual operations, fork-level timeouts for **legitimate whole-fork runtime**, and CI timeouts for the entire job.

**Do not set `forkCount=0`** if you need the ability to kill a hung test JVM independently: `forkCount=0` runs tests inside the Maven process, eliminating fork isolation and fork timeouts.

### 8.2. Use Fewer Forks Before Scaling Up

On a 2-vCPU CI runner, a multi-module build combining Maven `-T`, `forkCount=4`, and integration DB containers can pit dozens of JVMs and containers against each other. A normal 3-minute suite can stretch to 20 minutes or fail with out-of-memory, connection, or port errors.

When diagnosing a hang:

1. Temporarily run **sequentially** to detect cross-test interference.
2. Establish a baseline with `forkCount=1` and `reuseForks=true`.
3. If cross-class leaks are suspected, try `reuseForks=false` during diagnostics to isolate classes; accept the slower speed, **never treat it as a leak fix**.
4. Increase forks only after measuring CPU/RAM, max DB connections, container counts, and runner capacity.

### 8.3. Running Suspect Tests Individually

Linux/macOS:

~~~bash
./mvnw -Dtest=BoundedExecutorTest test
./mvnw -Dtest=BoundedExecutorTest#resultArrivesBeforeDeadline test
./mvnw -e test
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd "-Dtest=BoundedExecutorTest" test
.\mvnw.cmd "-Dtest=BoundedExecutorTest#resultArrivesBeforeDeadline" test
.\mvnw.cmd -e test
~~~

`-Dtest` is Surefire's selector. `-e` tells Maven to print exception details; `-X` produces verbose debug logs—use it only purposefully and never expose credentials in public logs.

Inspect `target/surefire-reports/`, especially the last test marked as running. A process can hang after the last test yet before Maven exits; capture a **thread dump of the forked JVM**, rather than reading only the Maven console.

### 8.4. Maven Failsafe for Integration Tests

For integration tests needing external services, **maven-failsafe-plugin** runs them in the `integration-test` and `verify` phases. Illustrative snippet inside `<build><plugins>`:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.5.5</version>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <forkCount>1</forkCount>
        <forkedProcessTimeoutInSeconds>1800</forkedProcessTimeoutInSeconds>
        <forkedProcessExitTimeoutInSeconds>30</forkedProcessExitTimeoutInSeconds>
    </configuration>
</plugin>
~~~

This **is not a complete POM**. The 1800-second limit is only an example for an integration test worker and must be tuned from real measurements. Failsafe normally matches names like `*IT.java` or `*ITCase.java`, distinct from Surefire's defaults. Run `mvn verify` to complete the full integration test lifecycle and inspect results; never stop at `mvn integration-test` when the project relies on `verify`/post-integration-test for cleanup and proper failure reporting.

Reports typically reside in `target/failsafe-reports/`. If a `pre-integration-test` step starts an external service, pair it with a stop step and fallback CI cleanup to avoid orphaned processes.

## 9. Gradle Test: Worker Limits, Memory, and Task Timeouts

Gradle runs `Test` tasks in **forked JVMs**. Key properties:

- `maxParallelForks`: number of forks running test classes concurrently within one task (typically 1 by default).
- `forkEvery`: maximum test classes per process before spawning a fresh one; `0` reuses indefinitely, `1` uses a fresh JVM per class (very expensive).
- `maxHeapSize`/`jvmArgs`: memory caps and JVM flags for test workers.
- `timeout`: **task-level timeout** limiting the entire Gradle `Test` task, not individual tests.
- `--max-workers`: caps total Gradle workers across the build, affecting actual concurrent test forks.
- JUnit `@Timeout` is still required to bound individual test methods.

### 9.1. Gradle Groovy DSL

For a Java/Spring Boot project applying the Java plugin and JUnit Jupiter:

~~~groovy
import java.time.Duration

tasks.withType(Test).configureEach {
    useJUnitPlatform()
    maxParallelForks = 1
    forkEvery = 0
    maxHeapSize = '512m'
    timeout = Duration.ofMinutes(15)

    testLogging {
        events 'failed', 'skipped'
    }
}
~~~

This is a **`build.gradle` snippet**, not a complete build file; it assumes JUnit engine dependencies via `spring-boot-starter-test` or compatible JUnit artifacts. `timeout` caps task duration, and `maxParallelForks` caps parallel forks within a task.

### 9.2. Gradle Kotlin DSL

In `build.gradle.kts`:

~~~kotlin
import java.time.Duration
import org.gradle.api.tasks.testing.Test

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    maxParallelForks = 1
    forkEvery = 0
    maxHeapSize = "512m"
    timeout.set(Duration.ofMinutes(15))
    testLogging {
        events("failed", "skipped")
    }
}
~~~

This is DSL configuration, not a standalone Kotlin program. If your Gradle/plugin version differs, check `Test`/`Task.timeout` documentation for your build version.

### 9.3. Running and Filtering Tests

Linux/macOS:

~~~bash
./gradlew test --info
./gradlew test --tests 'com.example.build.BoundedExecutorTest'
./gradlew test --stacktrace
./gradlew --max-workers=2 test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --info
.\gradlew.bat test "--tests=com.example.build.BoundedExecutorTest"
.\gradlew.bat test --stacktrace
.\gradlew.bat --max-workers=2 test
~~~

`--info` reveals task progress and test processes, while `--stacktrace` shows the Gradle failure stack; **this is not a thread dump of a stuck JVM**. If the task has not exited with an error yet, use Java process diagnostic tools to inspect the test worker's threads.

Gradle HTML reports typically live at `build/reports/tests/test/index.html`; XML results live at `build/test-results/test/`. In multi-module builds, paths live under each subproject.

### 9.4. Warning About Parallelism

A Gradle build with multiple `Test` tasks across modules can still consume heavy resources if `--parallel`/workers is high. `maxParallelForks=1` **per task** does not guarantee only one test JVM across **the entire build**. On resource-constrained CI, measure total concurrency: Gradle daemon/build JVM + test JVMs + databases/containers.

JUnit Jupiter also has its own class/method parallelism settings. **Gradle forks** and **JUnit threads inside a fork** are two separate concurrency layers; enabling both multiplies total threads beyond what you might expect.

## 10. Designing Independent Tests for Safe Parallel Execution

### 10.1. Dynamic Ports Over Fixed Ports

For HTTP integration tests, use `RANDOM_PORT` whenever possible. For custom `ServerSocket`s, use `new ServerSocket(0)` so the OS picks a free port and read `getLocalPort()`. However, never close a socket and reuse that port in another process without coordination: a race condition can occur between release and re-bind.

### 10.2. Isolated Filesystem per Test

JUnit Jupiter provides `@TempDir` to supply an isolated temporary directory. Example:

~~~java
package com.example.build;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;

class IsolatedFileTest {

    @TempDir
    Path workDir;

    @Test
    void writesIntoItsOwnDirectory() throws Exception {
        Path file = workDir.resolve("result.txt");
        Files.writeString(file, "ok", StandardCharsets.UTF_8);
        assertEquals("ok", Files.readString(file, StandardCharsets.UTF_8));
    }
}
~~~

This is a complete Java 17+ class using JUnit Jupiter from Spring Boot test dependencies. The file contents are `ok`; the test prints no stdout. JUnit manages `@TempDir`'s lifecycle, preventing multiple tests from editing `./result.txt` concurrently.

For databases, use isolated schemas, dedicated test databases, or clear idempotent cleanup boundaries. For brokers/topics, use unique names per test run or worker. A test **should never depend on an earlier test having run first**, unless a stateful lifecycle was designed intentionally.

### 10.3. Avoid Fixed `Thread.sleep` for Startup Waits

Never write `Thread.sleep(10000)` assuming a database/consumer "must be ready by then." On fast machines it wastes 10 seconds; on slow CI 10 seconds may still fail. Use readiness polling with a deadline and a clear failure message. Conceptual example:

~~~text
deadline = now + 30s
while service not ready:
    if now >= deadline:
        fail with last error and service logs
    sleep for small backoff
~~~

This is **pseudocode**, not Java source. A utility like Awaitility helps poll conditions with timeouts, provided you add the dependency explicitly; do not assume it is available in every project.

## 11. CI: Timeouts, Cleanup, and Retaining Evidence

Even test suites with good `@Timeout` coverage still need **job-level timeouts**. CI must guard against JVMs stuck in uninterruptible states or build tools hanging during resource resolution.

### 11.1. Recommended Deadline Layering

This is a **planning example**, not mandatory values:

| Layer | Example budget | Purpose |
| --- | --- | --- |
| HTTP connect | 2 seconds | Fail fast when service is unreachable |
| HTTP request | 5 seconds | Avoid waiting indefinitely on an endpoint |
| `Future.get` | 1–3 seconds | Avoid waiting indefinitely on async work |
| JUnit test method | 30 seconds | Catch tests exceeding expected duration |
| Maven fork / Gradle `Test` task | 15–30 minutes depending on suite | Prevent a stuck worker/task from hanging forever |
| CI job | Higher than sum of valid phases | Protect the entire pipeline |

If 100 test methods each take up to 30 seconds, you cannot set the **entire fork** timeout to 30 seconds and expect the suite to pass. Dependency downloads, code generation, compilation, integration setup, and packaging also consume CI time.

### 11.2. GNU `timeout` Example on Linux Runners

On Linux runners with `coreutils timeout`, you can wrap the Maven command with an outer guard:

~~~bash
timeout --signal=TERM --kill-after=30s 25m ./mvnw verify
~~~

If the command exceeds 25 minutes, `timeout` sends TERM first; if still alive after 30 seconds, it sends KILL per coreutils behavior. This command **is not available identically by default on all macOS or Windows hosts**, and whether signals propagate to all descendants/containers depends on process groups and CI runtimes. Never rely on `timeout` as your sole resource-cleanup mechanism.

When your CI provider offers **job timeouts** and post-step/finally/cleanup hooks, prefer those so logs and reports are archived and job-owned services/containers are stopped automatically.

### 11.3. Always Retain Reports on Failure or Timeout

Artifacts to collect:

- Maven: `target/surefire-reports/**`, `target/failsafe-reports/**`.
- Gradle: `build/test-results/**`, `build/reports/tests/**`.
- Thread dumps of the exact test worker (if captured).
- Application, database, and message broker/test container logs.
- CI memory/CPU/OOM diagnostics, last running test timestamp, and process exit codes.

**Security note:** thread dumps, environment dumps, and test logs can expose credentialed URLs, user data, or tokens in stacks/locals. Store them only with proper access controls and scrub secrets before sharing.

### 11.4. Cleanup When a Job Is Canceled

If tests start Docker containers or child processes, use tools or frameworks that track ownership and stop them in cleanup hooks. Job timeouts may bypass hooks if a runner is killed abruptly; add runner/container-orchestration cleanup as fallback when needed.

Never run "kill all java" or "docker rm -f every container" on shared runners. That can disrupt other teams' jobs or services.

## 12. Investigating a Hung Build

### 12.1. Evidence-Preserving Workflow

1. Record the **build command**, JDK, Maven/Gradle version, start time, and last logged test/phase.
2. Find the **exact PID** of the Maven/Gradle process and the **forked test JVM**; never guess a PID solely from process name.
3. While the process is still alive, **capture thread dumps**—ideally several snapshots 5–10 seconds apart to see whether stacks are progressing.
4. Inspect thread states (`RUNNABLE`, `WAITING`, `TIMED_WAITING`, `BLOCKED`) and stack frames in HTTP, JDBC, locks, executors, and native I/O.
5. Cross-check test reports and service/container logs; locate unclosed resource owners or unbounded waits.
6. After saving evidence, attempt graceful termination on the exact PID; if unresponsive, fall back to supervisor/timeout kill per CI policy.
7. Fix the root cause, then verify single-test runs, the full suite, parallel runs, and CI.

### 12.2. JDK Tools: `jcmd`, `jstack`

On Linux/macOS with matching JDK tools:

~~~bash
jcmd -l
jcmd 12345 Thread.print -l
~~~

On Windows PowerShell:

~~~powershell
jcmd -l
jcmd 12345 Thread.print -l
~~~

**PID `12345` is an example**—substitute the real PID of your test JVM. `jcmd Thread.print -l` requires attach permissions and compatible JDK tools; not every minimal CI container includes full JDK tools or permits attach.

An alternative where supported:

~~~bash
jstack -l 12345
~~~

On Unix, when attach is unavailable yet you can send signals, `kill -3 12345` normally instructs HotSpot JVMs to dump thread stacks to the **target process's** stdout/stderr. Target only the right PID and know where its logs are captured; `kill -3` differs from `kill -9`. On Windows, `jcmd` is the more controllable option.

### 12.3. Reading a Thread Dump

Common patterns:

- **`java.net.SocketInputStream` / `SocketDispatcher` / JDBC driver:** thread blocked on network I/O; check socket/read/query timeouts and service availability.
- **`CompletableFuture.get` / `FutureTask.get`:** thread waiting on an async result; trace which task should complete the future and which executor runs it.
- **`LockSupport.park` / `AbstractQueuedSynchronizer`:** waiting on a lock, condition, or queue; inspect owners/expected wakeups before assuming deadlock.
- **`BLOCKED` with lock ownership:** lock contention or deadlock; check JVM deadlock diagnostics and involved threads.
- **A non-daemon thread after tests passed:** trace back to an unclosed thread factory, executor, or scheduler; fix test/bean lifecycle.
- **High GC/CPU:** memory pressure or busy loop rather than lock waits; check CPU/heap metrics.

A thread dump is a **point-in-time snapshot**. Seeing threads in `WAITING` is not automatically a bug; idle thread-pool workers normally sit waiting. Compare across snapshots alongside deadlines, state transitions, and logs.

### 12.4. Gradle Daemon Is Not the Gradle Test Worker

`./gradlew --stop` stops Gradle daemons matching the invoked Gradle version; it is not a cure for test hangs, nor does it guarantee cleaning up external processes spawned by tests. When debugging, distinguish:

- The JVM running the Gradle daemon/build.
- The test worker JVM forked by the `Test` task.
- App server/container/DB child processes spawned by tests.

To understand why tests fail to exit, dump **the exact worker/process** and inspect resource ownership. Stop the daemon only if daemon state itself is implicated or after capturing evidence.

## 13. Anti-Patterns and Fixes

### 13.1. Using Skip Flags to Keep CI Green

Maven:

~~~bash
./mvnw package -DskipTests
~~~

or Gradle:

~~~bash
./gradlew build -x test
~~~

can help **strictly to isolate diagnostics** (checking whether a hang occurs inside tests), **never as a fix**. A build passing without tests does not prove the artifact is safe; never put skip configs into release pipelines to hide hangs.

In Maven, `-DskipTests` normally skips **test execution** while still compiling tests, whereas `-Dmaven.test.skip=true` can skip test compilation too; effects differ by plugin. Never silently alter your pipeline's verification contract.

### 13.2. Increasing Timeouts Indefinitely

If a test hangs on a deadlock, raising a timeout from 1 minute to 1 hour only delays the failure. Before raising any budget, inspect stack traces/metrics and confirm which resource genuinely needs more time. Timeouts should enforce a justified **SLO** backed by measurements.

### 13.3. Unbounded Retries When Services Are Unready

Retry loops lacking a deadline turn service failures into "hangs." If a service fails to start, infinite retries cannot fix it. Enforce max attempts or a deadline, apply backoff, and report the **last cause**. Never swallow exceptions and keep looping silently.

### 13.4. Creating Shared Executors or Static Contexts for All Tests

A `static ExecutorService` created by test A can keep threads alive into test B; test ordering and `reuseForks` make resulting bugs hard to reproduce. Scope executors to each test or managed bean with clear lifecycles and reset shared state; if sharing is unavoidable, establish clear ownership and `@AfterAll`/suite-level teardown.

### 13.5. Catching and Ignoring `InterruptedException`

Bad pattern:

~~~java
try {
    Thread.sleep(1000);
} catch (InterruptedException ignored) {
    // Swallow interrupt and keep running as usual.
}
~~~

This is a snippet inside a method, not a complete class. When interruption signals task cancellation, stop work/clean up and restore the interrupt flag when appropriate:

~~~java
try {
    Thread.sleep(1000);
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    return;
}
~~~

The second snippet assumes a `void` method; in value-returning methods, handle control flow appropriately. During test cancellation, swallowing interrupts can prevent `@Timeout` and shutdown from working as intended.

### 13.6. Confusing Timeout Expiration with Complete Cleanup

A `@Timeout` failure does not guarantee all threads, processes, or external resources have stopped. After a test timeout, run teardown/cancellation; after a worker timeout, run process-level cleanup; after CI cancellation, run runner-level cleanup. Across multiple layers, always know who owns closing each resource.

## 14. Practice Scenarios and Answers

**Scenario 1 — Tests pass, yet Maven never exits.** You see `Tests run: 120, Failures: 0` and the terminal freezes. One test created `Executors.newSingleThreadExecutor()` without shutting it down.

- **Likely cause:** the executor's non-daemon worker thread stays alive or the fork is waiting on shutdown.
- **Fix:** capture a fork thread dump, check thread names/stacks; add `shutdown`/`awaitTermination` in `@AfterEach`/`finally`. `forkedProcessExitTimeoutInSeconds` is a safety net, not a replacement for cleanup.

**Scenario 2 — Gradle tests hang when parallelism is enabled.** Tests share a database/schema and write to the same `./tmp/results.json`.

- **Likely cause:** race conditions, file locks, or transaction contention across test workers.
- **Fix:** temporarily set `maxParallelForks=1` to isolate; switch to `@TempDir`, unique schemas/ports, and resource isolation. Never assume "adding CPU" solves concurrency bugs.

**Scenario 3 — `@Timeout(10)` fails to stop a hang during Spring context startup.**

- **Likely cause:** the stall occurred during startup/extension callbacks before the test method, or in uninterruptible I/O.
- **Fix:** set readiness deadlines for DB/HTTP/Testcontainers, configure lifecycle timeouts, and keep fork/task/CI safeguards. Never treat method-level `@Timeout` as a hard process kill.

**Scenario 4 — Surefire fork timeout is 60 seconds, yet a healthy 200-test suite takes 90 seconds.**

- **Cause:** the timeout applies to the entire forked process (under `reuseForks`), not only stuck tests.
- **Fix:** measure suite duration; keep per-method timeouts tight as appropriate, and raise the worker-level budget to match legitimate worst-case duration and CI budgets.

**Scenario 5 — HTTP integration tests use `DEFINED_PORT` in parallel CI.**

- **Likely cause:** port conflicts cause server startup failures or tests hit the wrong endpoint.
- **Fix:** use `RANDOM_PORT` with clients reading the runtime port, and set connect/read timeouts; use fixed ports only with explicit coordination.

**Scenario 6 — Testcontainers stops a container while a cached Spring context still holds its datasource.**

- **Cause:** container lifecycle and Spring TestContext caching are out of sync.
- **Fix:** tie container lifetime to the context lifecycle or configure appropriate test isolation; never let subsequent suites share a container that already stopped.

**Scenario 7 — A Maven build hangs in CI, you spot a Java PID, and you are about to run `kill -9` immediately.**

- **Better approach:** verify which JVM owns the PID, capture logs and `jcmd Thread.print`/thread dumps first, attempt graceful termination, and force-kill only if necessary within the time budget. Never kill Java processes belonging to other jobs.

## 15. Pre-Merge Checklist for Build/Test Changes

- [ ] All critical I/O (HTTP, DB, sockets, external services) enforces explicit timeouts and clear error messages.
- [ ] All Futures/latches/polling loops enforce deadlines; zero unbounded wait loops.
- [ ] Every `ExecutorService`, socket, stream, temp file, container, and child process has clear ownership and lifecycle cleanup.
- [ ] Appropriate test/lifecycle methods use JUnit timeouts, knowing `@Timeout` is not a hard process kill.
- [ ] Surefire/Failsafe fork timeouts and exit timeouts reflect **full-fork duration**, not per-test assumptions.
- [ ] Gradle test workers, JVM heaps, and `timeout` match real CPU/RAM/CI limits.
- [ ] Parallel tests isolate ports, temp dirs, schemas, and data with no unguarded shared state.
- [ ] Spring `@SpringBootTest`/ApplicationContext/Testcontainers align lifecycles without overusing `@DirtiesContext`.
- [ ] CI enforces job timeouts, cleanup hooks, and archiving of reports/thread dumps on failure.
- [ ] Tested suspect cases individually, the full suite, and repeated runs to catch leaks.
- [ ] Never hid issues with `skipTests` or infinite retries.
- [ ] Process-termination commands target **the exact PID/resource** without impacting other jobs or services.

## 16. Official Documentation

- JUnit Jupiter `@Timeout` and timeout configuration: https://docs.junit.org/5.12.1/user-guide/index.html
- Maven Surefire Plugin — test goal configuration: https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html
- Maven Surefire — forked JVM shutdown: https://maven.apache.org/surefire/maven-surefire-plugin/examples/shutdown.html
- Maven Failsafe Plugin — integration-test and verify: https://maven.apache.org/surefire/maven-failsafe-plugin/
- Gradle — Testing in Java & JVM Projects: https://docs.gradle.org/current/userguide/java_testing.html
- Gradle — Controlling Task Execution / Task timeouts: https://docs.gradle.org/current/userguide/controlling_task_execution.html
- Gradle Test API (`maxParallelForks`, `forkEvery`, `maxHeapSize`): https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/testing/Test.html
- Spring Boot — Testing Applications: https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
- Spring Boot — Testcontainers integration: https://docs.spring.io/spring-boot/reference/testing/testcontainers.html

**Conclusion:** A reliable build must **either complete or fail with actionable diagnostics**, never hang indefinitely. Achieving this requires combining **lifecycle-scoped resource cleanup**, **operation-level deadlines**, **JUnit test/lifecycle timeouts**, **Maven/Gradle worker safeguards**, and **CI-level timeouts/cleanup**. When a hang happens, capture thread dumps and reports from the exact process before forcing termination, and fix the root cause rather than merely raising limits or skipping tests.
