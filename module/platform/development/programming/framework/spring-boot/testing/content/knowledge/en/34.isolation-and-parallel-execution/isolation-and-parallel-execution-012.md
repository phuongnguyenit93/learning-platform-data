# Cleaning Up Executors, Schedulers, Connections, and Containers After Tests Finish

> Module: **Spring Boot – testing**  
> Group: **Isolation and Parallel Execution**  
> Topic: **Cleaning up executors, schedulers, connections, and containers after tests finish**  
> Objective: Properly close test-owned resources, return JDBC handles to the pool, manage Spring-owned thread pools via the `ApplicationContext`, prevent background tasks from surviving across test classes, keep Testcontainers aligned with the Spring TestContext cache, and verify cleanup with bounded-timeout assertions. Examples use Java 17, JUnit Jupiter, Spring Boot 3.5, and PostgreSQL Testcontainers.

## 1. The Problem: Assertions Pass Yet Resources Keep Running

A test can finish all its assertions while Maven/Surefire hangs on exit because a thread pool was never shut down. Across a full suite, a background scheduler keeps writing to the DB, a connection pool holds open sockets, or a PostgreSQL Testcontainer stops while a cached Spring context still holds a `DataSource` pointing to the old container.

```java
@Test
void worksButLeaksPool() throws Exception {
    ExecutorService pool = Executors.newSingleThreadExecutor();
    Future<String> result = pool.submit(() -> "OK");

    assertThat(result.get()).isEqualTo("OK");
    // No shutdown() called: the thread pool stays alive!
}
```

This is an **anti-pattern snippet** without imports. `Future.get()` waits for one task to finish, but **does not** close the executor. If the pool uses non-daemon threads, it keeps the JVM alive after the test ends. Conversely, shutting down a Spring-managed executor prematurely in `@AfterEach` is also broken: other tests reusing the cached context will fail with `RejectedExecutionException`.

### 1.1. Common Symptoms

- `mvn test` prints results yet the process fails to exit.
- `pool-N-thread-M`, `scheduling-N`, or `task-N` threads remain alive after a class finishes.
- Scheduled jobs fire after cleanup and mutate another test's fixtures.
- `HikariPool ... connection leak detection triggered` warnings or active JDBC connections failing to drop back to expected levels.
- `Connection refused` when a reused context connects to a stopped Testcontainer.
- Local HTTP stubs hit `Address already in use` because a port or server was never released.
- Kafka consumers/Rabbit listeners keep consuming messages after the test ends, causing contention.
- Docker resources pile up across CI runs, or an overly broad global cleanup destroys another job's containers.
- Adding `@DirtiesContext` breaks other tests running in parallel against the same context.
- `@Transactional` rolls back the DB on the test thread while an async worker thread still commits.

**Principle:** Cleanup is a contract of **ownership**, **shutdown order**, **shutdown timing**, and **termination proof**—not blindly sprinkling `close()` everywhere.

## 2. Lifecycle Ownership Diagram

```text
CI job / Maven
  ├─ JVM fork 1
  │   ├─ JUnit class A
  │   │   ├─ method a() ─ owns ExecutorService A
  │   │   └─ method b() ─ owns HttpServer B
  │   ├─ JUnit class B
  │   └─ Spring TestContext cache
  │       └─ ApplicationContext X ─ owns:
  │          ├─ ThreadPoolTaskExecutor bean
  │          ├─ ThreadPoolTaskScheduler bean
  │          ├─ HikariDataSource bean
  │          ├─ listener containers
  │          └─ Spring-managed PostgreSQLContainer bean
  ├─ JVM fork 2 (separate static/cache)
  └─ External resources
      ├─ DB schemas/rows
      ├─ broker queues / Redis keys
      ├─ files / open ports
      └─ Docker daemon, network, volumes
```

A `@Test` finishing does not necessarily close the `ApplicationContext`. A JUnit class finishing does not mean the JVM fork exits. Spring TestContext can **cache** contexts across classes with matching configurations. Two JVMs keep separate static state yet still share Redis or the same Postgres DB if configured to point to the same endpoint.

### 2.1. Owner and Cleanup Matrix

| Resource | Owner | Proper Cleanup |
| --- | --- | --- |
| `Executors.newSingleThreadExecutor()` inside a method | Method | `shutdown()` → bounded `awaitTermination()` → `shutdownNow()` if needed |
| Test-owned `ScheduledExecutorService` | Method/class | Cancel `ScheduledFuture`, shutdown, bounded await |
| `ThreadPoolTaskExecutor` declared as `@Bean` | Spring context | Context lifecycle destruction; never shut down per method |
| `ThreadPoolTaskScheduler` declared as `@Bean` | Spring context | Cancel test-registered tasks when needed; context close manages scheduler |
| `Connection` borrowed from Hikari pool | Borrower | `Connection.close()` returns pooled handle |
| `PreparedStatement` / `ResultSet` | Query caller | `try-with-resources` |
| Manually created `HikariDataSource` | Test | `HikariDataSource.close()` in owner teardown |
| Boot auto-configured `HikariDataSource` | Spring | Context destruction |
| Spring `JdbcTemplate` | Spring/client facade | Never "close the pool" after each operation |
| Static `@Container` Testcontainers | JUnit extension | Stops after the class |
| Instance `@Container` | JUnit extension | Stops after the method |
| `@Bean PostgreSQLContainer` | Spring context | Stops after dependent beans when context closes |
| Test-created `HttpServer` | Test | `server.stop(0)` |
| Manually created Kafka client | Test | Stop poll loop/`wakeup`, `close()` |
| Spring-created Rabbit listener/container | Spring context | Spring lifecycle stop |
| `@TempDir` | JUnit | JUnit cleanup per scope |
| External files/queues/DB rows | Test/CI job | Clean up only the owner's namespace/IDs |

### 2.2. Resource Close Order Is the Reverse of Dependency Order

```text
Start:
  Postgres Testcontainer → Hikari pool → async worker/scheduler

Stop:
  Disable new work + cancel triggers
  → let in-flight work finish within deadline
  → shutdown workers/schedulers
  → close pooled connections/client beans
  → close DataSource
  → stop Postgres container
```

Stopping the database before a worker executing SQL finishes can crash the worker or leave transaction outcomes "unknown". With Spring-managed Testcontainers beans, Boot 3.5 supports starting container beans **before** dependent beans and stopping them **after** dependent beans are destroyed. With custom owners, you must enforce this ordering yourself.

## 3. JUnit Lifecycle: Cleanup at the Right Scope

### 3.1. `@AfterEach` vs `@AfterAll`

- `@AfterEach`: runs after **each** test method; suits resources opened in `@BeforeEach` or inside the method itself.
- `@AfterAll`: runs after **all** methods in the class; suits class-owned resources.
- `@BeforeEach` setup and `@AfterEach` cleanup do not automatically isolate resources **external to the test**, such as a Redis DB, shared connection factory, or cached Spring context.
- An `@AfterEach` wiping an entire DB table can destroy another parallel test's data.
- If cleanup throws an exception, **never swallow it** and report a false PASS.

Example managing an executor manually:

```java
class ExecutorLifecycleExample {
    private ExecutorService pool;

    @BeforeEach
    void start() {
        pool = Executors.newSingleThreadExecutor();
    }

    @AfterEach
    void stop() throws InterruptedException {
        pool.shutdown();
        if (!pool.awaitTermination(2, TimeUnit.SECONDS)) {
            pool.shutdownNow();
            assertThat(pool.awaitTermination(
                    2, TimeUnit.SECONDS)).isTrue();
        }
    }
}
```

This is a snippet without imports; the project section uses an `AutoCloseable` wrapper to eliminate duplication and handle interruption properly.

### 3.2. `try-with-resources` and Java 17

`InputStream`, JDBC `Connection`, `Statement`, `ResultSet`, and resources implementing `AutoCloseable` close automatically on block exit, even if an assertion throws:

```java
try (InputStream in = Files.newInputStream(path)) {
    byte[] bytes = in.readAllBytes();
    assertThat(bytes).isNotEmpty();
}
```

**Version detail:** In **Java 17**, `ExecutorService` **does not implement `AutoCloseable` yet**, so `try (ExecutorService pool = Executors.newSingleThreadExecutor())` will not compile. Use `finally` or an `AutoCloseable` wrapper. If reading Java 21+ examples of closing executors directly, never copy them verbatim into a Java 17 project.

### 3.3. JUnit `@AutoClose`

Since 5.11, JUnit Jupiter supports `@AutoClose` on resource fields exposing `close()`. Under the default `PER_METHOD` test class lifecycle, non-static fields close after each method; static fields close after the entire class. `PER_CLASS` ties instance fields to the class lifecycle.

```java
@AutoClose
AutoCloseable owned = () -> {
    // cleanup
};
```

This is a snippet. If two resources must close in a specific order, do not rely on implicit field-close ordering; use a composite owner whose `close()` closes them in explicit order. The runnable `JupiterAutoCloseTest` asserts cleanup in `@AfterAll`.

### 3.4. `@TempDir` Does Not Close Open File Streams

JUnit manages the temporary directory, yet if a test leaves a `Files.lines(...)` stream or `Files.newInputStream(...)` open—especially on Windows—directory deletion can fail. Always wrap file handles in `try-with-resources`, then let `@TempDir` remove the folder.

## 4. ExecutorService: Proper Shutdown to Avoid Hanging CI

### 4.1. Steps to Remember

```java
pool.shutdown();
boolean done = pool.awaitTermination(
        2, TimeUnit.SECONDS);

if (!done) {
    pool.shutdownNow();
    done = pool.awaitTermination(
            2, TimeUnit.SECONDS);
}
assertThat(done).isTrue();
```

- `shutdown()`: stops accepting new tasks; queued/running tasks may complete.
- `awaitTermination`: waits for pool termination **with a deadline**.
- `shutdownNow()`: attempts to interrupt running tasks and returns queued tasks; **not a guaranteed thread killer**.
- `Future.cancel(true)`: requests cancellation of **one task**; does not shut down the executor.
- `Future.get(timeout)`: awaits the result; does not shut down.
- `Thread.interrupt`: a cooperative cancellation signal; tasks must respond to it.

A task running `while(true)` that catches `InterruptedException` and keeps looping will defeat forced shutdown. Never use deprecated/unsafe `Thread.stop()` to force termination. Fix tasks to break/return on interruption.

### 4.2. Never Use `Thread.sleep` as Proof of Cleanup

```java
pool.shutdownNow();
Thread.sleep(100);
assertThat(Thread.activeCount()).isLessThan(10);
```

This is an anti-pattern. JVM/JUnit/GC/Testcontainers spawn background threads too, so `Thread.activeCount()` does not measure the owned pool accurately. `sleep` does not prove pool termination.

Use instead:

```java
pool.shutdown();
assertThat(pool.awaitTermination(
        2, TimeUnit.SECONDS)).isTrue();
assertThat(pool.isTerminated()).isTrue();
```

Tests should verify the specific resource they created rather than asserting the entire JVM thread count drops to zero.

### 4.3. Cleanup When a Test Assertion Fails

```java
ExecutorService owner =
        Executors.newSingleThreadExecutor();
try {
    // May throw before reaching shutdown...
}
finally {
    owner.shutdownNow();
    assertThat(owner.awaitTermination(
            2, TimeUnit.SECONDS)).isTrue();
}
```

This snippet omits imports; placing cleanup in `finally` or a `try-with-resources` wrapper prevents leaks even when tests fail.

### 4.4. When Termination Still Times Out

If a thread remains active after forced shutdown and the second bounded await:

1. Fail loudly instead of silently passing.
2. Capture a thread dump using the **test JVM fork's** exact PID, not the Maven parent process.
3. Inspect blocking I/O, deadlocks, swallowed interruptions, and callback states.
4. Keep CI job timeouts as a **last-resort containment**, never calling `System.exit(0)` in tests to hide leaks.
5. Check whether the stray task can keep mutating external resources after the test method exits.

## 5. Schedulers: Canceling Tasks vs Shutting Down the Scheduler

### 5.1. `ScheduledFuture`

```java
ScheduledExecutorService scheduler =
        Executors.newSingleThreadScheduledExecutor();

try {
    ScheduledFuture<?> future = scheduler.schedule(
            () -> System.out.println("late"),
            1, TimeUnit.HOURS);

    assertThat(future.cancel(false)).isTrue();
}
finally {
    scheduler.shutdownNow();
    assertThat(scheduler.awaitTermination(
            2, TimeUnit.SECONDS)).isTrue();
}
```

A one-hour delay keeps the cancellation test timing-independent. Canceling the future prevents that **specific scheduled task** from running; shutting down the scheduler releases pool-owned threads. `cancel(false)` does not interrupt a task already in progress; when interruption is needed and supported, pass `cancel(true)`.

### 5.2. Spring `@Scheduled`, `@EnableScheduling`, and Test Contexts

A `@Scheduled` method is automatically registered by Spring if `@EnableScheduling` is active in the context. If the context is cached, the scheduler stays alive past the test class. For tests unrelated to scheduling, gate registration conditionally before context refresh:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        name = "app.scheduling.enabled",
        havingValue = "true")
@EnableScheduling
class SchedulingSwitch {
}
```

This is a snippet. `app.scheduling.enabled` is an **application-defined custom property**. Never add `spring.task.scheduling.enabled=false` assuming Boot 3.5 has such a universal switch. `spring.task.scheduling.pool.size` configures pool size, not an enable/disable toggle.

### 5.3. Spring `ThreadPoolTaskScheduler`

When defining a `ThreadPoolTaskScheduler` bean:

- `setPoolSize(1)` sets worker scheduler thread count.
- `setThreadNamePrefix("lab-scheduler-")` aids ownership debugging.
- `setRemoveOnCancelPolicy(true)` removes canceled tasks from `ScheduledThreadPoolExecutor`'s queue where supported.
- `setWaitForTasksToCompleteOnShutdown(...)` chooses graceful waiting vs task interruption/queue handling.
- `setAwaitTerminationSeconds(int)` bounds shutdown wait time.

If a `ScheduledFuture` belongs to one test, cancel it during cleanup while the context remains alive. If `ThreadPoolTaskScheduler` is a singleton Spring bean, **never call `scheduler.shutdown()` in `@AfterEach`** when other tests will reuse the same context.

### 5.4. Boot 3.5 Shutdown Properties

```properties
spring.task.execution.shutdown.await-termination=true
spring.task.execution.shutdown.await-termination-period=5s

spring.task.scheduling.shutdown.await-termination=true
spring.task.scheduling.shutdown.await-termination-period=5s

spring.task.execution.thread-name-prefix=task-
spring.task.scheduling.thread-name-prefix=scheduling-
```

These are documented Boot 3.5 property names. They apply to **auto-configured** executors/schedulers. If an application declares custom `ThreadPoolTaskExecutor` or `ThreadPoolTaskScheduler` beans directly, these properties **do not necessarily apply**; configure shutdown on the bean directly or use Boot's builders.

Spring Framework 6.2 nuance: `waitForTasksToCompleteOnShutdown(true)` can cause executors to bypass the coordinated lifecycle stop phase and wait during the destruction phase instead. `acceptTasksAfterContextClose`/`strictEarlyShutdown` also govern task acceptance and shutdown ordering. Never flip flags blindly while tasks still depend on a DB/broker being destroyed.

### 5.5. Virtual Threads (Outside This Java 17 Project)

With Java 21+ and `spring.threads.virtual.enabled=true`, Boot may auto-configure `SimpleAsyncTaskExecutor`/`SimpleAsyncTaskScheduler` instead of pool-based implementations, rendering several pool properties inactive. Inspect the actual executor in use; never hard-code assertions assuming `ThreadPoolTaskExecutor` across all runtimes.

## 6. Spring ApplicationContext Lifecycle and TestContext Cache

### 6.1. Spring-Owned Beans

Spring invokes destruction callbacks (`@PreDestroy`, `DisposableBean.destroy`, configured destroy methods) only when the context **actually closes**. `ThreadPoolTaskExecutor` and `ThreadPoolTaskScheduler` are framework-managed components with lifecycle shutdowns.

```java
@Configuration(proxyBeanMethods = false)
class ThreadConfig {

    @Bean
    ThreadPoolTaskExecutor worker() {
        ThreadPoolTaskExecutor pool =
                new ThreadPoolTaskExecutor();
        pool.setThreadNamePrefix("worker-test-");
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(1);
        return pool;
    }
}
```

This is a snippet; the full file appears in the sample project. When a bean is Spring-managed, a JUnit method should not manually shut it down inside a shared context.

### 6.2. `@DirtiesContext` Is Not Universal Cleanup

`@DirtiesContext(classMode = AFTER_CLASS)` marks the context dirty, instructing Spring to evict it from the cache and close it after the test class. However:

- It does not roll back records committed on another thread.
- It does not delete external Redis keys/queues/files.
- It adds Spring restart overhead; never apply it to every test.
- When Spring tests run in parallel sharing a context, dirtying can break other classes.
- It does not stop manually created out-of-context executors.
- Do not assert inside `@AfterAll` that `AFTER_CLASS` already closed the context if the Spring listener closes it **after** `@AfterAll`.

To test direct context-close behavior, create an `AnnotationConfigApplicationContext` **inside a JUnit method** with `try-with-resources`, as shown in `SpringPoolLifecycleTest`.

### 6.3. Bean Destruction Order

If a background task depends on the DB, workers/producers must stop before the `DataSource` closes. Use constructor dependencies, Spring `SmartLifecycle`, phase coordination, or an explicit cleanup owner when truly needed. Never let a `@PreDestroy` bean send messages through an already-destroyed connection factory.

Context-owned beans shut down according to dependency/lifecycle mechanics, not necessarily the declaration order of injected fields in a test.

## 7. JDBC: `Connection.close()` vs `HikariDataSource.close()`

### 7.1. Returning a Borrowed Connection to the Pool

```java
try (Connection conn = dataSource.getConnection();
     PreparedStatement st =
             conn.prepareStatement("SELECT 1");
     ResultSet rs = st.executeQuery()) {

    assertThat(rs.next()).isTrue();
    assertThat(rs.getInt(1)).isEqualTo(1);
}
```

On a HikariCP pooled connection, calling `Connection.close()` on the **borrowed proxy** returns the connection to the pool (typically keeping the physical connection open for future borrows). It **does not close the `HikariDataSource`**.

Close `PreparedStatement` and `ResultSet` explicitly as well. Never rely on "closing the connection automatically cleans up child handles" when lexical ownership is clear.

### 7.2. `JdbcTemplate`

`JdbcTemplate` handles JDBC resource acquisition/release automatically per Spring JDBC and transaction synchronization:

```java
Integer one = jdbc.queryForObject(
        "SELECT 1", Integer.class);
assertThat(one).isEqualTo(1);
```

This is a snippet. `JdbcTemplate` does not mean the test owns a pool. When Spring Boot manages the `HikariDataSource` bean, let context destruction close the pool; never call `hikari.close()` inside a test method.

### 7.3. Hikari Pool Ownership

If a test instantiates its own `HikariDataSource`:

```java
HikariDataSource pool = new HikariDataSource();
try {
    // configure test URL, borrow, use, close Connection handles...
}
finally {
    pool.close();
}
```

When Spring creates the pool via `spring-boot-starter-jdbc`, the context owns and closes the pool. Closing it prematurely in one method causes subsequent classes reusing the cached context to fail with `HikariPool ... has been closed`.

### 7.4. Hikari Leak Detection and MXBean

`HikariPoolMXBean.getActiveConnections()` helps verify borrowed connections return to the pool. Assert on it only in an **isolated environment**, never on a shared pool with active schedulers/listeners/parallel requests. Leak detection logs merely warn when a connection is held too long; they never auto-close leaks and can emit false positives on slow SQL.

### 7.5. Transactions Do Not Replace Resource Cleanup

A `@Transactional` test method rolls back its test-managed transaction on the test thread, yet does not clean up executors, brokers, HTTP clients, containers, or file handles. Off-thread async workers do not join that transaction. JUnit preemptive separate-thread timeouts can also push execution outside the test-managed transaction.

## 8. Testcontainers: Class-Owned vs Context-Owned

### 8.1. JUnit Extension Lifecycle

```java
@Testcontainers
class ExamplePostgresTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
```

- Static `@Container`: starts once before methods, stops after the class.
- Instance `@Container`: starts/stops per method.
- The JUnit extension manages its own lifecycle; Spring's TestContext cache can outlive **the class**.
- Testcontainers JUnit extension docs warn that parallel execution is not supported as a default contract; never parallelize container lifecycles without explicit isolation.

### 8.2. Stopped-Container + Cached Spring Context Trap

```text
Class A:
  JUnit starts static Postgres A
  Spring context X creates DataSource → A
  Test A PASS
  JUnit stops A after class

Class B:
  Spring cache reuses context X
  DataSource still points to A's old port
  JDBC query → Connection refused
```

How to avoid this:

1. Pair class-owned `@Container` with `@DirtiesContext(AFTER_CLASS)` when the context binds to that container.
2. When caching Spring contexts across classes, prefer declaring the container as a Spring bean so its lifecycle matches the context.
3. Suite-wide singleton Testcontainers can be started manually, **never** combined with `@Container` (which makes JUnit stop them after each class).
4. Never call `stop`/`start` on a shared container between methods assuming mapped ports stay identical.
5. Never shut down a container while Spring beans still use its endpoint.

### 8.3. Spring-Managed Container Bean

Spring Boot 3.5 supports:

```java
@TestConfiguration(proxyBeanMethods = false)
class PostgresTestConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgres() {
        return new PostgreSQLContainer<>("postgres:16-alpine");
    }
}
```

This is a snippet; the full file appears in Section 9. Boot starts the container bean before dependent beans and stops it after dependent beans are destroyed. `@ServiceConnection` supplies dynamic JDBC connection details without hard-coding `localhost:5432`.

**Note:** Never combine `@Testcontainers`/`@Container` on the same Spring-managed bean; do not let both the JUnit extension and Spring fight over managing one resource under two lifecycles.

### 8.4. `@DirtiesContext(AFTER_CLASS)` with a Spring-Managed Container

In the sample project, there is one integration class with that annotation so the context, Hikari pool, and container are cleaned up when the class ends. In large suites wanting context reuse across classes, omit `@DirtiesContext` where appropriate and let the container bean live with the cached context. `@DirtiesContext` never replaces scoped cleanup for test fixtures/rows.

### 8.5. Never Run Global Docker Cleanup

Never execute `docker system prune --volumes` or `docker rm -f` across all containers on a shared runner. Base cleanup strictly on container IDs/labels owned by the test job. If a process is hard-killed, `@AfterAll` won't run; Testcontainers' resource reaper and CI cleanup policies clear orphaned resources safely—never disable the reaper just to turn tests green.

## 9. Runnable-Design Project: Java 17 + Spring Boot 3.5

The sample contains **10 JUnit `@Test` methods**: 4 JDK executor/scheduler tests, 2 Spring pool lifecycle tests, 1 JUnit `@AutoClose` test, and 3 PostgreSQL JDBC integration tests.

### 9.1. Structure

```text
resource-cleanup-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/cleanup/
    │   ├── CleanupLabApplication.java
    │   ├── LabThreadConfig.java
    │   └── OwnedExecutor.java
    ├── main/resources/
    │   ├── application.properties
    │   └── schema.sql
    └── test/java/com/example/cleanup/
        ├── OwnedExecutorTest.java
        ├── SpringPoolLifecycleTest.java
        ├── JupiterAutoCloseTest.java
        ├── PostgresTestConfig.java
        └── JdbcResourceIntegrationTest.java
```

Every public top-level Java type lives in a matching filename under package `com.example.cleanup`. Tests need no real HTTP server or RabbitMQ; the project uses real PostgreSQL Testcontainers to test connection lifecycles. No cloud credentials are required.

### 9.2. `pom.xml`

```xml
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
    <artifactId>resource-cleanup-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-testcontainers</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>postgresql</artifactId>
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

Boot 3.5 BOM manages JUnit Jupiter, Spring Framework 6.2, HikariCP, and Testcontainers 1.x. Never mix imports or Maven coordinates from Testcontainers 2.x while still using the Testcontainers 1.x BOM.

### 9.3. `CleanupLabApplication.java`

```java
// src/main/java/com/example/cleanup/CleanupLabApplication.java
package com.example.cleanup;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CleanupLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(CleanupLabApplication.class, args);
    }
}
```

`@EnableScheduling` is not enabled in the sample. Having a scheduler bean does not automatically make Spring scan and register `@Scheduled` methods.

### 9.4. `LabThreadConfig.java`

```java
// src/main/java/com/example/cleanup/LabThreadConfig.java
package com.example.cleanup;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration(proxyBeanMethods = false)
public class LabThreadConfig {

    @Bean("labExecutor")
    ThreadPoolTaskExecutor labExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("lab-executor-");
        executor.setWaitForTasksToCompleteOnShutdown(false);
        executor.setAwaitTerminationSeconds(2);
        return executor;
    }

    @Bean("labScheduler")
    ThreadPoolTaskScheduler labScheduler() {
        ThreadPoolTaskScheduler scheduler =
                new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("lab-scheduler-");
        scheduler.setRemoveOnCancelPolicy(true);
        scheduler.setWaitForTasksToCompleteOnShutdown(false);
        scheduler.setAwaitTerminationSeconds(2);
        return scheduler;
    }
}
```

Both beans are owned by the Spring context. Tests can create a dedicated `AnnotationConfigApplicationContext`, close it, and verify shutdown. No `@Scheduled` cron jobs exist, preventing unwanted background execution.

### 9.5. `OwnedExecutor.java` — `AutoCloseable` Wrapper for Java 17

```java
// src/main/java/com/example/cleanup/OwnedExecutor.java
package com.example.cleanup;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class OwnedExecutor implements AutoCloseable {

    private final ExecutorService executor;
    private final Duration timeout;

    public OwnedExecutor(Duration timeout) {
        this.timeout = Objects.requireNonNull(timeout);
        if (timeout.isNegative() || timeout.isZero()
                || timeout.toMillis() == 0) {
            throw new IllegalArgumentException(
                    "timeout must be positive milliseconds");
        }
        executor = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "owned-lab-worker"));
    }

    public <T> Future<T> submit(Callable<T> task) {
        return executor.submit(task);
    }

    public Future<?> submit(Runnable task) {
        return executor.submit(task);
    }

    public boolean isTerminated() {
        return executor.isTerminated();
    }

    @Override
    public void close() {
        executor.shutdown();
        try {
            long millis = timeout.toMillis();
            if (!executor.awaitTermination(
                    millis, TimeUnit.MILLISECONDS)) {
                executor.shutdownNow();
                if (!executor.awaitTermination(
                        millis, TimeUnit.MILLISECONDS)) {
                    throw new IllegalStateException(
                            "Executor did not terminate");
                }
            }
        }
        catch (InterruptedException ex) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Interrupted during shutdown", ex);
        }
    }
}
```

`close()` uses two bounded await phases: up to nearly **2 × timeout**, excluding scheduling overhead. When a thread refuses to cooperate, the test receives an explicit cleanup failure. Never assume `shutdownNow()` reliably terminates tasks blocked on I/O or swallowing interrupts.

### 9.6. `OwnedExecutorTest.java` — 4 Tests

```java
// src/test/java/com/example/cleanup/OwnedExecutorTest.java
package com.example.cleanup;

import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class OwnedExecutorTest {

    @Test
    void completedTaskDoesNotLeakExecutor() throws Exception {
        OwnedExecutor owner =
                new OwnedExecutor(Duration.ofMillis(250));
        try (owner) {
            assertThat(owner.submit(() -> "OK")
                    .get(2, TimeUnit.SECONDS))
                    .isEqualTo("OK");
        }
        assertThat(owner.isTerminated()).isTrue();
    }

    @Test
    void blockedWorkerStopsOnInterruption() throws Exception {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch gate = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean();

        OwnedExecutor owner =
                new OwnedExecutor(Duration.ofMillis(150));

        try (owner) {
            owner.submit(() -> {
                started.countDown();
                try {
                    gate.await();
                }
                catch (InterruptedException ex) {
                    interrupted.set(true);
                    Thread.currentThread().interrupt();
                }
            });
            assertThat(started.await(
                    2, TimeUnit.SECONDS)).isTrue();
        }

        assertThat(interrupted.get()).isTrue();
        assertThat(owner.isTerminated()).isTrue();
    }

    @Test
    void closedExecutorRejectsNewWork() {
        OwnedExecutor owner =
                new OwnedExecutor(Duration.ofMillis(250));
        owner.close();

        assertThat(owner.isTerminated()).isTrue();
        assertThatThrownBy(
                () -> owner.submit(() -> { }))
                .isInstanceOf(RejectedExecutionException.class);
    }

    @Test
    void cancelledFutureAndSchedulerBothCleanUp()
            throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();
        try {
            ScheduledFuture<?> future = scheduler.schedule(
                    () -> { throw new AssertionError(
                            "must not run"); },
                    1, TimeUnit.HOURS);

            assertThat(future.cancel(false)).isTrue();
            assertThat(future.isCancelled()).isTrue();
        }
        finally {
            scheduler.shutdownNow();
            assertThat(scheduler.awaitTermination(
                    2, TimeUnit.SECONDS)).isTrue();
        }
        assertThat(scheduler.isTerminated()).isTrue();
    }
}
```

No `Thread.sleep`. `CountDownLatch` proves the worker started before shutdown is triggered, then the forced phase interrupts `gate.await()`. Cooperative cancellation exits the worker; `isTerminated()` confirms no owned worker stays alive.

### 9.7. `SpringPoolLifecycleTest.java` — 2 Tests

```java
// src/test/java/com/example/cleanup/SpringPoolLifecycleTest.java
package com.example.cleanup;

import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

import static org.assertj.core.api.Assertions.assertThat;

class SpringPoolLifecycleTest {

    @Test
    void contextCloseShutsDownBothSpringPools()
            throws Exception {
        ThreadPoolTaskExecutor worker;
        ThreadPoolTaskScheduler scheduler;

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        LabThreadConfig.class)) {
            worker = context.getBean(
                    "labExecutor", ThreadPoolTaskExecutor.class);
            scheduler = context.getBean(
                    "labScheduler", ThreadPoolTaskScheduler.class);

            CountDownLatch executed = new CountDownLatch(1);
            worker.execute(executed::countDown);

            assertThat(executed.await(
                    2, TimeUnit.SECONDS)).isTrue();
            assertThat(worker.getThreadPoolExecutor()
                    .isShutdown()).isFalse();
        }

        assertThat(worker.getThreadPoolExecutor()
                .isShutdown()).isTrue();
        assertThat(scheduler.getScheduledThreadPoolExecutor()
                .isShutdown()).isTrue();
    }

    @Test
    void canceledTaskIsRemovedFromSchedulerQueue() {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        LabThreadConfig.class)) {
            ThreadPoolTaskScheduler scheduler =
                    context.getBean(
                            "labScheduler",
                            ThreadPoolTaskScheduler.class);

            ScheduledFuture<?> future = scheduler.schedule(
                    () -> { },
                    Instant.now().plus(Duration.ofHours(1)));

            assertThat(future).isNotNull();
            assertThat(future.cancel(false)).isTrue();

            assertThat(scheduler.getScheduledThreadPoolExecutor()
                    .getQueue()).isEmpty();
        }
    }
}
```

Spring initializes and destroys context-owned beans automatically. `setRemoveOnCancelPolicy(true)` removes canceled delayed tasks from the queue. The test does not assume Spring's TestContext cache closes after each JUnit method; it creates and closes its **own dedicated context** intentionally.

### 9.8. `JupiterAutoCloseTest.java` — 1 Test

```java
// src/test/java/com/example/cleanup/JupiterAutoCloseTest.java
package com.example.cleanup;

import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AutoClose;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class JupiterAutoCloseTest {

    private static final AtomicBoolean CLOSED =
            new AtomicBoolean();

    @AutoClose
    AutoCloseable owned = () -> CLOSED.set(true);

    @BeforeAll
    static void reset() {
        CLOSED.set(false);
    }

    @Test
    void resourceRemainsOpenDuringMethod() {
        assertThat(CLOSED.get()).isFalse();
        assertThat(owned).isNotNull();
    }

    @AfterAll
    static void closureWasCalled() {
        assertThat(CLOSED.get()).isTrue();
    }
}
```

Under JUnit's `PER_METHOD` lifecycle, the `@AutoClose` instance field closes after the method, letting `@AfterAll` verify the flag. Never use a static mutable flag as a cross-class fixture in larger suites; here it serves strictly a single-class/single-method demo reset in `@BeforeAll`.

### 9.9. `application.properties`, `schema.sql`

```properties
# src/main/resources/application.properties
spring.sql.init.mode=always
```

```sql
-- src/main/resources/schema.sql
CREATE TABLE lab_notes (
    note_id VARCHAR(72) PRIMARY KEY,
    body VARCHAR(200) NOT NULL
);
```

`spring.sql.init.mode=always` fits the lab against a real PostgreSQL container. Production projects should use controlled migrations rather than applying schema-creation scripts unconditionally to real DBs.

### 9.10. `PostgresTestConfig.java` — Spring-Owned Testcontainer

```java
// src/test/java/com/example/cleanup/PostgresTestConfig.java
package com.example.cleanup;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
public class PostgresTestConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgres() {
        return new PostgreSQLContainer<>("postgres:16-alpine");
    }
}
```

Do not use `@Testcontainers` or `@Container`: PostgreSQL is a **Spring bean**. Boot 3.5 starts it before dependent beans and stops it after dependent beans are destroyed, avoiding mismatches between JUnit class-scoped containers and cached `ApplicationContext`s.

### 9.11. `JdbcResourceIntegrationTest.java` — 3 Tests

```java
// src/test/java/com/example/cleanup/JdbcResourceIntegrationTest.java
package com.example.cleanup;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.UUID;

import com.zaxxer.hikari.HikariDataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.DirtiesContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Import(PostgresTestConfig.class)
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class JdbcResourceIntegrationTest {

    @Autowired
    HikariDataSource hikari;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void borrowedConnectionIsReturnedToPool()
            throws Exception {
        Connection borrowed = hikari.getConnection();

        try (borrowed) {
            assertThat(borrowed.isClosed()).isFalse();
            assertThat(borrowed.getMetaData()
                    .getDatabaseProductName())
                    .isEqualTo("PostgreSQL");
        }

        assertThat(borrowed.isClosed()).isTrue();
        assertThat(hikari.getHikariPoolMXBean()
                .getActiveConnections()).isZero();
        assertThat(hikari.isClosed()).isFalse();
    }

    @Test
    void closesStatementResultSetAndConnection()
            throws Exception {
        try (Connection connection = hikari.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement("SELECT 7");
             ResultSet rows = statement.executeQuery()) {
            assertThat(rows.next()).isTrue();
            assertThat(rows.getInt(1)).isEqualTo(7);
            assertThat(rows.next()).isFalse();
        }

        assertThat(hikari.getHikariPoolMXBean()
                .getActiveConnections()).isZero();
    }

    @Test
    void cleansOnlyItsOwnCommittedRow() {
        String id = UUID.randomUUID().toString();

        try {
            jdbc.update(
                    "INSERT INTO lab_notes(note_id, body) "
                            + "VALUES (?, ?)",
                    id, "test-owned");

            Integer count = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM lab_notes "
                            + "WHERE note_id = ?",
                    Integer.class, id);

            assertThat(count).isEqualTo(1);
        }
        finally {
            jdbc.update(
                    "DELETE FROM lab_notes WHERE note_id = ?", id);
        }

        Integer remaining = jdbc.queryForObject(
                "SELECT COUNT(*) FROM lab_notes "
                        + "WHERE note_id = ?",
                Integer.class, id);

        assertThat(remaining).isZero();
        assertThat(hikari.isClosed()).isFalse();
    }
}
```

Never call `hikari.close()` inside tests because the pool belongs to the Spring context. `@DirtiesContext(AFTER_CLASS)` closes the context when the class finishes; Spring Boot's managed container shutdown runs after bean destruction. `getActiveConnections()==0` is asserted here in an **isolated demo** (JUnit methods are sequential with no background DB clients); never copy it onto a shared pool with active listeners.

### 9.12. Total Test Count and Run Commands

| Test class | `@Test` methods | Needs Docker? | Contract |
| --- | ---: | --- | --- |
| `OwnedExecutorTest` | 4 | No | Bounded shutdown/cancellation |
| `SpringPoolLifecycleTest` | 2 | No | Spring bean shutdown, scheduler queue |
| `JupiterAutoCloseTest` | 1 | No | JUnit resource field close |
| `JdbcResourceIntegrationTest` | 3 | Yes | JDBC borrowed handles, pool, data cleanup |
| **Total** | **10** | Full suite needs Docker | Method/context/container cleanup |

```bash
java -version
mvn -version

# 7 JUnit methods requiring no Docker:
mvn -B -ntp -Dtest=OwnedExecutorTest,SpringPoolLifecycleTest,JupiterAutoCloseTest test

# 3 JDBC/PostgreSQL integration tests requiring Docker:
docker version
docker info
mvn -B -ntp -Dtest=JdbcResourceIntegrationTest test

# All 10 methods:
mvn -B -ntp test
```

These are instructions **for the learner to run themselves**, not a report claiming Maven or Docker executed during authoring. Never fabricate a `BUILD SUCCESS` console log; output depends on JDK, CI runner, and image pulls.

## 10. Other Clients and Connections Must Be Cleaned Up by Their Owners

### 10.1. RabbitMQ and Spring AMQP

When the Spring context creates `CachingConnectionFactory` and listener containers, let the context manage them. If a test creates its own connection factory, destroy/close it only after all listeners have stopped.

Order:

```text
stop new message production (if test owns it)
  → stop listener container
  → bounded wait for in-flight handlers/ACKs
  → close test-owned client/connection factory
  → clean test-owned queue/vhost
  → stop broker container at owner lifecycle
```

Never close a shared Spring connection factory in `@AfterEach` while other classes still use the context. `RabbitTemplate.convertAndSend` does not guarantee a consumer has finished processing the message, so "send returned" is not a cleanup guarantee.

### 10.2. Kafka Producers/Consumers

`KafkaConsumer` is not thread-safe for arbitrary concurrent calls. The consumer thread typically owns `poll()` and calls `close()` in `finally`; another thread can call `wakeup()` to unblock `poll()`. Then join with a bounded timeout; test-created producers call `flush()`/`close(Duration)`.

When Spring Kafka manages `KafkaMessageListenerContainer` and producer factories, the context is the owner. Never stop a shared broker before listeners stop. Messages, topics, and consumer group offsets have an external lifecycle: stopping the client does not delete topics or offsets.

### 10.3. HTTP Clients, Servers, Reactor Netty

- Test-created `com.sun.net.httpserver.HttpServer`: `server.stop(0)` in `@AfterEach` or `finally`.
- Test-created Apache `CloseableHttpClient`: `close()`.
- Java `HttpClient` on Java 17 does not have the same `AutoCloseable` lifecycle as newer releases; check the JDK implementation rather than copying Java 21+ snippets.
- Test-created Reactor Netty `ConnectionProvider`/`LoopResources`: `dispose()` or await `disposeLater()` per API/version.
- Spring-managed `WebClient` typically shares Reactor resources and does not own global event loops; never dispose global resources inside a method while other classes still use them.
- Local HTTP stubs use port 0 and dynamic URLs rather than hard-coding ports 8080/9999.

### 10.4. Redis and R2DBC

Spring-managed `RedisConnectionFactory` destroys automatically with the context; borrowed `RedisConnection`s or cursors/streams must be closed per API. Never run `FLUSHALL` to clean up one test on a shared Redis instance.

R2DBC `Connection.close()` returns a reactive `Publisher`, not a JDBC `AutoCloseable`; subscribe and verify completion per reactive contracts. `StepVerifier` finishing a subscription does not mean the network connection pool or container has closed. Distinguish releasing a connection lease from closing the pool owner.

### 10.5. Filesystem and Object Store

- Use `@TempDir`/unique filenames instead of sharing `./target/report.json` across concurrent tests.
- Close streams before cleaning up directories.
- For S3/object storage, prefix keys by CI run ID/test ID and delete only that prefix, never the entire bucket.
- Retry cleanup if external APIs exhibit eventual consistency, without infinite retries or hiding permission errors.

## 11. Parallel Tests and Cached Contexts: Hazardous Scenarios

### 11.1. `@DirtiesContext` with Parallel Classes

One class can close a cached context while another class is actively using it if scheduled concurrently without coordination. Spring TestContext docs advise caution with `@DirtiesContext`, bean overrides/`@MockitoBean`, global state, and shared external resources. When after-class context closing is needed, serialize related classes or separate context identities.

### 11.2. `@ResourceLock` Is Not a Distributed Lock

JUnit `@ResourceLock` coordinates tests within the same Jupiter test plan, yet does not lock across Surefire JVM forks, Maven parallel modules, or CI jobs. Use dedicated namespaces/IDs to clean up files/DB rows/queues by owner.

### 11.3. Connection Leak vs Data Leak

- A test inserts rows and calls `Connection.close()`: the connection returned to the pool, yet data may **have committed** and still remain in the database.
- A test deletes rows in `@AfterEach` yet forgets `Connection.close()`: data is clean, yet the pool leaks.
- A `@Transactional` test rolls back while a background scheduler sends a broker message: test-thread DB rollback **does not** cancel the message.
- A `@DirtiesContext` test spawns a `static ExecutorService` via `new` outside Spring: closing the context knows nothing about that resource.

Test **each state/resource type individually** rather than assuming one flag guarantees "clean test".

### 11.4. Stop Order When DB/Broker Are Involved

When workers may still call the DB or broker:

1. Disable new work/cron triggers.
2. Cancel/stop listeners and producers.
3. Await bounded in-flight work.
4. Shut down executors/schedulers and verify termination.
5. Close client/pool connections.
6. Stop the backing container.
7. Clean up test-owned external data per ownership policy before stopping the container if provider access is needed.

Spring Boot-managed containers handle shutdown ordering for dependent beans, whereas tasks created manually outside Spring require explicit cleanup.

## 12. Diagnosing Resource Leaks and Hanging Tests

| Symptom | Possible Cause | Evidence / Fix |
| --- | --- | --- |
| Maven refuses to exit | Non-daemon thread never shut down | Thread dump of test JVM, executor `isTerminated` |
| Spring task keeps ticking | Cached context or manually created scheduler | Cancel `ScheduledFuture`, disable registration, align context lifetime |
| `TaskRejectedException` in next class | Prior method shut down shared Spring executor | Leave ownership to context; never close in `@AfterEach` |
| `Connection refused` after Class A | `@Container` stopped while cached context reused | Spring-managed container or dirty context |
| Hikari active count climbs | Unclosed borrowed JDBC handles | `try-with-resources`, test-only Hikari MXBean |
| Hikari pool already closed | Test method called `hikari.close()` prematurely | Let Spring destroy the bean |
| JVM connection/socket leak | Unclosed HTTP/Kafka/gRPC clients | Explicit owner teardown |
| Leftover Docker containers | Resource reaper/lifecycle failure | Test-owned IDs/labels, no global prune |
| `@AfterAll` doesn't see pool shut down | Spring context still alive in cache | Dedicated manual context close test |
| Tests fail only in parallel | Shared context/resource cleanup race | Unique namespaces, selective serialization |
| Teardown timeout | Non-cooperative task | Bounded await + diagnostics, fix worker |
| Broker listener keeps receiving after test | Context/listener still active | Stop listener, await in-flight work |
| File cannot be deleted | Open stream/file handle | Close handles before `TempDir` cleanup |

### 12.1. When a Thread Dump Is Needed

Run `jcmd <test-JVM-PID> Thread.print` or `jstack <test-JVM-PID>` (on supported JVMs) to find app/test-created thread names. Maven Surefire may fork a JVM; the Maven parent PID is not the test worker PID. Never call `System.exit(0)` inside JUnit just to "make the test process exit".

### 12.2. `shutdownNow()` Cannot Rescue Every Task

Tasks blocked on non-interruptible I/O or deadlocked can survive forced shutdown. After a bounded timeout, fail the test and emit diagnostics. A CI job timeout can kill the whole fork as a last line of defense, though that is no proof of graceful cleanup.

### 12.3. Leak Detection Does Not Fix the Leak

Hikari leak detection warns when a borrowed connection is held too long; it does not close the connection. A slow SQL query can trigger the warning before releasing legitimately; inspect checkout stack traces/durations and active pool state before jumping to conclusions.

### 12.4. Docker Orphan Cleanup Must Be Scoped

If a job is hard-killed, `@AfterAll` cannot be guaranteed to run. Testcontainers' resource reaper and CI cleanup policies filtering by owner IDs/labels help clean orphans. Never run `docker system prune --volumes` on a shared Docker daemon or delete others' volumes/containers.

## 13. CI and Operability

### 13.1. Resource Scopes

```text
Method resources → close in @AfterEach/try-with-resources
Class resources  → close in @AfterAll
Spring beans     → close on ApplicationContext destruction
Container bean   → stop after dependent Spring beans
CI job resources → cleanup after test process/timeout
External data    → delete only test-owned namespace/IDs
```

### 13.2. Illustrative GitHub Actions Workflow

```yaml
name: Resource Cleanup Tests

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-24.04
    timeout-minutes: 20

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Docker preflight
        run: |
          docker version
          docker info --format 'Engine={{.ServerVersion}}'
      - name: JUnit + PostgreSQL integration
        run: mvn -B -ntp test
      - name: Upload Surefire reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: cleanup-reports
          path: target/surefire-reports/
          if-no-files-found: ignore
```

Container integration jobs require a Docker-compatible daemon, mapped ports, and container creation permissions. If Docker is missing, mandatory integration tests are an **environment failure**, not a silent skip. For untrusted PRs, avoid exposing a privileged Docker socket with shared secrets outside policy.

### 13.3. Forks and CI Shards

`forkCount=2` gives two JVMs separate Spring caches and statics, yet both can hit the same external database if configured with the same URL. JUnit `@ResourceLock` does not lock across forks. For external DBs/brokers/Redis in CI, namespace by run ID/fork/test ID with scoped cleanup.

### 13.4. Measurable Cleanliness

A healthy suite not only passes business assertions, it ensures:

- Test-created non-daemon executors do not outlive the JUnit worker.
- Spring-owned pools shut down cleanly when the context closes.
- Borrowed pool connections are returned.
- Test-specific scheduled tasks are canceled.
- Container lifecycles stay aligned with the context cache.
- Temp files/queues/rows stay inside owner namespaces.
- Production endpoints are never hit and shared resources are never wiped.
- Cleanup failures fail loudly with `FAIL`/`ERROR` rather than swallowed exceptions.

## 14. Mistakes to Avoid

**Mistake 1: `Future.get()` returning means the pool closed.** False; `get` only awaits the task, never shutting down the pool.

**Mistake 2: `shutdownNow()` always kills every thread.** False; it is a best-effort interrupt, and workers must cooperate.

**Mistake 3: `Thread.sleep(500)` followed by `Thread.activeCount()`.** Measures unrelated JVM threads and is timing-flaky.

**Mistake 4: Shutting down a Spring executor bean in `@AfterEach`.** Cached contexts and other tests still need that bean.

**Mistake 5: Assuming `@DirtiesContext` wipes Redis/DB data.** It closes/evicts the context without clearing external side effects.

**Mistake 6: Assuming `Connection.close()` closes the whole Hikari pool.** On a borrowed proxy, `close()` returns the connection to the pool.

**Mistake 7: Closing the Hikari pool after every query.** The pool is a Spring-managed singleton; closing it breaks later tests.

**Mistake 8: Using `@Transactional` to shut down brokers/executors.** DB rollback does not manage external threads or sockets.

**Mistake 9: Assuming a static `@Container` lives until JVM exit.** Under the JUnit extension, it stops after the test class.

**Mistake 10: Assuming the Spring context always closes after a class.** The context cache can reuse it across classes.

**Mistake 11: Putting `@Container` on a Spring-managed container bean.** Two lifecycle owners will conflict.

**Mistake 12: Asserting in `@AfterAll` that a Spring-managed pool shut down before the listener closes the context.** Check lifecycle timing or use a manual context close test.

**Mistake 13: Wiping an entire DB/queue to "guarantee cleanliness".** Can delete data belonging to concurrent parallel tests.

**Mistake 14: Calling Kafka consumer `close()` from an arbitrary thread while `poll()` is running.** Use ownership/`wakeup` and bounded joins.

**Mistake 15: Disabling Testcontainers' resource reaper to dodge Docker errors.** Leaves orphaned containers/volumes behind.

**Mistake 16: Using `@Timeout` instead of cleanup.** Timeouts do not guarantee unresponsive workers or containers stop cleanly.

**Mistake 17: Leaving streams open before `@TempDir` cleanup.** Frequently fails on Windows due to locked file handles.

**Mistake 18: Setting Boot task shutdown properties expecting custom pool beans to inherit them.** Custom beans must be configured directly or via Boot builders.

## 15. Hands-On Exercises

1. Remove `OwnedExecutor.close()` in a demo branch and observe the stray live thread; restore the wrapper so the runner exits cleanly.
2. Write a task blocked on `CountDownLatch.await()`, verify `shutdownNow` sets interrupted status and `isTerminated`; avoid fixed sleeps.
3. Call `ScheduledFuture.cancel(false)` on a task scheduled an hour out and inspect the queue with and without `setRemoveOnCancelPolicy(true)`.
4. Create an `AnnotationConfigApplicationContext` and assert Spring-owned pools shut down **after** `close()`, not before.
5. Borrow 1 JDBC connection with `try-with-resources` and assert Hikari active connections = 0. Intentionally hold a handle (against a test-only container) to observe pool exhaustion.
6. Close a Spring-managed `HikariDataSource` prematurely in a demo branch and observe subsequent queries failing; restore proper ownership.
7. Trigger a static `@Container` + context reuse mismatch across two classes; fix it using a managed `@Bean` container or properly scoped `@DirtiesContext`.
8. Write a Rabbit listener test stopping the listener before closing the broker container; assert no handlers run after teardown.
9. Run two HTTP stubs concurrently on port 0, stopping each cleanly; never hard-code a shared port.
10. Create a Kafka consumer worker using `wakeup` to exit `poll`; join with a timeout and close on the owning thread.
11. Separate integration and unit jobs in CI; report "Docker unavailable" as an environment failure rather than a pass.
12. Enable 2 Surefire forks and use run/fork namespaces so external cleanup never deletes another fork's resources.

## 16. Self-Check Questions

**1.** Does `Future.get()` finishing shut down the executor automatically? — **No.**

**2.** Does `shutdownNow()` always terminate a task? — **No; tasks must support interruption/cancellation.**

**3.** Can Java 17 `ExecutorService` be used directly in `try-with-resources`? — **Not yet; use a wrapper or `finally`.**

**4.** Should a Spring-owned `ThreadPoolTaskExecutor` be shut down in `@AfterEach`? — **No; the context owns it.**

**5.** What does `Connection.close()` do on a Hikari borrowed handle? — **Returns it to the pool; does not close `HikariDataSource`.**

**6.** Does `@Transactional` rollback stop a scheduler thread? — **No.**

**7.** Does `@DirtiesContext` automatically delete committed DB rows? — **No.**

**8.** When does a static `@Container` managed by the JUnit extension stop? — **After the test class.**

**9.** When does a Spring-managed `@Bean PostgreSQLContainer` stop? — **When the context closes, after dependent beans.**

**10.** Under `PER_METHOD`, when does an `@AutoClose` instance field close? — **After each test method.**

**11.** Why isn't `Thread.activeCount()==0` a valid goal? — **JVM/JUnit/GC threads remain alive.**

**12.** If teardown fails while the test assertion passed, what should be reported? — **Cleanup failure, never a silent PASS.**

**13.** What happens if a container stops before a cached `DataSource` closes? — **Stale connections / connection refused in subsequent classes.**

**14.** Why avoid global Docker pruning during cleanup? — **It can delete resources owned by other jobs.**

## 17. Pre-Merge Checklist

- [ ] Every executor, scheduler, connection, and container has an explicit owner.
- [ ] Test-created executors perform shutdown + bounded await.
- [ ] Cleanup still runs when test assertions throw.
- [ ] Tasks handle interruption cleanly instead of swallowing it and looping.
- [ ] Test-owned scheduled futures are canceled when no longer needed.
- [ ] Spring-managed pools are never closed prematurely by individual methods.
- [ ] Context caching and `@DirtiesContext` are used intentionally.
- [ ] Auto-configured task shutdown properties are not mistaken to apply to custom beans.
- [ ] Borrowed JDBC handles, statements, and result sets close via `try-with-resources`.
- [ ] Hikari pool ownership is clear: Spring-owned vs test-created.
- [ ] Transaction rollbacks are never treated as cleanup for external resources.
- [ ] Testcontainers lifecycles align with contexts: class-owned vs Spring-managed.
- [ ] Spring-managed containers stop after dependent beans.
- [ ] `@Container` extension management is never mixed with Spring-managed bean ownership.
- [ ] Resources are never stopped while another class or fork still uses them.
- [ ] External data cleanup is scoped by UUID/namespace.
- [ ] HTTP mocks shut down their servers and use random ports.
- [ ] Kafka/Rabbit listeners stop and drain before client/container shutdown.
- [ ] Neither `Thread.sleep` nor global thread counts are used as primary cleanup proof.
- [ ] Bounded cleanup timeouts emit clear failure diagnostics.
- [ ] CI uses no production credentials and performs no global pruning.
- [ ] Unit, integration, skipped, and environment failures are clearly distinguished.
- [ ] Sample projects are never claimed executed if only authored.

## 18. Official Documentation

- [Spring Boot 3.5 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html): executor/scheduler implementations.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.task.execution.shutdown.*` and `spring.task.scheduling.shutdown.*`.
- [Spring Framework 6.2 — ExecutorConfigurationSupport](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/concurrent/ExecutorConfigurationSupport.html): shutdown/drain/await.
- [Spring Framework 6.2 — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): managed executor lifecycle.
- [Spring Framework 6.2 — ThreadPoolTaskScheduler](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html): scheduled futures and remove-on-cancel.
- [Spring Framework — TestContext Cache](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html): reused contexts and JVM scope.
- [Spring Framework — Parallel Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/parallel-test-execution.html): dirty/shared contexts and parallelism.
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection`, managed container beans, and shutdown ordering.
- [Testcontainers — JUnit 5](https://java.testcontainers.org/test_framework_integration/junit_5/): static vs instance `@Container` lifecycles.
- [JUnit 5.12 — User Guide](https://docs.junit.org/5.12.0/user-guide/): lifecycle callbacks, `@AutoClose`.
- [Java 17 — ExecutorService API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): shutdown/await.
- [Java 17 — ScheduledExecutorService API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html): scheduling/cancellation.
- [Java 17 — Connection API](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html): JDBC `AutoCloseable`.
- [HikariCP repository/documentation](https://github.com/brettwooldridge/HikariCP): pool lifecycle/metrics/leak detection.

**Conclusion:** Proper resource cleanup depends on *who owns the resource and who is still using it*, not on closing everything indiscriminately. Tests creating executors must shut them down with bounded awaits; scheduled futures must be canceled; JDBC callers must return borrowed handles; the Spring context closes Hikari/executor/scheduler beans; and Spring-managed containers stop **after** dependent beans. Combine ownership-scoped cleanup, assertions on termination/connection states, and lifecycles aligned with the TestContext cache so suites never hang, never hit stale connections, and never destroy parallel tests' data.