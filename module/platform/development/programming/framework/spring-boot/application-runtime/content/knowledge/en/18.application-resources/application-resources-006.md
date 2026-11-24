# Releasing Resources When Initialization Only Partially Completes

## Learning Objectives

An application component can **partially initialize and then fail**: it opened a connection but creating the subscription failed; it opened a file but the parse step threw an exception; it created a thread pool but registering a worker failed; it allocated a cache but configuration validation failed. That is *partial initialization*. If you merely wait until Spring shuts down the application to invoke `@PreDestroy`, resources created before the bean finished initializing risk never being released.

In Spring Boot Application Runtime, under the **Application Resources** group, the core challenge is managing **resource ownership** at every stage—especially when a constructor, `@Bean` factory, `@PostConstruct`, `InitializingBean`, or `SmartLifecycle.start()` can fail.

After this lesson, you will be able to:

1. Identify precisely which resources are already open when initialization throws an exception.
2. Distinguish **cleanup on a failed initialization path** from **destroy callbacks on a successfully created bean**.
3. Use `try/catch`, `finally`, `try-with-resources`, and `Throwable.addSuppressed(...)` to clean up resources safely.
4. Close resources in **reverse opening order** without letting cleanup errors mask the original error.
5. Design **ownership transfer** from factory to managed bean **only once all initialization has succeeded**.
6. Use `@Bean(destroyMethod = "close")` and `@PreDestroy` within their proper scope, without relying on them when a factory has not returned the bean or an init method has not completed.
7. Run a **Java 17+ / Spring Boot 3.3.13 / Gradle** project across three scenarios: success, failure after the first resource, and failure after the second resource.
8. Design rollback for constructors, bean initialization, `SmartLifecycle.start()`, runners, and off-JVM resources; verify via failure injection.

**Version scope:** Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+. The example uses Spring Boot 3.3.13. Do not equate callbacks closing a **bootstrap context** during startup with the **application context** closing at shutdown.

## 1. What Is Partial Initialization?

Suppose a client requires three steps:

~~~text
createClient()
    |
    +-- openConnection()             [SUCCEEDED]
    |
    +-- registerSubscription()       [SUCCEEDED]
    |
    +-- verifyCredentials()          [FAILED]
    |
    +-- return client                [NOT EXECUTED]
~~~

When credential verification fails, the program does not have a successfully created client, yet two resources—**connection** and **subscription**—already exist. Leaving them open is a leak; closing the connection while forgetting to cancel the subscription can also leave unwanted state.

**Principle:** Every step that successfully opens a resource must be paired with a plan to close that resource if any subsequent step fails.

### Resources easily left behind

| Resource | Partial Initialization Example | Consequence |
| --- | --- | --- |
| `InputStream`, `FileChannel` | File A reads fine, file B fails | File descriptor/lock remains held |
| `Socket`/HTTP client | Socket opens, TLS configuration fails | Socket or internal workers stay alive |
| JDBC connection | Borrow connection, then statement creation fails | Connection leaked in pool |
| Executors and threads | Pool created, then job registration fails | Hanging threads or JVM fails to exit |
| Message consumer | Subscribed, then handler creation fails | Bad poll/ack or orphaned listener |
| Temporary file | Staging file created, then write fails | Junk files, wasted disk, or data exposure |
| Timers, callbacks | Listener registered, then later init fails | Callbacks still fire on an incomplete object |
| Remote lease/resource | Create API succeeds, then confirm step fails | External resource does not vanish automatically |

Different resource categories roll back differently. Sockets can be closed with `close()`; remote records require delete/compensate APIs; background tasks may need stop signals, cancellation, and bounded joins. No single generic `close()` call handles every situation.

## 2. Ownership: Who Is Responsible at Each Moment?

Picture a factory creating a bean:

~~~text
Factory starts create()
    |
    +-- Open resource A   (factory owns it)
    +-- Open resource B   (factory owns it)
    +-- Check invariants
          |
          +-- FAILURE
          |     └-- Factory closes B, closes A, rethrows original error
          |
          +-- SUCCESS
                |
                └-- Return managed bean and transfer ownership
                      |
                      +-- Bean used normally
                      |
                      └-- When Spring destroys bean: bean.close()
~~~

There are two independent cleanup paths:

- **Rollback during initialization:** the factory or init method that opened resources must clean them up itself if it cannot finish.
- **Normal destruction:** a created, Spring-managed bean is cleaned up when the context closes or the bean is destroyed per its lifecycle.

The point of **committing ownership** is typically when the factory returns the complete object, after validating all required conditions the factory is responsible for. If `@PostConstruct`/a `BeanPostProcessor` outside the factory can still fail afterward, that phase also needs a cleanup strategy for its own resources.

### Two opposite mistakes

**Resource leak:** The factory assumes Spring will clean up the connection even though the `@Bean` factory throws before returning an object to the container.

**Closing too early:** The factory wraps a connection in `try-with-resources` and returns an object holding that connection; when the scope exits, the connection is already closed before the caller uses it.

Therefore, the same resource **must not simultaneously "transfer ownership" and "auto-close" in the old scope**, unless there is an explicit shared reference/lease design.

## 3. Constructor, @Bean, @PostConstruct, and @PreDestroy Are Not One Milestone

For a normal Spring bean, the conceptual steps are:

~~~text
Spring selects bean definition
    |
    +-- Constructor or @Bean factory method
    +-- Resolve dependencies and injection
    +-- BeanPostProcessor before initialization
    |    └-- @PostConstruct (when matching processor is present)
    +-- InitializingBean.afterPropertiesSet()
    +-- Custom init method (if present)
    +-- BeanPostProcessor after initialization
    |
    +-- Bean finishes creation / usable
    |
    +-- Normal destruction when context closes
         ├-- @PreDestroy
         ├-- DisposableBean.destroy()
         └-- Custom destroy method (if present)
~~~

This is a simplified diagram and does not cover every `FactoryBean`, proxy, or scope. Key point: **returning from a constructor does not mean bean initialization is finished**; `@PostConstruct` can still fail.

Spring Framework supports destruction callbacks for beans it manages, yet **you must not treat the destroy callback of a bean that failed initialization as a guarantee to release every resource it opened prior to failing**.

### Example prone to leaking

~~~java
@Component
class DangerousSubscriber {

    private Socket socket;

    @PostConstruct
    void initialize() throws IOException {
        socket = new Socket("localhost", 8080);
        configureProtocol(socket); // may throw
    }

    @PreDestroy
    void destroy() throws IOException {
        if (socket != null) {
            socket.close();
        }
    }
}
~~~

This is a **problem-illustrating snippet**, not a standalone file: it requires imports for `Component`, `PostConstruct`, `PreDestroy`, `Socket`, `IOException`, and a definition of `configureProtocol`. If `configureProtocol` fails, the bean has not completed initialization. Even with `@PreDestroy` present, the right design is **closing the socket immediately in the init method's catch block**.

### Safer init pattern

~~~java
@PostConstruct
void initialize() throws IOException {
    Socket newlyOpened = new Socket("localhost", 8080);

    try {
        configureProtocol(newlyOpened);
        socket = newlyOpened; // Only publish state on success.
    }
    catch (IOException | RuntimeException original) {
        try {
            newlyOpened.close();
        }
        catch (IOException closeFailure) {
            original.addSuppressed(closeFailure);
        }
        throw original;
    }
}
~~~

This is an **illustrative method** inside a class with a `socket` field and `configureProtocol` method. If `configureProtocol` created additional internal resources and then threw before returning their handles, cleaning up those internal resources belongs to `configureProtocol` itself. The caller cannot close a handle it never received.

## 4. Why Is @Bean(destroyMethod = "close") Not Enough?

A method:

~~~java
@Bean(destroyMethod = "close")
ExternalClient externalClient() {
    return new ExternalClient();
}
~~~

tells Spring to call `close()` when destroying **a bean created and managed successfully**. However, if the factory performs multiple steps before `return`:

~~~java
@Bean(destroyMethod = "close")
ExternalClient externalClient() {
    Connection connection = openConnection();
    Subscription subscription =
            openSubscription(connection); // may throw
    return new ExternalClient(connection, subscription);
}
~~~

then when `openSubscription` throws, the container never receives a complete `ExternalClient` object. There is no guarantee Spring will close a connection held only in a factory's local variable.

**Right approach:** Record each handle as soon as it opens successfully, wrap subsequent steps in `try/catch`, and clean up existing handles before rethrowing the exception.

~~~java
@Bean(destroyMethod = "close")
ExternalClient externalClient() {
    Connection connection = openConnection();
    Subscription subscription = null;

    try {
        subscription = openSubscription(connection);
        validate(subscription);
        return new ExternalClient(connection, subscription);
    }
    catch (RuntimeException original) {
        closeSuppressing(subscription, original);
        closeSuppressing(connection, original);
        throw original;
    }
}
~~~

This is an **illustration**, lacking definitions for `Connection`/`Subscription`/`ExternalClient`/`closeSuppressing`. The complete example in Section 9 uses real fake resources with `close()` to demonstrate both failure points.

**Note on constructors:** If the `new ExternalClient(connection, subscription)` constructor also performs fail-prone I/O, ownership becomes ambiguous. Better to have the constructor simply assign already-validated fields; perform every failable step **before transferring ownership**.

## 5. Cleanup Order Should Reverse Initialization Order

Dependency example:

~~~text
open connection
    └-- open session using connection
          └-- open consumer using session
~~~

When rolling back:

~~~text
close consumer
close session
close connection
~~~

The consumer may need the session to flush/ack, and the session may need the connection to finish transactions. Closing the connection first can break the consumer's cleanup. Even for independent resources, defining a clear order keeps code predictable.

### Cleanup failures must not hide the original error

Anti-pattern:

~~~java
try {
    initializeSecondaryResource();
}
finally {
    primaryResource.close(); // If close also throws, it can mask the init error.
}
~~~

In Java, an error thrown inside `finally` can overwrite an exception propagating outward. A safe manual pattern:

~~~java
try {
    initializeSecondaryResource();
}
catch (Exception original) {
    try {
        primaryResource.close();
    }
    catch (Exception closeFailure) {
        if (closeFailure != original) {
            original.addSuppressed(closeFailure);
        }
    }
    throw original;
}
~~~

This is **code inside a method declaring `throws Exception`**, assuming `primaryResource` is `AutoCloseable`. `Throwable.addSuppressed(...)` preserves cleanup errors in `getSuppressed()` while the original exception remains the primary cause.

### Reusable cleanup helper for multiple resources

~~~java
static void closeOnFailure(
        AutoCloseable resource, Throwable original) {

    if (resource == null) {
        return;
    }

    try {
        resource.close();
    }
    catch (Exception | Error cleanupFailure) {
        if (cleanupFailure != original) {
            original.addSuppressed(cleanupFailure);
        }
    }
}
~~~

This illustrative helper can live in the factory class. Ensure you **still attempt to close remaining resources** even if one `close` throws.

Keeping `Error` in the multi-catch illustrates cleanup even when a severe error occurs during initialization. For `VirtualMachineError`s such as OOM, the JVM may not be in a state to clean up reliably; do not promise every resource is cleaned up under every VM error condition.

## 6. try-with-resources: Use the Right Lifetime Scope

`try-with-resources` is a great choice when a resource is only needed **within a single method or block**:

~~~java
try (InputStream in = Files.newInputStream(path)) {
    byte[] bytes = in.readAllBytes();
    return decode(bytes);
}
~~~

This is a **snippet** needing imports for `InputStream`, `Files`, `Path`, and a `decode` method. Java automatically closes `in` upon exiting the block, even if reading or decoding fails. With multiple resources in the header, Java closes them in **reverse declaration order** and preserves the body exception as primary if `close` also throws.

### Ownership transfer trap

~~~java
Client createClient() throws IOException {
    try (Socket socket = new Socket("localhost", 8080)) {
        return new Client(socket); // WRONG if Client still needs socket.
    }
}
~~~

This is an **anti-pattern**; it requires a `Client` definition and imports. `return` does not stop `try-with-resources` from running cleanup. By the time the method returns, the socket is already closed.

If the resource must live alongside a Spring bean, you need a **factory that rolls back on failure**, then transfers ownership to the complete bean with a configured destroy callback. Do not use a scope shorter than the resource's real lifetime.

### When only part of the resources belong to the bean

A factory may open a configuration file to read data and close the file, while storing the parsed result inside the bean. Here the file stream **does not transfer ownership**; `try-with-resources` fits well. Conversely, a network connection kept for runtime processing is a long-lived resource and should close at bean destruction.

## 7. Do Not Publish Incomplete Objects

A partially initialized object not only leaks resources, it can also cause concurrency bugs if published too early.

~~~java
class UnsafeClient {
    UnsafeClient() {
        GlobalRegistry.register(this);
        openSocket();
        subscribeToEvents(); // may fail
    }
}
~~~

This is an illustrative snippet missing helper definitions. If subscribing fails, the registry may hold an invalid object, and another thread may invoke its methods.

How to prevent this:

1. Never pass `this` into registries or worker threads from a constructor before invariants are established.
2. Open resources in local variables, validate all conditions, and only then return the object and publish it to the system.
3. If listeners or timers were registered prior to failing, **unregister/cancel** them via the proper API.
4. If threads were started, issue a stop signal and interrupt/join with a deadline; do not treat flipping a boolean as proof a thread has stopped.
5. For objects used across multiple threads, design safe publication and state transitions rather than relying arbitrarily on `final` fields or `volatile`.

**Distinction to keep in mind:** a Spring bean succeeding at Java instantiation does not mean it satisfies business readiness. After the factory returns, `@PostConstruct`, `BeanPostProcessor`s, or a start step can still mutate state. Every point with side effects needs a corresponding rollback path.

## 8. Checklist Before Writing a Multi-Step Factory

| Question | Meaning |
| --- | --- |
| Which step opens the socket/file/connection/thread? | Identify acquisition points |
| Where is each handle returned and stored? | Ensure a way to close if a later step fails |
| Does resource B need A in order to close? | Determine reverse cleanup order |
| Which exceptions can occur at each step? | Design `catch`/`throws` properly |
| Can `close` itself throw? | Do not let cleanup mask init errors |
| When does ownership transfer to the bean? | Neither close too early nor forget to close |
| By which mechanism is the bean destroyed? | `@PreDestroy`, `destroyMethod`, lifecycle |
| Do init callbacks run after factory return? | Do not overlook `@PostConstruct` failures |
| Is any state published before success? | Avoid exposing half-built objects |
| What if `close` is called twice? | Idempotency/state machine |
| What if init is retried? | Do not retain connections/threads from failed attempts |
| What if the JVM is killed? | External TTL, recovery, reconciliation |

For complex multi-step logic, use a **builder/rollback stack** or a dedicated resource-owning component rather than scattering `close()` calls across many `if` branches.

## 9. Runnable Project: Spring Boot Closing Resources on Success and Partial Failure Paths

This project uses **Java 17+**, **Spring Boot 3.3.13**, and Gradle as a **non-web** CLI application. We create a `ManagedPipeline` bean needing two simulated resources:

1. `connection`.
2. `subscription` built on top of `connection`.

There are three modes:

- `--demo.fail-at=none`: opens both successfully; Spring calls `ManagedPipeline.close()` when the context closes.
- `--demo.fail-at=connection`: fails right after opening `connection`, before opening `subscription`; the factory closes `connection` itself.
- `--demo.fail-at=subscription`: fails after both are open; the factory closes `subscription` and then `connection`.

Because the resources only print logs and do not touch real networking, there is no random timing or external I/O race. Each case produces an explainable and testable log order.

### 9.1. Directory structure

~~~text
partial-resource-cleanup-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/cleanup/
    └── PartialResourceApplication.java
~~~

**`settings.gradle`:**

~~~groovy
rootProject.name = 'partial-resource-cleanup-demo'
~~~

**`build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.cleanup.PartialResourceApplication'
}
~~~

Requires JDK 17+ and a Gradle version compatible with Spring Boot 3.3. If you have a Gradle Wrapper, you can use the wrapper instead of `gradle`. The sample omits a generated wrapper and does not need `spring-boot-starter-web`.

### 9.2. Full Java source

**`src/main/java/com/example/cleanup/PartialResourceApplication.java`:**

~~~java
package com.example.cleanup;

import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class PartialResourceApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(PartialResourceApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("MAIN: context started");
        }
        catch (RuntimeException failure) {
            System.out.println("MAIN: startup failed");
            // Do not swallow the error as a successful startup.
            throw failure;
        }

        System.out.println("MAIN: context closed");
    }

    @Bean(destroyMethod = "close")
    ManagedPipeline managedPipeline(
            @Value("${demo.fail-at:none}") String failAt) {

        return ManagedPipeline.create(failAt);
    }

    public static final class ManagedPipeline
            implements AutoCloseable {

        private final TrackedResource connection;
        private final TrackedResource subscription;
        private final AtomicBoolean closed = new AtomicBoolean();

        private ManagedPipeline(
                TrackedResource connection,
                TrackedResource subscription) {
            this.connection = connection;
            this.subscription = subscription;
        }

        public static ManagedPipeline create(String failAt) {
            // Validate before opening resources.
            if (!Set.of("none", "connection", "subscription")
                    .contains(failAt)) {
                throw new IllegalArgumentException(
                        "Unknown demo.fail-at: " + failAt);
            }

            TrackedResource connection = null;
            TrackedResource subscription = null;

            try {
                connection = TrackedResource.open("connection");

                if ("connection".equals(failAt)) {
                    System.out.println(
                            "INIT: failure after connection");
                    throw new IllegalStateException(
                            "Simulated connection-stage failure");
                }

                subscription = TrackedResource.open("subscription");

                if ("subscription".equals(failAt)) {
                    System.out.println(
                            "INIT: failure after subscription");
                    throw new IllegalStateException(
                            "Simulated subscription-stage failure");
                }

                System.out.println("INIT: completed");

                // Ownership transfers only after all steps succeed.
                return new ManagedPipeline(connection, subscription);
            }
            catch (RuntimeException | Error original) {
                closeOnFailure(subscription, original);
                closeOnFailure(connection, original);
                throw original;
            }
        }

        private static void closeOnFailure(
                AutoCloseable resource, Throwable original) {

            if (resource == null) {
                return;
            }

            try {
                resource.close();
            }
            catch (Exception | Error cleanupFailure) {
                if (cleanupFailure != original) {
                    original.addSuppressed(cleanupFailure);
                }
            }
        }

        @Override
        public void close() {
            if (!closed.compareAndSet(false, true)) {
                return;
            }

            // Simulated resources do not throw in close().
            try {
                subscription.close();
            }
            finally {
                connection.close();
            }
        }
    }

    public static final class TrackedResource
            implements AutoCloseable {

        private final String name;
        private final AtomicBoolean closed = new AtomicBoolean();

        private TrackedResource(String name) {
            this.name = name;
            System.out.println("RESOURCE: " + name + " opened");
        }

        public static TrackedResource open(String name) {
            return new TrackedResource(name);
        }

        @Override
        public void close() {
            if (closed.compareAndSet(false, true)) {
                System.out.println("RESOURCE: " + name + " closed");
            }
        }
    }
}
~~~

### 9.3. Why does this code not leak resources in the demo scenarios?

**At the factory:**

- `ManagedPipeline.create` validates the mode before opening any resource.
- `connection` is opened and assigned to a local variable. If the next step fails, the factory still has the handle to close it.
- `subscription` is opened next and also assigned to a local variable.
- If validation fails after `subscription`, `catch` closes `subscription` **before** `connection`.
- `closeOnFailure` prevents cleanup errors from replacing the original error; it uses `addSuppressed`.
- Only after creating both resources does the factory return `ManagedPipeline` holding two final fields. From that moment on, the bean owns the resources.

**At Spring:**

- `@Bean(destroyMethod = "close")` lets Spring call `ManagedPipeline.close()` once the bean is created successfully and the context shuts down normally.
- If the factory throws before `return`, the factory itself already cleaned up; it does not rely on a destruction callback for a bean that does not exist yet.
- `AtomicBoolean` in the demo ensures `close` prints only once if called repeatedly. This is a simple form of idempotency; production code may need an explicit state machine when cleanup itself can fail.

**At main:**

- The non-web program uses `try-with-resources` on **the application context**, without closing connections directly.
- When startup fails, `app.run(args)` throws an exception; code prints `MAIN: startup failed` and rethrows. The Gradle command may exit non-zero.
- When startup succeeds, the context closes upon exiting `try`, causing Spring to invoke the destroy method.

### 9.4. Successful run

~~~bash
gradle bootRun --args="--demo.fail-at=none"
~~~

**Lines printed by the Java code itself**, ignoring Spring/Gradle logs:

~~~text
RESOURCE: connection opened
RESOURCE: subscription opened
INIT: completed
MAIN: context started
RESOURCE: subscription closed
RESOURCE: connection closed
MAIN: context closed
~~~

Explanation:

1. Singleton bean `managedPipeline` is eagerly created during `ApplicationContext.refresh()`.
2. The factory opens `connection` then `subscription` and prints `INIT: completed`.
3. `SpringApplication.run(...)` returns, and `main` prints context started.
4. `try-with-resources` closes the context. Spring calls `ManagedPipeline.close()`, closing `subscription` and then `connection`.
5. `main` prints context closed after `context.close` finishes.

### 9.5. Failure after the first resource

~~~bash
gradle bootRun --args="--demo.fail-at=connection"
~~~

Lines printed by the Java code itself:

~~~text
RESOURCE: connection opened
INIT: failure after connection
RESOURCE: connection closed
MAIN: startup failed
~~~

There is no `subscription` because the second opening step never ran. There is no `MAIN: context started` because startup did not complete. Spring/Gradle may print additional stack traces and build failure messages. **The connection is closed inside the factory's catch block**, not by a destroy method on a complete bean.

### 9.6. Failure after the second resource

~~~bash
gradle bootRun --args="--demo.fail-at=subscription"
~~~

Lines printed by the Java code itself:

~~~text
RESOURCE: connection opened
RESOURCE: subscription opened
INIT: failure after subscription
RESOURCE: subscription closed
RESOURCE: connection closed
MAIN: startup failed
~~~

The factory closes both resources in reverse opening order. Notice each resource has exactly one closed line. This proves that **having opened both resources does not mean initialization was committed**.

### 9.7. Invalid input

~~~bash
gradle bootRun --args="--demo.fail-at=unknown"
~~~

Validation throws `IllegalArgumentException` **before** opening `connection`. Hence no `RESOURCE: ... opened` lines appear. In `main`, `MAIN: startup failed` prints and then the exception is rethrown.

### 9.8. Never open resources and ignore errors

Changing `catch` to:

~~~java
catch (RuntimeException original) {
    System.err.println("Ignored: " + original.getMessage());
    return new ManagedPipeline(connection, subscription);
}
~~~

is an **anti-pattern**, not a valid modification to the project: `subscription` may be `null`; the returned object will be in an invalid state and prone to delayed failures. Preserve the exception unless there is a **complete, pre-designed fallback**.

## 10. Error Paths in @PostConstruct

In the full example, both resources are opened inside the `@Bean` factory. However, a bean may be constructed first and open resources inside `@PostConstruct`.

Meaningful pattern:

~~~java
@Component
class ConfiguredClient {

    private AutoCloseable connection;
    private AutoCloseable consumer;

    @PostConstruct
    void init() throws Exception {

        AutoCloseable newConnection = null;
        AutoCloseable newConsumer = null;

        try {
            newConnection = openConnection();
            newConsumer = openConsumer(newConnection);
            verify(newConsumer);

            connection = newConnection;
            consumer = newConsumer;
        }
        catch (Exception | Error original) {
            closeOnFailure(newConsumer, original);
            closeOnFailure(newConnection, original);
            throw original;
        }
    }

    @PreDestroy
    void destroy() throws Exception {
        // Close consumer then connection on the normal destruction path.
    }
}
~~~

This is a **non-standalone illustrative snippet**: helpers `openConnection`, `openConsumer`, `verify`, `closeOnFailure`, and the normal cleanup body must be defined for the real system; imports `Component`, `PostConstruct`, and `PreDestroy` are also needed.

Key takeaways:

- Local resources **are owned by the init method** until `verify` succeeds.
- On error, the init method cleans up immediately without waiting for Spring to call destroy.
- On success, fields are assigned; later bean destruction can use those fields.
- If setup opens internal resources inside a helper and throws **before returning the handle**, the helper is responsible for internal cleanup.

When bean init fails, never rely on the assumption that `@PreDestroy` on that bean will definitely run. Spring may clean up other beans that succeeded, but the init method's duty toward the resources it just opened does not change.

## 11. When a Constructor Throws an Exception

A failing constructor returns no reference to a complete object:

~~~java
class BadClient {
    private final Socket socket;

    BadClient() throws IOException {
        socket = new Socket("localhost", 8080);
        verifyServer(socket); // if this throws, no BadClient is returned
    }
}
~~~

This is an anti-pattern snippet requiring imports/helpers. The caller has no `BadClient` to `close()` if the constructor fails to complete. Opened resources may stay alive.

**Better design:** Have constructors only accept already-verified resources and assign final fields; use static factories/builders to acquire, validate, and roll back. If a constructor itself can still throw, the factory or constructor must capture handles and clean up per the ownership contract.

### Avoiding `this` escape before the constructor finishes

If a constructor registers `this` into a global registry or starts a thread holding a reference to the object before initialization finishes, an init failure can leave a "ghost" object alive in another thread. Unregister/stop on the failure path, or never publish `this` before success.

## 12. SmartLifecycle.start() Failure

`SmartLifecycle` is another hook: a bean may already be created and initialized, yet `start()` opens a connection and then fails while subscribing.

~~~java
@Override
public void start() {
    channel.open();
    consumer.subscribe(); // throws
    running = true;
}
~~~

The snippet above **does not roll back automatically**. If `subscribe()` throws, `running` stays false while `channel` may remain open.

Safer pattern:

~~~java
@Override
public void start() {
    if (running) {
        return;
    }

    try {
        channel.open();
        consumer.subscribe();
        running = true;
    }
    catch (RuntimeException | Error original) {
        try {
            consumer.unsubscribeIfNecessary();
        }
        catch (RuntimeException cleanupFailure) {
            original.addSuppressed(cleanupFailure);
        }
        try {
            channel.closeIfOpen();
        }
        catch (RuntimeException cleanupFailure) {
            original.addSuppressed(cleanupFailure);
        }
        running = false;
        throw original;
    }
}
~~~

This snippet requires types with `unsubscribeIfNecessary()`, `closeIfOpen()`, and a `running` field. It illustrates **immediate rollback inside `start()`**. Do not rely on `stop(Runnable)` being invoked later by the framework to clean up a failed partial startup.

If `start()` merely submits an async task and returns, errors occurring **inside the other thread** are not caught by the caller thread's `try/catch`. You then need a `Future`/completion stage, startup barrier, cancellation, timeouts, and separate close handling. `running=true` must not mean "connection ready" just because the task was submitted.

## 13. Failing Runners Must Also Clean Up Resources They Opened

`ApplicationRunner`/`CommandLineRunner` executes **after context refresh**, before `ApplicationReadyEvent`. A runner may open a file to import data and throw an exception while parsing.

Anti-pattern:

~~~java
@Bean
ApplicationRunner importData() {
    return args -> {
        InputStream stream = Files.newInputStream(path);
        parse(stream); // throws
        stream.close(); // may not run
    };
}
~~~

This is a non-standalone snippet requiring `path` and `parse`. If `parse` throws, the stream is never closed.

Appropriate pattern when the stream **lives only within the runner**:

~~~java
@Bean
ApplicationRunner importData() {
    return args -> {
        try (InputStream stream = Files.newInputStream(path)) {
            parse(stream);
        }
    };
}
~~~

If the runner fails, Spring Boot may publish `ApplicationFailedEvent` and clean up the context, yet streams opened independently by the runner must still be cleaned up by the runner. A resource that must survive **after** the runner should not be closed when the runner returns; transfer ownership to a longer-lived component.

## 14. Rollback Stack for Multi-Step Acquisition

When there are more than two resources, a stack of cleanup actions helps avoid missing any:

~~~java
Deque<AutoCloseable> rollback = new ArrayDeque<>();

try {
    Resource a = openA();
    rollback.push(a);

    Resource b = openB(a);
    rollback.push(b);

    Resource c = openC(b);
    rollback.push(c);

    return new ManagedGroup(a, b, c);
}
catch (Exception | Error original) {
    while (!rollback.isEmpty()) {
        try {
            rollback.pop().close();
        }
        catch (Exception | Error cleanupFailure) {
            if (cleanupFailure != original) {
                original.addSuppressed(cleanupFailure);
            }
        }
    }
    throw original;
}
~~~

This is an **illustration** requiring `Deque`, `ArrayDeque`, `Resource`/`ManagedGroup` types, `openA/B/C` helpers, and an enclosing method signature.

`Deque.push(...)` records each resource right after acquisition succeeds, and `pop()` cleans up in **LIFO** order. On the success path, **transfer ownership** to `ManagedGroup` and **do not drain the stack** in `finally`. If you return an object on success while `finally` still closes every handle, the caller receives already closed resources.

### When rollback is compensation rather than close

Some steps produce side effects:

- Registering a listener → requires `unregister`.
- Creating a scheduled task → requires `cancel` and possibly waiting for task exit.
- Creating a remote subscription → requires an unsubscribe API.
- Creating a temporary file → requires delete if still locally owned.
- Creating a cloud resource → requires compensating delete or reconciliation.

These actions must be pushed onto the rollback stack/compensation log **after the corresponding step succeeds**. A remote API timeout can leave uncertain state; sometimes you must query by request ID/idempotency key before concluding whether the resource exists.

## 15. Preserving the Root Cause and Suppressed Exceptions

Suppose initialization fails due to TLS configuration, and closing the connection also raises an `IOException`. Catching the exception and throwing the cleanup error can make logs show only "close failed" while losing "certificate invalid."

Use:

~~~java
catch (Exception original) {
    try {
        resource.close();
    }
    catch (Exception closeFailure) {
        original.addSuppressed(closeFailure);
    }
    throw original;
}
~~~

On exception paths, standard loggers print both `Caused by` and `Suppressed`. Never log only `getMessage()` and drop suppressed errors in production telemetry.

### If cleaning up multiple resources throws repeatedly

Attempt to clean up **all** resources; do not stop after the first failing resource. The `closeOnFailure` helper in the Section 9 project does this. On **normal shutdown**, you can use `try-with-resources` or a close aggregator to preserve the first error and attach subsequent ones as suppressed while still attempting to close every resource.

### Never swallow critical errors

If an essential component fails to initialize, catching the exception and returning a half-baked bean so Spring Boot reaches ready is dangerous behavior. Only use a fallback when a valid operational configuration, proper health/readiness reporting, and business correctness are defined.

## 16. Close Idempotency and Cleanup State

A resource may be asked to close via multiple paths: rollback, context close, timeout, retry, or operator stop. If `close()` is not idempotent, double-release or state corruption can occur.

Simple pattern:

~~~java
private final AtomicBoolean closed = new AtomicBoolean();

@Override
public void close() {
    if (!closed.compareAndSet(false, true)) {
        return;
    }
    releaseResources();
}
~~~

This is a **snippet** needing an `AtomicBoolean` import and `releaseResources` method. It prevents running release logic twice on one instance. Yet if `releaseResources()` throws after `closed=true`, subsequent calls will not automatically retry. For resources requiring confirmed cleanup, use a state machine (`OPEN → CLOSING → CLOSED/FAILED`), logging, and safe retry/backoff.

**Do not equate** "called close" with "successfully released." Especially with network sockets, cloud leases, broker registrations, or file deletions, additional observation and reconciliation may be needed.

## 17. Which Beans Does Spring Clean Up When Startup Fails?

Spring Boot has failure handling that can publish `ApplicationFailedEvent` and close the created application context when appropriate. When context destruction runs, singleton beans **already completely managed by the container** can receive destruction callbacks.

However, do not deduce that:

- Factory throws before `return` → Spring knows the local resource to close.
- Constructor throws → Caller has a complete object to destroy.
- `@PostConstruct` throws → That exact bean's destroy callback is guaranteed to run.
- Thread created with `new Thread(...)` outside Spring → `BeanFactory` will always stop the thread.
- External resource created via HTTP API → JVM shutdown deletes it automatically.
- `ApplicationFailedEvent` listener always has a full `ApplicationContext` to inject beans.

That is why you need **local rollback right where resources are opened** alongside a separate destruction path for objects that were successfully constructed.

### Do not confuse bootstrap close with application close

`BootstrapRegistryInitializer` can register objects very early before the application context. `BootstrapContextClosedEvent` is a handoff milestone during **startup**, not `ContextClosedEvent` for application shutdown. If creating a client/resource at bootstrap, give it explicit ownership/cleanup and bridge explicitly if the client must live on as a Spring bean.

## 18. Testing via Failure Injection

A test that only starts up successfully and closes the context normally **is insufficient** to detect resource leaks during partial initialization.

### Matrix to test

| Failure Point | Open Resources | Expected Outcome |
| --- | --- | --- |
| Input validation before acquire | None | No `close` called |
| After connection | Connection | Connection closed exactly once |
| After subscription | Connection + subscription | Subscription closed before connection |
| After final validation | All resources | All cleaned up in reverse order |
| Success | All resources | Factory does not clean up; owner/bean cleans up on close |
| First cleanup throws | Multiple resources | Still attempts other resources; preserves original error |
| Repeated close calls | Created bean | Idempotency per contract |
| Lazy bean fails on first request | Partial resources | Cleaned up immediately even though startup was already ready |
| Async init fails | Tasks/threads and resources | Cancellation/stop/join or bounded recovery |
| Process receives `SIGKILL` | Off-JVM resources may remain | TTL/lease/reconciliation; do not expect Java callbacks |

### Automated tests

You can write unit tests for the `ManagedPipeline.create(...)` factory and fake resources with counters/spies, without booting an entire `SpringApplication`. Assert:

- Exact open/close counts.
- Cleanup order.
- Original exception keeps the expected type and cause.
- `getSuppressed()` contains cleanup errors when intentionally injecting a close failure.
- No resource is closed on the success path before `owner.close()`.
- No pending workers or subscriptions remain after failure.

Illustrative JUnit test:

~~~java
@Test
void cleanupWhenSecondStageFails() {
    assertThrows(
            IllegalStateException.class,
            () -> ManagedPipeline.create("subscription"));

    // In a complete test, replace System.out with a fake/spy
    // and assert each resource is closed exactly once.
}
~~~

This is a **non-standalone snippet**: it requires `spring-boot-starter-test`, JUnit 5 imports, and a valid reference to the `ManagedPipeline` nested class (`PartialResourceApplication.ManagedPipeline`). You can use `ApplicationContextRunner` or Spring Boot integration tests to verify startup failure branches and destruction of other beans.

### Why not rely on framework logs as absolute assertions?

Spring Boot can log varying details across versions/levels. The Section 9 example only asserts the order of **lines explicitly printed by the demo code**, not the order of all Boot/Gradle logs. For automated tests, prefer counters/spies and meaningful happens-before relationships rather than full console log strings.

## 19. Production Scenarios Hard to Roll Back Completely

### Databases and transactions

A borrowed JDBC connection typically needs `close()` to **return it to the pool** per the pool contract, not to stop the entire pool. If a transaction opened and failed, roll back via the transaction manager. With `@Transactional`, Spring manages transactions within properly proxied boundaries, yet code opening resources outside transactions still needs its own cleanup.

A DB transaction does not automatically roll back an already sent email or external HTTP request. For cross-system side effects, consider the outbox pattern, idempotency keys, compensating actions, and post-error state verification.

### Temporary files

~~~java
Path temp = Files.createTempFile("import-", ".tmp");
try {
    writePayload(temp);
    validatePayload(temp);
    publish(temp);
}
catch (Exception original) {
    try {
        Files.deleteIfExists(temp);
    }
    catch (IOException cleanupFailure) {
        original.addSuppressed(cleanupFailure);
    }
    throw original;
}
~~~

This is a snippet requiring helper definitions, `Path`/`Files`/`IOException` imports, and a method signature. Once `publish` succeeds, decide whether the temp file still belongs to the factory. After a successful move/rename, deleting the source in a generic path could accidentally delete what was published if ownership changed.

### Executors and worker threads

~~~java
ExecutorService executor = Executors.newFixedThreadPool(2);
try {
    initializeHandlers(executor);
}
catch (RuntimeException original) {
    executor.shutdownNow();
    throw original;
}
~~~

This is only a first step, **not enough to guarantee cleanup**. `shutdownNow()` only attempts to interrupt; tasks may ignore interrupts or block on I/O. You need `awaitTermination(timeout)`, proper task cancellation contracts, and telemetry confirming threads have exited. Never leave self-created workers alive forever because their enclosing bean failed to initialize.

### Message consumers

If a consumer subscribes and then fails creating a parser, pause/unsubscribe/close using the broker's exact API and avoid acking/committing offsets before side effects are truly durable. If startup is killed after a side effect but before ack, redelivery can duplicate work; idempotency is required.

### Remote resources and cloud APIs

A create API may succeed on the server while the client times out before receiving the resource ID. Then the caller does not know whether the resource was created. Use idempotency tokens, operation IDs, status queries, compensating rollbacks, and reconciliation jobs. Local `AutoCloseable` cannot resolve remote-side uncertainty on its own.

## 20. Common Mistakes

**1. "Just add `@PreDestroy` and Spring cleans up everything."** False for local resources opened inside an unsuccessful factory/init.

**2. "`@Bean(destroyMethod)` cleans up resources before `@Bean` returns."** Do not rely on this; the factory must roll back itself.

**3. "With `try-with-resources`, I can return an object holding the stream."** Wrong if the stream must live on; the `try` scope closes it before the caller uses it.

**4. "Cleanup errors should replace the init exception."** Wrong; keep the root cause and attach cleanup exceptions as suppressed.

**5. "Closing resources in opening order is fine."** Not when a later resource depends on an earlier one; usually close in reverse opening order.

**6. "If a handle is opened, it is definitely registered as a bean."** No. A local variable in a factory is not a completed bean.

**7. "If a constructor throws, the caller can close the object."** No complete object is returned.

**8. "If `@PostConstruct` throws, `@PreDestroy` is still guaranteed."** There is no suitable guarantee to use it as the sole cleanup mechanism for init failures.

**9. "When bean initialization fails, Spring cleans up external threads too."** Not automatically for threads created outside Spring's lifecycle.

**10. "Registering listeners before init finishes is harmless."** No; callbacks may hold a half-initialized object after failure.

**11. "`AtomicBoolean closed=true` certifies the resource was released."** Not if releasing can throw; state must reflect the outcome.

**12. "If the first close fails, skip the remaining resources."** Can cause a second leak; keep attempting cleanup.

**13. "If init fails, just log and return an empty object."** Easily leaves the app reporting ready with invalid components; fail fast or use a contracted fallback.

**14. "`SmartLifecycle.stop` definitely handles all `start()` failures."** Do not use the shutdown stop callback as the sole rollback path for `start()` failures.

**15. "If a runner fails, streams it opened are closed by Spring."** Not if the runner held resources outside bean management.

**16. "Lazy beans only fail at startup."** They can fail on first use long after Boot is ready.

**17. "Once `close()` is called, threads definitely stop."** No; interrupts do not guarantee termination; use join/deadlines.

**18. "Retrying initialization does not need to clean up prior failed attempts."** False; failed attempts accumulate connections, threads, and file handles.

**19. "`SpringApplication` failure cleans up all external resources."** No guarantee for resources the container never received or remote side effects.

**20. "The JVM always runs shutdown hooks."** False on `SIGKILL`, host crashes, or severe VM errors.

**21. "Local rollback always cancels remote transactions."** No; use compensating transactions/outbox/reconciliation per semantics.

**22. "Testing only the happy path is enough."** No; inject failures after every acquisition step.

## 21. Practice Exercises

1. In the Section 9 project, state the exact moment ownership transfers from the factory to the Spring-managed bean.
2. Why does `--demo.fail-at=connection` not print `subscription opened` yet must still close `connection`?
3. Why must `--demo.fail-at=subscription` close both resources in reverse order?
4. If you remove `closeOnFailure(connection, original)`, what bug appears on the `connection` branch?
5. If you reverse the close order to `connection` then `subscription`, which resource might fail to flush/ack in a real application?
6. Add a failure point after a third validation step, ensuring every opened resource is cleaned up.
7. Modify `TrackedResource.close()` to throw an exception; how do you keep the original init error on the outside?
8. When using `@PostConstruct` to open resources, where do you place cleanup for the init failure path?
9. Why is a constructor performing I/O and publishing `this` early a dangerous design?
10. Write a builder with a rollback stack and explain why LIFO is used.
11. In a `SmartLifecycle` bean, if `start()` throws after opening a socket, why should you not simply wait for `stop(Runnable)`?
12. If init spawns an async thread and that thread fails after the method returns, what mechanism catches the error?
13. Write a bean factory that opens a connection and then parses a config file; use `try-with-resources` for which resource and ownership transfer for which resource?
14. Write tests for all 3 modes, asserting `opened count`, `closed count`, and cleanup order.
15. Add a fake resource whose `close()` fails; assert `getSuppressed()` is non-empty and the other resource is still attempted.
16. If a resource is created via a cloud API and the client times out, how do you know whether compensation is needed?
17. Why does `@Bean(destroyMethod="close")` not replace the factory's `try/catch`?
18. A lazy bean is used for the first time after ready and fails init. Can it leak resources in a long-running JVM?
19. When a container receives `SIGKILL`, why is there no pure Java guarantee that `close` will run?
20. List needed metrics: resources opened/closed, partial init failures, cleanup failures, active handles, and retry count.
21. Design cleanup order across consumer, session, and connection so flushing is not broken.
22. A task sent an email, then the DB transaction rolled back: what cleanup prevents duplicate side effects on retry?
23. Compare "successful factory rollback" with "normal bean destroy"; when is each invoked?
24. During code review, locate every acquire statement placed **before** a statement that can throw. Is any catch cleanup missing?

## Takeaways

- **Partial initialization** occurs when some resources have been allocated but the object/bean has not finished initializing.
- **Clean up right where you acquire:** constructor helpers, factories, or init methods must clean up opened resources themselves if a subsequent step fails.
- **Ownership transfers only after success:** the factory owns resources during construction; the bean/owner manages them once initialization succeeds.
- `@PreDestroy`/`destroyMethod` serve the managed bean destruction path, **not as the sole guarantee for objects failing init**.
- Usually **close in reverse opening order** to avoid breaking dependencies of higher-level resources.
- Use `try-with-resources` when a resource lives only within a block scope; never accidentally close resources meant for a long-lived bean.
- Preserve the **original exception** and attach cleanup errors via `addSuppressed(...)`.
- If cleanup can fail, idempotency and state machines must reflect actual outcomes rather than merely marking "closed."
- For threads, queues, cloud resources, and remote side effects, add cancellation/deadlines, retries, idempotency, compensating actions, or reconciliation.
- Test with failure injection **after every acquisition step**, not just successful startup.

### References

- Spring Framework 6.1 — Bean Initialization and Destruction Callbacks: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Framework 6.1 — `@Bean` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Bean.html
- Spring Framework 6.1 — `@PostConstruct` and `@PreDestroy`: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/postconstruct-and-predestroy-annotations.html
- Spring Framework 6.1 — `SmartLifecycle` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Boot 3.3 — `SpringApplication` and Startup Failure: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Java 17 — `AutoCloseable`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html
- Java 17 — `Throwable.addSuppressed`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#addSuppressed(java.lang.Throwable)
- Java — `try-with-resources`: https://docs.oracle.com/en/java/javase/tutorial/essential/exceptions/tryResourceClose.html
