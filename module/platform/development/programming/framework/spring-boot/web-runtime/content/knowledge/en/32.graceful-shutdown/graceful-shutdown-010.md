# Releasing Executors, Connection Pools, Reactor Resources, and Temporary Files in Spring Boot

When a Spring Boot web application stops, Tomcat/Jetty/Reactor Netty stopping acceptance of new HTTP requests does not mean the whole process has been released. The app may still hold **ExecutorService, ThreadPoolTaskExecutor, ScheduledExecutorService, Hikari connection pools, HTTP client sockets, Reactor schedulers, Netty event-loop threads, subscriptions, file streams, and temporary files**. Closing them too early causes running requests to fail. Failing to close them leaves the JVM hanging on live threads, leaks connections/file descriptors, or leaves data on disk.

This lesson belongs to **Spring Boot - web-runtime → Graceful Shutdown**, presenting three pillars—**resource ownership, shutdown order, and cleanup verification**—then applying them to four practical groups: **executors, connection pools, Reactor, and temporary files**. Examples use **Java 17, Spring Boot 3.3.13, Spring MVC/Tomcat, HikariCP + H2, Reactor Core, and Maven**. The WebClient/Reactor Netty section provides separate code for apps with `spring-webflux`; the main demo project does not pretend to run Netty. SIGTERM/Kubernetes policies, orphan files after SIGKILL, and lifecycle testing are also covered.

## 1. Learning objectives

After this lesson, you can:

1. Distinguish **graceful web shutdown** from stopping background tasks and destroying Spring beans.
2. Explain **ApplicationContext, @PreDestroy, @Bean(destroyMethod), AutoCloseable, DisposableBean, SmartLifecycle, ContextClosedEvent**.
3. Shut down an ExecutorService in the sequence **stop intake → shutdown() → awaitTermination() → conditional shutdownNow()**.
4. Distinguish a **Spring-managed ThreadPoolTaskExecutor** from an executor created manually by the application.
5. Distinguish `Connection.close()` returning a JDBC connection to the pool from `HikariDataSource.close()` closing the entire pool.
6. Understand how **Schedulers.newBoundedElastic(...).dispose()** differs from shared `Schedulers.boundedElastic()`.
7. Understand **WebClient, ReactorResourceFactory, ConnectionProvider, LoopResources, global Reactor Netty resources**.
8. Use try-with-resources and `finally` to delete files right after a request/job rather than only waiting for shutdown.
9. Build workflows handling **SIGTERM, graceful drain, Kubernetes terminationGracePeriodSeconds, and SIGKILL recovery**.
10. Write a runnable application and tests proving executors, custom Schedulers, and owned workspaces are cleaned up after `context.close`.

## 2. Whoever owns the resource is responsible for closing it

| Resource | Typical owner | Proper closing method |
| --- | --- | --- |
| Embedded web server | Spring Boot ApplicationContext | `server.shutdown=graceful` and lifecycle stop. |
| Manually created ExecutorService | `@Service` or class instantiating executor | `shutdown`, bounded `awaitTermination`, `shutdownNow` when needed. |
| ThreadPoolTaskExecutor bean | Spring container | Bean lifecycle/destruction and shutdown configuration. |
| JDBC Connection borrowed from pool | Transaction/request scope | `Connection.close` or managed by JdbcTemplate/`@Transactional`. |
| HikariDataSource | Boot auto-configured DataSource bean | Spring bean destruction, `HikariDataSource.close` once. |
| Custom CloseableHttpClient | Client bean owner | `close` per library API. |
| Custom Reactor Scheduler | Bean created via `Schedulers.new*` | `Scheduler.dispose`. |
| Global Reactor Scheduler | Reactor process-level shared factory | Never close from individual components. |
| Reactor Netty event loops/connection pools | ReactorResourceFactory or custom resource owner | Factory lifecycle/`dispose`. |
| File stream/channel | Stream-opening scope | try-with-resources. |
| Per-request/job temp file | Request/job | `Files.deleteIfExists` in `finally`. |
| Owned temp directory | Application component | Cleanup once workers have stopped; janitor for crashes. |

**Never close a shared resource from a controller merely because one request errored.** Conversely, when instantiating an `ExecutorService` with `new` inside a Spring singleton without lifecycle hooks, Spring does not automatically know to shut it down unless the bean/owner implements cleanup.

### 2.1. Avoid double closing

If a Spring `@Bean` already has `destroyMethod=close` configured or Spring infers public `close`/`shutdown`, no other module should explicitly close that same resource before bean destruction. Some `close()` methods are idempotent, yet you must not assume every external client is. Pick one owner, determine when consumers stop, and close only when the resource is no longer used.

## 3. Safe shutdown order

~~~text
SIGTERM / context.close()
      |
      v
Kubernetes/Load Balancer stops routing new traffic
      |
      v
Boot graceful web shutdown:
stop accepting new requests, wait for in-flight HTTP
      |
      v
Stop producers: HTTP admission, queue consumers, schedulers
      |
      v
Drain background tasks, cancel/finish subscriptions
      |
      v
Close Hikari/HTTP pools, custom schedulers,
Reactor Netty resources, and file handles
      |
      v
Clean up owned temporary workspace
      |
      v
Process exits
~~~

This is an **architectural target**. In Spring, web server graceful shutdown runs while the context is closing and during `SmartLifecycle` stop phases. Many other resources are destroyed by Spring according to dependencies/lifecycles. You cannot assume a deterministic order between two unrelated `@PreDestroy` methods, so explicitly design the stages for stopping producers, workers, and resources.

### 3.1. Enabling graceful web shutdown

**application.yml:**

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Spring Boot 3.3 supports graceful shutdown with Tomcat, Jetty, Reactor Netty, and Undertow. On context close, the web server has a grace period for running requests. Tomcat/Jetty/Netty usually stop accepting new requests at the network layer; Undertow may return 503 for new requests. How new requests are rejected also depends on persistent connections and server implementations.

**Timeout-per-shutdown-phase is not a global deadline for every `@PreDestroy`.** A `@PreDestroy` that blocks forever can still stall process shutdown. Enforce explicit timeouts for `executor.awaitTermination`, network disposal, database pool draining, and file cleanup.

### 3.2. Do not close Hikari while requests are still in-flight

Example:

~~~text
Tomcat worker -> @Transactional service
-> borrowed Connection -> execute SQL -> commit
-> return Connection -> HTTP response
~~~

If a `ContextClosedEvent` listener calls `HikariDataSource.close` manually before web requests finish, transactions or queries can fail. For Spring Boot–managed pools, **let Spring destroy them at the right time**. HTTP graceful shutdown reduces the risk, though a detached job returning HTTP 202 before finishing will not automatically be awaited by Tomcat.

### 3.3. Different stop scenarios

| Scenario | Is `@PreDestroy` guaranteed? | Policy |
| --- | --- | --- |
| Normal `ApplicationContext.close` | Spring destroys already-created beans. | Deadlines and cleanup callbacks. |
| SIGTERM handled by JVM | Usually yes if enough time remains. | Readiness, web drain, resource teardown. |
| IDE stops process | Depends on signal sent by IDE. | Test via real SIGTERM. |
| SIGKILL, OOMKilled, crash, power loss | No | Durable queues, idempotency, orphan cleanup. |
| Startup fails mid-resource creation | Not all beans may be registered | Clean up partial allocations on init failure. |

## 4. Spring lifecycle: @PreDestroy, destroyMethod, SmartLifecycle

### 4.1. @PreDestroy

In Spring Boot 3, use **jakarta.annotation.PreDestroy**:

~~~java
@Component
public class OwnedComponent {

    @PreDestroy
    public void cleanup() {
        // Release only resources owned by this component.
    }
}
~~~

A class created via **new OwnedComponent()** outside the Spring container does not receive callbacks automatically. Cleanup methods must be synchronous, bounded, and log errors clearly. Never wait indefinitely or try to finish a long business workflow inside a shutdown callback.

### 4.2. @Bean(destroyMethod) and AutoCloseable

~~~java
@Bean(destroyMethod = "dispose")
Scheduler ownedScheduler() {
    return Schedulers.newBoundedElastic(
            2, 32, "owned-scheduler");
}
~~~

Spring invokes `dispose()` when the bean is destroyed. For a `@Bean` with public `close()`/`shutdown()` or `AutoCloseable`, Spring can infer the destroy method; declaring it explicitly improves clarity. **`DisposableBean.destroy()`** is another callback, though it couples domain code to a Spring API. Avoid attaching multiple callbacks that double-close the same resource.

### 4.3. SmartLifecycle and phases

**SmartLifecycle** has `start()`, `stop(Runnable callback)`, `isRunning()`, and `getPhase()`. On start, lower phases start first; on stop, **higher phases stop before lower phases**. Spring's `LifecycleProcessor` waits for a phase's callbacks within `timeout-per-shutdown-phase`.

Fits **queue consumer → executor workers → database**. Stop consumers first so no new jobs arrive, wait for workers, and only then let dependencies close. Never guess that `getPhase()=100` definitely stops before Spring Boot's internal web server; rely only on phases you control and test on your exact version.

### 4.4. ContextClosedEvent does not mean all requests are finished

A `ContextClosedEvent` listener is notified when the context begins closing. It can signal stopping admission, yet it is not the right place for arbitrary listeners to close all pools. Use lifecycle stop and `@PreDestroy` with clear dependency ordering.

## 5. ExecutorService: two-phase shutdown

### 5.1. Meaning of the APIs

- **shutdown()**: stops accepting new tasks; already-submitted tasks usually keep running.
- **awaitTermination(timeout, unit)**: waits up to a bounded period; returns true if the executor terminated.
- **shutdownNow()**: attempts to interrupt running tasks and returns unstarted tasks; **does not guarantee killing every thread**.
- **isTerminated()**: indicates the executor has completely terminated.
- **Future.cancel(true)**: requests interruption if the task is running; does not automatically roll back external side effects.

### 5.2. Standard Java 17 shutdown pattern

~~~java
executor.shutdown();
boolean terminated = false;

try {
    terminated = executor.awaitTermination(
            10, TimeUnit.SECONDS);

    if (!terminated) {
        executor.shutdownNow();
        terminated = executor.awaitTermination(
                2, TimeUnit.SECONDS);
    }
}
catch (InterruptedException ex) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}

if (!terminated) {
    log.warn("Executor still active after deadline");
}
~~~

This is a snippet needing imports, `ExecutorService executor`, and `Logger`. **Never use Thread.stop().** If a task holds a long monitor, waits on uninterruptible native I/O, or ignores the interrupt flag, `shutdownNow` cannot force it to stop.

### 5.3. Stop producers before shutdown

If schedulers/Kafka listeners/HTTP controllers keep submitting after `executor.shutdown()`, **`RejectedExecutionException`** occurs. Flip `accepting=false`, stop polling, and handle the race between checking the flag and submitting. Over HTTP, you can return 503 while draining; with message brokers, stop consuming or leave unacked records for another worker.

### 5.4. Detached tasks are outside HTTP graceful drain

A controller returning **202 Accepted** right after submitting a job has already ended the HTTP request while the job is still running. Tomcat does not wait for that job because it no longer belongs to an in-flight servlet request. If the task can run long or must finish, use a **durable job table/queue**, leases, checkpoints, idempotent retries, and ownership. Never place sole trust in the JVM shutdown grace period.

### 5.5. Spring-managed executors

When using **ThreadPoolTaskExecutor** or `ThreadPoolTaskScheduler`, Spring manages the lifecycle. Settings like **setWaitForTasksToCompleteOnShutdown(true)** and **setAwaitTerminationSeconds(15)** work per Spring Framework 6.1. With `@Async`, verify which executor is actually injected and ensure a custom bean didn't unintentionally override auto-config. Java 21 virtual threads are lighter, yet shutdown, cancellation, and durability still need the same care.

## 6. Connection pools: borrowed connection vs pool owner

### 6.1. HikariCP

~~~text
HikariDataSource (Spring bean)
    |
    +-- getConnection() -> pooled Connection C1
    |       |
    |       +-- query / commit / rollback
    |       +-- Connection.close() -> return to pool
    |
    +-- HikariDataSource.close() -> close pool
~~~

**`Connection.close()` on a pooled connection typically returns the handle to the pool.** It does not equate to `HikariDataSource.close()` tearing down the entire pool. The connection-using layer must return connections in scope, while the pool-owning layer closes the pool upon context destruction.

### 6.2. JDBC resource scope

~~~java
try (Connection conn = dataSource.getConnection();
     PreparedStatement ps = conn.prepareStatement(
             "select name from users where id = ?")) {

    ps.setLong(1, 42);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            return rs.getString(1);
        }
    }
}
~~~

Snippet inside a method with `DataSource` and a matching return type. With `JdbcTemplate`/`@Transactional`, Spring already manages connection/transaction scope; never hold a `Connection` in a singleton field or close `HikariDataSource` directly after a `SQLException`.

### 6.3. Spring Boot JDBC/Hikari

**spring-boot-starter-jdbc** with H2 or a matching DB driver makes Boot auto-configure a `DataSource`, usually Hikari. The DataSource bean closes per Spring lifecycle. Monitor **hikaricp.connections.active**, **idle**, **pending**, transaction durations, and closure logs to verify.

Beyond JDBC, there are **CloseableHttpClient**, Redis/Lettuce, MongoDB, and R2DBC ConnectionPool; each library has its own close/dispose API. If a client is instantiated outside Spring, register a Spring bean lifecycle or manage it manually. Never issue a global shutdown when only one consumer stops.

## 7. Reactor Core: closing Schedulers and Subscriptions properly

### 7.1. Reactor Publishers are not a pool

**Mono/Flux** describe pipelines. A publisher like `Mono.just` needs no close; a long-running subscription may need cancellation, and custom **Schedulers** can own threads.

| Object | Lifecycle |
| --- | --- |
| `Mono.just`/`Flux.range` | Not a thread pool, usually needs no close. |
| `Disposable` from `subscribe()` | Can `dispose`/cancel the stream. |
| `Schedulers.newBoundedElastic`/`newSingle`/`newParallel` | Custom scheduler; owner calls `dispose()`. |
| `Schedulers.boundedElastic()`/`parallel()`/`single()` | Shared Scheduler; never close arbitrarily. |
| Reactor Netty `ConnectionProvider` | Pool owning sockets; dispose by owner. |
| Reactor Netty `LoopResources` | Owns event loop threads; dispose by owner. |

### 7.2. Owned vs shared

~~~java
Scheduler shared = Schedulers.boundedElastic();

Scheduler owned = Schedulers.newBoundedElastic(
        4, 100, "background-adapter");
~~~

Snippet with Reactor imports. **owned** is created by the component and should be disposed when the context closes. **shared** belongs to Reactor's process-level factory; never call **Schedulers.shutdownNow()** from one service to clean up its own job, as it can cause rejections in other components.

### 7.3. Stream stopping order

If a Flux receives data using a custom Scheduler and network client:

~~~text
Stop source/producer
    -> cancel or drain active subscriptions
    -> dispose owned Scheduler
    -> close underlying HTTP/network pools
~~~

Do not dispose the scheduler early while streams still need to schedule operators. Cancellation does not guarantee a remote POST had no side effects; idempotency/reconciliation are required. For files/readers opened upon subscription, consider **Flux.using/usingWhen** to clean up on complete/error/cancel.

~~~java
Flux<String> lines = Flux.using(
        this::openReader,
        reader -> Flux.fromStream(reader.lines()),
        reader -> closeReader(reader));
~~~

Snippet requiring methods and imports; blocking readers must be offloaded from event loops if running WebFlux.

## 8. WebClient/Reactor Netty: lifecycle of connection/event-loop resources

### 8.1. WebClient is not itself a pool

**WebClient** is a client API. When the underlying connector is Reactor Netty, the real resources are **connection pools and event loops**. In Spring Boot 3.3, inject Boot-managed **WebClient.Builder** to share connectors/codecs/resources cleanly.

~~~java
@Service
public class PartnerClient {
    private final WebClient client;

    public PartnerClient(WebClient.Builder builder) {
        client = builder
                .baseUrl("https://partner.example.test")
                .build();
    }
}
~~~

Snippet usable only when `spring-webflux` is on the classpath. A `WebClient` object has no single `close()` tearing down all Netty resources. **Never call `WebClient.create()` per request** assuming resources will be managed like a bean.

### 8.2. ReactorResourceFactory

Spring provides **ReactorResourceFactory** to tie Reactor Netty resources to the `ApplicationContext`.

- **Use global resources**: uses global Reactor Netty `HttpResources`, typically shared across the process.
- **Use own resources**: `setUseGlobalResources(false)` makes the factory create/close dedicated resources; clients/servers must be wired properly.
- Spring Boot's reactive Netty server can auto-configure `ReactorResourceFactory`; managed `WebClient.Builder` typically shares resources with the server when using the same technology.

When one JVM creates/destroys multiple contexts (IDE dev tools, integration tests, WAR/external containers), global Netty threads can outlive context close unless managed properly. **Never dispose global resources from a single client.**

### 8.3. Custom factory configuration for a separate WebFlux project

File **NettyClientResourcesConfiguration.java**, added only when **spring-boot-starter-webflux / Reactor Netty** is present, not part of the MVC demo project below:

~~~java
package com.example.shutdown.reactive;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.http.client.reactive.ReactorResourceFactory;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class NettyClientResourcesConfiguration {

    @Bean
    ReactorResourceFactory reactorResourceFactory() {
        ReactorResourceFactory factory =
                new ReactorResourceFactory();
        factory.setUseGlobalResources(false);
        return factory;
    }

    @Bean
    WebClient partnerWebClient(
            WebClient.Builder builder,
            ReactorResourceFactory resources) {

        ReactorClientHttpConnector connector =
                new ReactorClientHttpConnector(
                    resources,
                    client -> client.responseTimeout(
                            Duration.ofSeconds(3)));

        return builder
                .clientConnector(connector)
                .baseUrl("https://partner.example.test")
                .build();
    }
}
~~~

**The Spring Framework 6.x API is `setUseGlobalResources(false)`.** If using both Netty web server and client in one app, consider sharing one resource factory and checking Boot auto-configuration; declaring a custom factory can alter default behavior. The placeholder hostname must not be used for real calls.

### 8.4. Manually created ConnectionProvider/LoopResources

~~~java
ConnectionProvider provider =
        ConnectionProvider.builder("partner")
                .maxConnections(40)
                .build();

LoopResources loops =
        LoopResources.create("partner-io");
~~~

Snippet needing Reactor Netty imports; both objects are custom resources with clear owners. Disposal can use `dispose()` or `disposeLater()` depending on API; if `disposeLater()` returns a Publisher, you must **subscribe/await with a deadline** off the event loop rather than creating a Mono and abandoning it.

### 8.5. MVC using WebClient still spawns Netty threads

A Servlet MVC application using WebClient for outbound HTTP can still pull in the Reactor Netty runtime even without a WebFlux server. Thus you still must mind the lifecycle of client connectors/resources, especially if contexts open/close repeatedly in one JVM. Lacking a Netty server does not eliminate the need to manage the Netty HTTP client pool.

## 9. Temporary files: delete on completion, don't wait for shutdown

### 9.1. Per-job finally

~~~java
Path file = Files.createTempFile(
        "task-", ".tmp");
try {
    Files.writeString(
        file, "temporary", StandardCharsets.UTF_8);
    // Process file.
}
finally {
    Files.deleteIfExists(file);
}
~~~

Java 17 snippet with required imports. Close `InputStream`/`OutputStream`/`FileChannel` before deleting via try-with-resources. On Windows, open file handles can throw `AccessDeniedException`.

### 9.2. Dedicated app-owned workspace

Create a workspace with **Files.createTempDirectory("shutdown-demo-")**. Clean up per-task files in `finally`; during shutdown you can delete leftovers in the owned workspace, but **only after no worker is still writing files**. Never recursively delete all of `/tmp`, `java.io.tmpdir`, shared volumes, or paths taken from requests.

### 9.3. walkFileTree

~~~java
Files.walkFileTree(root,
    new SimpleFileVisitor<Path>() {
        @Override
        public FileVisitResult visitFile(
                Path file, BasicFileAttributes attrs)
                throws IOException {
            Files.deleteIfExists(file);
            return FileVisitResult.CONTINUE;
        }

        @Override
        public FileVisitResult postVisitDirectory(
                Path dir, IOException error)
                throws IOException {
            if (error != null) throw error;
            Files.deleteIfExists(dir);
            return FileVisitResult.CONTINUE;
        }
    });
~~~

Snippet with an app-owned `root`. `Files.walkFileTree` does not follow symbolic links by default unless `FOLLOW_LINKS` is passed; still, in directories writable by untrusted parties, guard against races/path traversal and enforce filesystem permissions.

### 9.4. Multipart uploads

`MultipartFile` and container-managed temporary files have request/container-scoped lifecycles. If you need to process an upload after returning HTTP 202, copy it into an owned staging area, persist durable job state, and enforce TTLs/quotas and cleanup. Never retain a request-scoped `MultipartFile` or temp path that the container may delete once the request ends.

### 9.5. SIGKILL and orphan files

SIGKILL, OOMKilled, or node crashes can prevent `@PreDestroy` from running. You need a janitor based on **ownership/active leases/TTL** and byte quotas, preserving data needed for recovery and avoiding deleting another replica's files. Never blindly wipe every file older than 1 hour in a shared directory. A real recovery mechanism must be safe when two workers run concurrently.

## 10. Runnable Maven project: executor, Hikari, Reactor, and temp files

Demo includes:
- **GET /demo/work?value=hello**: submits work to a 4-thread pool, creates/deletes a temp file, returns JSON.
- **GET /demo/db**: JdbcTemplate queries H2 via Spring-managed HikariCP.
- **GET /demo/reactor**: runs a task on an owned Scheduler bean.
- **Spring `@PreDestroy`** stops the executor, awaits completion with a deadline, and deletes the workspace if safe.
- **`@Bean(destroyMethod="dispose")`** cleans up the Reactor Scheduler.
- Tests via HTTP and closing a small `ApplicationContext` to prove resources were released.

### 10.1. Directory tree

~~~text
shutdown-runtime-demo/
  pom.xml
  src/main/java/com/example/shutdown/
    ShutdownApplication.java
    OwnedWorkResources.java
    SchedulerConfiguration.java
    ReactorService.java
    DemoController.java
  src/main/resources/application.yml
  src/test/java/com/example/shutdown/
    ShutdownHttpTest.java
    ShutdownLifecycleTest.java
~~~

### 10.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>shutdown-runtime-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot's BOM manages Hikari, Reactor, H2, and Spring Framework versions. The project uses Java 17 and needs neither Java 21 nor WebFlux starter. **Spring Boot 3.3.13 is the lesson baseline**; new deployments should use supported versions with current security updates.

### 10.3. ShutdownApplication.java

~~~java
package com.example.shutdown;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShutdownApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShutdownApplication.class, args);
    }
}
~~~

### 10.4. OwnedWorkResources.java

~~~java
package com.example.shutdown;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.Locale;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class OwnedWorkResources {

    private static final Logger log =
            LoggerFactory.getLogger(OwnedWorkResources.class);

    private final ExecutorService executor =
            Executors.newFixedThreadPool(4);

    private final AtomicBoolean accepting =
            new AtomicBoolean(true);

    private final Path workspace;

    public OwnedWorkResources() throws IOException {
        workspace = Files.createTempDirectory("shutdown-demo-");
    }

    public String transform(String input)
            throws InterruptedException,
                   ExecutionException,
                   TimeoutException {

        if (!accepting.get()) {
            throw new RejectedExecutionException(
                    "Shutdown in progress");
        }

        Future<String> future = executor.submit(() -> {
            Path file = Files.createTempFile(
                    workspace, "job-", ".txt");
            try {
                Files.writeString(
                    file, input, StandardCharsets.UTF_8);
                return Files.readString(
                    file, StandardCharsets.UTF_8)
                    .toUpperCase(Locale.ROOT);
            }
            finally {
                Files.deleteIfExists(file);
            }
        });

        try {
            return future.get(3, TimeUnit.SECONDS);
        }
        catch (TimeoutException ex) {
            future.cancel(true);
            throw ex;
        }
        catch (InterruptedException ex) {
            future.cancel(true);
            Thread.currentThread().interrupt();
            throw ex;
        }
    }

    public Path workspaceForTest() {
        return workspace;
    }

    public boolean terminatedForTest() {
        return executor.isTerminated();
    }

    @PreDestroy
    public void shutdown() {
        accepting.set(false);
        executor.shutdown();

        boolean terminated = false;
        try {
            terminated = executor.awaitTermination(
                    5, TimeUnit.SECONDS);
            if (!terminated) {
                log.warn("Worker drain timed out");
                executor.shutdownNow();
                terminated = executor.awaitTermination(
                        2, TimeUnit.SECONDS);
            }
        }
        catch (InterruptedException ex) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }

        if (!terminated) {
            // A task might still be writing; do not delete the directory.
            log.error("Worker still active; leave workspace {}",
                    workspace);
            return;
        }

        try {
            deleteWorkspace(workspace);
            log.info("Owned resources released");
        }
        catch (IOException ex) {
            log.warn("Workspace cleanup failed: {}",
                    workspace, ex);
        }
    }

    private static void deleteWorkspace(Path root)
            throws IOException {
        if (!Files.exists(root)) {
            return;
        }

        Files.walkFileTree(root,
            new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFile(
                        Path file, BasicFileAttributes attrs)
                        throws IOException {
                    Files.deleteIfExists(file);
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult postVisitDirectory(
                        Path dir, IOException failure)
                        throws IOException {
                    if (failure != null) throw failure;
                    Files.deleteIfExists(dir);
                    return FileVisitResult.CONTINUE;
                }
            });
    }
}
~~~

**Mechanism:**
1. Spring singleton creates the executor and owned workspace exactly once.
2. Each task creates its own file and deletes it in `finally` right after processing.
3. Setting `accepting=false` before `executor.shutdown` curbs new tasks; still catch `RejectedExecutionException` due to submit races.
4. `Future.get` has a 3s timeout; `cancel(true)` only requests interruption.
5. `@PreDestroy` waits 5s for the pool to stop, falling back to `shutdownNow` and 2s more.
6. If the pool stays active, retain the workspace rather than deleting it while a task may still write.
7. Only deletes the directory created by this component, never the shared `java.io.tmpdir`.
8. Deadlines are for the lab only; production must balance against Kubernetes termination budgets.
9. This class owns neither Hikari nor the Reactor Scheduler, so it does not close those two resources.
10. A file deletion failure can cause `Future` to throw `ExecutionException`; production apps should log/alert on cleanup failures.

### 10.5. SchedulerConfiguration.java

~~~java
package com.example.shutdown;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@Configuration
public class SchedulerConfiguration {
    @Bean(destroyMethod = "dispose")
    public Scheduler applicationScheduler() {
        return Schedulers.newBoundedElastic(
                2, 32, "shutdown-adapter");
    }
}
~~~

This is a custom Scheduler owned by a Spring bean; `destroyMethod=dispose` ensures cleanup on context close without stopping global `Schedulers`.

### 10.6. ReactorService.java

~~~java
package com.example.shutdown;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;

@Service
public class ReactorService {

    private final Scheduler scheduler;

    public ReactorService(
            @Qualifier("applicationScheduler")
            Scheduler scheduler) {
        this.scheduler = scheduler;
    }

    public String execute() {
        return Mono.fromCallable(() -> "reactor-ok")
                .subscribeOn(scheduler)
                .block(Duration.ofSeconds(2));
    }
}
~~~

`block()` here is invoked **from an MVC worker thread**, not from a WebFlux Netty event loop. On a reactive event loop, calling `block()` is an anti-pattern; compose `Mono`/`Flux` or offload blocking adapters properly.

### 10.7. DemoController.java

~~~java
package com.example.shutdown;

import java.util.Map;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeoutException;

import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class DemoController {

    private final OwnedWorkResources workers;
    private final JdbcTemplate jdbc;
    private final ReactorService reactor;

    public DemoController(
            OwnedWorkResources workers,
            JdbcTemplate jdbc,
            ReactorService reactor) {
        this.workers = workers;
        this.jdbc = jdbc;
        this.reactor = reactor;
    }

    @GetMapping("/demo/work")
    public Map<String, String> work(
            @RequestParam(defaultValue = "hello")
            String value) {

        if (!value.matches("[A-Za-z0-9-]{1,50}")) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid input");
        }

        try {
            return Map.of("result", workers.transform(value));
        }
        catch (RejectedExecutionException ex) {
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "Worker is draining", ex);
        }
        catch (TimeoutException ex) {
            throw new ResponseStatusException(
                    HttpStatus.GATEWAY_TIMEOUT,
                    "Work timed out", ex);
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "Work interrupted", ex);
        }
        catch (ExecutionException ex) {
            throw new ResponseStatusException(
                    HttpStatus.INTERNAL_SERVER_ERROR,
                    "Worker failed", ex);
        }
    }

    @GetMapping("/demo/db")
    public Map<String, Integer> database() {
        Integer answer =
                jdbc.queryForObject("select 1", Integer.class);
        return Map.of("answer", answer);
    }

    @GetMapping("/demo/reactor")
    public Map<String, String> reactor() {
        return Map.of("result", reactor.execute());
    }
}
~~~

The demo REST controller validates input, never takes arbitrary paths from users, and never exposes the workspace location. HTTP 503 illustrates when the worker has stopped accepting tasks. The Hikari pool is used indirectly by `JdbcTemplate` and is never closed by the controller.

### 10.8. application.yml

~~~yaml
spring:
  application:
    name: shutdown-runtime-demo
  lifecycle:
    timeout-per-shutdown-phase: 20s
  datasource:
    generate-unique-name: true
    hikari:
      maximum-pool-size: 4
      connection-timeout: 2000

server:
  port: 8080
  shutdown: graceful

management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics"
  endpoint:
    health:
      show-details: never
~~~

H2 is auto-configured with `starter-jdbc` and the H2 runtime dependency. The HikariCP bean lifecycle is managed by Spring Boot; no manual code closes Hikari. Actuator metrics are exposed only in the lab; production must restrict network/auth access.

### 10.9. Run and output

Linux/macOS:

~~~bash
mvn clean package
java -jar target/shutdown-runtime-demo-0.0.1-SNAPSHOT.jar
~~~

Windows:

~~~text
mvn.cmd clean package
java -jar target/shutdown-runtime-demo-0.0.1-SNAPSHOT.jar
~~~

Test:

~~~bash
curl -i "http://localhost:8080/demo/work?value=hello"
curl -i http://localhost:8080/demo/db
curl -i http://localhost:8080/demo/reactor
curl -i http://localhost:8080/actuator/health
~~~

**Expected** 200 and body:

~~~text
/demo/work?value=hello  -> {"result":"HELLO"}
/demo/db                -> {"answer":1}
/demo/reactor           -> {"result":"reactor-ok"}
/actuator/health        -> {"status":"UP"}
~~~

This shows the output structure, not fixed HTTP Date/Content-Length/header ordering. After `/demo/work`, the `job-*.txt` file is already deleted, while the workspace directory remains until shutdown.

On Linux, to send SIGTERM:

~~~bash
ps -ef | grep shutdown-runtime-demo
kill -TERM ACTUAL_PID
~~~

Replace `ACTUAL_PID` with the process ID. Do not use `kill -9` when testing graceful shutdown. Observe Tomcat graceful logs, `OwnedWorkResources` cleanup, HikariPool shutdown, and process exit.

## 11. HTTP tests and closing the context

### 11.1. ShutdownHttpTest.java

~~~java
package com.example.shutdown;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ShutdownHttpTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void canUseExecutorDatabaseAndReactor() {
        String work = http.getForObject(
                "/demo/work?value=hello", String.class);
        String db = http.getForObject(
                "/demo/db", String.class);
        String reactor = http.getForObject(
                "/demo/reactor", String.class);

        assertThat(work).contains("HELLO");
        assertThat(db).contains("\"answer\":1");
        assertThat(reactor).contains("reactor-ok");
    }

    @Test
    void rejectsInvalidInput() {
        var response = http.getForEntity(
                "/demo/work?value=%21", String.class);
        assertThat(response.getStatusCode().value())
                .isEqualTo(400);
    }
}
~~~

`RANDOM_PORT` sends requests through real embedded Tomcat, not just `MockMvc`. It proves the API works **before shutdown**, not yet that resources are released.

### 11.2. ShutdownLifecycleTest.java

~~~java
package com.example.shutdown;

import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import reactor.core.scheduler.Scheduler;

import static org.assertj.core.api.Assertions.assertThat;

class ShutdownLifecycleTest {

    @Test
    void executorAndWorkspaceAreReleased()
            throws Exception {

        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();
        context.registerBean(OwnedWorkResources.class);
        context.refresh();

        OwnedWorkResources worker =
                context.getBean(OwnedWorkResources.class);
        Path dir = worker.workspaceForTest();

        try {
            assertThat(Files.isDirectory(dir)).isTrue();
            assertThat(worker.transform("hello"))
                    .isEqualTo("HELLO");

            try (var files = Files.list(dir)) {
                assertThat(files.count()).isZero();
            }
        }
        finally {
            context.close();
        }

        assertThat(worker.terminatedForTest()).isTrue();
        assertThat(Files.exists(dir)).isFalse();
    }

    @Test
    void customSchedulerIsDisposed() {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    SchedulerConfiguration.class);
        Scheduler scheduler = context.getBean(
                "applicationScheduler", Scheduler.class);

        try {
            assertThat(scheduler.isDisposed()).isFalse();
        }
        finally {
            context.close();
        }

        assertThat(scheduler.isDisposed()).isTrue();
    }
}
~~~

`AnnotationConfigApplicationContext` creates a **separate** Spring context, registers callbacks, and destroys beans on close. Never close a shared `@SpringBootTest` context inside a test because it can break other tests. The first test proves executor and workspace cleanup; the second proves custom Scheduler disposal. To verify `HikariPool.close`, run a full Boot context closure or separate SIGTERM integration test; do not use this minimal test to claim Hikari was initialized in the small context.

Run:

~~~bash
mvn test
~~~

**No Maven runtime execution was run in this documentation**: this is a complete project and test suite for learners to copy and run. All public classes, packages, and paths match the project structure.

## 12. SmartLifecycle for queue consumers before worker pools

A non-HTTP system may use a pipeline:

~~~text
Kafka/Rabbit consumer polling
    -> executor task
    -> JDBC transaction / external HTTP POST
~~~

During shutdown, stop consumer polling first to reject new jobs; finish/checkpoint in-flight work; only then close JDBC/HTTP pools. A `SmartLifecycle` skeleton:

~~~java
@Component
public class IntakeGate implements SmartLifecycle {

    private volatile boolean running;

    @Override
    public void start() {
        running = true;
    }

    @Override
    public void stop() {
        running = false;
    }

    @Override
    public void stop(Runnable callback) {
        try {
            running = false;
        }
        finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public int getPhase() {
        return 100;
    }
}
~~~

Snippet needs Spring `SmartLifecycle`/`@Component` imports and is not a real consumer yet. **Phase 100 does not automatically guarantee stopping before Boot's internal web server phase.** With async stop logic, invoke the callback only after stopping finishes—do not call it immediately while producers keep enqueuing.

## 13. Kubernetes readiness and terminationGracePeriodSeconds

### 13.1. Pod termination

~~~text
Pod marked terminating / EndpointSlices update
    -> optional preStop
    -> JVM receives SIGTERM
    -> readiness REFUSING_TRAFFIC
    -> web server graceful drain
    -> custom task drain and resource close
    -> JVM exit
    -> if deadline exceeded: SIGKILL
~~~

Steps can overlap due to load balancer propagation lag. `Readiness=false` does not block direct Pod IP traffic like a firewall; retries/idempotency are still needed for open connections.

### 13.2. Deployment YAML

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: shutdown-runtime-demo
spec:
  replicas: 2
  selector:
    matchLabels:
      app: shutdown-runtime-demo
  template:
    metadata:
      labels:
        app: shutdown-runtime-demo
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: app
          image: example.invalid/shutdown-runtime-demo:1.0
          ports:
            - name: http
              containerPort: 8080
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
~~~

This is a sample; `example.invalid` does not exist and must be replaced, and a Service, resource limits, and security policies must be added on deployment. Spring Boot 3.3 usually auto-enables liveness/readiness groups in Kubernetes; locally you can set **management.endpoint.health.probes.enabled=true**. With a separate `management.server.port`, consider additional paths `/livez` and `/readyz` on the main port.

**45 seconds is not optimal for every system.** Measure total web drain (20s in the lab), executor wait (up to ~7s), Hikari/Reactor/file cleanup, preStop, and ingress overhead. If the Pod hits SIGKILL before cleanup, durable recovery is mandatory.

### 13.3. Tasks outlasting the deadline

Never design multi-minute background jobs that must finish completely inside the Kubernetes grace period. Use durable queues, checkpoints, leases, idempotent retries, and status persistence. Stop accepting new jobs first; unfinished jobs are validly reassigned when workers restart.

## 14. Monitoring cleanup

| Metric/log | Meaning |
| --- | --- |
| Shutdown duration | Did SIGTERM to exit fit within grace budget? |
| HTTP in-flight/connection drain | Did the server wait for long requests successfully? |
| Executor active/queue/rejections | Tasks waiting, canceled, or rejected? |
| Hikari active/idle/pending | Unreturned connections or pool contention? |
| Reactor Scheduler pending/disposed | Any tasks rejected after dispose? |
| Netty active/idle connections, event loops | Were global/custom resources cleaned up? |
| Temporary file count/bytes | File leaks or orphan backlog? |
| JVM threads/file descriptors | Any non-daemon threads/sockets/file handles left alive? |
| Kubernetes exit reason/OOMKilled | Normal shutdown or force kill? |
| Cleanup exceptions | IO/security errors, retry policies? |

With Actuator you can inspect:

~~~bash
curl -i http://localhost:8080/actuator/metrics
curl -i http://localhost:8080/actuator/metrics/hikaricp.connections.active
curl -i http://localhost:8080/actuator/metrics/hikaricp.connections.pending
~~~

Metrics may not appear before the pool is used or under different configurations; do not conclude a leak solely from a 404 metric. To track custom executor queues/temp file counts, add custom instrumentation. Never log file contents, credentials, Authorization headers, or PII.

## 15. Common mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| JVM fails to exit after SIGTERM | Manually created executor holds non-daemon threads | Thread dump, add owner shutdown. |
| HTTP stops while task keeps running | Detached job outside HTTP graceful lifecycle | Await/persist/queue handoff. |
| SQL errors mid-shutdown | Hikari closed before requests or jobs finished | Let Spring own DataSource, drain first. |
| RejectedExecutionException | Producer submitted after shutdown | Stop intake and handle races. |
| shutdownNow fails to stop task | Task ignores interrupt or native blocking | Timeouts, checkpoints, cooperative cancel. |
| Pod SIGKILL before cleanup | Shutdown exceeded grace | Balance phase deadlines and durable jobs. |
| Hikari pending connections climb | DB pool exhausted or leaked connections | Trace transactions/SQL/try-with-resources. |
| WebClient keeps Netty threads alive | Context lifecycle didn't manage global resources | ReactorResourceFactory and shared ownership. |
| Custom Scheduler tasks rejected | `dispose` ran before subscriptions ended | Cancel/drain then dispose. |
| Global Reactor code breaks | `Schedulers.shutdownNow` called at wrong scope | Dispose only owned schedulers. |
| Temp files grow continuously | Deleted only in `@PreDestroy` | Per-job `finally`, quotas, and janitor. |
| Windows cannot delete file | Stream/channel still open | try-with-resources before `Files.deleteIfExists`. |
| Cleanup deletes other files | Deleted shared dir or input path | Owned workspace, never recursive-delete `/tmp`. |
| `@PreDestroy` does not run | Direct `new`, unclosed context, SIGKILL | Bean management and recovery. |
| Test suite fails after shutdown test | Test closed shared `SpringBootTest` context | Use isolated lifecycle contexts. |

## 16. Investigation runbook

1. Check whether the process received SIGTERM or was SIGKILLed.
2. Verify Boot `server.shutdown=graceful` and `timeout-per-shutdown-phase`.
3. Count in-flight HTTP requests and background queue tasks.
4. Inventory owners of custom executors, schedulers, clients, and temp dirs.
5. Take thread dumps to locate non-daemon workers, deadlocks, and blocking calls.
6. Measure Hikari active/pending connections and transaction durations.
7. Check Reactor subscriptions, Scheduler disposal, and Netty pool owners.
8. Check open file handles and workspace cleanup logs.
9. Cross-reference Kubernetes grace period, ingress propagation, and OOMKilled.
10. Re-test on staging with slow requests and Pod rollovers; write a runbook with owners, deadlines, and remediation.

## 17. Exercises

### Exercise 1 — Executor drain
Create a 2-second task in a copy of the lab, send SIGTERM while it is running. Observe shutdown/await/shutdownNow and file cleanup. Explain why `awaitTermination` should not be infinite.

### Exercise 2 — JDBC pool
Call `/demo/db` multiple times and inspect Hikari metrics. Explain the difference between `Connection.close()` and `HikariDataSource.close()`, and the consequence of closing the pool while a transaction is active.

### Exercise 3 — Reactor lifecycle
Use a custom `@Bean` Scheduler, close a separate `ApplicationContext`, and assert `isDisposed=true`. Compare with shared `Schedulers.boundedElastic`, avoiding global `shutdownNow`.

### Exercise 4 — Reactor Netty
In a separate WebFlux project, use managed `WebClient.Builder` and `ReactorResourceFactory`, start/close the context repeatedly, and count Netty threads/sockets. Ensure the custom factory is properly shared by client/server.

### Exercise 5 — Temporary files
Run 100 requests and verify no `job-*.txt` files remain between requests; after `context.close`, the workspace disappears. Create a simulated orphan file and design TTL+lease cleanup without deleting `/tmp`.

### Exercise 6 — Durable jobs
Change `/demo/work` to `POST /jobs` returning 202, then design durable state/queue/leases and idempotent retries after SIGKILL so no work is lost and side effects aren't duplicated.

### Exercise 7 — Kubernetes rollout
Send long requests on staging during a rolling restart. Measure graceful completion, connection draining, resource cleanup, and process exit time, tuning `terminationGracePeriodSeconds` from real measurements.

## 18. Pre-production checklist

- [ ] Every resource has an owner, init, users, stop-intake, close API, and deadline.
- [ ] Web server graceful shutdown and request draining are verified.
- [ ] Executors have bounded shutdown/await and task cancellation policies.
- [ ] Detached background jobs have durable persistence where needed.
- [ ] Spring-managed Hikari DataSource is never closed prematurely.
- [ ] Connection/Statement/ResultSet handles are returned per transaction/request scope.
- [ ] HTTP client connection pools have clear ownership.
- [ ] Custom Reactor Schedulers are disposed; shared Schedulers are never shut down improperly.
- [ ] ReactorResourceFactory/Netty resources are used and closed consistently.
- [ ] Subscriptions are drained/canceled before closing dependencies.
- [ ] Temp files deleted in `finally`; streams/channels closed before deletion.
- [ ] Owned workspace cleaned up only after workers stop.
- [ ] Orphan recovery exists for SIGKILL, OOMKilled, and restarts.
- [ ] Lifecycle callbacks never duplicate closes or block forever.
- [ ] Both context-close tests and staging SIGTERM tests exist.
- [ ] Kubernetes grace period, readiness, and ingress propagation are measured.
- [ ] Metrics/logs cover resource leaks, failures, durations, with zero leaked secrets.

## 19. Self-check questions

**1. Does `server.shutdown=graceful` automatically close a manually created `ExecutorService`?** No. It only handles web server graceful draining; custom pools need an owner.

**2. Does `shutdownNow()` guarantee stopping all tasks?** No, it is best-effort interruption.

**3. Does `Connection.close()` close the Hikari pool?** No; pooled connections are typically returned to the pool.

**4. Does `@PreDestroy` run after SIGKILL?** Not guaranteed. Crash recovery is required.

**5. Why not delete the temp directory immediately upon receiving SIGTERM?** Workers may still be writing files. Stop/await first, delete afterward.

**6. When should `SmartLifecycle` be used?** When phased stops and callbacks are needed to coordinate producers/workers/dependencies.

**7. How do `Schedulers.newBoundedElastic` and `Schedulers.boundedElastic` differ?** `new*` creates a dedicated Scheduler while `boundedElastic` is shared; never shut down the shared one from a sub-component.

**8. Does `WebClient` have a single `close()` shutting down all Netty resources?** No. Cleanup must follow the resource factory/connector owner.

**9. Does sending HTTP 202 mean the graceful web server waits for the background job?** No. Detached work needs its own drain/durable queue.

**10. Does `timeout-per-shutdown-phase` bound every `@PreDestroy`?** No; set dedicated deadlines for cleanup.

## 20. References

1. [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html): `server.shutdown`, phase timeouts, and web server behavior.
2. [Spring Framework — Bean Destruction](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): `@PreDestroy`, destroy methods, lifecycle callbacks, and `SmartLifecycle`.
3. [Spring Boot 3.3 — SQL Databases](https://docs.spring.io/spring-boot/3.3/reference/data/sql.html): DataSource/Hikari, embedded H2, and pooling.
4. [Spring Boot 3.3 — Calling REST Services](https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html): managed `WebClient.Builder` and HTTP resources.
5. [Spring Boot 3.3 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): `ReactorResourceFactory` and Netty sharing.
6. [Spring Framework — WebClient Resources](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): global/managed Reactor Netty resources.
7. [Reactor — Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): custom/shared schedulers.
8. [Java 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `shutdown` and `awaitTermination`.
9. [Java 17 — Files API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `createTempFile`, `deleteIfExists`, `walkFileTree`.
10. [Kubernetes — Pod Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#termination-of-pods): SIGTERM, preStop, deadlines, and SIGKILL.

**Conclusion:** Proper application shutdown means **stopping new intake, draining in-flight work, releasing owned resources in order**, and verifying the result. Spring Boot graceful shutdown handles HTTP, not every executor or temp file; let the container close Hikari at the right moment, dispose only owned Reactor resources, and always clean up per-job files via `finally`. Because SIGKILL can bypass all callbacks, production systems need durable recovery, deadlines, and monitoring rather than blind faith in `@PreDestroy`.
