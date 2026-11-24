# @PreDestroy, DisposableBean, and destroyMethod

A Spring bean usually is not just created and used forever. Over an application's lifetime, a bean may open connections, create thread pools, hold file handles, initialize clients for external services, or own a resource that needs closing when the application stops. If these resources are not released properly, the application may hold unnecessary connections, fail to flush data, leave background threads running, or prolong shutdown.

Spring provides callback mechanisms for beans to perform cleanup work when their lifecycle ends. Three common approaches are:

- **`@PreDestroy`:** marks a method to be called before the bean is destroyed.
- **`DisposableBean`:** implements Spring's interface and provides the `destroy()` method.
- **`destroyMethod`:** declares a custom destroy method name on the bean definition, typically via `@Bean`.

All three serve the end-of-lifecycle phase of a bean, but they differ in declaration style, degree of coupling to Spring, and where each is best used. Understanding them correctly helps manage resources intentionally and avoid confusing stopping a bean with executing regular business logic.

## 1. Why Do Beans Need Destruction Callbacks?

Consider a service that creates a thread pool to process reports:

~~~java
@Service
public class ReportWorker {
    private final ExecutorService executor =
            Executors.newFixedThreadPool(4);

    public void submit(Runnable task) {
        executor.submit(task);
    }
}
~~~

`ExecutorService` holds worker threads. If the application stops without asking the executor to shut down, running threads or tasks may continue holding resources and affect process termination.

Another example is a client for an external service:

~~~java
public class VendorClient implements AutoCloseable {
    @Override
    public void close() {
        // Close connection pool or internal resources.
    }
}
~~~

If `VendorClient` opens a connection pool when created, the pool needs to be closed when the bean is no longer in use. Similarly, beans may own:

- Connection pools or HTTP clients.
- Thread pools, schedulers, and background workers.
- Files, streams, sockets, or native handles.
- Buffers that need flushing or resources needing completion.
- Connections to message brokers or external systems.

A destruction callback lets the bean perform cleanup at the moment the container finishes managing the instance. For singletons, this moment is typically when the ApplicationContext closes.

### Initialization and destruction are two halves of the lifecycle

You can picture the simplified lifecycle:

~~~text
Bean definition
      |
      v
Create instance
      |
      v
Inject dependencies
      |
      v
Initialization callback
      |
      v
Bean active
      |
      v
ApplicationContext closes
      |
      v
Destruction callback
      |
      v
Release resources
~~~

`@PostConstruct`, `InitializingBean.afterPropertiesSet()`, and `initMethod` belong to the initialization callback group. `@PreDestroy`, `DisposableBean.destroy()`, and `destroyMethod` belong to the destruction callback group.

Destruction callbacks are only managed by Spring for instances and scopes whose lifecycle the container is responsible for managing. An object created with `new` in business code does not automatically receive callbacks just because its class carries Spring annotations.

## 2. @PreDestroy: Marking a Method Before Bean Destruction

`@PreDestroy` is an annotation from Common Annotations, supported by Spring to mark cleanup methods. The method is invoked during bean destruction, before the instance is removed from the container.

Example with Spring Boot 3 and Spring Framework 6:

~~~java
package com.example.store.infrastructure;

import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class CacheConnection {

    public void refresh() {
        // Use cache connection.
    }

    @PreDestroy
    public void close() {
        // Close connection or release resources.
        System.out.println("Closing cache connection");
    }
}
~~~

When the `CacheConnection` bean is managed by Spring and its scope lifecycle ends, Spring invokes the annotated `close()` method.

### Basic rules for @PreDestroy methods

The annotated lifecycle method should have an appropriate signature:

- Takes no parameters.
- Returns `void`.
- Is an instance method, not a static method.
- Declared on a Spring-managed bean.
- Contains safe cleanup work with a reasonable execution time.

The method can have any name such as `cleanup()`, `close()`, or `stopWorker()`; Spring detects it by annotation rather than by name. Example:

~~~java
@Component
public class TemporaryFileManager {
    @PreDestroy
    void removeTemporaryFiles() {
        // Clean up temporary files owned by the bean.
    }
}
~~~

In modular Java projects or environments with reflection access restrictions, ensure the framework can access the lifecycle method. Using a readable, parameterless method is safe and maintainable.

### Annotation package depends on the Spring version

An important difference between Spring generations:

| Platform | Commonly used annotation package |
|---|---|
| Spring Framework 5 / Spring Boot 2 | `javax.annotation.PreDestroy` |
| Spring Framework 6 / Spring Boot 3 | `jakarta.annotation.PreDestroy` |

Examples in this lesson use `jakarta.annotation.PreDestroy` per the Spring Boot 3 generation. If an older project still uses Spring Boot 2, use the `javax.annotation` namespace and the corresponding annotation dependency. Do not mix `javax.annotation.PreDestroy` and `jakarta.annotation.PreDestroy` in the same application expecting Spring to recognize both identically.

The annotation API must be present on the classpath. Whether it is provided out of the box or needs to be declared explicitly depends on the Spring Boot version and project dependencies.

### @PreDestroy is not the place for order-completion business logic

A destruction callback should serve releasing resources belonging to the bean, such as closing pools or stopping executors. Do not rely on this callback to:

- Send invoices or process customer payments.
- Perform critical business state transitions.
- Send notifications that the system must guarantee delivery for.
- Save a single business transaction right before shutdown.
- Execute a workflow requiring retries and confirmation from external systems.

Shutdown can be interrupted abruptly by power loss, process kill, or infrastructure failures. If an action must be guaranteed, execute it in a use case with proper transactions, persistence, retries, or message delivery; cleanup callbacks should only be a resource termination mechanism.

## 3. DisposableBean: Implementing Spring's Interface

Spring provides the `org.springframework.beans.factory.DisposableBean` interface. A bean implementing this interface must define the method:

~~~java
void destroy() throws Exception;
~~~

Example:

~~~java
package com.example.store.infrastructure;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.stereotype.Component;

@Component
public class MessageBrokerConnection implements DisposableBean {

    public void publish(String message) {
        // Send message.
    }

    @Override
    public void destroy() throws Exception {
        // Close connection to broker.
        System.out.println("Closing broker connection");
    }
}
~~~

When a container-managed bean enters the destruction phase, Spring calls `destroy()`.

### Advantages and limitations

`DisposableBean` has one clear advantage: the interface contract explicitly expresses that the bean has cleanup behavior. However, the class must depend on the Spring Framework API:

~~~java
import org.springframework.beans.factory.DisposableBean;
~~~

This couples the class more tightly to the framework. If you want to reuse the class as a plain Java component or avoid exposing Spring's lifecycle contract in a domain/infrastructure API, an annotation or a standard Java close method may be more appropriate.

`DisposableBean` is often reasonable in infrastructure classes that already depend on Spring and want to use the framework's lifecycle contract directly. For regular application classes, `@PreDestroy` is typically less intrusive.

### Do not both implement DisposableBean and call destroy manually

The container already has the responsibility of calling the callback for the bean. Do not write another place that arbitrarily calls `destroy()` while the bean is still in use, as that could close resources prematurely or cause two cleanup flows to act on the same resource.

If the class needs an explicit close API for both the container and plain Java clients, you can design a `close()` method and have the callback call it. Still, clearly define lifecycle ownership and avoid having multiple parties unsafely close the same resource.

## 4. destroyMethod: Configuring a Destroy Method in the Bean Definition

In some cases, the class is not owned by the project or should not be modified to add annotations/interfaces. Spring allows declaring a destroy method where the bean is defined.

The common approach is the `destroyMethod` attribute of `@Bean`:

~~~java
@Configuration
public class ClientConfiguration {

    @Bean(destroyMethod = "close")
    public VendorClient vendorClient() {
        return new VendorClient();
    }
}
~~~

When the ApplicationContext closes, Spring calls the `close()` method of the instance produced by the factory method, provided the bean is managed and the method is compatible.

This is a useful choice when:

- The object comes from a third-party library.
- You cannot or do not want to modify the class to add `@PreDestroy`.
- You want to declare the lifecycle right at the composition root.
- The cleanup method has a specific name such as `shutdown()` or `stop()`.

Example with a different name:

~~~java
@Bean(destroyMethod = "shutdown")
public SearchClient searchClient() {
    return new SearchClient();
}
~~~

`SearchClient` here is a hypothetical type with a parameterless `shutdown()` method suitable for invocation. The name in `destroyMethod` must match the actual cleanup method.

### Inferred close or shutdown mechanism

On `@Bean`, the default value of `destroyMethod` uses an inference mechanism. Spring can automatically detect a public method named `close` or `shutdown` to use as the destruction callback if present.

Example:

~~~java
public class ExternalResource implements AutoCloseable {
    @Override
    public void close() {
        // Release resources.
    }
}

@Configuration
public class ResourceConfiguration {
    @Bean
    public ExternalResource externalResource() {
        return new ExternalResource();
    }
}
~~~

With `@Bean`'s default configuration, Spring can infer `close` as the destroy method. This is especially convenient for classes implementing `AutoCloseable` or exposing a public `close()/shutdown()` method.

If you want to **disable destroy method inference** for that bean, you can declare an empty string:

~~~java
@Bean(destroyMethod = "")
public ExternalResource externalResource() {
    return new ExternalResource();
}
~~~

Only disable it when there is a clear reason, such as the resource's lifecycle being owned by another component or not wanting Spring to automatically call the close method. If you disable inference while the resource truly needs cleanup, make sure another cleanup mechanism exists.

### destroyMethod is not a Java method called immediately when creating the bean

`destroyMethod` is metadata in the bean definition. It specifies the callback name for the destruction phase. The method is not called when Spring creates the bean, not called after every request, and is not a command for business code to actively request closing the bean.

## 5. Comparing the Three Mechanisms

| Criterion | `@PreDestroy` | `DisposableBean` | `@Bean(destroyMethod = "...")` |
|---|---|---|---|
| Declaration | Annotation on method | Implement interface | Metadata on factory method |
| Coupling to Spring | Lower, via lifecycle annotation | Direct via Spring interface | Spring configuration |
| Modify bean class | Yes | Yes | Not necessarily |
| Suits third-party classes | Possible if annotation can be added, usually not | No if class cannot be modified/wrapped | Very suitable |
| Method name | Any | Mandatory `destroy()` | Specified name |
| Example | `@PreDestroy void close()` | `destroy()` | `@Bean(destroyMethod = "close")` |

You can choose by rule of thumb:

- Application-owned classes needing cleanup: `@PreDestroy` is usually the most readable choice.
- Infrastructure classes already depending on Spring wanting to implement the framework lifecycle contract: `DisposableBean` is an option.
- Objects provided by external libraries or wanting lifecycle kept in configuration: `destroyMethod` fits well.

There is no need to apply all three to every bean. Choose one clear way to express cleanup and avoid duplicating the same action across multiple callbacks.

## 6. Destruction Callback Order When One Bean Uses Multiple Mechanisms

Spring supports combining lifecycle callback types. For a bean that has a `@PreDestroy` method, implements `DisposableBean`, and has a custom destroy method, the typical destruction order is:

1. Methods annotated with `@PreDestroy`.
2. `DisposableBean.destroy()`.
3. Custom destroy method configured in the bean definition, e.g., `destroyMethod`.

Illustrative example:

~~~java
@Component
public class LifecycleExample implements DisposableBean {

    @PreDestroy
    public void preDestroy() {
        System.out.println("1. @PreDestroy");
    }

    @Override
    public void destroy() {
        System.out.println("2. DisposableBean.destroy()");
    }

    public void customShutdown() {
        System.out.println("3. custom destroy method");
    }
}
~~~

If using `@Bean` to register the bean, you can declare the custom method:

~~~java
@Bean(destroyMethod = "customShutdown")
public LifecycleExample lifecycleExample() {
    return new LifecycleExample();
}
~~~

This snippet shows that the mechanisms can participate together in the lifecycle. In real code, do not split a single cleanup job into three callbacks just to leverage the order. That makes resource state harder to track and can cause duplicate cleanup calls if multiple callbacks perform the same operation.

A simpler approach is having one callback coordinate a single close method, or using only one appropriate mechanism. When genuinely distinct cleanup stages are needed, name them and document the dependency order clearly.

### Destruction order among beans with dependencies

If bean A depends on bean B, Spring generally ensures the dependent bean A is destroyed before the bean it needs B, so A still has a chance to use B during cleanup. This is part of managing dependency relationships among singleton beans.

Example:

~~~text
OrderService  --->  PaymentClient
      |                   |
      | destroyed first    | destroyed later
      v                   v
cleanup OrderService  cleanup PaymentClient
~~~

Do not close `PaymentClient` directly from `OrderService` if the container also manages it. Each bean should clean up the resources it owns; the container coordinates the lifecycle along the dependency graph.

## 7. When Are Destruction Callbacks Called?

For singleton beans managed by the ApplicationContext, destruction callbacks are typically called when the context closes gracefully.

Some ways to close a context:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(StoreApplication.class, args);

// When the application needs a controlled shutdown:
context.close();
~~~

In a Java program that manages the context manually, you can use try-with-resources if the context type supports AutoCloseable:

~~~java
try (ConfigurableApplicationContext context =
             new SpringApplicationBuilder(StoreApplication.class).run(args)) {
    // Use the application or perform work.
}
// context is closed upon exiting the try block.
~~~

In a normally running Spring Boot application, Spring Boot manages the ApplicationContext and registers a shutdown hook under default configuration to close the context when the JVM terminates normally. When the context closes, managed singleton beans receive their destruction phase.

Distinguish **controlled context closure** from **forced process termination**. If the machine loses power, the container runtime kills the process without allowing shutdown to finish, or the JVM crashes, callbacks cannot be guaranteed to run. Therefore, destruction callbacks are not the sole place to persist critical state.

### What about a lazy bean that was never created?

A lazy singleton that was never initialized has no instance to clean up. Do not expect a callback to run for a bean that was never created.

### Do prototype beans have automatic destruction callbacks?

This is a particularly important point: Spring creates and configures a prototype bean and hands it over to the client, but **does not track the full lifecycle of a prototype instance after handing it off**. Consequently, Spring does not automatically invoke destruction callbacks for prototypes like singletons.

If a prototype holds resources that need closing, the client receiving the instance must take responsibility for cleanup or another lifecycle management mechanism is needed.

~~~java
ReportSession session = provider.getObject();
try {
    session.generate();
} finally {
    session.close();
}
~~~

In the example, `close()` is an API defined by the class and actively called by the consumer. Do not rely on `@PreDestroy` on a prototype to automatically release resources once references are dropped.

### Web scopes end according to their scope

For request, session, application, or WebSocket scopes supported and registered in an appropriate environment, destruction callbacks are tied to the end of the corresponding scope. For example, a request-scoped bean can be cleaned up when the HTTP request finishes; a session-scoped bean when the session is destroyed or expires per the web container mechanism.

However, web scope callbacks do not turn data into durable persistence either. If a session is lost abruptly or the server is force-stopped, callbacks cannot be treated as a guarantee of data persistence.

## 8. Practical Example: Safely Stopping an ExecutorService

A bean managing a worker pool needs to stop accepting new tasks and give running tasks an opportunity to finish.

~~~java
package com.example.store.background;

import jakarta.annotation.PreDestroy;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Component;

@Component
public class ReportWorker {

    private final ExecutorService executor =
            Executors.newFixedThreadPool(4);

    public void submit(Runnable task) {
        executor.submit(task);
    }

    @PreDestroy
    public void stop() {
        executor.shutdown();

        try {
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        } catch (InterruptedException ex) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Sequence:

1. `shutdown()` stops accepting new tasks while allowing already-submitted tasks to continue running.
2. `awaitTermination(...)` waits for a bounded period.
3. If time runs out before the pool stops, `shutdownNow()` requests stopping running tasks and returns unstarted tasks.
4. If the waiting thread is interrupted, call `shutdownNow()` and restore the interrupt flag.

There is no guarantee every task stops immediately after `shutdownNow()`; tasks must cooperate with the interruption mechanism. If work can run long, design timeouts, cancellation, and appropriate work state handling.

This example shows that cleanup callbacks should be **time-bounded**. If a shutdown callback waits indefinitely on an unresponsive external server, closing the entire context can be delayed.

## 9. Example with a Third-Party Resource and destroyMethod

Suppose an external library provides `SearchClient` with a `close()` method but no Spring annotations:

~~~java
public class SearchClient {
    public SearchClient(String endpoint) {
        // Open connection pool.
    }

    public void search(String query) {
        // ...
    }

    public void close() {
        // Close connection pool.
    }
}
~~~

Bean registration:

~~~java
@Configuration
public class SearchConfiguration {

    @Bean(destroyMethod = "close")
    public SearchClient searchClient(
            SearchSettings settings
    ) {
        return new SearchClient(settings.endpoint());
    }
}
~~~

Service using the client via constructor:

~~~java
@Service
public class SearchService {
    private final SearchClient searchClient;

    public SearchService(SearchClient searchClient) {
        this.searchClient = searchClient;
    }
}
~~~

Spring creates `SearchClient` via the factory method, injects it into `SearchService`, and when the context closes calls `close()` per the destroy method metadata.

The service does not need to hold `ApplicationContext` to fetch the client itself, nor does it need to close the client itself. The bean definition owns the lifecycle configuration; the consumer just uses the dependency.

If `SearchClient` has a public `close()` and Spring infers the destroy method by default, explicitly writing `destroyMethod = "close"` may not be required. Explicit declaration is still valuable when clarifying intent or when the method name is outside the default inference group.

## 10. AutoCloseable and Closeable in Java

Java provides standard interfaces for resources needing closure:

- `AutoCloseable` defines `close()` which may throw `Exception`.
- `Closeable` extends `AutoCloseable` and is commonly used for I/O resources, with `close()` throwing `IOException`.

A bean implementing `AutoCloseable` normally works well with `@Bean`'s `close` inference mechanism:

~~~java
public class ReportArchive implements AutoCloseable {

    @Override
    public void close() throws IOException {
        // Close stream or file resource.
    }
}
~~~

~~~java
@Configuration
public class ArchiveConfiguration {
    @Bean
    public ReportArchive reportArchive() throws IOException {
        return new ReportArchive();
    }
}
~~~

Under default `@Bean` configuration, Spring can infer the `close()` method as the destroy method. If you want to be explicit:

~~~java
@Bean(destroyMethod = "close")
public ReportArchive reportArchive() {
    return new ReportArchive();
}
~~~

Differences between Java resource management and Spring lifecycle:

- `try-with-resources` closes a resource at the end of its usage block.
- Spring destroy callbacks close a bean when the bean/container lifecycle ends.
- An object created with `new` inside a method can still use try-with-resources, even if it is not a bean.
- A Spring-managed bean should not necessarily be closed manually by individual consumers; doing so can break other consumers using the same singleton.

Choose the mechanism based on **who owns the lifecycle**. If a singleton bean shares a resource, the container is usually the right place to manage closing that resource.

## 11. Distinguishing Destroy Callbacks from SmartLifecycle

`@PreDestroy`, `DisposableBean`, and `destroyMethod` serve destruction callbacks. However, some background components need an ordered start/stop process, coordination with other components, or support for stopping before the container closes completely.

Spring has the `Lifecycle` and `SmartLifecycle` interfaces for managing the lifecycle of components capable of starting/stopping. `SmartLifecycle` also supports phases to coordinate start/stop order and an auto-start mechanism.

Conceptual example:

~~~java
@Component
public class EventConsumer implements SmartLifecycle {

    private volatile boolean running;

    @Override
    public void start() {
        // Start receiving events.
        running = true;
    }

    @Override
    public void stop() {
        // Stop receiving events and halt processing.
        running = false;
    }

    @Override
    public boolean isRunning() {
        return running;
    }
}
~~~

The simplified example does not implement a real safe stopping mechanism; a real consumer needs to stop receiving messages, wait for in-flight processing, handle timeouts, and close the client. `SmartLifecycle` fits better when operational sequencing needs managing; destruction callbacks remain useful for releasing final resources.

Start/stop lifecycles and destruction callbacks can be combined, while avoiding calling the same closing operation twice. Design should maintain state or make cleanup operations idempotent so repeated calls do not corrupt resources.

## 12. Cleanup Should Be Idempotent and Bounded

In practice, stopping an application can occur after an error or a complex shutdown sequence. A good cleanup method should be designed to be safe for repeated calls whenever possible:

~~~java
@Component
public class ManagedConnection {

    private Connection connection;
    private boolean closed;

    @PreDestroy
    public synchronized void close() {
        if (closed) {
            return;
        }

        closed = true;

        if (connection != null) {
            try {
                connection.close();
            } catch (SQLException ex) {
                // Log appropriately.
            }
        }
    }
}
~~~

This example illustrates the idea of idempotency, not the optimal connection management approach for every application. If a connection is provided by a pool, the consuming bean generally should not close the pool; it should only return the connection to the pool. The bean owning the pool is what closes the pool when the context stops.

Useful cleanup principles:

- Only close resources that the bean genuinely owns.
- Do not close a shared singleton dependency just because one consumer stops operating.
- Stop accepting new work before waiting for in-progress work to finish.
- Use timeouts for network calls or waiting on threads.
- Restore the interrupt flag if catching `InterruptedException` without rethrowing it.
- Log cleanup errors sufficiently for operations to investigate, while avoiding logging secrets.
- Design callbacks to be safe when state is already closed or initialization did not complete.
- Do not depend on callbacks to guarantee persisting critical business data.

### Shutdown hooks and application stop time

Spring Boot has a mechanism to close the ApplicationContext on normal JVM shutdown. However, deployment platforms may send a stop signal and only grant the process a limited window before killing it. Therefore, cleanup callbacks must complete within a reasonable time.

If the application runs in a container or orchestrator, align the platform's graceful shutdown period with the internal application cleanup time. Never make a callback wait indefinitely on an operation.

## 13. Things Not to Do in Destroy Callbacks

### Do not call critical business APIs assuming they always succeed

Example you should not rely on:

~~~java
@PreDestroy
public void destroy() {
    paymentService.captureAllPendingPayments();
}
~~~

Shutdown is not a business transaction. If the process is killed, the call may not run; if the external API fails, there is no reliable retry mechanism from the callback alone. Process payments in a business flow and save recoverable state.

### Do not block indefinitely

~~~java
@PreDestroy
public void close() {
    remoteClient.waitUntilServerRespondsForever();
}
~~~

An unbounded callback can prevent the context from finishing closure. Use timeouts and fallback strategies.

### Do not manually close container-owned dependencies

If `OrderService` and `InvoiceService` both use a singleton `DatabaseClient`, having `OrderService` close the client when destroyed can cut `InvoiceService`'s connection before it gets cleaned up.

Each bean should release resources it owns. The container manages lifecycle order among beans based on dependencies.

### Do not look up new dependencies during destruction unnecessarily

Destruction callbacks should use already-provided dependencies and bean-owned resources. Avoid calling `ApplicationContext.getBean` to locate another bean right while the context is closing; that dependency may already be destroyed or no longer available.

### Do not assume callbacks always run

Forced shutdowns, crashes, power loss, and certain runtime failures can skip cleanup. Data requiring durability must be persisted during normal operation rather than waiting for bean destruction.

## 14. Testing Destroy Callbacks

To test a callback, create the bean in a real context and close that context. Example with a small context:

~~~java
class CleanupProbe {
    private boolean closed;

    @PreDestroy
    public void close() {
        closed = true;
    }

    public boolean isClosed() {
        return closed;
    }
}
~~~

~~~java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();

context.registerBean(CleanupProbe.class);
context.refresh();

CleanupProbe probe = context.getBean(CleanupProbe.class);

context.close();

// After the context closes, probe.isClosed() is expected to be true.
~~~

This example shows the callback is tied to closing the context. In real tests, you can use a probe with a flag or a mock to verify the cleanup method was called.

### Testing @Bean destroyMethod

You can register a bean with a `close()` or `shutdown()` method, close the context, and assert that resource state was released. This verifies the destroy method configuration is actually applied by Spring.

### Testing prototypes

If a test retrieves a prototype bean, do not expect `context.close()` to automatically invoke destruction callbacks for every handed-out prototype instance. Verify and clean up manually per the object's contract.

### Testing a Spring Boot context

With `@SpringBootTest`, Spring Test typically caches the ApplicationContext across test classes. Thus, the context does not close and destroy callbacks do not run after every test method. If you need to test context-closing lifecycles in tests, use a dedicated context or an appropriate `@DirtiesContext` mechanism to mark that the context needs closing after the test.

Do not write tests relying on arbitrary cleanup order across an entire suite. Creating a small, isolated context makes lifecycle verification much more predictable.

## 15. Which Mechanism to Choose in Each Scenario?

| Scenario | Typically appropriate approach | Reason |
|---|---|---|
| Project-owned service needing to stop a scheduler | `@PreDestroy` | Declared right on the bean, no need to implement a Spring interface |
| Bean already depending on Spring wanting to use the framework's destroy contract | `DisposableBean` | The `destroy()` method is an explicit contract |
| Third-party SDK with `close()` | `@Bean(destroyMethod = "close")` or default inference | No need to modify library class |
| Bean with a dedicated `shutdown()` method | `@Bean(destroyMethod = "shutdown")` | Specifies callback name in configuration |
| Background component needing ordered start/stop | `SmartLifecycle`, possibly combined with cleanup | Provides richer lifecycle semantics than a single destroy callback |
| Object created and used within a short block | `try-with-resources` | Lifecycle stays within the using code's scope |
| Prototype holding resources | Explicit close/factory API or dedicated ownership mechanism | Container does not automatically clean up prototypes after handing them out |

A good choice usually has these characteristics:

- Declared where resource ownership is easy to identify.
- Only one place is responsible for closing the resource.
- Does not require business services to look up the context for cleanup.
- Has timeouts and proper error handling.
- Easy to test by closing the context or calling the close contract in a controlled manner.

## 16. Practice Exercise

Suppose a Spring Boot application has three beans:

- `ReportScheduler` creates scheduled tasks and needs to stop the scheduler.
- `VendorClient` comes from an external library and has a `close()` method.
- `TemporaryExport` is a prototype bean holding a temporary file for each export.

Choose the cleanup approach:

1. For `ReportScheduler`, you can use `@PreDestroy` to stop accepting new tasks, wait for running tasks for a bounded time, and then shut down the executor.
2. For `VendorClient`, declare with `@Bean(destroyMethod = "close")` or rely on close/shutdown inference if appropriate.
3. For `TemporaryExport`, the caller receiving the prototype instance must take responsibility for closing the file after export; do not expect Spring to automatically call a callback when the context closes.

Continue analyzing:

- If `ReportScheduler` uses `VendorClient`, the scheduler must stop before the client closes. Dependency relationships and container destruction order can help coordinate if dependencies are declared properly.
- If an export fails midway, the temporary file still needs to be closed or deleted via `finally`/try-with-resources.
- If the application is force-killed, cleanup callbacks may not finish; critical data must be protected during processing rather than waiting for shutdown.

## 17. Principles to Remember

1. **`@PreDestroy` marks a cleanup method on a Spring-managed bean.** The method takes no parameters, returns void, and is called during the destruction phase.
2. **`DisposableBean` is Spring's contract.** Implement `destroy()` if the class wants to participate directly in the lifecycle interface.
3. **`destroyMethod` belongs to the bean definition.** Useful for third-party objects or when wanting to declare cleanup method names in configuration.
4. **`@Bean` has close/shutdown inference.** You can explicitly specify a method or use `destroyMethod = ""` to disable inference when there is a reason.
5. **Callback order within a bean can be combined:** `@PreDestroy`, `DisposableBean.destroy()`, then custom destroy method.
6. **Singletons are cleaned up on controlled context closure.** Prototypes do not receive full Spring-managed destruction automatically after being handed to callers.
7. **Cleanup does not replace durable business logic.** Callbacks may not run if a process is killed; do not use them as the sole place to process payments or save critical state.
8. **Only close resources owned by the bean.** Do not manually close shared dependencies still managed by the container.
9. **Use SmartLifecycle when start/stop coordination is needed.** A single destroy callback does not replace the full lifecycle of a complex background worker.
10. **Test by closing a real context.** Do not assume a cached context in Spring Test closes after every test method.

## Conclusion

`@PreDestroy`, `DisposableBean`, and `destroyMethod` all help Spring perform cleanup when a bean reaches the end of its lifecycle, yet they express intent in different places. The annotation fits application-owned classes; the interface is a direct Spring contract; destroy methods allow configuring cleanup for objects created via factory methods, which is especially useful for external libraries.

Identify which resources each bean owns, what its scope is, when the container ends that scope, and who is responsible for closing resources. Destruction callbacks should be concise, time-bounded, safe when state is incomplete, and free of critical guaranteed business logic. When lifecycle ownership is expressed clearly, Spring Boot shutdown becomes predictable and the system is less prone to resource leaks.
