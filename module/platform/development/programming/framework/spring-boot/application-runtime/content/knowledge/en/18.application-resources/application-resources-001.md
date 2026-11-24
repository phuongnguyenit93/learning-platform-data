# Defining Resource Ownership and Lifetime in Spring Boot

## 1. The Problem: Creating a Resource Is Not Enough—You Must Know Who Closes It

A Spring Boot application uses many resources: connection pools, HTTP clients, executors, file streams, JDBC connections, message consumers, transactions, caches, threads, sockets, and objects allocated per request. **Every resource needs a clearly defined owner and lifetime.**

For example, an HTTP request wants to read data:
- The request handler **borrows** a connection from the pool.
- The pool **owns the physical connections** and decides when to open, reuse, and evict them.
- Business code **owns the borrowed handle/lease** and must return it at the right time.
- `ApplicationContext` (usually via a pool bean) manages the lifetime of the pool within the application.
- The external database server **is not owned by the JVM**, so shutting down the application has no right to delete the database.

If these roles are confused, two opposite bugs occur:

1. **Resource leaks:** nobody closes files, connections, response bodies, threads, or subscriptions.
2. **Premature closing:** one request closes a shared pool/client, causing other requests to fail.

The question in this guide is not just "should I use `@PreDestroy` or `try-with-resources`?" but rather: **Who created or assumed ownership, who is only borrowing, who has the right to close, when does the right to use expire, and who cleans up if initialization fails?**

## 2. Five Pieces of Information to Specify for Every Resource

A good decision table should describe at least:

| Attribute | Question to Answer | Example |
| --- | --- | --- |
| **Creator** | Who calls the create/open API? | Auto-configuration creates `DataSource` |
| **Owner** | Who is responsible for ensuring release? | Container-managed connection pool bean |
| **Borrower/User** | Who is allowed to use but does not own the underlying resource? | Repository borrows a JDBC connection |
| **Lifetime** | From which milestone to which milestone is the resource valid? | Pool lives alongside `ApplicationContext` |
| **Close trigger** | What ends it and who executes close? | Context shutdown → pool's destroy method |

You should also include **failure cleanup**: when initialization partially succeeds, who closes the parts already opened? For resources with unbounded I/O, add deadlines, cancellation, retries, and monitoring.

### Owner differs from creator

The object calling the constructor does not necessarily have to close it itself. A factory can create a resource and then **transfer ownership** to another managing component. However, the transfer of ownership must be explicit: from the moment transfer succeeds, the creator must no longer arbitrarily close it, and the recipient must ensure cleanup.

For example:
- A `@Bean` method creates a client and returns it to the Spring IoC container. Typically, the container manages the destruction of a singleton bean.
- A factory returns an `InputStream` to the calling code. Under standard Java contracts, the caller takes responsibility for closing it unless stated otherwise.
- A pool creates physical connections, while business code receives a lease. Calling `Connection.close()` on a connection obtained from a pool usually **returns the handle to the pool** rather than closing the entire pool.

### An owner can be a larger enclosing object

Ownership often forms a tree:

~~~text
JVM / process
  |
  +-- Spring ApplicationContext
       |
       +-- Singleton bean: Connection Pool (owner)
       |      +-- physical connections (managed by pool)
       |      +-- request A: JDBC Connection lease (request owns lease)
       |      +-- request B: JDBC Connection lease (request owns lease)
       |
       +-- Singleton bean: HTTP client (owner)
       |      +-- request: response stream (operation owns handle)
       |
       +-- SmartLifecycle consumer (owner of subscription/worker)
       |      +-- each delivery: processing context / ack handle
       |
       +-- Controller/Service (borrower of the singletons above)
~~~

This is an **ownership** diagram, not a Java class inheritance diagram or a one-to-one bean graph. A Java object may just be a wrapper, while the real resource resides in a library or an external server.

## 3. Lifetime: There Is No Single Scope for Every Resource

### 3.1. Classification by lifetime

| Resource | Typical Recommended Lifetime | Appropriate Owner | User |
| --- | --- | --- | --- |
| `DataSource` / connection pool | Scope of ApplicationContext | Bean managed by Spring/auto-configuration | Services, repositories, transaction managers |
| Reusable HTTP client | Application or client bean scope | Singleton bean / client configuration | Multiple requests, tasks |
| Custom-created `ExecutorService` | Owner bean or worker lifecycle | Bean managing the executor | Submitted tasks |
| Kafka consumer / message listener container | `SmartLifecycle` component scope | Framework container / listener bean | Message-handling handlers |
| Borrowed JDBC `Connection` | Operation/transaction scope | Caller or transaction manager | Current query |
| `InputStream` / `Files.lines` | File-reading block scope | Scope with `try-with-resources` | Parser processing the file |
| HTTP response body/stream | Single outbound request scope | Code receiving response or client abstraction | Response parser |
| Temporary file | Until job/retention completes | Job/component creating the file | Job steps |
| Per-request upload buffer | Request or forwarding task scope | Framework/handler per API | Request handler |
| Scheduled task handle | Task registration lifetime | Registering component | Scheduler |
| Socket session | Connection lifetime | Server/session manager | Per-message handler |
| `@Scope("prototype")` bean holding a resource | Recipient instance scope | Caller receiving the prototype after creation | Single operation |
| External DB server, topic, cloud bucket | Outside JVM; has independent lifetime | Infrastructure management system | Application acts as client |

These are guidelines, not immutable rules. An HTTP client may be owned by the framework; a temporary file may need to survive across multiple requests until a job finishes. What matters is that **the lifetime matches the business context and is expressed through clear API/ownership contracts**.

### 3.2. "Who closes?" must be separated from "who uses?"

A service injected with a `DataSource` usually **does not own the pool**, so it must not do:

~~~java
// Wrong idea: service borrows the pool but closes the shared pool itself.
((AutoCloseable) dataSource).close();
~~~

This is pseudocode illustrating an error: not every `DataSource` implements `AutoCloseable`; casting and closing can also fail. More importantly, the pool is shared among many components and the pool's owner must decide when to close it.

Conversely, an `InputStream` opened inside a method has a very short lifetime:

~~~java
try (InputStream in = Files.newInputStream(path)) {
    // Read the file here.
}
~~~

This is an illustrative snippet requiring imports for `java.io.InputStream`, `java.nio.file.Files`, and the `path` variable. At the end of the block, the caller of `Files.newInputStream` closes the stream even if an exception occurs. Do not defer closing the stream until `ApplicationContext.close()`.

## 4. Bean Scope and Resource Lifetime: Related, Not Identical

Spring supports multiple scopes. You must know **when the container creates a bean and when it commits to calling destruction**.

| Bean Scope | Typical Quantity/Lifetime | Destruction Managed by Spring? | Resource Notes |
| --- | --- | --- | --- |
| `singleton` (default) | One bean instance per Spring container/bean definition | Yes, for container-owned singletons | Usually suitable for shared pools/clients |
| `prototype` | Creates an instance on demand | **Does not automatically invoke destroy callbacks for each prototype after handoff** | Caller must clean up |
| `request` (Web) | One instance per HTTP request | Managed by web scope when request ends, in supported contexts | Do not hold connections longer than the request |
| `session` (Web) | One instance per HTTP session | Depends on session/web scope lifecycle | Do not inadvertently keep sockets/JDBC connections alive for the whole session |
| `application` (Servlet web scope) | Scope of `ServletContext` | Managed by scope per web app | Do not equate with singleton across multiple contexts |
| Custom scope | Per custom contract | Depends on `Scope` implementation | Verify destruction callbacks yourself |

**Most importantly:** the Spring Framework documentation states that a `prototype` bean is created, configured, and handed over, after which the container **does not manage its complete lifecycle**: configured destroy callbacks are not automatically invoked for each prototype. If a prototype holds a resource, the recipient must take responsibility for closing it or use a dedicated tracking mechanism.

### A prototype injected into a singleton is only retrieved at injection time

~~~java
@Component
class SingletonWorker {
    private final PerOperationResource resource;

    SingletonWorker(PerOperationResource resource) {
        this.resource = resource;
    }
}
~~~

This is a non-standalone illustrative snippet. If `PerOperationResource` has prototype scope, constructor injection into a normal singleton creates/retrieves the prototype **only when the singleton is created**. It does not automatically become a fresh prototype for every method call.

When a new instance per operation is needed, use `ObjectProvider<PerOperationResource>`, a dedicated factory, or an appropriate scoped proxy; **after obtaining a prototype instance that holds a resource, define how to close it**. `ObjectProvider.getObject()` only retrieves the instance; it does not automatically add `try-with-resources` if the type does not support `AutoCloseable`.

### Request scope does not mean holding resources until the end of the request is best

Even when request scope has a destruction callback, a file stream or JDBC connection needed for only 5 ms should be closed early at the end of the operation. Waiting until the end of the request can exhaust the pool under high load. Choose **the shortest lifetime sufficient for the purpose**.

### A Spring singleton is different from a Java static singleton

A Spring singleton is one instance per bean definition **within a single container**, not by default a JVM-wide singleton. If tests create multiple contexts or an application has parent/child contexts, there can be multiple singleton beans of the same class. A `static` variable shared across contexts has JVM lifetime and can be closed by mistake when one context shuts down.

## 5. Rules for Managing Resources Within a Method

**Whoever opens or borrows a handle for an operation must usually return that handle at the end of the operation**, unless the contract explicitly states that a transaction/framework is managing it.

### 5.1. Try-with-resources for per-operation resources

~~~java
try (BufferedReader reader = Files.newBufferedReader(path)) {
    String line;
    while ((line = reader.readLine()) != null) {
        process(line);
    }
}
~~~

The snippet above is not standalone because `path` and `process` are application placeholders; it requires importing `BufferedReader` and `Files`. The exact pattern is **open → use → close in the exact lexical scope**. Java calls `AutoCloseable.close()` when exiting the block even if an exception occurs.

If `close()` also throws an error while the block body has already thrown an error, Java preserves the primary error and attaches the close error to the `suppressed exceptions` list. Do not catch all exceptions and swallow them, as doing so hides resource leaks.

### 5.2. JDBC connection borrowed from a pool

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement stmt =
             connection.prepareStatement("select id from users where id = ?")) {
    stmt.setLong(1, userId);
    try (ResultSet rs = stmt.executeQuery()) {
        if (rs.next()) {
            return rs.getLong(1);
        }
        return null;
    }
}
~~~

This is a **non-standalone DAO snippet**, requiring `dataSource`, `userId`, JDBC type imports, and a `Long` return type. The caller closes the `ResultSet`, statement, and connection handle at the end of the operation. With a pool such as HikariCP, closing a pooled connection **typically returns the lease to the pool** rather than closing the entire pool.

**Warning about `@Transactional`:** if the Spring transaction manager/`JdbcTemplate` is managing a connection bound to a transaction, do not manually interfere by closing the framework-owned connection. Prefer `JdbcTemplate`, JPA, or the appropriate transaction abstraction rather than mixing raw `DataSource.getConnection()` with connections synchronized by Spring transactions. In framework-managed layers, follow the framework's handle-return/release contract rather than applying a close rule mechanically.

### 5.3. HTTP responses and streams

If an HTTP library returns a `Response` or streaming body, read its Javadoc to know who must close it. With streaming HTTP, failing to close can keep a connection out of the pool; conversely, closing the entire shared HTTP client after every request breaks the lifetime of other requests.

In other words: **close the response/lease per request; close the client/pool per application** (if the client is owned by the application).

## 6. How Does Spring Own Resources at the Bean Level?

### 6.1. Creating and handing ownership to the container

~~~java
@Configuration
class ClientConfig {

    @Bean(destroyMethod = "close")
    SharedRemoteClient sharedRemoteClient() {
        return new SharedRemoteClient();
    }
}
~~~

This snippet illustrates configuration and is not standalone: it requires `SharedRemoteClient` and imports. When a bean is a Spring-managed singleton, Spring invokes the bean's destroy method when the container shuts down normally.

In Java configuration, `@Bean` by default also has a **destroy method inference** mechanism: a public `close()` or `shutdown()` method can be detected automatically, including `AutoCloseable` / `Closeable`. Specifying `destroyMethod = "close"` makes the ownership contract more explicit. Avoid both calling `close()` manually from multiple borrowers and relying on Spring to close it again without idempotence.

### 6.2. Resources borrowed from outside the container

Sometimes a factory returns an object **owned by another system**. If you register that object as a `@Bean`, Spring may by default infer a `close()` method and **mistakenly close the borrowed resource** when the context ends.

If the contract makes it clear that Spring may only use but must not close this object:

~~~java
@Bean(destroyMethod = "")
ExternalOwnedClient borrowedExternalClient() {
    return externalSystem.client();
}
~~~

This is an illustrative, non-standalone snippet; `externalSystem` and `ExternalOwnedClient` are hypothetical objects. `destroyMethod = ""` disables custom destroy method inference on `@Bean`. It **does not disable every form of destruction**, such as callbacks from `DisposableBean` or dedicated destroy annotations if the bean has them. You must check the entire contract when handing an external object to the container.

In many cases, a better approach is **not to register the borrowed object as an owned bean**, and instead create an adapter/wrapper with an explicit lifecycle contract. The deciding factor is who is actually responsible for closing, not merely placing an annotation.

### 6.3. @PreDestroy, DisposableBean, destroyMethod

Common options:

- `@PreDestroy`: callback inside the bean class, using `jakarta.annotation.PreDestroy` on Spring Boot 3.x.
- `DisposableBean.destroy()`: Spring-specific interface, suitable when a direct Spring contract is needed.
- `@Bean(destroyMethod = "close")`: specifies the close method on the bean factory, convenient for library classes.
- `AutoCloseable.close()`: Java contract for closeable objects, combined with `try-with-resources` or destroy method inference.

They are not completely interchangeable. If multiple different callbacks are configured on the same bean, they may be invoked in different orders; avoid having each callback close the underlying resource and accidentally double-close it. Prefer **a single clearly owned cleanup path that is safe to call repeatedly**.

### 6.4. Do not use finalize or System.gc to guarantee closing

Do not rely on the garbage collector or finalizers to release finite handles in a timely manner. GC depends on memory pressure, not on the number of connections remaining in a pool; a JVM can run out of connections or file descriptors before GC reclaims objects. Modern Java favors `AutoCloseable`, lexical scoping, lifecycle callbacks, and explicit close mechanisms.

## 7. Runnable Example: Owner Lives with Context, Lease Lives with Operation

This example creates a **simulated client** with two resource tiers:

- `SharedClient`: a singleton bean **owned by ApplicationContext** and closed when the context closes.
- `Lease`: a handle borrowing the client, **owned by the operation** and closed as soon as processing finishes.
- `ApplicationRunner`: uses the client but **does not own the right to close the client**.
- `main()`: opens the Spring context with `SpringApplication.run`, then closes the context via `try-with-resources` when the demo completes.

The code opens no real sockets so stdout is deterministic. This is an ownership model, not a production connection pool implementation.

### 7.1. Create a Java 17+ Maven project

~~~text
resource-ownership-demo/
├── pom.xml
└── src/main/java/com/example/ownership/
    └── ResourceOwnershipApplication.java
~~~

**File pom.xml:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>resource-ownership-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

Spring Boot 3.5.16 is a released 3.5.x version. The example is intended for learning mechanisms on the 3.5 branch; for production systems, choose a currently supported branch and verify APIs against the version actually used.

### 7.2. Complete Java file

**File src/main/java/com/example/ownership/ResourceOwnershipApplication.java:**

~~~java
package com.example.ownership;

import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ResourceOwnershipApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ResourceOwnershipApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            SharedClient client = context.getBean(SharedClient.class);
            System.out.println(
                    "07_MAIN_OWNER_STILL_OPEN=" + !client.isClosed());
        }

        System.out.println("09_CONTEXT_CLOSED");
    }

    // ApplicationContext is the owner of the singleton SharedClient.
    @Bean(destroyMethod = "close")
    SharedClient sharedClient() {
        return new SharedClient();
    }

    // Runner only uses SharedClient; it does not call client.close().
    @Bean
    ApplicationRunner demo(SharedClient client) {
        return args -> {
            System.out.println("02_RUNNER_BEGIN");

            // This operation is the owner of Lease.
            try (Lease lease = client.borrow()) {
                lease.execute();
            }

            System.out.println("06_RUNNER_END");
        };
    }

    static final class SharedClient implements AutoCloseable {
        private boolean closed;
        private int activeLeases;

        SharedClient() {
            System.out.println("01_SHARED_CLIENT_CREATED");
        }

        synchronized Lease borrow() {
            ensureOpen();
            activeLeases++;
            System.out.println(
                    "03_LEASE_ACQUIRED active=" + activeLeases);
            return new Lease(this);
        }

        synchronized void use() {
            ensureOpen();
            System.out.println("04_LEASE_USED");
        }

        synchronized void release() {
            if (activeLeases <= 0) {
                throw new IllegalStateException("release without borrow");
            }
            activeLeases--;
            System.out.println(
                    "05_LEASE_RELEASED active=" + activeLeases);
        }

        synchronized boolean isClosed() {
            return closed;
        }

        private void ensureOpen() {
            if (closed) {
                throw new IllegalStateException("client already closed");
            }
        }

        @Override
        public synchronized void close() {
            if (closed) {
                return; // Idempotent shutdown.
            }
            if (activeLeases != 0) {
                throw new IllegalStateException(
                        "cannot close with active leases="
                                + activeLeases);
            }
            closed = true;
            System.out.println("08_SHARED_CLIENT_CLOSED");
        }
    }

    static final class Lease implements AutoCloseable {
        private final SharedClient owner;
        private final AtomicBoolean closed = new AtomicBoolean();

        Lease(SharedClient owner) {
            this.owner = owner;
        }

        void execute() {
            if (closed.get()) {
                throw new IllegalStateException("lease already closed");
            }
            owner.use();
        }

        @Override
        public void close() {
            if (closed.compareAndSet(false, true)) {
                owner.release(); // Return the lease, DO NOT close the owner.
            }
        }
    }
}
~~~

The code is **a single complete Java file** in the Maven project above, requiring neither a database nor an HTTP server. `SharedClient` has no `@Component` annotation and is registered **once** via `@Bean`; `Lease` is not a bean and is owned by the operation itself.

**Ownership analysis:**

| Object | Who Creates It? | Who Owns It? | When Is It Closed? |
| --- | --- | --- | --- |
| `ConfigurableApplicationContext` | `SpringApplication.run` | `main()` in the CLI demo program | At the end of `try-with-resources` in `main` |
| `SharedClient` | `@Bean` factory method | Spring context | Spring calls `close()` when closing the context |
| `Lease` | `SharedClient.borrow()` | Runner's operation block | At the end of the runner's `try-with-resources` |
| `ApplicationRunner` | Spring context | Spring context | Runner does not close `SharedClient` itself |
| External server resources | Not created in the demo | External system | Outside the demo's close authority |

This simulation cleanly separates **closing a lease** from **closing the owner**. When `Lease.close()` calls `owner.release()`, it only returns the handle to the managing tier; it does not close `SharedClient`. The Spring context closes `SharedClient` after operations complete.

`SharedClient.close()` checks `activeLeases`. In the demo, if a lease is held too long, closing the owner throws an error so it does not mask a borrowed handle still open. In production, the owner typically needs graceful draining with a timeout, task cancellation policies, and metrics; simply throwing an error inside a destroy method is not a complete shutdown strategy.

### 7.3. Compile and run

In the directory containing `pom.xml`:

~~~bash
mvn package
java -jar target/resource-ownership-demo-0.0.1-SNAPSHOT.jar
~~~

Or:

~~~bash
mvn spring-boot:run
~~~

**Lines printed by the program itself** in the following order (banner, Maven output, and Spring Boot logs may appear in between):

~~~text
01_SHARED_CLIENT_CREATED
02_RUNNER_BEGIN
03_LEASE_ACQUIRED active=1
04_LEASE_USED
05_LEASE_RELEASED active=0
06_RUNNER_END
07_MAIN_OWNER_STILL_OPEN=true
08_SHARED_CLIENT_CLOSED
09_CONTEXT_CLOSED
~~~

Sequence explanation:

1. `SharedClient` is created once by Spring during singleton instantiation.
2. `ApplicationRunner` is invoked by Boot after the context refreshes.
3. The runner borrows a `Lease`; active leases increase from 0 → 1.
4. The runner uses the `Lease`, without closing the owner.
5. Upon exiting `try-with-resources`, the `Lease` is returned and active leases decrease from 1 → 0, even if code in the block throws an exception.
6. The runner completes; `SharedClient` **remains open**.
7. `SpringApplication.run` returns; `main` verifies that the owner is still alive.
8. `main` closes the context at the end of the block. Spring invokes the singleton's `destroyMethod` `close`, and the owner is closed.
9. `main` continues after the context closes.

**Key takeaway:** the bean factory method returns `SharedClient`, but **the context itself** owns destruction responsibility. The runner receives a shared reference and must not call `client.close()` after a single pass of processing.

### 7.4. Reading the output properly

If you see Spring Boot's "Started..." log before the runner lines, do not conclude that the JVM has finished all startup tasks. `ApplicationRunner` executes after refresh and before Ready. The demo prints clear markers when the runner executes and when the context closes, making it easy to distinguish startup, operation, and shutdown lifecycles.

The example has no web server, so the program actively closes the context after the runner. **Do not apply closing the context immediately after `run()` directly to a long-lived web service**: doing so will stop the server immediately.

### 7.5. Try failure scenarios

- Remove the `try-with-resources` around `Lease` and borrow without closing: by the time the context closes, `activeLeases` is still positive, and the owner detects and reports an error. This is a leak-detection mechanism, not a substitute for real cleanup.
- Call `client.close()` inside the runner after returning the `Lease`: the borrowing caller closed the owner prematurely. Another operation will receive "client already closed".
- Change `Lease.close()` to call `owner.close()`: ownership is wrong, and it can fail when multiple `Lease` instances are active.
- Call `Lease.close()` twice: `AtomicBoolean` guards against releasing more than once. Although idempotence is good, you must still place close in the right scope.
- In a real application, add tests for closing under concurrent requests, drain deadlines, exceptions during close, and cases where context startup fails.

## 8. Responsibilities on Error Paths and Shutdown

### 8.1. Partially opened when initialization fails

Suppose creating a client requires three steps: opening a socket, authenticating, and subscribing. If subscribing fails, the owner must close the socket opened earlier; you cannot simply wait for a destruction callback on a bean that was never successfully created.

Illustrative pattern:

~~~java
Socket socket = new Socket();
try {
    socket.connect(address, timeoutMillis);
    authenticate(socket);
    subscribe(socket);
    return socket; // Transfer ownership if the factory succeeds.
} catch (Exception failure) {
    try {
        socket.close();
    } catch (Exception closeFailure) {
        failure.addSuppressed(closeFailure);
    }
    throw failure;
}
~~~

This is a **non-standalone illustrative snippet**: `address`, `timeoutMillis`, `authenticate`, and `subscribe` are hypothetical APIs/variables. The key point is rolling back partial resources before rethrowing. Only after the factory successfully transfers ownership does the caller/container become responsible for closing it later.

### 8.2. Normal Spring shutdown

On the standard context-closing path:

~~~text
ApplicationContext.close() requested
  |
  +-- ContextClosedEvent
  +-- Stop appropriate Lifecycle / SmartLifecycle beans
  +-- Execute singleton destroy callbacks
  |     +-- @PreDestroy
  |     +-- DisposableBean.destroy()
  |     +-- custom @Bean(destroyMethod = "...")
  |
  +-- Context close completed
~~~

This general order helps design shutdown: **stop generating new work before closing resources that ongoing work depends on**. If a consumer depends on a pool, the consumer should stop and drain before the pool is closed. You can use `SmartLifecycle.getPhase()` and dependency relationships to coordinate.

This does not mean every situation guarantees all callbacks: a JVM killed by `SIGKILL`, crashing, losing power, or failing too early during startup can bypass part of the lifecycle. External resources need TTLs, lease expiration, timeouts, and appropriate recovery mechanisms.

### 8.3. SmartLifecycle for background resources

An executor or message consumer has two stages:
- **stop**: stop accepting new work and wait for in-flight work (within the allowed deadline);
- **destroy/close**: release resources after work has stopped.

`SmartLifecycle.stop(Runnable)` lets you notify the lifecycle processor **after stopping has genuinely completed**. Invoking the callback immediately after `ExecutorService.shutdown()` while tasks are still running reports completion too early. Conversely, failing to invoke the callback may cause Spring to wait until the phase timeout expires.

With Spring Boot, you can configure:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

This property bounds how long the processor waits per phase; it does not force tasks or network connections to close themselves. The resource owner still needs its own timeouts and force-stop/cancellation policies.

### 8.4. Do not close resources on the wrong event timing

`ApplicationStartedEvent` occurs after refresh but before runners; `ApplicationReadyEvent` occurs after runners and before the readiness event. These are **startup milestones**, not triggers to close clients. `ContextClosedEvent` is the context-closing milestone, though listeners for that event usually run **before** destroy callbacks; use it to coordinate stopping new work, not as a place where every borrower races to close the same pool.

## 9. Ownership in Dependency Injection and Multiple Contexts

### 9.1. Injecting a dependency does not grant close rights

If a service receives a singleton via constructor injection, it usually receives only **usage rights**. It does not become the owner:

~~~java
@Service
class OrderService {
    private final SharedClient client;

    OrderService(SharedClient client) {
        this.client = client;
    }

    void execute() {
        // Use SharedClient according to its API.
        // Do not call client.close() here.
    }
}
~~~

This is a non-standalone illustrative snippet: it requires the corresponding imports, implementations, and contracts. This rule prevents a shared bean from being shut down by a short-lived borrower.

### 9.2. Prototypes need the recipient to manage them

A prototype bean holding a resource is an easy place to leak:

~~~java
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
@Bean
PerJobHandle perJobHandle() {
    return new PerJobHandle();
}
~~~

This is a non-standalone config snippet. Spring does not automatically invoke destruction callbacks for each prototype after handoff. If a job retrieves an instance from `ObjectProvider<PerJobHandle>`, the job must close the handle or hand that responsibility to another owner. Do not simply put `@PreDestroy` on a prototype and assume Spring will invoke it on `ApplicationContext.close()`.

In many cases, it is better to inject a **singleton factory** that creates an `AutoCloseable` handle per operation and use `try-with-resources`; that makes ownership immediately visible in the code.

### 9.3. Parent and child ApplicationContexts

In systems with multiple contexts:
- A parent context may own a shared pool.
- Child contexts may create their own services, controllers, or consumers.
- Closing a child context should not close a resource owned by the parent, because other children may still be using it.
- A `static` pool shared across multiple contexts does not automatically become a resource owned by any particular context.

You must specify **which context** scopes the owner, rather than vaguely writing "Spring manages it" and ignoring boundaries.

### 9.4. Reloading, tests, and multiple contexts

Tests using `@SpringBootTest` may cache contexts across tests; a single test case must not close a global client when the context is still being reused. If a test creates a `ConfigurableApplicationContext` itself, it should close it after the test completes; if Spring TestContext owns it, let the framework manage it.

When multiple contexts exist in the same JVM, the number of singleton beans or pools can be greater than one. Therefore, **per-context resource limits** and the number of times contexts are created directly affect file descriptors, database connections, and memory.

## 10. Ownership Contracts Across Async/Thread Boundaries

A method may return before asynchronous work using a resource has finished. For example:

~~~java
try (InputStream in = Files.newInputStream(path)) {
    executor.submit(() -> consume(in));
}
~~~

This is **illustrative pseudocode**, with undefined `path`, `executor`, and `consume`. The block exits right after `submit()`, closing the stream before the background task can read it. This is a bug where **the resource's lifetime is shorter than the borrower's lifetime**.

Better designs:

1. Have the task **open and close** the `InputStream` itself inside the task, because the task owns the operation.
2. Transfer ownership via an explicit abstraction and ensure the recipient closes it in `finally`; the sender must not close after a successful transfer.
3. Wait for the task to finish inside the block if the caller truly must own the stream, with timeouts and interruption handling.
4. When using a shared resource such as an HTTP client/pool, the task only borrows the client; do not close the owner at the end of the task.
5. For an application-owned executor, stop accepting new tasks, wait for in-flight tasks, and only then close the pool/client that the tasks use.

**Rule:** a resource must live at least until **every valid borrower has finished**, yet no longer than necessary. This includes async flows, callbacks, lazily evaluated streams, and reactive subscriptions.

### Ownership in reactive/streaming

A `Publisher`/`Flux` may be constructed during a request while actually being subscribed to later. Do not use lexical `try-with-resources` to close a resource before the pipeline completes. Use APIs that manage resources according to the subscription lifecycle, such as `using` / `usingWhen` in the appropriate reactive library, and follow the ownership contract of the HTTP client in use.

Do not assume that emitting an entity means the HTTP connection has already been released; that depends on how the response body/stream is consumed and on the specific API.

## 11. Diagnosing Leaks and Premature Closing

| Symptom | Likely Cause | Check |
| --- | --- | --- |
| Pool runs out of connections even at low RPS | Lease not returned, transactions too long | Active/idle/pending connections, borrower stack traces |
| Random "Connection is closed" | Borrower closed owner or lease used after close | Lifecycle logs, owner/lease IDs |
| Threads keep running after shutdown | Executor not closed or stop does not wait for tasks | Thread dumps, executor state, shutdown callbacks |
| Opening files fails with "too many open files" | Streams/channels not closed | File descriptor count, error paths |
| `@PreDestroy` never runs for prototype | Spring does not auto-destroy prototypes | Verify scope and caller responsible for cleanup |
| Extra pools after each integration test | Each context creates its own singleton | Context cache, test lifecycle, bean creation |
| One request breaks the whole service | Shared pool/client closed by a request | Search for `close()` in borrower code |
| Shutdown hangs | Work still holding resources, callback never finishes | Timeouts, in-flight count, `SmartLifecycle` |
| Memory keeps growing even after closing connections | Buffers/caches/listeners retaining references | Heap dump, subscription registrations, callbacks |
| Closing while new resources are created | Start/stop race, missing closing state | Synchronize resource ownership and generations |
| JVM exits while cloud job keeps running | External job outside JVM lifecycle | Remote lease/TTL/cancel API, external system contract |

**Minimum observability** for a production resource owner should include: current state (OPEN/CLOSING/CLOSED), active borrowers, create/close counts, pending tasks, drain duration, and cleanup errors. Never log passwords, tokens, or credentials in lifecycle events.

### Closing properly does not guarantee zero leaks

A client may be closed properly while individual response bodies/leases are held longer than expected, preventing resources from being reused before shutdown. Therefore, measure both **owner lifetime** and **borrower lifetime**, not just a single "closed" boolean.

## 12. Choosing the Right Management Tool for Each Resource Type

| Need | Preferred Tool | Reason |
| --- | --- | --- |
| Method-local file/stream/handle | `try-with-resources` | Cleans up when exiting lexical scope, even on exception |
| Client/pool shared across services | Singleton `@Bean` + destroy callback | Context manages lifetime and closes at shutdown |
| Resource tied to a specific bean | `@PreDestroy` or configured destroy method | Bean takes responsibility for release |
| Worker/consumer needing ordered start/stop | `SmartLifecycle` | Coordinates phases and graceful stop |
| JDBC transaction | `@Transactional`, `JdbcTemplate`, transaction manager | Framework manages transactions/connections |
| Prototype holding a resource | Factory + `AutoCloseable` handle closed by caller | Prototypes are not auto-destroyed by the container |
| HTTP request-scoped state | Appropriate request scope, close per operation as early as possible | Avoids holding connections across slow requests |
| Asynchronous job | Job/task owner, completion callback / future cleanup | Lifetime matches work, not method return |
| Borrowed object from external API | Do not close owner; explicit adapter | Avoids erroneous container destroy inference |
| External durable resource | Independent provisioning/lease/TTL contract | JVM does not own the entire external system |

Do not pick `@PreDestroy` for everything just because it is "easy to remember." Likewise, do not use `try-with-resources` on a singleton bean inside its factory method and return an already closed object. Each mechanism maps to a distinct **ownership/lifetime boundary**.

## 13. Anti-Patterns to Eliminate

### 13.1. Closing a shared pool in a request's finally block

~~~java
try {
    doWork(sharedDataSource);
} finally {
    closeTheWholePool(sharedDataSource); // Wrong ownership.
}
~~~

This is pseudocode. A request only borrows; it does not own the entire pool. Fix it by releasing the lease/transaction that the request actually owns, letting the pool owner close the pool at the end of the application's life.

### 13.2. Returning an already closed resource to the caller

~~~java
InputStream load(Path path) throws IOException {
    try (InputStream in = Files.newInputStream(path)) {
        return in; // Wrong: caller receives an already closed stream.
    }
}
~~~

This is a method illustration requiring the corresponding imports. If a method transfers ownership of a stream to its caller, **do not close it before returning**, and document "caller closes." Even better, have the method return the read data (a byte array or domain object) if the data is small, hiding ownership altogether.

### 13.3. Holding a transaction connection for an entire session

An HTTP session can last tens of minutes or longer. Holding a JDBC `Connection` in a session exhausts the pool, creates stale connections, and stretches transactions beyond their intended scope. Open/borrow connections for short transactions and close/return them immediately after the unit of work.

### 13.4. Creating an executor in every callback

If every incoming message calls `Executors.newSingleThreadExecutor()` without managing its close, thread counts grow without bound. Normally you should inject an executor with clear ownership or use a framework-configured task executor with a well-defined shutdown procedure.

### 13.5. Relying on GC to close

File descriptors, sockets, and connection pools have finite quotas; they can run out before GC runs. Do not use finalizers or `System.gc` as a cleanup contract.

### 13.6. Double-close via two destroy callbacks

If a bean has its own `@PreDestroy` and is also configured with `@Bean(destroyMethod = "close")` where both close the same resource, different callbacks may run sequentially and double-close. Have a single idempotent cleanup path or remove redundant registrations.

### 13.7. Closing immediately on ApplicationReadyEvent

Ready only indicates that startup has completed; it is not the end-of-life point for resources. Closing a pool/client as soon as the app is ready will break subsequent requests. Shared resources normally must live until context shutdown; stopping acceptance of new tasks belongs in the shutdown lifecycle.

### 13.8. Ambiguous asynchronous ownership handoff

A sender submits a task and then closes the stream, or the sender assumes the task will close it while the task lacks a `finally` block. Make the handoff a one-way, testable contract documented in the API.

## 14. Testing Ownership, Lifetime, and Failure Paths

### 14.1. Testing per-operation leases

With `SharedClient` in the example:

~~~text
Client OPEN, active=0
borrow()                -> active=1
lease.execute()         -> succeeds
lease.close()           -> active=0
second lease.close()    -> still active=0
client.isClosed()       -> false
context.close()         -> client.isClosed() == true
~~~

This is the **expected behavior** of the example implementation, not a framework API that prints these lines automatically.

### 14.2. Testing premature close

Intentionally close the owner before borrowing:
- `borrow` must reject the request.
- No further leases may be granted after `CLOSE`.
- No operation may use an already closed owner.

In multithreaded applications, close and borrow must be coordinated atomically to avoid a "check open → context close → create lease" race. The demo uses `synchronized` on `borrow`, `release`, and `close` to keep state consistent.

### 14.3. Testing resource leaks

Borrow a lease without closing it, then attempt to close the owner. The demo reports an error because an active lease still remains. In production, you need leak detection and a policy: wait for drain, set a deadline, warn, and force-close when necessary—without ignoring ownership ambiguity.

### 14.4. Testing errors mid-operation

Make `lease.execute()` throw an exception. With `try-with-resources`, `lease.close()` still runs and returns the handle. Verify both the lease state and the active counter after the error, not only the exception message.

### 14.5. Testing partial startup failure

A factory opens resource A, and step B fails. Verify that A is closed on the error path, even though the bean was never successfully registered to receive a destruction callback from Spring.

### 14.6. Testing multiple contexts

Create and close two contexts independently. Verify that each context owns its own resources and does not accidentally close an external resource shared across contexts. Do not use a mutable static singleton as an owner without an explicit handoff protocol.

### 14.7. Testing shutdown with remaining tasks

While a consumer is processing messages:
- Stop accepting new tasks.
- Wait for in-flight tasks within an appropriate bound.
- Return/close any remaining active leases.
- Finally, close the pool/client owner.
- Timeouts must have a clear policy and be recorded.

### 14.8. Testing forced termination

Simulate killing the process: Java callbacks may not run. External resources such as distributed locks, cloud leases, and message deliveries need independent TTLs or retry/recovery mechanisms.

## 15. Checklist When Designing a New Resource

For code reviews, answer each question:

1. **What is the resource?** The underlying client/pool or just a lease/handle?
2. **Who creates it?** Constructor, `@Bean`, factory, library, transaction manager, or external system?
3. **Who owns it?** Spring context, bean, operation, task, request, or external service?
4. **Who borrows it?** How many concurrent borrowers exist? May borrowers close the owner?
5. **When does its lifetime start?** Context refresh, borrow call, request start, or subscription?
6. **When does its lifetime end?** End-of-block, completion, cancellation, session end, or context close?
7. **What is the cleanup trigger?** `try-with-resources`, `AutoCloseable`, `@PreDestroy`, `SmartLifecycle`, or lease expiry?
8. **Can the resource be partially created and fail?** Where is rollback handled?
9. **What if close is called twice?** Is it idempotent? Could callbacks be dropped?
10. **What if close races with borrow?** Is there a lock/state machine preventing operations after close?
11. **What if async work outlives the method?** Who retains and ultimately returns the resource?
12. **What if shutdown is forced?** Are there external TTLs, deadlines, recovery, or retries?
13. **Are resource counts and timings tested?** Do tests cover success, error, cancel, timeout, and concurrent calls?
14. **Is sensitive information logged?** Never log credentials or tokens in resource lifecycle logs.
15. **Is the contract documented in the API?** For example, "caller must close response" or "client managed by Spring."

A good design lets anyone reading the code identify the owner and closing point **without guessing**.

## 16. Review Questions

**Question 1:** Does a service injected with a singleton `DataSource` have the right to close the pool after a request?

**Answer:** No, unless that service was explicitly granted ownership of the pool. A service typically only borrows the API, while the bean/auto-configuration manages the pool's lifetime.

**Question 2:** Who closes a JDBC `Connection` borrowed from a pool inside a method that does not use a Spring transaction abstraction?

**Answer:** The caller must release the handle promptly, usually via `try-with-resources`. Closing a connection handle from a pool typically returns the lease to the pool rather than closing the pool.

**Question 3:** Will Spring automatically invoke `@PreDestroy` on a prototype bean when the context closes?

**Answer:** You cannot rely on that. Spring does not manage the destruction of individual prototypes after handoff; the caller needs separate cleanup.

**Question 4:** If a singleton bean has a public `close` method and is declared with `@Bean` without specifying `destroyMethod`, can Spring close it automatically?

**Answer:** Yes. Java config `@Bean` by default infers public `close`/`shutdown` as a destroy method. If it is a borrowed external object, pay attention and adjust the contract.

**Question 5:** Why is wrapping an `InputStream` in `try-with-resources` and then submitting a task that uses that stream dangerous?

**Answer:** The caller's block can exit before the task uses the stream, causing the stream to be closed prematurely. The lifetime must follow the task or the caller must wait for completion.

**Question 6:** Does a client pool living with `ApplicationContext` mean every `Connection` must live with the context?

**Answer:** No. The pool is the long-lived owner, while each connection lease has a short lifetime scoped to an operation/transaction.

**Question 7:** If startup partially creates a resource and then fails, can you wait for `@PreDestroy` to clean it up automatically?

**Answer:** No. The bean may not have been created successfully, so its destroy callback is not registered. The factory/owner must roll back partial resources.

**Question 8:** When the context closes, should you close the consumer or the pool the consumer needs first?

**Answer:** Typically stop the consumer and wait for in-flight work first, then close the pool. Use lifecycle phases, dependencies, and graceful shutdown to coordinate.

**Question 9:** Is a Spring singleton a single JVM-wide object?

**Answer:** No. A singleton is scoped to a container/bean definition; multiple contexts can create multiple distinct singletons.

**Question 10:** Why is closing the context not guaranteed to release external system resources?

**Answer:** JVM crashes, `SIGKILL`, or network errors can bypass callbacks. External resources need separate lease/TTL/retry/recovery mechanisms.

## 17. Hands-On Exercises

**Exercise A — ownership table:** List `DataSource`, JDBC `Connection`, HTTP client, HTTP response body, `InputStream`, `ExecutorService`, and Kafka consumer in your project. Fill in creator, owner, borrower, lifetime, close trigger, and failure cleanup for each type.

**Exercise B — idempotent lease:** Run the Section 7 demo. Call `lease.close()` twice in the same operation and verify `activeLeases` does not drop below 0. Explain why closing a lease does not affect `SharedClient.isClosed()`.

**Exercise C — lease leak:** Intentionally hold onto a `Lease` until context close. Observe the owner refusing to close while an active lease remains. Propose a drain mechanism with a deadline for production.

**Exercise D — prototype resource:** Create a prototype bean holding an `AutoCloseable` handle, obtain an instance with `ObjectProvider`, and close it from the caller. Verify that Spring does not automatically guarantee destruction for a handed-off prototype.

**Exercise E — asynchronous lifetime:** Move file reading into a `CompletableFuture`. Intentionally close the stream prematurely, then fix it by letting the task open and close the stream itself. Test normal, exceptional, and cancellation paths.

**Exercise F — borrowed bean:** Simulate a client created outside Spring and registered with `@Bean`. Compare default destroy inference with `@Bean(destroyMethod = "")`. Explain why additional ownership rules are needed if the object has other destroy callbacks.

**Exercise G — graceful shutdown:** Create a `SmartLifecycle` worker that borrows `SharedClient`. Choose a phase so the worker stops/drains before the client bean is destroyed; use a timeout and check the active lease count at close time.

## 18. Official References

- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html): singleton, prototype, web scopes, and prototype destruction.
- [Spring Framework — Bean Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): `@PostConstruct`, `@PreDestroy`, `DisposableBean`, `SmartLifecycle`, inferred close/shutdown.
- [Spring Framework — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html): `destroyMethod` and how Spring manages beans from Java configuration.
- [Spring Boot 3.5 — SpringApplication](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): `ApplicationContext`, shutdown hook, and application events.
- [Spring Boot 3.5.16 — SpringApplication Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html): context creation and shutdown hook.
- [Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): `try-with-resources`, close, and suppressed exceptions.

### Final Takeaways

1. **Every resource needs a clear owner.** Creator and user are not necessarily the owner.
2. **The owner closes the underlying resource; the borrower only returns the lease/handle.** Never close a shared pool inside a single request.
3. **Lifetime must match usage scope**, rather than simply matching a single annotation scope.
4. **Context-owned Spring singletons** typically have destruction callbacks; **handed-off prototypes are not automatically destroyed by Spring**.
5. **`@Bean` has inferred close/shutdown**; for borrowed external objects, avoid unintentionally handing over close authority.
6. **`try-with-resources`** is for per-operation resources; **bean destroy/`SmartLifecycle`** is for long-lived resources and background activity.
7. **On failure paths, clean up partially opened resources** before rethrowing; do not wait for the context to destroy a bean that was never created.
8. **Async work needs a lifetime tied to the task/stream/subscription**, not to the returning method.
9. **Shutdown must stop borrowers before closing owners**, with timeouts and policies for forced termination.
10. **Ownership is a testable contract**: who may close, when, active handle counts, and behavior under repeated/concurrent calls.
