# Releasing Resources and Destruction Callback Limits for Prototypes in Spring Framework

## 1. The Problem: Creating a Prototype Is Easy, but Who Closes Resources?

In the Spring Core Container, a bean with `prototype` scope is created anew every time the container receives a request for that bean. Spring performs object instantiation, dependency injection, and **initialization callbacks**. However, **after handing the prototype instance to the requester, the container does not automatically manage the full destruction lifecycle of that instance** as it does for singletons.

This is especially critical when a bean holds resources that must be released: file handles, sockets, JDBC connections, streaming sessions, native buffers, threads, or subscriptions. If you simply expect `@PreDestroy`, `DisposableBean.destroy()`, `@Bean(destroyMethod = "...")`, or `AutoCloseable.close()` to be invoked automatically by Spring when the context closes, prototypes can hold onto resources for far too long.

> **Rule:** For a Spring-supplied prototype, **the recipient using the instance must design how that instance's lifecycle ends and how cleanup runs**. Spring does not track every handed-out prototype to invoke destruction callbacks on `ApplicationContext.close()`.

After this lesson, you will be able to:

- Clearly distinguish **initialization**, **destruction callbacks**, and Spring's **scope of responsibility** for prototypes.
- Know why `@PreDestroy`, `DisposableBean`, and custom `destroyMethod` are not automatically called for prototypes merely when the context closes.
- Choose resource cleanup via `AutoCloseable`/try-with-resources, `finally`, or an ownership-managing factory/use-scope.
- Know when you can explicitly call `ConfigurableBeanFactory.destroyBean(beanName, instance)` and how it differs from calling `close()` directly.
- Handle prototypes injected into singletons, mid-operation exceptions, concurrent threads, and cases where a prototype does not actually hold resources.
- Experiment with a complete Java 17 + Spring Context 6.1 example with exact output and lifecycle verification.

## 2. Comparing Spring's Responsibility Across Scopes

A **bean definition** describes how Spring creates and manages a bean. Scope dictates the boundary along which the container supplies instances. A destruction lifecycle is not inferred merely from a bean implementing `AutoCloseable`.

| Scope | When Spring creates the bean | Initialization callbacks | Automatic destruction callbacks |
| --- | --- | --- | --- |
| `singleton` | Normally one instance per bean definition/container | Run when the instance is created | Spring normally invokes them on clean context close |
| `prototype` | Every target request creates a new instance | Run for each new target | **Not automatically invoked by the container after handoff** |
| `request` | Per HTTP request | Run when the request's target is created | Web scope can invoke them when the request ends |
| `session` | Per HTTP session | Run when the session's target is created | Web scope can invoke them when the session expires/is invalidated |
| `application` | Per `ServletContext` | Run when the target is created | Follows the web application lifecycle |
| Custom scope | Implementation-dependent | During bean creation | Only if the scope supports and properly triggers destruction callbacks |

This table reflects how Spring Framework manages scopes in suitable environments. For web scopes or custom scopes, running destruction callbacks also depends on the scope's lifecycle and graceful shutdown. Cleanup is not guaranteed on `kill -9`, power loss, or process crash.

### What does "prototypes are not destroyed by Spring" mean precisely?

When calling `context.getBean(MyPrototype.class)`, Spring still executes everything on the **creation/initialization** side: instantiation, dependency injection, bean post-processing, and init callbacks. After returning the object to the caller, Spring does not maintain a list of all prototypes to automatically invoke their destroy callbacks when the context closes. The recipient owns cleanup.

This **does not mean** destruction callbacks are useless for prototypes: you can deliberately trigger destruction handling via a Spring mechanism like `ConfigurableBeanFactory.destroyBean(beanName, instance)`, or invoke a resource-closing method exposed by the bean. Choose the right contract.

### A resource-holding prototype vs a data-only prototype

- A `CalculationContext` holding only a `List`, `Map`, counters, and normal heap structures usually **needs no dedicated destroy method**. Java's garbage collector reclaims heap memory once unreachable.
- A `FileSession` holding an `InputStream`, `RandomAccessFile`, socket, or native handle needs **explicit resource closing**; waiting for GC can exhaust file descriptors, pool slots, or native memory.
- A prototype spawning threads or executors needs an appropriate stop/shutdown policy; never assume threads stop automatically when a Java variable goes out of scope.

**GC is not a lifecycle callback.** Reclaiming memory and terminating finite resources are two separate concerns.

## 3. Destruction Callbacks: Mechanisms and Limits

### 3.1. `@PreDestroy`

A method annotated with `jakarta.annotation.PreDestroy` can be invoked by Spring during destruction of **a bean whose destruction lifecycle is actually handled by Spring**.

~~~java
import jakarta.annotation.PreDestroy;

public class ResourceOwner {
    @PreDestroy
    public void release() {
        System.out.println("release resources");
    }
}
~~~

This is an illustrative class; for Spring to process the callback, the bean must be registered in a container with annotation processing. On Spring 6.x use `jakarta.annotation.PreDestroy`, rather than defaulting to `javax.annotation.PreDestroy` from legacy apps.

If `ResourceOwner` is a **singleton**, Spring invokes the callback on normal context close. If it is a **prototype already handed to a caller**, do not expect context shutdown to automatically invoke the callback for that instance.

### 3.2. `DisposableBean.destroy()`

Spring's interface:

~~~java
import org.springframework.beans.factory.DisposableBean;

public class ResourceOwner implements DisposableBean {
    @Override
    public void destroy() {
        System.out.println("Spring destruction callback");
    }
}
~~~

For container-managed singletons, Spring automatically calls `destroy()` during destruction. For prototypes, implementing `DisposableBean` **does not change Spring's policy of not tracking prototypes after handoff**.

Trade-off: the class couples directly to a Spring API. For resource objects usable standalone, `AutoCloseable` is usually a more reusable Java contract.

### 3.3. Custom `@Bean(destroyMethod = "...")`

~~~java
@Configuration(proxyBeanMethods = false)
class ResourceConfiguration {
    @Bean(destroyMethod = "disconnect")
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    ExternalClient externalClient() {
        return new ExternalClient();
    }
}
~~~

This is an illustrative configuration snippet: `ExternalClient` must have a no-arg `disconnect()` method, along with required Spring imports. `destroyMethod` is declared on the bean definition, yet **does not make Spring auto-destroy prototypes on context close**.

Advantage of a custom destroy method: `ExternalClient` needs no awareness of Spring, making it suitable for external libraries.

### 3.4. `AutoCloseable` and destroy method inference

For Java-config `@Bean` methods, Spring can infer a public no-arg `close()` or `shutdown()` as the destroy method when `destroyMethod` is unspecified. This behavior is helpful for **singletons** fully managed by Spring:

~~~java
@Bean // May infer close() for this singleton bean.
ManagedChannel managedChannel() {
    return new ManagedChannel();
}
~~~

If you do not want Spring calling an inferred method on a `@Bean`, you can use `@Bean(destroyMethod = "")`—for instance when the resource is actually managed by an external owner. However, that **does not disable other callback mechanisms** such as `DisposableBean` if the bean implements that interface.

For **prototypes**, even if declared with `@Bean(destroyMethod = "close")`, inference or explicit method configuration only decides **what to do if destruction is deliberately triggered**; it does not create a tracker to auto-destroy prototypes.

## 4. Full Diagram: Where Spring Stops Managing a Prototype

~~~text
Caller requests prototype bean
           |
           v
BeanFactory creates new object
           |
           v
Inject dependencies / properties
           |
           v
BeanPostProcessors + init callbacks
           |
           v
Return prototype P1 to caller
           |
           +---- Caller uses P1 in business logic
           |               |
           |               v
           |        Caller owns cleanup responsibility
           |               |
           |               +-- P1.close()
           |               '-- beanFactory.destroyBean(name, P1)
           |
           '-- ApplicationContext.close()
                        |
                        +-- Destroys container-owned singletons
                        '-- Does NOT track down P1 to destroy it
~~~

Distinguish two boundaries:

- **Initialization boundary:** Spring creates the instance and runs callbacks such as `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, and custom `initMethod`.
- **Ownership boundary:** Spring hands the prototype to caller code; the caller must determine when usage ends and clean up its resources.

If a prototype is injected directly into a singleton, that prototype instance may stay in the singleton's field for a very long time. Even though the singleton has a Spring-managed lifecycle, **there is no general rule that Spring will automatically invoke destroy callbacks for that prototype dependency**. The singleton's owner may have to take responsibility for cleaning up the prototype it holds.

## 5. Complete Example: Spring Context 6.1, Java 17, and Two Cleanup Approaches

The program below intentionally creates two prototypes. The first prototype is destroyed **explicitly via BeanFactory**. The second prototype is not auto-closed by Spring on context shutdown; the caller calls `close()` itself afterward. An `AutoCloseable` singleton illustrates the contrasting behavior.

### 5.1. Project structure

~~~text
prototype-cleanup-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── cleanup/
                        └── PrototypeCleanupDemo.java
~~~

### 5.2. File `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>prototype-cleanup-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.13</version>
        </dependency>
        <dependency>
            <groupId>jakarta.annotation</groupId>
            <artifactId>jakarta.annotation-api</artifactId>
            <version>2.1.1</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>com.example.cleanup.PrototypeCleanupDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.3. File `PrototypeCleanupDemo.java`

~~~java
package com.example.cleanup;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;

public class PrototypeCleanupDemo {

    public static void main(String[] args) {
        PrototypeLease second;

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            PrototypeLease first = context.getBean(PrototypeLease.class);
            second = context.getBean(PrototypeLease.class);

            System.out.println("Different prototypes: " + (first != second));

            // Explicitly trigger Spring destruction callbacks for first.
            context.getBeanFactory()
                .destroyBean("prototypeLease", first);
            System.out.println("First closed: " + first.isClosed());

            System.out.println("Closing ApplicationContext");
        }

        // Context closed singletons, but did not auto-close prototype second.
        System.out.println("Second closed after context: " + second.isClosed());

        // Caller releases second directly using the Java contract.
        second.close();
        System.out.println("Second closed manually: " + second.isClosed());
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        SingletonLease singletonLease() {
            return new SingletonLease();
        }

        @Bean(destroyMethod = "close")
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        PrototypeLease prototypeLease() {
            return new PrototypeLease();
        }
    }

    public static class SingletonLease implements AutoCloseable {
        public SingletonLease() {
            System.out.println("Singleton created");
        }

        @Override
        public void close() {
            System.out.println("Singleton closed by Spring");
        }
    }

    public static class PrototypeLease implements AutoCloseable {
        private static final AtomicInteger SEQUENCE = new AtomicInteger();

        private final int number = SEQUENCE.incrementAndGet();
        private final AtomicBoolean closed = new AtomicBoolean();

        public PrototypeLease() {
            System.out.println("Prototype created #" + number);
        }

        @PostConstruct
        public void initialize() {
            System.out.println("Prototype initialized #" + number);
        }

        @PreDestroy
        public void beforeDestroy() {
            System.out.println("Prototype @PreDestroy #" + number);
        }

        @Override
        public void close() {
            if (closed.compareAndSet(false, true)) {
                System.out.println("Prototype closed #" + number);
            }
        }

        public boolean isClosed() {
            return closed.get();
        }
    }
}
~~~

The classes are declared `public static` inside one Java file for learning convenience. They are registered via `@Bean` methods; `AnnotationConfigApplicationContext(Config.class)` detects and processes `@Configuration`. `jakarta.annotation-api` supplies `@PostConstruct` and `@PreDestroy` in the namespace matching Spring Framework 6.x.

In the example:

- `SingletonLease` is a singleton because `@Bean` specifies no other scope. Spring can infer `close()` as the destroy callback.
- `PrototypeLease` is a prototype. Spring runs `@PostConstruct` for each new instance.
- `destroyBean("prototypeLease", first)` intentionally asks Spring to run **the destruction path** for `first`: `@PreDestroy`, followed by the configured custom `close()`.
- `second` stays open after the context closes. Finally, the caller closes it via `AutoCloseable`; calling `close()` directly **does not automatically invoke the `@PreDestroy` method**.

### 5.4. Running the program

Requires JDK 17+ and Maven 3.9.x. Run in the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

Active stdout lines from the program, in exact order:

~~~text
Singleton created
Prototype created #1
Prototype initialized #1
Prototype created #2
Prototype initialized #2
Different prototypes: true
Prototype @PreDestroy #1
Prototype closed #1
First closed: true
Closing ApplicationContext
Singleton closed by Spring
Second closed after context: false
Prototype closed #2
Second closed manually: true
~~~

Maven or logging frameworks may emit other environment-specific output; the listing above reflects only `System.out.println` statements in the code.

**Point to observe:** There is no `Prototype @PreDestroy #2` line when closing the context. The second prototype stays open until the caller calls `second.close()`. This is not a Spring bug: prototypes **are not included in the container's automatic destruction callback list** once the instance is handed out.

### 5.5. Difference between `destroyBean` and `close()`

| Call | Who executes it? | Expected callbacks in the example |
| --- | --- | --- |
| `context.getBean(PrototypeLease.class)` | Spring creates target | Constructor, dependency injection, `@PostConstruct` |
| `beanFactory.destroyBean("prototypeLease", first)` | Caller asks Spring to process destruction for a specific instance | `@PreDestroy`, `close()` because the bean definition has `destroyMethod = "close"` |
| `second.close()` | Caller invokes Java contract | Only the `close()` method defined by the class |
| `context.close()` | Spring destroys beans/containers it manages | Singleton `close()`; **does not auto-close prototype `second`** |

When calling `destroyBean`, pass the exact **bean definition name** and the exact **instance obtained from the factory**. This API is part of `ConfigurableBeanFactory`, a Spring configuration/infrastructure API. If the application only needs to close ordinary Java resources, `AutoCloseable.close()` is usually simpler and reduces coupling to the bean factory.

## 6. Recommended Approach: try-with-resources

When a prototype represents **a working session with a clear start/end**, design the class to implement `AutoCloseable` and acquire it at the start of a unit of work.

~~~java
import java.io.IOException;
import org.springframework.beans.factory.ObjectProvider;

public final class ExportService {
    private final ObjectProvider<ExportSession> sessions;

    public ExportService(ObjectProvider<ExportSession> sessions) {
        this.sessions = sessions;
    }

    public void export() throws IOException {
        try (ExportSession session = sessions.getObject()) {
            session.writeHeader();
            session.writeBody();
        } // close() is automatically called even if writeBody() throws.
    }
}
~~~

This is an illustrative class, not standalone runnable code; `ExportSession` must be implemented as an `AutoCloseable` with `writeHeader()`, `writeBody()`, and `close()`. In a Spring application, register `ExportSession` as a prototype and `ExportService` as a bean to inject `ObjectProvider`.

A conceptual implementation:

~~~java
public final class ExportSession implements AutoCloseable {
    private final java.io.ByteArrayOutputStream buffer =
        new java.io.ByteArrayOutputStream();

    public void writeHeader() throws java.io.IOException {
        buffer.write("HEADER\n".getBytes(java.nio.charset.StandardCharsets.UTF_8));
    }

    public void writeBody() throws java.io.IOException {
        buffer.write("BODY\n".getBytes(java.nio.charset.StandardCharsets.UTF_8));
    }

    @Override
    public void close() throws java.io.IOException {
        buffer.close();
    }
}
~~~

Note: `ByteArrayOutputStream.close()` has no effect on external resources; this snippet merely shows valid Java types and try-with-resources syntax. In real code, `ExportSession` might hold a `FileOutputStream`, `InputStream`, socket, or another resource that truly needs releasing. In that case, handle ownership and potential `IOException` properly.

**Avoid misconception:** `ObjectProvider.getObject()` does not auto-close the prototype; try-with-resources itself triggers `close()`. At the same time, direct Java `close()` does not automatically trigger `@PreDestroy` or `DisposableBean.destroy()` unless your `close()` code invokes that logic.

### When you also want Spring lifecycle callbacks

If cleanup logic only lives inside `@PreDestroy` and `DisposableBean.destroy()` and `close()` does not duplicate it, you can create an **owner/factory wrapper** that calls `beanFactory.destroyBean(beanName, instance)` inside the wrapper's `close()`:

~~~java
import org.springframework.beans.factory.config.ConfigurableBeanFactory;

public final class SpringOwnedHandle<T> implements AutoCloseable {
    private final ConfigurableBeanFactory factory;
    private final String beanName;
    private final T instance;
    private boolean closed;

    public SpringOwnedHandle(
            ConfigurableBeanFactory factory,
            String beanName,
            T instance) {
        this.factory = factory;
        this.beanName = beanName;
        this.instance = instance;
    }

    public T get() {
        return instance;
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            factory.destroyBean(beanName, instance);
        }
    }
}
~~~

This is a **syntactically complete Java class**, though using it in an application requires code creating handles from an active bean factory, valid bean name, and matching instance; do not assume thread safety because `closed` is unsynchronized. If multiple threads can call `close()` concurrently, use `AtomicBoolean.compareAndSet(false, true)`.

This approach introduces a layer coupled to Spring infrastructure. Only use it when you must run the exact Spring destruction callback chain; for ordinary resources, closing directly via `AutoCloseable` is usually easier to maintain.

## 7. Why Injecting a Prototype Directly into a Singleton Can Make Things Worse

Consider:

~~~java
@Component
@Scope("prototype")
class TemporaryWriter implements AutoCloseable {
    @Override
    public void close() {
        // Close resource.
    }
}

@Service
class BatchService {
    private final TemporaryWriter writer;

    BatchService(TemporaryWriter writer) {
        this.writer = writer;
    }

    void process() {
        // Every method call still uses the same injected writer.
    }
}
~~~

This is illustrative code requiring imports for `Component`, `Scope`, and `Service`. When Spring creates the `BatchService` singleton instance, it resolves the constructor dependency once and injects one `TemporaryWriter` prototype. The singleton then holds that reference in its field.

Consequences:

1. That prototype is **not fresh for each `process()` call**.
2. It can live as long as the singleton if the field is never replaced.
3. Spring does not register a separate destruction callback for the prototype merely because it was injected into a singleton.
4. If the writer is not thread-safe, concurrent requests calling the singleton can access the same writer.
5. If the service does not proactively clean up, resources are held until the caller releases them or the process exits.

The proper solution is usually injecting `ObjectProvider<TemporaryWriter>` into the singleton, acquiring a writer **inside each `process()` call**, and closing it in `try-with-resources`:

~~~java
@Service
class BatchService {
    private final ObjectProvider<TemporaryWriter> writers;

    BatchService(ObjectProvider<TemporaryWriter> writers) {
        this.writers = writers;
    }

    void process() {
        try (TemporaryWriter writer = writers.getObject()) {
            // Perform work with this exact writer.
        } catch (Exception ex) {
            throw new IllegalStateException("Processing failed", ex);
        }
    }
}
~~~

This is an **alternative version** of `BatchService` above—do not define two classes with the same name in one package. If `TemporaryWriter.close()` declares no checked exception, you can omit the broad catch; design exception handling per business logic and ensure primary errors are not masked.

## 8. When You Want Spring to Manage Destroying All Prototypes via BeanPostProcessor

Spring documentation mentions the option of using a custom `BeanPostProcessor` that retains references to prototypes needing cleanup and disposes of their resources later. This is an **advanced** option:

- A registry must track which instances were created, which owner they belong to, and when they are truly finished being used.
- Simply appending every prototype to a global `List` and waiting for context close can retain objects and resources far too long, causing memory leaks.
- You must avoid cleaning up while a prototype is still in use by another request/job.
- The registry must be thread-safe when multiple workers create/destroy prototypes concurrently.
- If cleaning up via Spring destruction callbacks, avoid double-destroying a single instance.

Therefore, only choose this approach when the system has a **clearly designed ownership/lifecycle manager**. It is not the default choice for every prototype holding a file or socket. Usually it is much better to implement `AutoCloseable` and keep the object within the lexical scope of `try-with-resources`.

## 9. Why `@PreDestroy` Is Not Synonymous with `close()`

There are three forms of "cleanup" to distinguish:

| Mechanism | Triggered by | When it runs |
| --- | --- | --- |
| `@PreDestroy` | Spring destruction lifecycle (or annotation-aware framework) | When destruction callbacks are actually dispatched |
| `DisposableBean.destroy()` | Spring destruction lifecycle | When Spring dispatches callbacks for the bean |
| `AutoCloseable.close()` | Java code such as `try-with-resources`, or Spring if configured/inferred as destroy method | When the caller or Spring actually invokes `close()` |

A `@PreDestroy` method is not automatically a `close()` method. Calling `close()` does not scan annotations to invoke all lifecycle callbacks. Conversely, if both a `@PreDestroy` method and an inferred `close()` exist on a singleton bean, Spring can trigger both; design them so you **do not clean up the same resource twice in a hazardous way**.

Some developers write both:

~~~java
@PreDestroy
public void stop() {
    close();
}

@Override
public void close() {
    // release
}
~~~

If the bean also has custom/inferred `destroyMethod = "close"`, Spring can call `stop()` and then `close()` a second time. Do not rely on guessing callback deduplication mechanics in your design. Choose one owner and one cleanup point, or ensure `close()` is idempotent.

### What is idempotency?

An **idempotent** close method can be called multiple times without causing harmful side effects or attempting to release the same handle twice. Example:

~~~java
private final AtomicBoolean closed = new AtomicBoolean();

@Override
public void close() {
    if (closed.compareAndSet(false, true)) {
        // Close the real resource exactly once.
    }
}
~~~

The code above is a snippet inside a class implementing `AutoCloseable`, requiring `import java.util.concurrent.atomic.AtomicBoolean;`. Clearly decide behavior if cleanup throws an exception: setting the atomic flag before closing means callers will not automatically retry via the same method; sometimes a state machine or retry handling in the resource manager is required.

## 10. Are Destruction Callbacks Guaranteed to Run When a Process Stops Abruptly?

No. Even Spring-managed singletons cannot rely on destruction callbacks across every failure mode.

| Scenario | Can cleanup run? | Notes |
| --- | --- | --- |
| Normal `AnnotationConfigApplicationContext.close()` | Yes, for container-managed singletons | Unless errors or special lifecycles intervene |
| Graceful Spring Boot shutdown with shutdown hook | Possible | Depends on shutdown progress and OS |
| `System.exit(...)` with shutdown hooks running | Possible | Not guaranteed if hooks fail or time out |
| JVM crash, `kill -9`, power outage | Cannot be guaranteed | Java callbacks have no chance to run |
| Prototype handed out and context later closes | **Not automatic** | Caller remains responsible |
| Prototype inside `try-with-resources` | Java attempts `close()` when leaving block | Depends on control flow and JVM still being alive |

For critical resources, you need system-level durability mechanisms: transaction boundaries, timeouts, leases, server-side expiration, connection pools, or crash recovery. Lifecycle callbacks are a valid cleanup mechanism along normal execution paths, **not a guarantee against all failures**.

## 11. Special Notes for Connection Pools, JDBC, and HTTP Clients

Having a resource does not automatically mean you should make it a prototype:

- **Thread-safe connection pools / HTTP clients** should normally be long-lived, such as a singleton `@Bean` with an appropriate destroy method. Creating an entire new pool per prototype request is very expensive and can exhaust connections.
- **Connections or streams borrowed from a pool** should be acquired and returned within a transaction/task scope, usually via `try-with-resources` or resource-management infrastructure. "Closing" a pooled connection usually means returning it to the pool.
- **Spring transaction management** may bind a connection to the current transaction. Never arbitrarily close framework-managed resources behind the transaction manager's back.
- **File handles, sockets, archive writers** **truly owned** by a prototype should have a clear closing contract, usually `AutoCloseable`.

Identify **who owns the resource**, rather than just noticing a `close()` method. If a bean merely references a shared resource owned by a singleton, the prototype must not close the shared resource when it finishes.

## 12. Designing Clear Ownership

A prototype can participate in relationships like:

~~~text
Singleton ResourceManager
      |
      | opens/lends
      v
Prototype WorkSession  <-- owned by one unit of work
      |
      | uses borrowed resource
      v
Close / release at end of work
      |
      v
ResourceManager continues existing
~~~

**Questions to answer in code review:**

1. Who calls Spring to obtain the prototype?
2. Who decides the instance is no longer in use?
3. Who calls `close()` or `destroyBean(...)`, and on which success/failure branches?
4. Does the prototype own its own resource or merely borrow a shared one?
5. Can `close()` be called concurrently or twice?
6. If initialization fails midway, which resources are already open and how are they rolled back?
7. If an async task runs long, who ensures cleanup happens when the task genuinely finishes?
8. Could bean proxying cause you to close a **proxy** rather than the **target resource**?

For beans holding only pure Java computational data, no destroy callback may be needed. For beans holding resources, cleanup responsibility must be visible in the API rather than expecting GC or the Spring context to guess for you.

## 13. Cleanup When an Exception Occurs Mid-Task

### 13.1. `try-with-resources` covers error paths too

~~~java
try (WorkSession session = sessions.getObject()) {
    session.stepOne();
    session.stepTwo();  // Even if this throws, close() is still invoked.
}
~~~

This is illustrative code; `sessions` is `ObjectProvider<WorkSession>`, and `WorkSession` implements `AutoCloseable`. The compiler generates a `finally` block to call `close()`, and if both the body and `close()` throw, the `close()` exception is typically attached as a *suppressed exception* on the primary exception.

### 13.2. What if a factory opens a resource but constructor/init fails?

You cannot rely on a caller to clean up a prototype **that failed mid-creation and was never handed to the caller**. For resources opened directly in a constructor or init method, apply exception safety:

~~~java
public ResourceSession(Path path) throws IOException {
    this.stream = Files.newOutputStream(path);
    try {
        validateConfiguration();
    } catch (RuntimeException | Error ex) {
        try {
            stream.close();
        } catch (IOException cleanupFailure) {
            ex.addSuppressed(cleanupFailure);
        }
        throw ex;
    }
}
~~~

This is an illustrative constructor snippet inside `ResourceSession`; the class needs an `OutputStream stream` field, `validateConfiguration()`, and imports for `Path`, `Files`, and `IOException`. It demonstrates cleaning up an already-opened resource when initialization fails. In an even cleaner design, defer opening the resource to a factory capable of clear cleanup or use `try-with-resources` right at acquisition.

### 13.3. What if `close()` fails?

Do not swallow all resource-closing errors. Depending on context, log with a correlation ID, attach suppressed exceptions, or propagate per the API contract. With pools/networking, closing a resource can sometimes fail due to corrupted state; establish a recovery policy instead of infinite retries.

## 14. Prototypes, Scoped Proxies, and Limits of `try-with-resources`

Suppose a prototype bean is declared with a proxy:

~~~java
@Component
@Scope(
    value = "prototype",
    proxyMode = ScopedProxyMode.TARGET_CLASS
)
public class ProxiedWorker implements AutoCloseable {
    public void work() {
        // ...
    }

    @Override
    public void close() {
        // ...
    }
}
~~~

This is an illustrative class requiring imports for `Component`, `Scope`, and `ScopedProxyMode`.

A **prototype scoped proxy** can resolve a different target for **each method invocation**. If a caller holds a reference to the proxy and writes:

~~~java
try (ProxiedWorker worker = injectedWorkerProxy) {
    worker.work();
}
~~~

Do not assume `work()` and `close()` execute on the same target. The target of `work()` can differ from the target of `close()`; in that case, the actual work resource is not closed properly. This is a key reason **not to treat a prototype scoped proxy as a stable resource handle**.

For resources needing multiple calls on **the same instance**, obtain the prototype target directly from `ObjectProvider.getObject()` and hold it in a local variable for the task. When the bean does not enable a scoped proxy, the provider returns the actual prototype target so `try-with-resources` closes the right object.

## 15. Asynchronous Scenarios, Multiple Threads, and Premature Closing

A singleton method might hand a prototype to another thread:

~~~java
WorkSession session = sessions.getObject();
executor.submit(() -> session.process());
session.close(); // Risk of closing before the background task finishes using it.
~~~

This is an illustrative snippet; `executor` is an `ExecutorService`. You cannot close the session on the calling thread right after submitting and expect the worker to have finished. Place cleanup at the actual completion path of the task:

~~~java
executor.submit(() -> {
    try (WorkSession session = sessions.getObject()) {
        session.process();
    }
});
~~~

If `sessions.getObject()` is not permitted on a worker thread because a dependency is bound to request scope, pass a data snapshot instead of passing a scoped proxy. With ordinary prototypes, acquiring inside the worker is fine as long as the container stays alive.

Multiple threads sharing one prototype still must synchronize mutable state themselves. Prototype scope **does not guarantee thread safety**. With concurrent task cancellation/execution, design ownership and synchronization so `close()` cannot occur while `process()` is still using the resource.

## 16. Testing Prototype Cleanup Policies

A good test must verify both **being closed** and **not being auto-closed by Spring**, per the contract:

1. Create a context from `@Configuration`.
2. Obtain two prototypes and verify they do not share object identity.
3. Verify initialization callbacks ran on both.
4. Call `beanFactory.destroyBean(name, first)` and assert `first` is closed.
5. Close the context and assert `second` is still not closed.
6. Call `second.close()` and assert `second` is closed.
7. Verify a singleton with a destroy callback was invoked by Spring.

The `main` example in Section 5 sequentially verified all these steps via stdout. In automated tests, prefer asserting `boolean`/counters/state rather than matching log text alone, because frameworks may emit extra output.

If tests use prototypes that open real OS resources, always clean up in `finally` or `try-with-resources` **even when an assertion fails**. Tests must not leak file handles just because an `assertThat(...)` branch throws an exception.

## 17. Common Pitfalls and How to Resolve Them

| Symptom | Cause | How to resolve |
| --- | --- | --- |
| `@PreDestroy` does not run on context close | Instance is a prototype already handed to caller | Clean up proactively; use `close()` or `destroyBean(...)` per contract |
| `DisposableBean.destroy()` is not auto-called | Spring does not track prototypes for automatic destruction | Design an owner; do not rely on context shutdown |
| `destroyMethod = "close"` is set yet prototype stays open | Declaring a callback does not auto-trigger it | Caller invokes `close()` or explicitly triggers destruction |
| Singleton closes while prototype does not | Singletons belong to container destruction list; prototypes do not | Expected behavior; handle prototypes separately |
| Resource gets closed twice | `@PreDestroy` and inferred `close()` both close, or two owners call it | Single cleanup owner; make `close()` idempotent where appropriate |
| Resource closed while job is still running | Cleanup happened before async task completed | Tie ownership to the job's actual lifetime |
| File/socket leaked on exception | Missing `try/finally` or `try-with-resources` | Wrap all exit paths in cleanup |
| Prototype retained too long in singleton field | Direct injection resolves only once | Per-operation provider/factory; clean up each instance |
| Context shutdown does not release resources | Confusing JVM shutdown with prototype cleanup | Design explicit destruction and timeouts/recovery |
| `close()` on proxy does not close the right target | Prototype proxy may pick a different target per call | Obtain real target via provider and hold in a local variable |
| Wrongly closing shared resource | Prototype only borrows a resource owned by another singleton | Only return/release the lease, do not close the resource manager |
| Container context closes while worker is still running | Worker holds prototype/context beyond valid lifetime | Drain job lifecycle, stop accepting tasks, await/cancel, and clean up cleanly |

## 18. Strategy Selection Guide

**Data-only objects:** No need to invent fake resource cleanup. Fresh prototypes or plain `new` Java objects can be left to GC.

**Objects holding dedicated resources within a method:** Use `AutoCloseable` and `try-with-resources`. Inject `ObjectProvider<T>` into the singleton to acquire a prototype at the start of the method, and use that single instance throughout the operation.

**Objects that must execute Spring's exact lifecycle callbacks:** Consider `ConfigurableBeanFactory.destroyBean(beanName, instance)` from a controlled owner layer. Document clearly why you invoke the framework API instead of Java `close()`.

**Libraries with `close()` or `shutdown()`:** Declare a singleton `@Bean` if the library is a shared client/pool; Spring usually infers the destroy method for `@Bean`. Set `destroyMethod` explicitly when special rules apply.

**Many async tasks:** Tie prototype creation and release to **each task**, not to thread submission or context shutdown. When bounding resources is required, use an appropriate pool/semaphore/lease.

**Wanting "Spring to auto-close every prototype on context close":** This is not default behavior. If you genuinely need a lifecycle registry, establish a clear owner, end-of-use rules, synchronization, and memory retention checks. Usually managing directly by task scope is simpler.

## 19. Self-Check Questions

**Question 1:** A prototype `@Bean` has `@PreDestroy` and `destroyMethod = "close"`. After calling `getBean()`, if only `context.close()` runs, do both callbacks execute automatically?

**Answer:** Not automatically for prototypes handed to callers. The container does not track all prototype instances to destroy at close time. Proactive cleanup is required.

**Question 2:** Does `context.getBeanFactory().destroyBean("prototypeLease", lease)` differ from `lease.close()`?

**Answer:** Yes. `destroyBean` uses the bean definition to execute Spring's destruction lifecycle (such as `@PreDestroy`, `DisposableBean`, custom destroy method). `close()` invokes a Java method directly. Both must be called when the resource is genuinely done being used.

**Question 3:** Why is `@Bean(destroyMethod = "")` not a way to "disable every destroy callback"?

**Answer:** It disables bean-definition custom destroy-method inference/naming; mechanisms like `DisposableBean.destroy()` still have their own contracts. For prototypes, the main issue is that destruction is not auto-triggered, not merely missing method config.

**Question 4:** A singleton injects a prototype `FileWriter` directly. Why do repeated calls to the singleton not create a new writer and why can the writer stay open too long?

**Answer:** The prototype dependency is resolved when the singleton is created, storing one object in a field. Method calls do not ask Spring for a new prototype. Use a per-operation provider/factory and lifecycle-scoped cleanup.

**Question 5:** If a prototype scoped proxy implements `AutoCloseable`, can you guarantee `proxy.work()` and `proxy.close()` act on the same target?

**Answer:** No. A prototype scoped proxy can resolve a new target on each call. Hold a direct reference to a single prototype target obtained from a provider whenever an operation needs stable state/resources.

**Question 6:** Is `@PreDestroy` needed on a prototype holding only a `List<String>`?

**Answer:** Usually not. If it holds no off-heap resources and has no side effects to revert, Java GC reclaims memory once the object becomes unreachable. Do not add destroy callbacks just "for lifecycle completeness".

## 20. Official Documentation

- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): prototype contract, initialization callbacks, destruction callback limits, and caller cleanup responsibility.
- [Spring Framework — Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): `@PreDestroy`, `DisposableBean`, custom destroy methods, callback order.
- [Spring Framework — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html): `destroyMethod`, inferring `close()`/`shutdown()`, `destroyMethod = ""`.
- [ConfigurableBeanFactory Javadoc — `destroyBean(String, Object)`](https://docs.spring.io/spring-framework/docs/6.1.6/javadoc-api/org/springframework/beans/factory/config/ConfigurableBeanFactory.html): API to trigger destruction per bean definition for a specific bean instance.
- [Spring Framework — Method Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-method-injection.html): how to obtain fresh prototypes when a singleton needs a per-operation dependency.
