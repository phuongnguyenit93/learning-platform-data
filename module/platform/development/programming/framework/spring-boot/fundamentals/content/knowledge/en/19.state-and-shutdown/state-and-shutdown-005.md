# Shutdown Hooks, Context Closing, and Bean Destruction

A Spring Boot application does not only have a startup process. When the process needs to terminate, the application must also stop accepting new work, allow in-flight work to finish within a reasonable limit, close connections, and release resources. Skipping this stage can cause an application to lose buffered logs, abort a request mid-flight, leave connections open, or prevent external systems from knowing a consumer has stopped.

Spring Boot coordinates shutdown through the **JVM shutdown hook**, **closing `ApplicationContext`**, **lifecycle components**, and **bean destruction callbacks**. These mechanisms are related yet serve distinct roles:

- A *shutdown hook* is the entry point the JVM invokes when the process terminates along a normal shutdown path.
- *`ApplicationContext.close()`* tells the Spring container to close, emit events, and process the lifecycle of the beans it manages.
- *`SmartLifecycle`* gives background components or web servers an opportunity to stop in order before singletons are destroyed.
- *`@PreDestroy`*, `DisposableBean.destroy()`, and `@Bean(destroyMethod = "...")` release resources owned by each bean.

Key point: **the JVM shutdown hook is only one way to trigger context closure**. Application code can also call `close()` directly; conversely, a forcefully terminated process may never get a chance to run cleanup. This lesson traces from process termination events down to bean destruction order, followed by hands-on practice with a Spring Boot 3.3 and Java 21 application.

## 1. The Big Picture When Spring Boot Shuts Down

When an application is launched via `SpringApplication.run(...)`, Boot registers a shutdown hook with the JVM by default. During a normal JVM shutdown, the hook executes and requests closing the registered context.

General flow:

~~~mermaid
flowchart TD
    A["JVM begins normal shutdown"] --> B["Spring Boot shutdown hook runs"]
    B --> C["Close ApplicationContext"]
    C --> D["Publish ContextClosedEvent"]
    D --> E["LifecycleProcessor stops Lifecycle / SmartLifecycle"]
    E --> F["Destroy singleton beans in dependency order"]
    F --> G["@PreDestroy / DisposableBean / destroy method"]
    G --> H["Close bean factory and complete context"]
    H --> I["Process can exit"]
    J["Code calls context.close()"] --> C
~~~

This is the general flow for a normally closed context. Detailed ordering among independent beans, how a web server drains requests, and wait deadlines depend on lifecycle configuration.

Two types of ordering must be distinguished:

1. **Order of stopping running components**: determined by `LifecycleProcessor`, `SmartLifecycle` phases, and dependencies.
2. **Order of destroying beans**: determined by the container and dependency graph; each bean's destruction callbacks belong to this stage.

A `@PreDestroy` does not replace stopping a listener that is actively receiving messages. If a listener must stop accepting work before closing resources, design those two steps with the appropriate lifecycle APIs.

## 2. What Is a Shutdown Hook?

The JVM allows registering special threads via `Runtime.getRuntime().addShutdownHook(...)`. When the JVM enters an orderly shutdown sequence, registered hooks get a chance to run cleanup work.

Plain Java example:

~~~java
public class PlainJavaShutdown {
    public static void main(String[] args) {
        Runtime.getRuntime().addShutdownHook(
                new Thread(() -> System.out.println("JVM is shutting down"))
        );

        System.out.println("Application started");
    }
}
~~~

In a standard Spring Boot application, you **do not need to create your own hook just to call `ApplicationContext.close()`**. `SpringApplication` already registers a hook for the context by default.

### 2.1. When Does a Shutdown Hook Get a Chance to Run?

Situations that typically cause the JVM to begin an orderly shutdown:

- Code calls `System.exit(...)`.
- The Java process receives a normal termination signal such as `SIGTERM` in supported environments.
- The user presses Ctrl+C in the console, if the JVM receives the interrupt signal along the normal shutdown path.
- A process manager sends a stop signal that the JVM can handle.
- The JVM exits via normal shutdown when no non-daemon threads remain.

On Windows machines, how an IDE or terminal stops a process can differ from Linux. Do not assume every "Stop" button in an IDE produces the same lifecycle sequence.

### 2.2. Cases Where Hooks May Not Run

Shutdown hooks are a **best-effort** mechanism, not a guarantee that cleanup runs every time a process disappears.

| Termination method | Can hooks be expected to run? | Notes |
| --- | --- | --- |
| `System.exit(0)` | Normally yes | JVM enters shutdown sequence |
| Normal `SIGTERM` | Normally yes | Standard for many deployment systems |
| Ctrl+C in console | Usually yes | Depends on how console and JVM receive the signal |
| `SIGKILL` / `kill -9` | No | OS terminates the process forcefully |
| `Runtime.getRuntime().halt(...)` | No | Bypasses shutdown hook sequence |
| Power loss, container forcefully killed | Not guaranteed | Cannot rely on final callbacks |
| Severe JVM crash | Not guaranteed | Process may lose ability to run cleanup |

Therefore, never put an operation that is the **sole guarantee of persisting critical data** inside `@PreDestroy` or a shutdown hook. State requiring durability must be written while the application is running, using transactions, acknowledgments, checkpoints, or corresponding mechanisms.

### 2.3. Do Not Rely on Ordering Between Different JVM Hooks

Multiple libraries may register their own shutdown hooks. The JVM does not provide a predictable sequential order across hooks: they may start executing concurrently.

If two resources must stop in a deterministic order, manage them within the same Spring context and lifecycle/dependency graph. Avoid creating multiple independent shutdown hooks and expecting hook A to always finish before hook B.

## 3. How Does SpringApplication Register the Hook?

Familiar startup:

~~~java
package com.example.shutdown;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShutdownDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShutdownDemoApplication.class, args);
    }
}
~~~

By default, Spring Boot registers a shutdown hook to close `ApplicationContext` when the JVM terminates. Standard Spring lifecycle callbacks are invoked while closing the context.

You can control hook registration when instantiating `SpringApplication` yourself:

~~~java
SpringApplication application =
        new SpringApplication(ShutdownDemoApplication.class);

application.setRegisterShutdownHook(false);

ConfigurableApplicationContext context = application.run(args);
~~~

The example only demonstrates the configuration API. **If you disable the hook**, the code owning the context must ensure it closes the context at the right time. Otherwise, infrastructure beans may not receive destruction callbacks along the normal path.

In most Spring Boot web applications, keep the default. Disable it only when another lifecycle owner is explicitly designed, such as a test harness or an embedded Spring context where the host actively calls `close()`.

### 3.1. Should You Add Your Own Runtime Shutdown Hook?

Not needed for a typical Boot application:

~~~java
// Avoid creating a second hook just to close the same context.
Runtime.getRuntime().addShutdownHook(
        new Thread(context::close)
);
~~~

An extra hook can cause confusion over who owns the context, cleanup ordering, and duplicate closing. If you want to execute an action when the Spring context closes, use `ContextClosedEvent`, `SmartLifecycle`, or bean destruction callbacks as appropriate.

### 3.2. Shutdown Hooks Do Not Keep an Application Running

Hooks only run when the JVM **is shutting down**. A hook is not a non-daemon worker keeping the process alive. A batch application with no other non-daemon threads can finish on its own and the JVM will execute hooks.

In Java 21 configurations using virtual threads, those threads are daemon threads; using virtual threads alone does not keep the JVM running. For applications that need to keep the process alive, use appropriate Spring Boot lifecycle mechanisms instead of treating shutdown hooks as permanent workers.

## 4. Closing ApplicationContext Programmatically

`ApplicationContext` is the abstraction for reading beans and accessing container services. The `ConfigurableApplicationContext` interface adds lifecycle management operations such as `refresh()`, `start()`, `stop()`, and `close()`.

A CLI application can explicitly open and close the context:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.ConfigurableApplicationContext;

public class CliLauncher {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(CliConfiguration.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setRegisterShutdownHook(false);

        try (ConfigurableApplicationContext context =
                     application.run(args)) {
            ImportService service = context.getBean(ImportService.class);
            service.importData();
        } // Automatically calls context.close(), even if importData throws an exception.
    }
}
~~~

The example assumes `CliConfiguration` and `ImportService` are defined by the application. `ConfigurableApplicationContext` implements `AutoCloseable`, so it can be used in `try-with-resources`.

For web applications that need to serve HTTP long-term, **do not put the context in a `try-with-resources` block that ends right after `run()`**; doing so will close the web server immediately after startup finishes. The context must remain alive until the application is actually requested to stop.

### 4.1. Are close() and stop() the Same?

No.

| Operation | Meaning |
| --- | --- |
| `context.start()` | Sends start signal to beans participating in `Lifecycle` |
| `context.stop()` | Sends stop signal to `Lifecycle` beans; context is not fully closed yet |
| `context.close()` | Closes context, emits close event, stops lifecycle, and destroys singletons |
| `context.isActive()` | Indicates whether the context is active according to its lifecycle |
| `System.exit(code)` | Requests JVM termination; hooks may close context if registered |

`context.stop()` is not equivalent to destruction. A bean's `@PreDestroy` **is not invoked just because of context.stop()**. When the context is started again, some lifecycle components can resume operating per their contract.

`context.close()` is the operation that ends the context's lifecycle. Once closed, do not continue accessing beans as if the context were still active or assume you can arbitrarily refresh that context again.

### 4.2. Can close() Be Called Multiple Times?

Spring has lifecycle guards when closing a context. Still, application cleanup callbacks should be written to be **safe if resources are already closed** and avoid races between shutdown hooks, tests, and workers. Do not intentionally call close in multiple places just "to be safe"; establish one clear lifecycle owner.

## 5. Sequence Inside ApplicationContext.close()

In a standard Spring context, the closing phase follows this general order:

1. Spring checks that the context is active and begins the closing sequence.
2. Publishes `ContextClosedEvent`.
3. Asks `LifecycleProcessor` to stop components participating in lifecycle.
4. Destroys singleton beans, respecting the dependency graph.
5. Closes the bean factory and completes context cleanup.
6. The context is no longer usable as an active container.

Diagram:

~~~mermaid
sequenceDiagram
    participant Caller as JVM hook / caller
    participant Context as ApplicationContext
    participant Events as Event listeners
    participant Life as LifecycleProcessor
    participant Beans as Singleton bean registry
    Caller->>Context: close()
    Context->>Events: ContextClosedEvent
    Events-->>Context: Listener callbacks finish
    Context->>Life: onClose()
    Life->>Life: Stop SmartLifecycle / Lifecycle by phase
    Life-->>Context: Stop completes or phase timeout expires
    Context->>Beans: destroySingletons()
    Beans->>Beans: Destroy dependents before dependencies
    Beans-->>Context: Destruction callbacks finish
    Context-->>Caller: Context closed
~~~

Do not deduce that all background tasks are guaranteed to finish before the destroy step just because the close event fired. That depends on how `SmartLifecycle.stop(...)`, executors, listener containers, and timeouts are implemented.

### 5.1. When Is ContextClosedEvent Published?

`ContextClosedEvent` is a Spring Framework event published when the context begins closing, **before the phase of stopping lifecycle beans and destroying singletons finishes**.

Example:

~~~java
package com.example.shutdown;

import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ShutdownEventLogger {

    @EventListener
    public void onContextClosed(ContextClosedEvent event) {
        System.out.println(
                "Closing context: " + event.getApplicationContext().getId()
        );
    }
}
~~~

Use the event for observation, logging, intra-process notifications, or short, controlled reactions. Do not use the event listener to invoke many services, request creating new beans, or run a long network call. The context is already closing and some dependencies may be about to stop.

### 5.2. ContextStoppedEvent vs. ContextClosedEvent

`ContextStoppedEvent` can be published when a context is `stop()`ped. It indicates a lifecycle stop signal without destroying all beans.

`ContextClosedEvent` indicates a context close. Singleton destruction callbacks belong to the `close()` path, not `stop()` alone.

If the requirement is pausing a consumer while keeping the context alive, use the component's start/stop API. If the requirement is releasing all application resources, close the context.

## 6. Destroying Beans with @PreDestroy

`@PreDestroy` marks a method to be called by Spring during the destruction phase of a container-managed bean. With Spring Boot 3.x and the Jakarta namespace, import:

~~~java
import jakarta.annotation.PreDestroy;
~~~

Example of a bean owning a resource:

~~~java
package com.example.shutdown;

import jakarta.annotation.PreDestroy;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

@Component
public class LocalResourceManager {
    private final AtomicBoolean closed = new AtomicBoolean(false);

    public void useResource() {
        if (closed.get()) {
            throw new IllegalStateException("Resource is closed");
        }
        // Operate on the resource.
    }

    @PreDestroy
    public void cleanup() {
        if (closed.compareAndSet(false, true)) {
            System.out.println("Releasing LocalResourceManager");
            // Close file handle, connection, or bean-owned resource.
        }
    }
}
~~~

The cleanup method is called when this singleton bean is destroyed during context closure. `AtomicBoolean` illustrates making cleanup idempotent; real code must also ensure no other threads continue using the resource after closing.

### 6.1. What Should Be Done in @PreDestroy?

Appropriate tasks include:

- Closing streams or resources directly owned by the bean.
- Closing a client or adapter when no separate lifecycle mechanism exists.
- Flushing buffers within a bounded time limit.
- Unregistering listeners/registrations created by the bean.
- Writing a brief diagnostic log entry.

Do not place critical business logic that only runs at JVM exit inside this method. Callbacks may not run if the process is forcefully killed.

### 6.2. @PreDestroy Methods Take No Parameters

A `@PreDestroy` annotated method normally takes no parameters and returns `void`. Do not expect Spring to inject services or shutdown events as parameters to this method.

If a dependency is needed during cleanup, inject it via the constructor when creating the bean and manage destruction order through dependency relationships.

### 6.3. Is @PreDestroy Called for Every Bean?

No. Destruction callbacks apply to beans that the container actually manages in scopes with corresponding destruction lifecycles. For singletons created and still in the context at close time, Spring invokes destruction callbacks per contract.

For prototypes, Spring manages creation and initialization but **does not automatically call destruction callbacks** after handing the instance to the caller. The caller or an appropriate owner must clean up.

For request/session scoped beans, the target's lifecycle and destruction callbacks belong to that scope; they are not equivalent to a singleton living until the application context closes.

## 7. DisposableBean and @Bean(destroyMethod)

Beyond `@PreDestroy`, Spring supports other ways to declare cleanup.

### 7.1. DisposableBean

A bean can implement Spring's interface:

~~~java
import org.springframework.beans.factory.DisposableBean;

public class RemoteConnection implements DisposableBean {
    private boolean open = true;

    @Override
    public void destroy() {
        if (open) {
            open = false;
            // Release external connection.
        }
    }
}
~~~

When the bean is destroyed by the container, Spring calls `destroy()`. This makes lifecycle explicit, yet couples the class directly to Spring Framework. For business code or plain Java libraries, `@PreDestroy` or a regular close method is often more reusable.

### 7.2. @Bean(destroyMethod = "close")

When creating an object from a third-party library whose source you do not control, specify the destroy method in Java configuration:

~~~java
public class ExternalClient implements AutoCloseable {
    private boolean open = true;

    public String fetch() {
        if (!open) {
            throw new IllegalStateException("Client is closed");
        }
        return "data";
    }

    @Override
    public void close() {
        open = false;
        // Release resources.
    }
}
~~~

Register the bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean(destroyMethod = "close")
    ExternalClient externalClient() {
        return new ExternalClient();
    }
}
~~~

When the context destroys the `externalClient` singleton, Spring invokes `close()` according to metadata. The `ExternalClient` class remains plain Java.

### 7.3. Inferring close/shutdown for @Bean Methods

For `@Bean` in Java configuration, Spring can by default **infer** destruction methods such as `close` or `shutdown`; `AutoCloseable` or `Closeable` implementations are also supported.

Example:

~~~java
@Bean
ExternalClient externalClient() {
    return new ExternalClient();
}
~~~

If `ExternalClient` has a recognized close method, Spring can invoke it upon bean destruction without explicitly declaring `destroyMethod = "close"`.

When you want to disable destruction method inference for a special bean:

~~~java
@Bean(destroyMethod = "")
ExternalClient externallyManagedClient() {
    return externallyOwnedClient;
}
~~~

Use this only if the resource is **genuinely managed elsewhere**. Suppressing the callback without a replacement owner creates a resource leak risk.

### 7.4. Callback Order Within a Single Bean

If a single bean declares multiple destruction hooks, the typical order is:

1. `@PreDestroy` method.
2. `DisposableBean.destroy()`.
3. Configured custom destroy method.

For instance, a class that has `@PreDestroy`, implements `DisposableBean`, and declares a custom `close` may receive multiple callbacks during a single destruction. If all three close the same resource, you might accidentally release it repeatedly.

Pick one primary mechanism or have cleanup methods delegate to an idempotent operation. Do not declare multiple callbacks just "to be sure it gets called".

## 8. Destruction Order Between Beans

If bean A depends on bean B, A normally needs to be destroyed **before** B so B remains usable during A's cleanup.

Example:

~~~java
@Component
public class ConnectionManager {
    @PreDestroy
    public void close() {
        System.out.println("ConnectionManager closed");
    }
}

@Component
public class ReportConsumer {
    private final ConnectionManager manager;

    public ReportConsumer(ConnectionManager manager) {
        this.manager = manager;
    }

    @PreDestroy
    public void close() {
        System.out.println("ReportConsumer closed");
    }
}
~~~

The constructor relationship lets Spring know `ReportConsumer` depends on `ConnectionManager`. For two container-managed singletons, dependent `ReportConsumer` is destroyed before dependency `ConnectionManager`.

~~~mermaid
flowchart LR
    A["Initialize: ConnectionManager"] --> B["Initialize: ReportConsumer"]
    C["Destroy: ReportConsumer"] --> D["Destroy: ConnectionManager"]
~~~

### 8.1. @DependsOn When the Relationship Is Only Ordering

Sometimes a bean does not hold a reference to another bean yet requires an initializer to be ready beforehand. You can declare:

~~~java
@Component("providerRegistry")
public class ProviderRegistry {
    @PostConstruct
    void initialize() {
        // Register provider in legacy library.
    }

    @PreDestroy
    void shutdown() {
        // Unregister provider after dependents have closed.
    }
}

@Component
@DependsOn("providerRegistry")
public class LegacyClient {
    @PreDestroy
    void close() {
        // Client must close before providerRegistry is destroyed.
    }
}
~~~

`@DependsOn` forces `providerRegistry` to initialize before `LegacyClient` and lets Spring record the reverse destruction order for singletons. It does not inject a reference.

If the client actually needs to call the registry's API, constructor injection is usually clearer. If there is only a side-effect ordering requirement, `@DependsOn` is the right tool.

### 8.2. Do Not Rely on Accidental Ordering of Independent Beans

Two unrelated singletons may happen to be destroyed in some observed order in one run, but never treat that as a fixed business contract.

If A's cleanup requires B to still be alive, express the dependency relationship explicitly. Never infer container guarantees from class names, file declaration order, or log order.

## 9. SmartLifecycle: Stopping Work Before Destroying Resources

Many components do not just hold resources; they **actively run**: consumers listening for messages, schedulers, embedded servers, polling threads, or integration endpoints.

If `@PreDestroy` simply closes a connection while a worker is still processing messages, errors can occur. Spring provides `Lifecycle` and `SmartLifecycle` to manage components capable of starting and stopping.

`SmartLifecycle` belongs to package:

~~~java
import org.springframework.context.SmartLifecycle;
~~~

Key methods:

| Method | Meaning |
| --- | --- |
| `start()` | Starts the component |
| `stop()` | Stops the component per the `Lifecycle` contract |
| `stop(Runnable callback)` | Stops and notifies the lifecycle processor when finished |
| `isRunning()` | Current running state of the component |
| `isAutoStartup()` | Whether to start automatically on context refresh |
| `getPhase()` | Phase controlling start/stop order |

### 9.1. Small Worker Example

~~~java
package com.example.shutdown;

import jakarta.annotation.PreDestroy;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class MessagePollingWorker implements SmartLifecycle {

    private final AtomicBoolean running = new AtomicBoolean(false);

    @Override
    public void start() {
        running.set(true);
        System.out.println("Worker started");
    }

    @Override
    public void stop() {
        running.set(false);
        System.out.println("Worker stopped");
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
            // In a real worker, wait for in-flight tasks to finish
            // within the allowed limit before calling callback.
        } finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 100;
    }

    @PreDestroy
    public void releaseResources() {
        System.out.println("Worker resources released");
    }
}
~~~

This is a skeleton illustrating callback ordering; it does not create a real executor or message consumer. In a real worker, `running.set(false)` only flips a flag and is not enough to wait for active tasks. Real stopping must stop accepting new work and finish or cancel existing work per the system's contract.

When closing the context, `SmartLifecycle` stopping occurs before `@PreDestroy`. That gives the component a chance to halt activity before resources are released.

### 9.2. Must Invoke the Callback When stop(Runnable) Finishes

`stop(Runnable callback)` enables asynchronous coordination. Once a component finishes stopping, it must call `callback.run()` to notify `LifecycleProcessor`.

If the callback is never invoked, the container may have to wait until the phase timeout expires. If called too early, Spring may move on to stopping other components or destroying beans while the worker is still processing.

A sensible asynchronous design:

~~~java
@Override
public void stop(Runnable callback) {
    stopAcceptingNewMessages();

    drainExecutor.execute(() -> {
        try {
            waitForInFlightMessages();
        } finally {
            running.set(false);
            callback.run();
        }
    });
}
~~~

This is method-level pseudocode: `stopAcceptingNewMessages()`, `drainExecutor`, and `waitForInFlightMessages()` must be defined in a real implementation. Avoid scheduling cleanup work on the very executor about to shut down if it might reject tasks.

### 9.3. SmartLifecycle Phase

Components with lower phases usually **start before** higher phases and **stop after** higher phases. On shutdown, higher phases are processed before lower phases.

Example:

| Component | Phase | Start | Stop |
| --- | ---: | --- | --- |
| Connection manager | 0 | Earlier | Later |
| Message consumer | 100 | Later | Earlier |

If the consumer needs the connection manager to remain active while stopping, the scheme above makes sense. Beyond phase, Spring also considers dependency/`@DependsOn` relationships among lifecycle beans.

Do not assign phases arbitrarily to every service. Use them only when components have clear start/stop lifecycles and ordering genuinely matters.

## 10. Graceful Shutdown for HTTP Servers

For web applications, shutdown is not just closing Spring beans. The server may be handling requests; an important response might not be complete yet when the process receives a stop command.

Spring Boot 3.3 supports **graceful shutdown** for popular embedded web servers, including Servlet and Reactive stacks. With Boot 3.3, enable it via configuration:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Equivalent in properties:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

In Boot 3.3, `server.shutdown=graceful` is the property required to enable web server graceful shutdown. In other Boot versions, defaults may change, so verify against your exact project version.

### 10.1. What Does Graceful Shutdown Do?

When the context closes, Spring Boot stops the web server via the lifecycle mechanism. When graceful shutdown is enabled, the web server attempts to:

1. Stop accepting new requests or reject new requests according to what the server supports.
2. Allow in-flight requests to finish within the configured grace period.
3. Continue the lifecycle stop sequence and bean destruction after the wait period ends.

~~~mermaid
sequenceDiagram
    participant Platform as Process manager
    participant Boot as Spring Boot
    participant Server as Web server
    participant Request as In-flight request
    Platform->>Boot: SIGTERM / shutdown
    Boot->>Boot: close context
    Boot->>Server: Graceful stop
    Server->>Server: Stop accepting new requests
    Request->>Server: Completes within grace period
    Server-->>Boot: Stop completes or times out
    Boot->>Boot: Destroy singleton beans
    Boot-->>Platform: Process exits
~~~

How new requests are rejected varies by server. For example, Tomcat, Jetty, and Reactor Netty generally stop accepting at the network layer; Undertow may return HTTP 503 for new connections during shutdown.

### 10.2. Timeout per Shutdown Phase

The `spring.lifecycle.timeout-per-shutdown-phase` property sets the wait deadline for `SmartLifecycle` phases. In the example, each phase is allowed a corresponding stop window according to Spring's mechanism.

It is not a guarantee that the entire process will exit in exactly 20 seconds. Other parts such as event listeners, destruction callbacks, or custom cleanup code can consume additional time. The process manager or orchestration system may also enforce its own timeout.

Choose timeouts based on actual request/job durations rather than setting huge values to hide a task that lacks a proper stop mechanism.

### 10.3. Graceful Shutdown Does Not Guarantee Every Request Finishes

A request may exceed the grace period, an external dependency may hang, or a client may disconnect. Applications still need proper idempotency, timeouts, transaction boundaries, and retries.

In particular, do not rely on HTTP graceful shutdown to guarantee a payment event is durably saved. Data persistence and business acknowledgment must be guaranteed independently of process shutdown.

## 11. Shutdown in Containers and Kubernetes

When running in Docker or Kubernetes, shutdown occurs across multiple layers:

~~~mermaid
flowchart TD
    A["Orchestrator decides to stop instance"] --> B["Stop routing / update readiness"]
    B --> C["Send termination signal to process"]
    C --> D["JVM shutdown hook closes Spring context"]
    D --> E["Graceful stop and destruction callbacks"]
    E --> F{"Stopped within grace period?"}
    F -->|Yes| G["Process exits cleanly"]
    F -->|No| H["Orchestrator forcefully terminates"]
~~~

The exact order of readiness, endpoint removal, and signal delivery depends on platform, configuration, and propagation delays. Do not assume that every load balancer stops sending traffic the instant shutdown begins.

### 11.1. SIGTERM and Platform Termination Deadlines

Kubernetes typically grants containers a termination grace period before forcing termination. Keep the total time for draining requests, stopping consumers, and cleanup within that budget.

If Spring Boot is configured to wait 30 seconds while the orchestrator force-kills after 10 seconds, cleanup may be cut short. Never configure timeouts on only one side.

### 11.2. Process Must Receive the Signal

In Docker, how the entrypoint and shell wrappers are written determines whether signals reach the Java process. A common configuration uses the exec form so Java receives signals properly:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/application.jar"]
~~~

If using a script as the entrypoint, the script must manage signals and child processes carefully. A shell wrapper that does not forward signals can prevent the JVM from running shutdown hooks as expected.

### 11.3. Readiness and Graceful Shutdown Serve Two Purposes

- *Readiness* helps the orchestrator decide whether to keep routing requests to the instance.
- *Graceful shutdown* helps the instance finish existing requests and stop resources in order.

Both are needed when deploying services handling real traffic. Enabling graceful shutdown alone does not mean the load balancer will immediately stop routing to the instance.

## 12. SpringApplication.exit and Exit Codes

For CLI or batch applications, once work finishes, you may want to close the context and return a meaningful exit code to the operating system.

Spring Boot provides:

~~~java
int exitCode = SpringApplication.exit(context);
~~~

This method calculates the exit code via `ExitCodeGenerator`s and closes the context if possible. To turn that code into the JVM's exit code, call `System.exit(exitCode)`:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class BatchApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(BatchApplication.class, args);

        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }
}
~~~

The example assumes the batch work runs synchronously via `ApplicationRunner` or `CommandLineRunner` during `SpringApplication.run(...)`. If a job runs asynchronously afterward, you must wait for it to finish before calling exit.

### 12.1. ExitCodeGenerator

A bean can provide an exit code:

~~~java
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ExitConfiguration {

    @Bean
    ExitCodeGenerator exitCodeGenerator() {
        return () -> 0;
    }
}
~~~

In real applications, the exit code typically reflects job outcome. `0` usually denotes success, while non-zero values indicate errors per the calling system's contract.

Note: `System.exit(...)` requests the JVM to terminate; `SpringApplication.exit(...)` primarily calculates the exit code and closes the context. The two methods do not fully replace each other.

### 12.2. Do Not Call System.exit() Inside a @PreDestroy

Calling `System.exit()` inside a callback running during shutdown can cause unpredictable behavior. Let the launcher class or process owner decide the exit code and request process termination; beans should focus on cleaning up the resources they own.

## 13. Bean Scope and Destruction Callbacks

Scope determines up to what point the container manages an instance.

| Scope | Who manages destruction timing? | What to remember |
| --- | --- | --- |
| `singleton` | Spring context when bean is destroyed / context closes | `@PreDestroy` and destroy methods are invoked per contract |
| `prototype` | Primarily the code receiving the instance | Spring does not automatically execute destruction callbacks after handing out the instance |
| `request` | Web request scope | Target is destroyed with the request lifecycle, if managed by scope |
| `session` | Web session scope | Target follows the corresponding HTTP session lifecycle |
| `application` | Web application scope | Target follows the `ServletContext`/application scope lifecycle |

A prototype injected once into a singleton constructor becomes a reference held by that singleton, rather than creating a new prototype each time the singleton invokes a method. If a prototype owns closeable resources, establish ownership of that instance or use a factory/provider with explicit cleanup management.

With request-scoped proxies, a singleton bean usually holds a **proxy**, while the request-scoped target has its own lifecycle. Do not expect the target's `@PreDestroy` to run only when the entire application stops.

### 13.1. Uninstantiated Lazy Singletons

A `@Lazy` singleton that was never initialized has no instance on which to run `@PreDestroy`. Therefore, do not place a task that must always run inside the callback of a bean that might never be created.

If work must run even if a bean was never used, use an explicit lifecycle owner instead of relying only on bean destruction.

## 14. Example Testing Bean Destruction Order

You can use a minimal context to observe init/destroy behavior with `@DependsOn` without starting an HTTP server.

Define a collector:

~~~java
import java.util.ArrayList;
import java.util.List;

public class LifecycleLog {
    private final List<String> events = new ArrayList<>();

    public void add(String event) {
        events.add(event);
    }

    public List<String> snapshot() {
        return List.copyOf(events);
    }
}
~~~

Resource:

~~~java
public class TransportResource {
    private final LifecycleLog log;

    public TransportResource(LifecycleLog log) {
        this.log = log;
    }

    public void initialize() {
        log.add("transport:init");
    }

    public void close() {
        log.add("transport:close");
    }
}
~~~

Consumer:

~~~java
public class TransportConsumer {
    private final LifecycleLog log;

    public TransportConsumer(LifecycleLog log) {
        this.log = log;
    }

    public void initialize() {
        log.add("consumer:init");
    }

    public void close() {
        log.add("consumer:close");
    }
}
~~~

Java configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;

@Configuration(proxyBeanMethods = false)
public class LifecycleTestConfiguration {

    @Bean
    LifecycleLog lifecycleLog() {
        return new LifecycleLog();
    }

    @Bean(initMethod = "initialize", destroyMethod = "close")
    TransportResource transportResource(LifecycleLog log) {
        return new TransportResource(log);
    }

    @Bean(initMethod = "initialize", destroyMethod = "close")
    @DependsOn("transportResource")
    TransportConsumer transportConsumer(LifecycleLog log) {
        return new TransportConsumer(log);
    }
}
~~~

`TransportConsumer` does not inject `TransportResource` directly; `@DependsOn` simply declares the ordering requirement.

JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class BeanDestructionOrderTest {

    @Test
    void dependentIsDestroyedBeforeItsDependency() {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        LifecycleTestConfiguration.class
                );

        LifecycleLog log = context.getBean(LifecycleLog.class);

        try {
            assertEquals(
                    List.of("transport:init", "consumer:init"),
                    log.snapshot()
            );
        } finally {
            context.close();
        }

        assertEquals(
                List.of(
                        "transport:init",
                        "consumer:init",
                        "consumer:close",
                        "transport:close"
                ),
                log.snapshot()
        );
    }
}
~~~

The test demonstrates that singleton destruction runs in the reverse order of dependencies. It does not test the JVM shutdown hook; the test explicitly calls `context.close()`, producing deterministic results without terminating the JVM.

### 14.1. Testing ContextClosedEvent and @PreDestroy

Another test can register a `ContextClosedEvent` listener and a `@PreDestroy` bean that both write to a collector. After calling `close()`, verify that the close event is received before singleton destruction callbacks.

To keep tests lightweight, use `AnnotationConfigApplicationContext`. Never call `System.exit(...)` inside a unit test because it can terminate the entire test runner JVM.

## 15. Observing Shutdown in a Web Application

Try a Boot 3.3 application with Spring MVC:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Configuration:

~~~yaml
server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Add an endpoint simulating slow work:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SlowController {

    @GetMapping("/slow")
    public String slow() throws InterruptedException {
        Thread.sleep(5000);
        return "completed";
    }
}
~~~

`Thread.sleep` is only used to illustrate an in-flight request; in real applications, avoid intentionally blocking server threads unnecessarily, especially on reactive stacks.

Manual observation steps:

1. Run the application from a terminal so you can send a normal termination signal.
2. Send a request to `/slow`.
3. While the request is still running, send an appropriate stop signal to the process.
4. Observe that the current request can complete within the grace period.
5. Observe context shutdown logs and the destruction callback of a `@PreDestroy` bean.
6. Try shortening the timeout or lengthening the request to see the boundaries of graceful shutdown.

Do not use `kill -9` to test graceful shutdown; it bypasses the normal shutdown path and leads to wrong conclusions.

### 15.1. Logging Cleanup Order

Example:

~~~java
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class CleanupLogger {

    @PreDestroy
    public void onShutdown() {
        System.out.println("CleanupLogger: @PreDestroy called");
    }
}
~~~

When the context closes normally, the log above confirms the bean's destruction callback was invoked. However, this log only confirms one callback ran—it does not prove all requests or external transactions completed.

### 15.2. Do You Need to Call close() Yourself When Pressing Ctrl+C?

No, for a standard `SpringApplication` keeping default settings. Boot's JVM shutdown hook is responsible for closing the context when the process follows an orderly shutdown path.

If you manually create multiple independent contexts, determine which context is managed by the hook and which must be closed by another owner.

## 16. Common Issues and How to Handle Them

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| `@PreDestroy` does not run | Process was forcefully killed or bean is not Spring-managed | Check how the process stopped and bean ownership |
| `@PreDestroy` does not run for prototype | Spring does not destroy prototypes after handing out instances | Caller manages cleanup |
| Context closes right after startup | `try-with-resources` ends immediately after `run()` in a web app | Keep context alive until shutdown |
| Listener keeps accepting work after stop signal | Missing proper stop/quiesce mechanism | Use `SmartLifecycle` or listener container mechanism |
| Connection pool closes before consumer | Missing or wrong dependency/phase relationship | Express dependencies and lifecycle order |
| Shutdown hangs for a long time | `stop(Runnable)` fails to call callback or waits indefinitely on I/O | Invoke callback, set timeouts, and control stopping |
| Container killed before cleanup finishes | Orchestrator grace period is shorter than total stop time | Adjust timeouts and reduce processing time |
| New requests still arrive at stopping instance | Readiness/load balancer did not stop routing immediately | Coordinate readiness, draining, and graceful shutdown |
| Resource closed twice | Multiple destruction callbacks release the same resource | Use one primary callback or idempotent cleanup |
| ContextClosedEvent not observed | Context not closed, listener not registered, or JVM killed forcefully | Check lifecycle and signals |
| `context.stop()` does not invoke `@PreDestroy` | Stop is not destroy | Call `close()` when you truly need to close the context |
| Bean unavailable inside close listener | Creating/using beans too late in the shutdown cycle | Keep event listener work brief and observational |
| Hook works in terminal but not in IDE | IDE may terminate processes differently | Check IDE Stop behavior and actual signals |

### 16.1. Do Not Overuse Shutdown Hooks

If a bean only needs to close resources, use `@PreDestroy` or `@Bean(destroyMethod = "close")`. If it needs to stop accepting work before closing, use `SmartLifecycle`.

Custom hooks are appropriate when controlling a non-Spring Java process or meeting a special process-level requirement. Do not add separate hooks per bean and manually manage dependency ordering.

### 16.2. Do Not Treat @PreDestroy as the Final Commit Point

For example, a consumer reading messages from a broker must confirm/acknowledge messages per contract during processing. If processing state is only saved inside `@PreDestroy`, a process crash can lose that state.

Use transactions or the broker's delivery/acknowledgment mechanism. Cleanup releases resources; it does not replace business durability.

### 16.3. Do Not Block Shutdown with Unbounded Sleeps

An infinitely running `@PreDestroy` callback can hold the process in shutdown until the orchestrator forcefully kills it. When waiting for in-flight tasks, establish a clear deadline, sufficient diagnostic logging, and a fallback plan on timeout.

## 17. Choosing the Right Mechanism by Goal

| What do you want to do? | Appropriate mechanism |
| --- | --- |
| Ensure Spring context closes on normal JVM shutdown | Spring Boot's default shutdown hook |
| Explicitly close a context created by code | `ConfigurableApplicationContext.close()` |
| Pause lifecycle components while keeping context | `ConfigurableApplicationContext.stop()` or component API |
| Observe when context closing begins | `ContextClosedEvent` |
| Stop message consumers/polling before destroy | `SmartLifecycle` |
| Control start/stop order of components | `SmartLifecycle.getPhase()` and dependency graph |
| Clean up component bean resources | `@PreDestroy` |
| Close an object created by `@Bean` | `destroyMethod` or inferred `close/shutdown` |
| Provide an exit code for a CLI | `ExitCodeGenerator` and `SpringApplication.exit(...)` |
| Let in-flight HTTP requests finish | `server.shutdown=graceful` and lifecycle timeout |
| Coordinate shutdown across multiple nodes | Readiness, process managers, and orchestration |
| Ensure business data durability | Transactions, durable storage, acknowledgments/checkpoints |

An easy way to remember the layers: **the hook steers the process into context closure; lifecycle components stop active work; destruction callbacks close resources; the deployment platform decides how long it is allowed to wait.** Each layer solves one part of shutdown.

## 18. Practice Exercises

### Exercise 1 — Verify @PreDestroy

Create a singleton bean `FileBuffer` with `@PostConstruct` and `@PreDestroy`. Run the Spring Boot app from a terminal, stop it normally, and observe log ordering. Try creating an instance via `new FileBuffer()` outside Spring and explain why callbacks do not run automatically.

### Exercise 2 — Context.close() vs. context.stop()

Create a `SmartLifecycle` bean that logs inside `start`, `stop`, and `@PreDestroy`. Call `context.stop()`, then `context.start()`, and finally `context.close()`. Record which callbacks run and distinguish stop from destroy.

### Exercise 3 — Destruction Order via @DependsOn

Create `ProviderBootstrap` and `LegacyClient`, using `@DependsOn` so the client initializes after the provider. Log init/destroy methods and verify the client is destroyed before the provider. Compare with injecting the provider via constructor.

### Exercise 4 — SmartLifecycle and Phases

Create a connection manager at phase 0 and a consumer at phase 100. Observe start/stop ordering on context refresh and close. Explain why the consumer should stop before the connection manager closes.

### Exercise 5 — HTTP Graceful Shutdown

Create an endpoint with a fixed processing time. Enable `server.shutdown=graceful` and set `spring.lifecycle.timeout-per-shutdown-phase=20s`. Send a request and stop the app in a way that delivers a shutdown signal to the JVM. Observe the in-flight request and destruction callbacks.

### Exercise 6 — Limits of Shutdown Hooks

Compare normal JVM shutdown against a forced kill in a test environment. Identify which callbacks do or do not get a chance to run. Explain why critical business data must never be persisted solely inside `@PreDestroy`.

### Exercise 7 — CLI with Exit Code

Create an `ApplicationRunner` running a batch job and an `ExitCodeGenerator`. After the runner finishes, call `SpringApplication.exit(context)` and return the code via `System.exit(code)`. Confirm the context closes and the exit code reflects job outcome.

## 19. References

- [Spring Boot 3.3 — SpringApplication / Application Exit](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html)
- [Spring Framework — Bean Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [SpringApplication API 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)

## 20. Takeaways

By default, Spring Boot registers a JVM shutdown hook to close `ApplicationContext` when the JVM exits normally. However, the same context closing sequence can also be triggered explicitly via `ConfigurableApplicationContext.close()` or `SpringApplication.exit(context)`. Hooks are not guaranteed to run in every scenario, especially when the process is forcefully killed.

When closing the context, Spring emits `ContextClosedEvent`, stops `Lifecycle`/`SmartLifecycle` components, and then destroys singletons according to the dependency graph. Within each bean, Spring supports `@PreDestroy`, `DisposableBean.destroy()`, and custom destroy methods. For a bean dependency A → B, A is destroyed before B; with lifecycle phases, components that need to stop early can be assigned appropriate phases. `context.stop()` only stops lifecycle; `context.close()` ends the container's lifecycle.

In Spring Boot 3.3 web applications, `server.shutdown=graceful` lets the web server stop accepting new work and wait for in-flight requests within configured limits. For workers, use `SmartLifecycle` to stop taking work and await in-flight tasks before `@PreDestroy` closes resources. Critical data must be persisted durably right inside the business flow because no shutdown callback can replace transactions, acknowledgments, or crash recovery.
