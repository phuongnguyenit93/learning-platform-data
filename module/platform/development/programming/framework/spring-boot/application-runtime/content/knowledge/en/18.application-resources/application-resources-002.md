# Registering Clients, Connection Pools, and Executors as Container-Managed Resources

## 1. Why Must Shared Resources Belong to ApplicationContext?

A Spring Boot application typically owns many resources whose lifetime extends beyond a single method call: HTTP clients maintaining connection pools, JDBC `DataSource`s, Redis or message broker clients, executors running background tasks, schedulers, file watchers, caches, and library-created threads. Creating an object is only half the problem; the other half is **who will stop usage, wait for in-flight work, and close the resource when the application shuts down?**

If a resource is created inside a controller/service with `new` or an arbitrary factory without a clear owner, the program may:

- Keep non-daemon threads alive, making it hard for the JVM to exit.
- Create multiple connection pools to the same database, exhausting allowed connections.
- Leave HTTP response streams/sockets unreturned to the pool.
- Close a client prematurely while another request is still using it.
- Let background tasks run after `DataSource` has already been destroyed.
- Leak classloaders/threads across repeated `ApplicationContext` creations in tests.
- Lose tasks on shutdown even after returning HTTP 202 Accepted.
- Fail to reclaim resources when bean initialization fails mid-way.

**Preferred solution in Spring Boot:** place shared resources into **Spring-managed beans** or leverage resources **auto-configured** by Spring Boot; callers simply inject and borrow the resource, while the Spring container holds lifecycle coordination authority.

That does not mean the container automatically closes everything stored in an object's fields. You must still choose a **single owner**, declare cleanup callbacks, define where per-operation handles are closed, design stop/await for background tasks, and verify actual shutdown behavior.

This lesson uses **Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+**. The complete example manages an Apache HTTP client, a HikariCP connection pool, and a `ThreadPoolTaskExecutor` together.

## 2. Ownership Mindset: Who Creates, Who Borrows, Who Closes?

A resource typically has two lifecycle tiers:

1. **Application tier:** pools and clients are created once, shared across services/requests, and closed when the owner (usually `ApplicationContext`) stops.
2. **Operation tier:** connections borrowed from a pool, JDBC statements, HTTP responses, and file streams are closed as soon as the operation finishes.

| Resource/Handle | Normal Scope | Who Closes? |
| --- | --- | --- |
| `CloseableHttpClient` / shared client pool | Application singleton | Owner Spring bean when context closes |
| `HikariDataSource` | Application singleton | Spring Boot/container when context closes |
| JDBC `Connection` borrowed from Hikari | Single operation/transaction | Borrower or transaction framework returns it to the pool |
| `Statement` / `ResultSet` | Single query | Operation code, typically via `try-with-resources` |
| HTTP response/response body stream | Single HTTP call | Caller/response handler per client API |
| `ThreadPoolTaskExecutor` | Application singleton | Spring lifecycle/destroy callback |
| Custom-created `ExecutorService` | Custom-defined owner scope | That owner itself, using shutdown/await |
| `ThreadPoolTaskScheduler` | Application singleton | Spring lifecycle/destroy callback |
| File stream | Single read/write activity | `try-with-resources` |
| `JdbcTemplate`/repository | Facade bean using `DataSource` | Typically does not close the shared `DataSource` |

**Important:** calling `connection.close()` on a connection obtained from Hikari normally **returns the connection to the pool**, not destroying the Hikari pool. Conversely, calling `hikariDataSource.close()` closes **the entire pool**, which can cause other requests to fail.

### 2.1. One owner, many borrowers

A client may be injected into many services, which does not give every service the right to call `close()`. Place ownership in:

- A dedicated resource bean with a destroy callback; or
- A single wrapper bean that owns the inner resource; or
- Spring Boot's / the integration library's auto-configuration.

**Do not** register both the raw client as a bean with a destroy callback and a wrapper that also closes **the exact same client**, unless you intentionally build and verify a special shared-ownership policy.

### 2.2. Do not use arbitrary static globals

```java
private static final ExecutorService EXECUTOR =
        Executors.newFixedThreadPool(8);
```

This is a counter-example snippet. A static pool lives for the process lifetime and is not bound to a single Spring context. When tests or redeploys create multiple contexts in the same JVM, which context closes it? If one context closes it, other contexts using this pool may fail; if nobody closes it, threads may remain alive.

Using a singleton **scoped to `ApplicationContext`** is clearer for most Spring Boot services.

## 3. Through Which Mechanisms Does Spring Manage Bean Lifecycles?

```text
SpringApplication.run(...)
     |
Create ApplicationContext
     |
Load bean definitions
     |
ApplicationContext.refresh()
     |
Create non-lazy singletons and inject dependencies
     |
Invoke init callbacks / BeanPostProcessors
     |
Beans used by services/runners/controllers
     |
Application shutdown
     |
Coordinated stop: SmartLifecycle / LifecycleProcessor
     |
Destroy singleton beans
     |
@Bean(destroyMethod="close"), @PreDestroy, DisposableBean ...
     |
ApplicationContext.close() completes
```

This is a conceptual diagram. A `@Lazy` bean that was never instantiated does not necessarily have an instance to destroy. For executors/background jobs, coordinated stop and destroy have distinct contracts.

### 3.1. @Bean(destroyMethod = "close")

```java
@Bean(destroyMethod = "close")
CloseableHttpClient httpClient() {
    return HttpClients.createDefault();
}
```

Snippet inside a `@Configuration` class, requiring Apache HttpClient 5 and `@Bean` imports. Spring calls `close()` when this bean is destroyed. For resources with the right method, this expresses the contract very clearly.

Spring Framework also supports **inferred destroy methods** for `@Bean`, typically detecting public methods such as `close()` and `shutdown()` or `AutoCloseable`. Even so, specifying `destroyMethod` explicitly makes ownership easier to read and review.

### 3.2. @PreDestroy

```java
@Component
class ResourceOwner {

    private final ExecutorService pool =
            Executors.newFixedThreadPool(2);

    @PreDestroy
    void cleanup() {
        pool.shutdown();
    }
}
```

This is a Spring Boot 3.x snippet importing `jakarta.annotation.PreDestroy`. It illustrates an owner bean closing a private field itself. However, `shutdown()` does not wait for tasks to finish; to be production-safe, you also need bounded await, cancellation policies, and handling for unfinished jobs.

### 3.3. DisposableBean and SmartLifecycle

`DisposableBean.destroy()` is a Spring callback, while `SmartLifecycle.stop(Runnable callback)` lets a bean participate in **coordinated stopping** by phase prior to destruction. When a service has continuously running producers/consumers, `SmartLifecycle` expresses stopping work intake and signaling completion more clearly than cramming everything into `@PreDestroy`.

Tasks running on an executor can keep executing after a service bean is destroyed if the executor is not coordinated. Therefore, configuring bean destruction is a **necessary condition**, not always sufficient for an orderly graceful shutdown.

## 4. Registering a Shared Apache HTTP Client as a Bean

Apache HttpComponents 5 provides `CloseableHttpClient`, which can hold a connection manager/pool. A basic configuration:

```java
@Configuration(proxyBeanMethods = false)
class PartnerClientConfiguration {

    @Bean(destroyMethod = "close")
    CloseableHttpClient partnerHttpClient() {
        PoolingHttpClientConnectionManager manager =
                PoolingHttpClientConnectionManagerBuilder.create()
                        .setMaxConnTotal(20)
                        .setMaxConnPerRoute(5)
                        .build();

        return HttpClients.custom()
                .setConnectionManager(manager)
                .build();
    }
}
```

This is a **class snippet**, requiring imports for `CloseableHttpClient`, `HttpClients`, `PoolingHttpClientConnectionManager`, `PoolingHttpClientConnectionManagerBuilder`, and Spring annotations. The hands-on section below provides complete code.

**Meaning:**

- `@Bean` lets Spring manage a single shared instance.
- The pool caps total connections and connections per route.
- With a connection manager not in shared mode, the Apache client owns the manager under its standard contract.
- Spring calls `client.close()` when the bean is destroyed, not after every HTTP request.
- Services inject the client; they only close **responses** in the proper scope.

### 4.1. Avoiding double-close of the connection manager

You can separate the connection manager into its own bean if multiple HTTP clients **share the same pool**. But then you must decide **who closes the manager** and whether clients use `setConnectionManagerShared(true)`. Do not register both the client and the manager as two resources owning the same manager without understanding the contract.

A simpler model for most services: one client bean owns one manager, and the client is closed once by the container.

### 4.2. Client wrapper for domain services

A `PartnerGateway` can expose business methods and own the raw HTTP client internally:

```java
@Bean(destroyMethod = "close")
PartnerGateway partnerGateway() {
    CloseableHttpClient apacheClient = HttpClients.createDefault();
    return new PartnerGateway(apacheClient);
}
```

This snippet assumes `PartnerGateway` implements `AutoCloseable` and `close()` closes `apacheClient`. If you choose this approach, **do not** simultaneously register `apacheClient` as a bean with a second destroy callback. The complete example uses this wrapper pattern, paired with a bounded connection manager.

### 4.3. Not every HTTP client on every JDK has the same close API

`java.net.http.HttpClient` in **Java 17** does not have the same `AutoCloseable.close()` contract as some newer JDK versions. Do not copy code using `try (HttpClient client = ...)` or `destroyMethod="close"` from newer JDK docs onto Java 17 without checking.

What you must do is choose the right lifecycle API **for the implementation and version in use**. In this guide, Apache's `CloseableHttpClient` is chosen because it has an explicit resource-closing contract.

## 5. HikariCP DataSource: Prefer Spring Boot Auto-Configuration

In Spring Boot 3.3, `spring-boot-starter-jdbc` and `spring-boot-starter-data-jpa` typically bring HikariCP into the runtime. When a JDBC driver is present and no custom `DataSource` bean is declared that causes it to back off, Boot can auto-configure a pooling `DataSource`.

Benefits:

1. One pool with a clear owner.
2. Externalized configuration via `spring.datasource.*` and `spring.datasource.hikari.*`.
3. Components inject `DataSource`, `JdbcTemplate`, or repositories.
4. The framework manages transactions/connections per contract.
5. On context close, `HikariDataSource` is destroyed according to lifecycle.

Typical service example:

```java
@Service
class ProductRepository {

    private final JdbcTemplate jdbcTemplate;

    ProductRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    int numberOfProducts() {
        return jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM products", Integer.class);
    }
}
```

This snippet assumes a `products` table exists and needs imports for `@Service` and `JdbcTemplate`. The repository **does not create a pool itself** and does not call `dataSource.close()` after each query.

### 5.1. Example properties

```properties
spring.datasource.url=jdbc:postgresql://db.example.internal:5432/catalog
spring.datasource.username=example_user
spring.datasource.password=example_secret

spring.datasource.hikari.maximum-pool-size=12
spring.datasource.hikari.minimum-idle=2
spring.datasource.hikari.connection-timeout=3000
spring.datasource.hikari.max-lifetime=1800000
```

This is an **illustrative** configuration; do not use sample usernames/passwords/hostnames in production. Place secrets in environment variables/a secret manager and restrict logging. `maximum-pool-size` must be calculated **across total pods/instances**: 25 instances × 12 connections = up to 300 connections to the DB, not counting other services.

Note: do not raise pool size indefinitely to fix slow queries. Inspect transaction duration, connection hold time, DB max connections, timeouts, and workload.

### 5.2. Close the borrowed connection, not the pool

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
             "SELECT id FROM products WHERE id = ?")) {

    statement.setLong(1, productId);

    try (ResultSet result = statement.executeQuery()) {
        if (result.next()) {
            process(result.getLong("id"));
        }
    }
}
```

This snippet assumes `dataSource`, `productId`, `process`, and the `products` table already exist. When `try-with-resources` finishes, the JDBC handles are closed; with Hikari, `Connection.close()` **returns the borrowed connection to the pool** for reuse.

**Counter-example:**

```java
// Do not do this at the end of a request:
((HikariDataSource) dataSource).close();
```

This operation closes **the entire Hikari pool**. Other requests using the shared bean may fail. The pool belongs to the container, not to an individual request.

### 5.3. When multiple DataSources are needed

When an application has primary/replica DBs or multiple independent data sources, you can create multiple `@Bean DataSource` instances, using `@Qualifier`/`@Primary` and corresponding transaction managers. Ensure **each pool** has an owner/destroy callback and clearly specify which service injects which pool.

Creating a custom `DataSource` bean can cause Spring Boot to **back off** its default auto-configuration path. Avoid accidentally initializing a manual pool inside a service while another unused auto-configured Hikari pool also exists.

## 6. If You Must Configure HikariDataSource Manually

In a multi-database module, a custom Hikari bean can make sense:

```java
@Bean(destroyMethod = "close")
HikariDataSource auditDataSource() {
    HikariConfig config = new HikariConfig();
    config.setJdbcUrl("jdbc:h2:mem:audit;DB_CLOSE_ON_EXIT=FALSE");
    config.setUsername("sa");
    config.setPassword("");
    config.setMaximumPoolSize(3);
    return new HikariDataSource(config);
}
```

This snippet requires Hikari class imports and an H2 dependency. This is an in-memory DB for learning/testing, **not** a production credentials example. When the context closes, Spring calls `HikariDataSource.close()`.

### 6.1. Pool failure modes to distinguish

| Issue | Symptom | Resolution |
| --- | --- | --- |
| Connection leak | Borrowed connections not returned, pool exhausted | `try-with-resources`, transaction management, timeouts, leak detection |
| Pool leak | App/context stopped but pool remains alive | Container lifecycle/owner cleanup |
| Too many pools | Each service/request creates its own pool | Reuse singleton beans and audit pools per instance |
| Pool too small for workload | Queuing for connections, timeouts | Measure queries/transactions/concurrency before resizing |
| Invalid/stale connections | Queries fail after network failover | Driver/pool validation/timeouts, appropriate retries |

Hikari's `leakDetectionThreshold` helps detect connections held too long; it **does not** replace closing connections properly and does not fix pool ownership by itself.

## 7. ThreadPoolTaskExecutor as a Managed Resource

An executor holds worker threads, a queue, task state, and references to other beans. Creating a pool inside a controller is an anti-pattern:

```java
@PostMapping("/reports")
String requestReport() {
    ExecutorService pool = Executors.newFixedThreadPool(4);
    pool.submit(this::generateReport);
    return "accepted";
}
```

This is an anti-pattern snippet; the `generateReport` method and imports are undefined. Each request can create a new pool with no cleanup or shared backpressure. If the workers are non-daemon, the JVM may fail to exit.

Turn the executor into a bean:

```java
@Bean("managedWorkExecutor")
ThreadPoolTaskExecutor managedWorkExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(16);
    executor.setThreadNamePrefix("managed-work-");
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(5);
    return executor;
}
```

This method belongs to `@Configuration` or `@SpringBootApplication`; Spring creates, initializes, and destroys the bean. The controller does not need to call `shutdown()` itself after each submission.

### 7.1. Bounded queues and rejection policies

When `queueCapacity` is finite, the pool can grow from core to max after the queue fills, yet still has an upper bound. Callers must handle `TaskRejectedException`/`RejectedExecutionException` according to contract: return an appropriate error, perform bounded retries, or persist work to a durable queue.

When the queue is unbounded, `maxPoolSize` may rarely be reached because tasks keep entering the queue. That can increase latency or memory usage while thread count stays low.

### 7.2. JDK ExecutorService requires custom shutdown if created manually

- `shutdown()`: stops accepting new work, allowing submitted tasks to complete; **does not wait**.
- `awaitTermination(timeout, unit)`: bounded wait after shutdown.
- `shutdownNow()`: attempts to interrupt running tasks and returns unstarted ones, **best effort**.
- `isShutdown()` does not mean `isTerminated()`.
- `Future.cancel(true)` does not close the executor itself.
- `ExecutorService` on **Java 17** does not yet have `AutoCloseable.close()` as in newer JDK APIs.

If you must keep an `ExecutorService` in a private field, use an owner bean with `@PreDestroy`/`DisposableBean`, bounded await, and handling for unfinished tasks; do not expect GC to close threads automatically.

### 7.3. Schedulers share the same responsibility

A Spring-managed `ThreadPoolTaskScheduler` or Boot auto-configured `TaskScheduler` should be preferred for `@Scheduled`. A scheduler has a pool, task queue, and shutdown policy; it does not automatically provide persistent job storage or exactly-once delivery.

When jobs must survive restarts, an in-memory executor/scheduler is not enough. You need a durable queue, checkpoints, and idempotent processing.

## 8. Shutdown Must Respect the Dependency Graph

```text
SIGTERM / application shutdown
    |
Readiness REFUSING_TRAFFIC, drain HTTP traffic
    |
Stop producers/schedulers/consumers from accepting new jobs
    |
Executor stops accepting new tasks
    |
Await in-flight tasks (bounded)
    |
Commit/rollback/checkpoint/requeue unfinished jobs
    |
Close remaining borrowed response/connection handles
    |
Close HTTP client / DataSource pool / executor threads
    |
ApplicationContext.close() completes
```

This is the **desired flow**, not a guarantee that Spring automatically orders every custom component correctly. Bean dependency/destruction order and `SmartLifecycle` phases matter; a background task outside the container can still access an already destroyed resource.

### 8.1. Why not simply call close in ContextClosedEvent?

`ContextClosedEvent` is a shutdown milestone, but a listener cannot replace full lifecycle coordination. If a listener closes `DataSource` while tasks are still running, tasks can fail mid-transaction. For Spring-managed resources, prefer the proper owner's destroy callback and coordinated stop for producers/workers.

In a context hierarchy, a listener on the parent can also receive a child's `ContextClosedEvent`; failing to filter the event origin can close the parent's pool by mistake when a child closes.

### 8.2. SmartLifecycle for task-producing components

A `SmartLifecycle` component can:

1. On `start()`: subscribe to messages or start scheduling.
2. On `stop(Runnable callback)`: stop receiving messages, wait for in-flight work, and then invoke the callback.
3. Choose an appropriate phase so producers stop before consumers/resources according to dependencies.

The callback **must be invoked** when stopping completes, even when errors are handled, so the lifecycle processor can proceed. Do not hold the callback indefinitely.

### 8.3. Time budgets when running in Kubernetes

`server.shutdown=graceful` and `spring.lifecycle.timeout-per-shutdown-phase` apply to the corresponding Spring Boot/Framework phases. `ThreadPoolTaskExecutor` has its own await termination period. Kubernetes also enforces `terminationGracePeriodSeconds` before sending a hard kill.

If the platform allows 30 seconds while the executor waits 90 seconds, cleanup can be cut off mid-way. Design the total budget, network/DB timeouts, queue checkpoints, and test `SIGTERM` in staging.

## 9. Runnable Demo: HTTP Client, Hikari Pool, and Executor Managed Together by Spring

The following example **runs without an external database server or HTTP server**. H2 in-memory is used via auto-configured HikariCP; the Apache HTTP client is created without making network calls; a task runs inside a managed `ThreadPoolTaskExecutor`. When `ApplicationContext` closes, the program verifies that the pool and executor have stopped.

### 9.1. Structure

```text
managed-resources/
  settings.gradle
  build.gradle
  src/main/resources/application.properties
  src/main/java/com/example/resources/
    ManagedResourcesApplication.java
    ResourceConfiguration.java
    PartnerGateway.java
```

### 9.2. settings.gradle

```groovy
rootProject.name = 'managed-resources'
```

### 9.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.apache.httpcomponents.client5:httpclient5'
    runtimeOnly 'com.h2database:h2'
}
```

This is a Groovy DSL build script for the demo. The Spring Boot BOM manages versions for Apache HttpClient5 and H2. If you do not have a Gradle Wrapper yet, generate one with a compatible Gradle version or use Spring Initializr.

### 9.4. application.properties

```properties
# H2 in-memory: avoid H2 auto-shutdown outside Spring.
spring.datasource.url=jdbc:h2:mem:managed;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

# One Hikari pool auto-configured by Spring Boot.
spring.datasource.hikari.maximum-pool-size=4
spring.datasource.hikari.minimum-idle=0
spring.datasource.hikari.connection-timeout=3000

# Do not open an HTTP server in the demo.
spring.main.web-application-type=none
```

H2 is only for the example, not for use as a persistent DB. `DB_CLOSE_ON_EXIT=FALSE` prevents H2 auto-shutdown from conflicting with container lifecycle. The Hikari pool is managed separately by Boot.

### 9.5. PartnerGateway.java

```java
package com.example.resources;

import java.io.IOException;
import java.util.concurrent.atomic.AtomicBoolean;

import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;

public final class PartnerGateway implements AutoCloseable {

    private final CloseableHttpClient client;
    private final AtomicBoolean closed = new AtomicBoolean();

    public PartnerGateway(CloseableHttpClient client) {
        this.client = client;
    }

    public boolean isOpen() {
        return !closed.get();
    }

    @Override
    public void close() throws IOException {
        if (closed.compareAndSet(false, true)) {
            try {
                client.close();
            } finally {
                System.out.println("PARTNER_CLIENT_CLOSED");
            }
        }
    }
}
```

`PartnerGateway` is the sole owning wrapper of the Apache client in the demo. `isOpen()` only reflects the wrapper's flag, **not an HTTP/network health check**. `AtomicBoolean` keeps the wrapper from calling close repeatedly during cleanup, while stopping and awaiting in-flight requests remains the application's responsibility.

### 9.6. ResourceConfiguration.java

```java
package com.example.resources;

import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class ResourceConfiguration {

    @Bean(destroyMethod = "close")
    PartnerGateway partnerGateway() {
        PoolingHttpClientConnectionManager manager =
                PoolingHttpClientConnectionManagerBuilder.create()
                        .setMaxConnTotal(20)
                        .setMaxConnPerRoute(5)
                        .build();

        CloseableHttpClient httpClient = HttpClients.custom()
                .setConnectionManager(manager)
                .build();

        return new PartnerGateway(httpClient);
    }

    @Bean("managedWorkExecutor")
    ThreadPoolTaskExecutor managedWorkExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("managed-work-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(5);

        return executor;
    }
}
```

**Ownership in this file:**

- Spring manages the `PartnerGateway` bean and calls `close()` on destruction. The gateway closes the Apache `CloseableHttpClient`. Neither the manager nor the client is registered as a second bean with a destroy callback.
- Spring manages the `ThreadPoolTaskExecutor` bean and invokes its corresponding lifecycle/shutdown. Do not call `executor.initialize()` manually inside `@Bean`.
- The file **does not** create `HikariDataSource`: Boot auto-configuration handles that from the JDBC starter and properties.

### 9.7. ManagedResourcesApplication.java

```java
package com.example.resources;

import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import javax.sql.DataSource;

import com.zaxxer.hikari.HikariDataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@SpringBootApplication
public class ManagedResourcesApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ManagedResourcesApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        HikariDataSource pool;
        ThreadPoolTaskExecutor executor;

        try (ConfigurableApplicationContext context = app.run(args)) {
            pool = context.getBean(HikariDataSource.class);
            executor = context.getBean(
                    "managedWorkExecutor", ThreadPoolTaskExecutor.class);

            System.out.println("CONTEXT_ACTIVE=" + context.isActive());
        }

        System.out.println("DB_POOL_CLOSED=" + pool.isClosed());
        System.out.println("EXECUTOR_TERMINATED="
                + executor.getThreadPoolExecutor().isTerminated());
    }

    @Bean
    ApplicationRunner exercise(
            DataSource dataSource,
            PartnerGateway gateway,
            @Qualifier("managedWorkExecutor")
            ThreadPoolTaskExecutor executor) {

        return args -> {
            try (Connection connection = dataSource.getConnection();
                 Statement statement = connection.createStatement();
                 ResultSet rs = statement.executeQuery("SELECT 1")) {

                rs.next();
                System.out.println("DB_RESULT=" + rs.getInt(1));
            }

            System.out.println("PARTNER_CLIENT_OPEN=" + gateway.isOpen());

            Future<String> future = executor.submit(() -> "processed");
            System.out.println("TASK_RESULT="
                    + future.get(3, TimeUnit.SECONDS));
        };
    }
}
```

Step-by-step walkthrough:

1. Spring Boot creates a non-web `ApplicationContext` and `HikariDataSource` from properties.
2. A `PartnerGateway` bean is created, containing an Apache closeable HTTP client.
3. A `ThreadPoolTaskExecutor` bean is created and managed by Spring.
4. After refresh, `ApplicationRunner` acquires a JDBC connection, executes `SELECT 1` on H2, and returns handles via `try-with-resources`.
5. The runner checks the Gateway flag without making external network calls.
6. The runner submits a very short task and awaits the `Future` for up to three seconds; the task completes before the runner returns.
7. `SpringApplication.run(...)` finishes. `main` retrieves `HikariDataSource` and the executor to inspect them, printing active status.
8. Exiting `try-with-resources` on **ConfigurableApplicationContext** calls `context.close()`, and the container runs shutdown and destroy callbacks.
9. After `context.close`, `main` checks `HikariDataSource.isClosed()` and the thread pool status.

### 9.8. Run command

```bash
./gradlew bootRun
```

Windows CMD: `gradlew.bat bootRun`; PowerShell: `.\gradlew.bat bootRun`. If the project has multiple main classes, configure `springBoot.mainClass` in Gradle rather than assuming the plugin picks the right one automatically.

### 9.9. Output lines printed by the demo itself

Ignore the banner, Spring/Hikari logs, and Gradle output. On a normal successful run:

```text
DB_RESULT=1
PARTNER_CLIENT_OPEN=true
TASK_RESULT=processed
CONTEXT_ACTIVE=true
PARTNER_CLIENT_CLOSED
DB_POOL_CLOSED=true
EXECUTOR_TERMINATED=true
```

This code path sends no network requests and has no long-running tasks, so cleanup is fast. `PARTNER_CLIENT_CLOSED` runs during bean destruction; it appears after `CONTEXT_ACTIVE` and before the two check lines after `close()`. **Do not assume a fixed destroy log order for other beans** as you expand the application.

If startup or the query throws an exception, these success lines will not necessarily appear; that is a case requiring dedicated error handling and testing.

## 10. Why Not Create Clients/Pools/Executors Directly Inside Services?

```java
@Service
class UnsafeService {
    private final CloseableHttpClient http =
            HttpClients.createDefault();
    private final ExecutorService workers =
            Executors.newFixedThreadPool(4);

    void performAsync(Runnable job) {
        workers.submit(job);
    }
}
```

This is a **counter-example** missing lifecycle callbacks and imports. Because `UnsafeService` is a bean, Spring manages that bean, **which does not mean every private field is a managed bean**. Without `@PreDestroy` or owner logic, the workers and HTTP client can outlive the service's destruction.

**Preferred:** register resource beans separately via `@Configuration` and inject them into the service. If a service must own an internal resource, write an owner bean with `@PreDestroy` and cooperative cleanup.

### 10.1. Owner bean example with JDK ExecutorService

```java
@Component
class OwnedJobs {

    private final ExecutorService executor =
            Executors.newFixedThreadPool(2);

    void submit(Runnable task) {
        executor.submit(task);
    }

    @PreDestroy
    void stop() {
        executor.shutdown();
        try {
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        } catch (InterruptedException ex) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
```

This is an **illustrative class** needing imports for `Component`, `PreDestroy`, `ExecutorService`, `Executors`, and `TimeUnit`. For production use, continue tracking unstarted tasks, verify executor termination, or log/cancel/checkpoint appropriately. `shutdownNow()` is best effort, not a guarantee of complete shutdown.

For most Spring workloads, a `ThreadPoolTaskExecutor` bean with container-managed lifecycle requires less boilerplate.

## 11. Do Not Close Twice and Do Not Close the Wrong Object

Common mistakes:

- `PartnerGateway.close()` closes the Apache client itself while another `CloseableHttpClient` bean has a destroy callback on **the same instance**.
- A service calls `dataSource.close()` after every request when the datasource is a singleton.
- A controller calls `executor.shutdown()` after submitting to "clean up," causing the next request to be rejected.
- `@PreDestroy` closes the resource, and then `@Bean(destroyMethod="close")` closes the same resource again without idempotence.
- The HTTP client closes the pool, while code still holds unhandled response streams.
- A Spring parent context owns a resource, and a child context closes and triggers cleanup on the parent's resource.

Solution: **one owner, one lifecycle policy**, while distinguishing per-call handle cleanup from shared resource shutdown.

### 11.1. Inferred destroy methods do not solve every case

With `@Bean`, Spring can infer `close`/`shutdown` methods. However, if an object sits in a private field rather than its own bean and the owner does not invoke cleanup, Spring lacks enough information to close that field automatically.

Conversely, a plain facade such as `RestTemplate` is typically **not itself the resource holding the pool**. Identify which underlying client/request factory owns the resource, instead of adding `destroyMethod="close"` to a class that lacks such a method.

### 11.2. Uninstantiated lazy beans

A `@Lazy` bean that was never created has no instance to destroy. This is not a resource leak if the bean never opened a resource. But if the resource is created in a utility or static field outside `BeanFactory`, `@Lazy` metadata does not make Spring aware of that resource.

## 12. What If Startup Fails Mid-Way While Building a Resource?

A subtle bug:

```java
@Bean
PartnerGateway partnerGateway() {
    CloseableHttpClient raw = HttpClients.createDefault();

    validateConfiguration(); // May throw an exception.

    return new PartnerGateway(raw);
}
```

This is an illustrative snippet: `validateConfiguration()` is undefined. If validation throws an exception **after the client is created but before the method returns the bean**, Spring does not yet have a bean instance on which to invoke destroy. The raw resource may leak.

**Solutions:**

- Validate configuration before opening resources.
- Use `try/catch`, closing already created resources if subsequent initialization fails.
- If opening multiple resources, hand off ownership step-by-step explicitly.
- Test startup failures, not only the happy path.

A pattern:

```java
@Bean(destroyMethod = "close")
PartnerGateway partnerGateway() throws IOException {
    validateConfiguration(); // Fail early before opening the client.

    CloseableHttpClient raw = HttpClients.createDefault();
    try {
        return prepareGateway(raw);
    } catch (RuntimeException ex) {
        raw.close();
        throw ex;
    }
}
```

This is a **snippet** requiring real `validateConfiguration`/`prepareGateway` helpers; its purpose is illustrating an exception-safe factory, not a standalone runnable file.

## 13. ThreadPoolTaskExecutor and In-Flight Tasks During Shutdown

If tasks use `PartnerGateway` and `DataSource`, closing them before tasks complete can cause tasks to fail mid-execution. Yet waiting indefinitely can also cause Kubernetes to kill the pod before cleanup finishes.

A responsible strategy:

1. Advertise readiness refusing or stop accepting new traffic where appropriate.
2. Stop schedulers, consumers, and producers from submitting tasks.
3. Switch the executor to stop accepting new jobs.
4. Wait for running tasks within a deadline.
5. If overdue, cancel/rollback/checkpoint/requeue per contract.
6. Release remaining borrowed JDBC/HTTP handles.
7. Close underlying pools/clients once no valid consumers remain.
8. Measure shutdown duration and unfinished task counts.

Spring's `ThreadPoolTaskExecutor`/`ThreadPoolTaskScheduler` support shutdown policies, but **do not automatically turn tasks into durable transactions**.

### 13.1. setWaitForTasksToCompleteOnShutdown and awaitTermination

`setWaitForTasksToCompleteOnShutdown(true)` lets the executor finish queued work instead of interrupting it immediately upon shutdown. `setAwaitTerminationSeconds(5)` bounds how long the container waits in the corresponding shutdown phase. Do not assume combining both flags guarantees every task finishes within five seconds; if tasks hang or the queue is long, separate error handling is needed.

When using `SmartLifecycle` to stop producers, note that executor policies can change task acceptance after `ContextClosedEvent`. Spring Framework 6.1 changed default coordinated shutdown behavior, so check the version's Javadoc when enabling these flags together.

### 13.2. Coordinating with graceful shutdown

For web servers, Spring Boot supports `server.shutdown=graceful` and `spring.lifecycle.timeout-per-shutdown-phase`. Kubernetes also has `terminationGracePeriodSeconds`. The combined drain+await+cleanup duration must fit within the infrastructure limit.

A worker writing data needs transactions/offset checkpoints/retries, not just a longer timeout. If critical tasks must survive restarts, use a durable queue/job store.

## 14. Does Boot Configuration Apply to Custom Executors?

Spring Boot 3.3 auto-configures `AsyncTaskExecutor` when no `Executor` bean causes auto-configuration to back off. On Java 17, the typical implementation is `ThreadPoolTaskExecutor`. Properties such as:

```properties
spring.task.execution.pool.core-size=4
spring.task.execution.pool.max-size=8
spring.task.execution.pool.queue-capacity=64
spring.task.execution.shutdown.await-termination=true
spring.task.execution.shutdown.await-termination-period=10s
```

affect the executor **auto-configured by Boot under the right conditions**, and do not automatically configure custom beans created with `new ThreadPoolTaskExecutor()` or `Executors.newFixedThreadPool(...)`.

When an application has multiple executor beans, select the right pool:

```java
@Async("managedWorkExecutor")
public CompletableFuture<String> compute() {
    return CompletableFuture.completedFuture("done");
}
```

This is an illustrative method inside a Spring bean, requiring `@EnableAsync`, `@Async`, and invocation through a proxy; self-invocation `this.compute()` can bypass the proxy. `managedWorkExecutor` must be a bean named as configured, not merely a local variable.

Do not assume Spring MVC async, GraphQL, and `@Async` all pick the same executor when custom pools exist; Spring Boot applies bean-type/name selection rules, such as `applicationTaskExecutor` for certain web integrations.

## 15. Multiple ApplicationContexts and Parent-Child Contexts

Spring can have multiple contexts in integration tests, hierarchies, or multiple applications running in the same JVM. If a parent context owns the Hikari pool while a child only uses it, closing the child **does not** mean the parent's pool should be closed.

Rules:

- Whichever context owns a resource bean is its lifecycle owner.
- A child can inject beans from its parent, but must not close the parent's resource after a request.
- A `ContextClosedEvent` listener on the parent can receive child events; distinguish event origin when performing manual shutdown actions.
- Avoid static executors/global clients shared across multiple contexts without a clear JVM-level owner.
- TestContext caching can reuse the same application context; do not manually close a resource in a test and break subsequent tests.

If you need to test closing, create an independent context and close it inside the integration test rather than calling close on a bean in a shared cached context.

## 16. Testing Lifecycle: Do Not Only Test That the Application Starts

The test suite should cover:

**Creation:**
- Each singleton resource is created once per context as designed.
- Services inject the intended bean via `@Qualifier` when multiple clients/pools exist.
- Hikari pool size matches the profile, with no unintended duplicate `DataSource`.
- Executor queue/rejection policies match the workload.

**Per-call:**
- JDBC connections return to the pool even when queries throw exceptions.
- HTTP responses/streams are closed according to API.
- A request never closes a shared client/executor.
- Tasks receive errors/rejections per contract; never report false acceptance.

**Shutdown:**
- `context.close()` invokes resource destroy callbacks properly.
- `HikariDataSource.isClosed()` is true after context close.
- The executor terminates once no long-running tasks remain.
- The HTTP client wrapper closes exactly once.
- Producers stop submitting after pool shutdown.
- When tasks hang, deadlines and failure paths are handled.
- When startup fails mid-way, resources created before the failure are cleaned up.

**Operations:**
- Repeatedly creating/closing contexts does not increase thread counts.
- Multi-pod rollouts do not exceed max DB connections.
- `SIGTERM` provides enough time for draining/awaiting/cleanup.
- Critical tasks are not lost on pod restarts.
- Secrets are never written in logs/startup exceptions.

### 16.1. Testing with ApplicationContextRunner

`ApplicationContextRunner` from `spring-boot-test` can be useful for creating small configuration contexts and closing them within test scope. However, for demos with full JDBC auto-configuration and starters, `@SpringBootTest`/integration tests may be a better fit.

Do not use a unit test mocking `CloseableHttpClient` to conclude that the real Hikari pool closes; each assertion only proves the layer being tested. Some resources require integration tests inside a real context.

## 17. Monitoring and Resource Observability

| Resource | Metric/Symptom | Action Needed |
| --- | --- | --- |
| Hikari | Active/idle/pending connections, timeouts | Connection held too long, pool too small, or DB overloaded |
| HTTP client | Leased/pending/available connections, response timeouts | Unclosed responses, pool exhaustion, slow external API |
| Executor | Active threads, queue size, rejected tasks | Overload, large backlog, callers blocked |
| Scheduler | Job duration, overlaps, failures | Non-idempotent jobs, not stopping cleanly on shutdown |
| JVM | Live thread count, open file descriptors | Thread/socket leaks or resources held beyond scope |
| Spring | Startup/shutdown duration | Slow destroy callbacks, stuck tasks |
| Deployment | Restart count, rollout readiness delay | Grace period too short, dependencies not ready |

`ThreadPoolTaskExecutor` provides `getActiveCount()`, `getPoolSize()`, and `getQueueSize()`. Hikari has appropriate metrics/JMX/Micrometer integration; Apache's connection manager exposes pool statistics. Do not assume all metrics appear automatically just because a bean exists; verify actual Actuator/Micrometer configuration.

## 18. Common Errors and Fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| JVM does not exit after `context.close` | Custom executor not shut down, non-daemon threads | Spring-managed executor or owner `@PreDestroy` |
| DB connections remain after closing context | Hikari pool outside container not closed | Create managed `DataSource` bean/auto-config |
| "Client already closed" on next request | Singleton HTTP client closed per-request | Close only responses, not the shared client |
| Hikari reports pool exhausted | Unreturned connections, slow queries, too many requests | `try-with-resources`, transaction tuning, pool metrics |
| Two HTTP client cleanup paths | Raw client and wrapper both act as owners | Single owner; specify shared manager if needed |
| A client created on every request | Not reusing a bean | Singleton client bean and inject it |
| Tasks run after DB closes | Producers not stopped/awaited before resource teardown | `SmartLifecycle`, bounded wait, and ordering |
| `@PreDestroy` present yet app still hangs | Tasks ignore interrupts, executor not terminated | Timeouts/cancellation, thread dumps |
| Startup fails after `new client` | Factory has not returned bean yet; container not owner | Validate upfront, `catch/finally` cleanup |
| Unexpected multiple DB pools | Custom `DataSource` and auto-config on overlapping/separate paths | Audit `BeanFactory` and qualifiers |
| Executor rejects yet HTTP returns Accepted | `TaskRejectedException` ignored | Return proper error, durable queue when needed |
| High pool max yet threads never scale | Unbounded queue holds entire backlog | Bounded queue, observe rejections |
| Second test fails because pool is closed | Test closed a bean in a cached context | Scope test independently, let context owner close |
| Tasks lost on pod restart | In-memory executor is not durable | Durable queue/job store/checkpoint |
| Only tweaking `connection-timeout` to stop errors | Root cause is connection leak/slow queries | Profile queries and transaction lifecycle |
| Java 17 code calls `HttpClient.close` | Wrong JDK version API | Use the specific JDK/client API properly |

## 19. Checklist for Adding a New Resource to Spring Boot

1. Identify the class that actually owns the socket/thread/pool/file.
2. Choose the scope: application singleton, per-tenant, per-request, or process.
3. Prefer Boot auto-config when available and appropriate.
4. If creating a custom bean, declare the right `destroyMethod`/`@PreDestroy`/`DisposableBean`.
5. Ensure only one owner closes each resource.
6. Avoid creating pools/clients in controllers or per request.
7. For HTTP, close responses/streams per API after each call.
8. For JDBC, return `Connection` to the pool; never close `DataSource` per call.
9. Configure sensible pool/queue/concurrency/timeout values.
10. Have a rejection/backpressure policy for executors.
11. Know how to stop producers and await in-flight tasks.
12. Set a bounded shutdown deadline matching infrastructure limits.
13. When tasks do not finish, have a cancel/requeue/checkpoint strategy.
14. Prevent resources from closing before consumers have stopped using them.
15. In startup factories, clean up resources if an error occurs before returning the bean.
16. Check whether nested resources have an owner.
17. Do not use static/global pools when context scope is intended.
18. Test across multiple contexts/restarts to catch leaks.
19. Distinguish readiness/liveness from client and DB availability.
20. Never put credentials, tokens, or sensitive endpoints into logs.
21. Track metrics for threads/queues/connections and shutdown duration.
22. Test shutdown under load, not only when the app is idle.
23. Do not use APIs from newer JDKs if the project runs on Java 17.
24. Document clearly which beans are injected and who is responsible for closing them.

## 20. Summary

```text
               SPRING APPLICATION CONTEXT
                           |
       +-------------------+--------------------+
       |                   |                    |
   HTTP CLIENT         JDBC DataSource      TASK EXECUTOR
   PartnerGateway      HikariCP             ThreadPoolTaskExecutor
       |                   |                    |
   shared client       getConnection()      shared worker pool
       |                   |
   close RESPONSE      close CONNECTION
   after each call     => return to pool
       |                   |                    |
       +-------------------+--------------------+
                           |
              APPLICATION SHUTDOWN
                           |
         Stop producers / drain in-flight tasks
                           |
             Spring destroy managed beans
                           |
       Close HTTP client, DataSource pool, Executor
```

**Core rule:** **register clients, connection pools, and executors as resources with a single clear owner**; use dependency injection to share them, close *handles* after each operation, and let the container close *shared resources* when the context stops. Spring Boot assists with lifecycle management, yet does not automatically solve cancellation, backpressure, transactions, timeouts, or durable jobs. Those still have to be designed, configured, and tested.

## Official Documentation

- [Spring Boot 3.3 — SQL Databases / DataSource / HikariCP](https://docs.spring.io/spring-boot/3.3/reference/data/sql.html)
- [Spring Boot 3.3 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html)
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Spring Framework — Bean lifecycle and destroy methods](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework 6.1 — ThreadPoolTaskExecutor API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework 6.1 — ExecutorConfigurationSupport API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/concurrent/ExecutorConfigurationSupport.html)
- [Apache HttpClient 5 — Connection Management](https://hc.apache.org/httpcomponents-client-5.6.x/connection-management.html)
- [Java 17 — ExecutorService API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
