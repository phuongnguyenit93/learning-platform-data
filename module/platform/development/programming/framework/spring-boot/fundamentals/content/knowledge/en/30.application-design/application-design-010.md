# Managing Resources Across the Application Lifecycle

A Spring Boot application does more than simply instantiate objects and use them. While running, it also opens database connections, creates HTTP clients, starts thread pools, schedules background jobs, opens files, registers listeners, and holds resources that must be released upon shutdown.

If a resource is created without being closed at the right time, the application can suffer from:

- Leaked connections or file handles.
- Background threads continuing to run after the context has closed.
- The JVM failing to exit because an executor still has active threads.
- New requests arriving while the application is shutting down.
- Unflushed data or abandoned in-flight work.
- One bean closing a resource that another bean is still using.

Spring manages the lifecycle of beans in the ApplicationContext and provides callbacks to initialize, stop, or release resources. However, **the container only properly manages resources whose ownership the application hands over to it**. A file stream opened locally inside a method still needs try-with-resources; an executor living for the entire application run needs an explicit lifecycle; a prototype bean may not have its destroy callback invoked automatically by Spring.

This lesson focuses on **resource ownership**, bean creation/destruction phases, **@PostConstruct**, **@PreDestroy**, **initMethod**, **destroyMethod**, **AutoCloseable**, singleton/prototype/scoped beans, **Lifecycle/SmartLifecycle**, graceful shutdown, and testing resource cleanup.

## 1. Application Lifecycle and Resource Lifecycles

A resource can exist for a very short scope or nearly the entire lifetime of the process:

| Resource | Typical Scope | Appropriate Management |
|---|---|---|
| InputStream reading a file | Within one method | try-with-resources |
| JDBC Connection borrowed from pool | Within one transaction/operation | Let transaction manager or connection-owning code close it promptly |
| DataSource connection pool | Application lifecycle | Bean/container lifecycle |
| Shared HTTP client | Application lifecycle | Bean with close/shutdown callback |
| ScheduledExecutorService | Application lifecycle | Bean managing start/stop/destroy |
| ThreadPoolTaskExecutor | Application lifecycle | Spring bean with shutdown policy |
| Temporary file for a task | Within one task | Create and delete within the task scope |
| Message consumer | Application lifecycle or one subscription | Ordered lifecycle start/stop |
| Local cache | Bean/context lifecycle | Bean lifecycle or self-managed cache library |

The key is determining **who creates the resource, who uses it, and who is responsible for closing it**.

### 1.1. The Ownership Rule

An easy rule to apply:

> The component that creates and owns a resource is responsible for releasing it, unless ownership has been explicitly transferred.

For example, a method opens a file and finishes reading it:

~~~java
public String readFile(Path path) throws IOException {
    try (InputStream input = Files.newInputStream(path)) {
        return new String(
                input.readAllBytes(),
                StandardCharsets.UTF_8);
    }
}
~~~

The method opens the stream and also closes it. There is no reason to store `InputStream` in a service field just to read one file.

Conversely, if a service creates a shared HTTP client:

~~~java
public class PartnerClient implements AutoCloseable {
    // Client holds a connection pool and internal resources.
    @Override
    public void close() {
        // Close client/pool.
    }
}
~~~

then the client must be closed when its owner's lifecycle ends. If it is a singleton Spring bean, the container can run cleanup callbacks when the context closes.

### 1.2. Do Not Close Resources You Merely Borrow

Suppose a service receives a `DataSource` via its constructor:

~~~java
@Service
public class OrderRepository {

    private final DataSource dataSource;

    public OrderRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }
}
~~~

The repository **uses** the container-managed `DataSource`. It does not own the `DataSource` and must not call `dataSource.close()` after every request.

Similarly:

- Do not close a shared HTTP client managed by another bean.
- Do not shut down a shared executor if the service only submits tasks to it.
- Do not close the ApplicationContext from a business bean.
- Do not manually release a connection pool auto-configured by Spring Boot.

Closing a shared resource prematurely can break other beans even while the application is not shutting down.

### 1.3. Resource Ownership Should Be Clear in the API

A method accepting an `InputStream` must specify who closes the stream:

~~~java
public void importData(InputStream input) {
    // Does this API only read the stream or take ownership?
}
~~~

If the method closes the stream, callers must know the stream is unusable afterward. If the caller retains ownership, the method must not close it.

Express ownership through method names/contracts, documentation, and try-with-resources structure. Never leave callers guessing.

## 2. Phases in a Spring Bean's Lifecycle

For a typical singleton bean, Spring instantiates the object, injects dependencies, invokes initialization callbacks, and eventually manages cleanup when the context closes.

~~~text
ApplicationContext refresh
          │
          ▼
Create bean instance
          │
          ▼
Inject constructor / properties
          │
          ▼
Aware callbacks (if any)
          │
          ▼
BeanPostProcessor before initialization
          │
          ▼
@PostConstruct
          │
          ▼
InitializingBean.afterPropertiesSet()
          │
          ▼
Custom init method
          │
          ▼
BeanPostProcessor after initialization
          │
          ▼
Bean ready for use
          │
          ▼
ApplicationContext closes
          │
          ▼
@PreDestroy
          │
          ▼
DisposableBean.destroy()
          │
          ▼
Custom destroy method
~~~

This is a conceptual diagram for a fully Spring-managed bean. Exact callbacks depend on bean type, scope, proxies, and container configuration.

### 2.1. Constructors: Establishing Necessary State

Constructor injection is suited for receiving required dependencies:

~~~java
@Component
public class ReportService {

    private final ReportRepository repository;
    private final ReportExporter exporter;

    public ReportService(
            ReportRepository repository,
            ReportExporter exporter) {
        this.repository = repository;
        this.exporter = exporter;
    }
}
~~~

Constructors should:

- Accept required dependencies.
- Assign fields.
- Validate simple invariants.
- Establish safe internal state.

Avoid opening sockets, calling remote APIs, running long batches, or creating hard-to-roll-back side effects in constructors. If initialization fails midway, the object is not yet fully registered and cleaning up newly opened resources becomes error-prone.

### 2.2. Dependency Injection Happens Before Init Callbacks

When `@PostConstruct` is invoked, dependencies have already been injected under the normal lifecycle. Thus this callback can use collaborators received via the constructor to complete local setup steps.

However, do not assume every other bean in the context has finished initialization just because one bean is running `@PostConstruct`. The bean graph initializes in dependency order; unrelated singletons might not be created yet.

If a step requires the entire context to be ready, look at appropriate lifecycle events or runners instead of relying on accidental component-scan ordering.

### 2.3. Initialization Callbacks Are Not for Running All Startup Work

A bean initialization callback should be brief and tied to that bean's validity, such as:

- Validating local configuration.
- Preparing an internal data structure.
- Verifying an owned resource opened properly.
- Creating a handle owned by the bean.

Tasks like importing millions of rows, calling multiple external services, or waiting for another system to come online can stall context startup and complicate timeout handling. Choose `ApplicationRunner`, a lifecycle component, or a separate job depending on the nature of the work.

## 3. @PostConstruct: Initializing After Dependencies Are Injected

`@PostConstruct` is a standard Jakarta annotation marking a method to run after dependency injection completes and before the bean is put into service under the standard lifecycle.

In Spring Boot 3, import:

~~~java
import jakarta.annotation.PostConstruct;
~~~

Example:

~~~java
package com.example.reports;

import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;

@Component
public class ReportFormatRegistry {

    private final ReportFormatRepository repository;
    private Map<String, ReportFormat> formats;

    public ReportFormatRegistry(
            ReportFormatRepository repository) {
        this.repository = repository;
    }

    @PostConstruct
    void initialize() {
        this.formats = Map.copyOf(repository.loadBuiltInFormats());
    }
}
~~~

This example assumes `loadBuiltInFormats()` only reads required data and can run safely during initialization. If it depends on a database or network, evaluate startup policies and error handling.

### 3.1. Characteristics of a @PostConstruct Method

- Usually a no-argument method.
- Does not need to be public; it can be package-private or protected per runtime/framework rules.
- Should not return a value.
- Must not be declared static.
- Should have only one matching callback in the hierarchy per annotation processing rules.

Example:

~~~java
@PostConstruct
void warmUpLocalIndex() {
    this.index = buildLocalIndex();
}
~~~

### 3.2. What Happens If @PostConstruct Throws an Exception?

If an initialization callback throws an unhandled exception, bean creation fails. For a required singleton, `ApplicationContext` refresh normally fails as well, and Spring Boot will not start.

This is appropriate when the bean cannot operate safely without that resource.

Do not catch and ignore every exception:

~~~java
@PostConstruct
void initialize() {
    try {
        connectToRequiredSystem();
    } catch (Exception ex) {
        // Ignore so the application still starts.
    }
}
~~~

If the dependency is required, silently swallowing errors leaves the application running in an invalid state.

### 3.3. Do Not Use @PostConstruct to Self-Inject Dependencies

Avoid:

~~~java
@PostConstruct
void initialize() {
    this.repository = applicationContext.getBean(
            ReportRepository.class);
}
~~~

This is a service locator: the dependency is hidden inside a method instead of the constructor. Declare `ReportRepository` directly in the constructor to expose the bean's contract.

### 3.4. Avoid Depending on Uninitialized Beans

A `@PostConstruct` method calling another service can trigger initialization of that bean. In complex graphs, this easily causes premature side effects, circular dependencies, or confusing startup ordering.

Keep callbacks focused on the bean's own state. If you need to coordinate multiple beans after the context is ready, consider events or runners.

## 4. @PreDestroy: Releasing Resources Before Bean Destruction

`@PreDestroy` marks a method called when the container prepares to destroy a bean during lifecycle cleanup.

Spring Boot 3:

~~~java
import jakarta.annotation.PreDestroy;
~~~

Example of a bean holding a resource:

~~~java
package com.example.integration;

import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class PartnerConnectionManager {

    private final PartnerClient client;

    public PartnerConnectionManager(PartnerClient client) {
        this.client = client;
    }

    @PreDestroy
    void releaseResources() {
        client.close();
    }
}
~~~

This example is only valid if `PartnerConnectionManager` genuinely owns `PartnerClient`. If the client is a shared bean injected from elsewhere, the bean managing the client should close it.

### 4.1. Cleanup Must Be Safe During Shutdown

A destroy callback should:

- Be safe to call while the application is stopping.
- Not assume new requests are still being served.
- Not depend on beans that have already been destroyed.
- Have bounded wait times if waiting on tasks/flushes.
- Preserve diagnostic information if cleanup fails.

Do not make unbounded remote calls inside `@PreDestroy`. If the network is degraded, shutdown can stall or get killed by the process manager before cleanup finishes.

### 4.2. Do Not Close the Same Resource from Multiple Owners

If `PartnerClient` is its own `@Bean` with a `close` destroy method and `PartnerConnectionManager` also calls `client.close()` in `@PreDestroy`, the resource can be closed twice.

Some APIs allow idempotent multiple closes safely, yet you should not rely on that without an explicit contract.

Pick a single owner:

- Either the bean factory creates the client and the container closes it.
- Or the manager creates the client and the manager closes it.

Do not split ownership ambiguously across beans.

### 4.3. @PreDestroy Is Not Guaranteed in Every Termination Scenario

Spring invokes destroy callbacks when the context closes through a normal lifecycle. However, callbacks are not guaranteed when:

- The process is forcefully killed.
- The JVM crashes or the machine loses power.
- A container is terminated before its shutdown grace period finishes.
- The application calls `Runtime.halt()` or exits abnormally.
- Certain bean scopes do not have container-managed destruction.

Therefore, never use `@PreDestroy` as the sole mechanism guaranteeing critical business transactions commit. Durable data must be persisted via appropriate transactions or durable storage during processing.

## 5. Lifecycle Annotations in Spring Boot 2 vs. 3

A common difference is the annotation package:

| Platform | @PostConstruct / @PreDestroy |
|---|---|
| Spring Boot 3 / Spring Framework 6 | jakarta.annotation.PostConstruct, jakarta.annotation.PreDestroy |
| Spring Boot 2 / Spring Framework 5 | Typically javax.annotation.PostConstruct, javax.annotation.PreDestroy when the matching dependency is present |

Boot 3 example:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
~~~

Do not accidentally import `javax.annotation` from an old transitive dependency in a Boot 3 app. `jakarta` and `javax` packages are distinct namespaces.

### 5.1. Do Annotation Dependencies Need to Be Added Separately?

In Boot 3 environments, the Jakarta annotation API is normally provided by the application/framework's dependencies. If the compiler cannot find `jakarta.annotation`, check your dependency graph and starters rather than adding an arbitrary API version incompatible with dependency management.

### 5.2. Standard Annotations vs. Spring-Specific Lifecycle Interfaces

`@PostConstruct` and `@PreDestroy` are standard Jakarta annotations. `InitializingBean` and `DisposableBean` are Spring interfaces. Both are supported by the container, with differing levels of Spring coupling.

For ordinary business components, annotations usually keep classes less coupled to Spring APIs.

## 6. InitializingBean and DisposableBean

Spring provides two lifecycle interfaces:

~~~java
org.springframework.beans.factory.InitializingBean
org.springframework.beans.factory.DisposableBean
~~~

Example:

~~~java
import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.stereotype.Component;

@Component
public class LocalIndex implements InitializingBean, DisposableBean {

    @Override
    public void afterPropertiesSet() {
        // Prepare index after properties are injected.
    }

    @Override
    public void destroy() {
        // Release resources owned by the bean.
    }
}
~~~

### 6.1. afterPropertiesSet()

`afterPropertiesSet()` is invoked during initialization after properties and dependencies have been set under Spring's lifecycle.

It serves a similar purpose to `@PostConstruct`:

- Finalizing internal state.
- Checking configuration preconditions.
- Preparing local resources owned by the bean.

### 6.2. destroy()

`destroy()` is the cleanup callback when the container destroys a bean under a supported lifecycle.

It can close clients, stop workers, or flush resources owned by the bean.

### 6.3. Pros and Cons

| Approach | Advantages | Trade-offs |
|---|---|---|
| @PostConstruct / @PreDestroy | Standard annotations, less Spring API coupling | Requires matching Jakarta/Javax namespace |
| InitializingBean / DisposableBean | Explicit lifecycle contract, invoked directly by Spring | Class depends on Spring Framework |
| initMethod / destroyMethod | Configures lifecycle at bean declaration site | Methods are not visible as annotations on the class |

If a class is designed as a plain Java component or a library usable outside Spring, standard annotations or `AutoCloseable` may fit better. If the class is a Spring-specific adapter, lifecycle interfaces remain a valid option.

### 6.4. Do Not Implement All Three Mechanisms for the Same Job

A bean does not simultaneously need:

- `@PostConstruct`
- `InitializingBean.afterPropertiesSet()`
- custom init method

just to invoke the same setup routine three times. That obscures execution order and risks duplicate side effects.

Pick one primary mechanism per lifecycle responsibility. If multiple genuinely distinct initialization steps exist, name them clearly and understand callback ordering.

## 7. Declaring initMethod and destroyMethod on @Bean

When a bean is created from a factory method, callbacks can be configured where the bean is registered:

~~~java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean(
            initMethod = "start",
            destroyMethod = "stop")
    PartnerClient partnerClient() {
        return new PartnerClient();
    }
}
~~~

Here:

- Spring calls `start()` during bean initialization.
- Spring calls `stop()` when the bean is destroyed per lifecycle.

### 7.1. Well-Suited for Third-Party Classes

You cannot add `@PostConstruct` to a library class you do not own. However, if the class provides `initialize()`/`shutdown()` methods, you can declare:

~~~java
@Bean(
        initMethod = "initialize",
        destroyMethod = "shutdown")
ThirdPartyClient thirdPartyClient() {
    return ThirdPartyClient.builder()
            .endpoint("https://api.example.invalid")
            .build();
}
~~~

This keeps lifecycle management in Spring configuration without modifying the library.

### 7.2. Methods Must Match the Callback Contract

Methods declared as init/destroy methods generally need a signature Spring can invoke under its lifecycle—commonly a no-argument method.

Do not use methods requiring `ApplicationContext`, `Environment`, or business arguments as destroy methods unless a supported mechanism handles them.

### 7.3. @Bean Can Automatically Infer close/shutdown

Spring supports destroy-method inference for `@Bean` declarations, typically looking for matching public `close()` or `shutdown()` methods.

Example:

~~~java
@Bean
PartnerClient partnerClient() {
    return new PartnerClient();
}
~~~

If `PartnerClient` implements `AutoCloseable` or has a public `close` method matching Spring's inference rules, the container can automatically invoke cleanup on destruction.

Even so, for critical resources, declaring it explicitly:

~~~java
@Bean(destroyMethod = "close")
PartnerClient partnerClient() {
    return new PartnerClient();
}
~~~

makes ownership and cleanup intent immediately visible to readers.

### 7.4. Disabling Inferred Destroy Methods When the Container Does Not Own the Bean

If the returned bean is a shared object created/managed externally and Spring must not close it, configure:

~~~java
@Bean(destroyMethod = "")
ExternalSharedClient externalSharedClient() {
    return externallyManagedClient();
}
~~~

Do this only when external ownership is clearly established. If the bean is actually created and owned by the application, disabling the destroy method causes resource leaks.

### 7.5. Avoid Calling close Immediately Inside Factory Methods

Do not write:

~~~java
@Bean
PartnerClient partnerClient() {
    PartnerClient client = new PartnerClient();
    client.close();
    return client;
}
~~~

The returned bean is already closed before any consumer uses it. Let lifecycle callbacks handle cleanup at the right time.

## 8. AutoCloseable and try-with-resources

Java defines the standard interface:

~~~java
public interface AutoCloseable {
    void close() throws Exception;
}
~~~

A resource implementing `AutoCloseable` can be closed automatically upon exiting a `try-with-resources` block:

~~~java
try (PartnerClient client = new PartnerClient()) {
    client.send(message);
}
~~~

This is appropriate when the resource's lifetime is bound to a block or method and the code owns it directly.

### 8.1. Local Resources: try-with-resources

File-reading example:

~~~java
public List<String> readLines(Path path) throws IOException {
    try (BufferedReader reader =
                 Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        return reader.lines().toList();
    }
}
~~~

When the block finishes normally or via an exception, Java automatically calls `close()`. If `close()` also throws while the block already threw another exception, Java preserves the primary exception and attaches the close exception as a suppressed exception.

### 8.2. Bean-Lived Resources: Spring Lifecycle

If a client is reused across many requests:

~~~java
@Bean(destroyMethod = "close")
PartnerClient partnerClient() {
    return new PartnerClient();
}
~~~

Spring manages the bean and invokes `close` when the bean is destroyed under its lifecycle.

### 8.3. Do Not Use try-with-resources on Injected Shared Beans

Do not write:

~~~java
public void sendMessage(String message) throws Exception {
    try (PartnerClient client = injectedClient) {
        client.send(message);
    }
}
~~~

If `injectedClient` is a shared singleton, this method closes the client after one message. Subsequent requests will fail.

Callers only own a resource when an API explicitly transfers ownership to the caller. For container-managed beans, let the owner bean or container close them.

### 8.4. Distinguishing close and shutdown

Libraries use different method names:

- `close()`: closes a resource, stream, client, or pool.
- `shutdown()`: instructs an executor/service to stop accepting new work.
- `stop()`: stops a component according to a lifecycle contract.
- `dispose()`: releases resources per a library's API.

Do not guess names. Read the library's contract and ensure the destroy callback calls the right method.

## 9. Singleton Beans and Prototype Beans Have Different Cleanup Rules

Spring supports multiple bean scopes. Scope determines instance count and bean lifetime.

### 9.1. Singleton

Singleton is the default scope. Spring creates one instance per bean definition in an ApplicationContext and manages that instance's lifecycle.

~~~java
@Component
public class SharedPartnerClient {
    // One instance shared within the context.
}
~~~

For fully managed singletons, Spring invokes destroy callbacks when the context closes.

### 9.2. Prototype

Prototype creates a new instance each time the container is asked to resolve a bean of that scope.

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class CsvImportSession implements AutoCloseable {

    @Override
    public void close() {
        // Close file/session owned by this instance.
    }
}
~~~

**Spring manages creation, injection, and initialization of prototype beans, but does not track full destruction of every instance after handing it to the caller.**

Consequently, the container does not guarantee invoking `@PreDestroy` or destroy methods for prototype beans once the caller finishes with them.

### 9.3. Callers Are Responsible for Cleaning Up Prototypes

When obtaining prototypes via `ObjectProvider`:

~~~java
@Service
public class ImportCoordinator {

    private final ObjectProvider<CsvImportSession> sessions;

    public ImportCoordinator(
            ObjectProvider<CsvImportSession> sessions) {
        this.sessions = sessions;
    }

    public void importOne(Path file) {
        CsvImportSession session = sessions.getObject();
        try {
            session.importFile(file);
        } finally {
            session.close();
        }
    }
}
~~~

The caller creates the instance and must close it when done. You can use `try-with-resources` if the type implements `AutoCloseable`:

~~~java
try (CsvImportSession session = sessions.getObject()) {
    session.importFile(file);
}
~~~

This requires designing the class API and ownership accordingly. Never expect Spring to automatically call destroy callbacks on prototype objects.

### 9.4. Injecting a Prototype Directly into a Singleton Does Not Create a New Instance per Use

Example:

~~~java
@Service
public class ImportCoordinator {

    private final CsvImportSession session;

    public ImportCoordinator(CsvImportSession session) {
        this.session = session;
    }
}
~~~

Because singleton `ImportCoordinator` is created once, its prototype dependency is normally resolved at singleton creation time. The singleton keeps that single instance; calling multiple methods does not create new prototypes.

If you need a new instance per use, use `ObjectProvider`, `Provider`, or an appropriate scoped proxy.

### 9.5. Request/Session Scope

In web applications, Spring provides scopes like `request` and `session`. Scoped beans are created within the request/session scope and the container manages their lifecycle when that scope ends.

Example:

~~~java
@Component
@RequestScope
public class RequestContextData {
    // Data tied to a single HTTP request.
}
~~~

For scoped beans, destruction callbacks are handled when the corresponding scope ends under the web context mechanism. Do not retain references to request-scoped resources in a singleton and access them outside the request.

### 9.6. Scope and Destruction Comparison Table

| Scope | Lifetime | Who Manages Cleanup? |
|---|---|---|
| singleton | Tied to ApplicationContext | Spring invokes destroy callbacks when the context closes |
| prototype | New instance on each resolution | Caller is responsible for cleanup after receiving the instance |
| request | Within one HTTP request | Web scope/container when the request completes |
| session | Tied to HTTP session | Web scope/container when the session ends per lifecycle |
| application | Tied to ServletContext in a web app | Web application context |
| custom scope | Defined by the scope contract | Scope implementation must manage callbacks properly |

## 10. Application Lifecycle Differs from a Single Bean's Lifecycle

A bean can be created and destroyed while the ApplicationContext stays alive, such as a request-scoped bean. Conversely, an application may need to coordinate a sequence of components starting and stopping together.

Distinguish:

- **Bean initialization/destruction:** callbacks tied to one bean.
- **Application startup/readiness:** the point when the application finishes starting.
- **Application lifecycle:** managing components starting work, stopping intake, and releasing resources.
- **Process lifecycle:** JVM/container startup and termination.

Do not use `@PostConstruct` for everything merely to run code "when the app starts."

### 10.1. ApplicationRunner and CommandLineRunner

If you need to run a step after the ApplicationContext has refreshed and before `SpringApplication` reports readiness, use:

~~~java
@Component
public class StartupDataCheck implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        // Verify or prepare data after context refresh.
    }
}
~~~

`ApplicationRunner` and `CommandLineRunner` run during the startup flow after context refresh. They are better suited than a single bean's `@PostConstruct` for startup work requiring beans to already be ready.

Note that if a runner throws an exception, application startup still fails. Do not use runners to execute unbounded jobs that prevent deployments from ever reaching ready state.

### 10.2. ApplicationReadyEvent

Spring Boot publishes `ApplicationReadyEvent` once the application is ready according to the startup lifecycle:

~~~java
@Component
public class ReadyListener {

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        // Perform action after the app is ready.
    }
}
~~~

This is an appropriate signal when an action must wait for the entire startup flow to finish. However, the listener still runs inside the process; if it opens a long-lived resource, define an owner and matching cleanup.

### 10.3. ContextClosedEvent

Spring publishes `ContextClosedEvent` when the ApplicationContext begins closing:

~~~java
@Component
public class ShutdownObserver {

    @EventListener
    public void onContextClosed(ContextClosedEvent event) {
        // Record event or emit internal signal.
    }
}
~~~

This event is helpful for observing or coordinating actions during context shutdown. For resources owned by a bean, destroy callbacks like `@PreDestroy` or `destroyMethod` express ownership more directly and are easier to control.

Do not use an event listener to close all global resources without clear owners.

### 10.4. ApplicationReadyEvent Does Not Replace @PostConstruct

`@PostConstruct` runs during a bean's lifecycle. `ApplicationReadyEvent` fires later, after the application startup flow completes.

Choose by purpose:

| Need | Appropriate Mechanism |
|---|---|
| Finalize one bean's internal state | @PostConstruct or init callback |
| Checks/setup across multiple beans after refresh | ApplicationRunner |
| Execute an action once the app is ready | ApplicationReadyEvent |
| Release a bean's resource | @PreDestroy/destroyMethod |
| Coordinate starting/stopping components | Lifecycle/SmartLifecycle |

## 11. Lifecycle and SmartLifecycle

Spring provides the interfaces:

~~~java
org.springframework.context.Lifecycle
org.springframework.context.SmartLifecycle
~~~

`Lifecycle` describes a component that can start and stop:

~~~java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
~~~

`SmartLifecycle` adds auto-startup, phases, and asynchronous stop completion callbacks.

### 11.1. When to Use Lifecycle?

Well suited for components with an explicit active state:

- Message listener containers.
- Consumer subscriptions.
- Background polling workers.
- Components receiving events from external systems.
- Services that must stop accepting work before dependencies close.

You do not need to implement `Lifecycle` for every service that simply exposes business methods. A stateless pricing class does not need start/stop.

### 11.2. Example of a Lifecycle-Managed Consumer

~~~java
package com.example.messaging;

import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class OrderEventConsumer implements SmartLifecycle {

    private volatile boolean running;

    @Override
    public void start() {
        // Open subscription or begin receiving messages.
        running = true;
    }

    @Override
    public void stop() {
        // Stop receiving messages and close subscription.
        running = false;
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 0;
    }
}
~~~

This is a skeleton example. A real consumer must retain its subscription handle, stop accepting new messages, handle in-flight messages per policy, and close any client it owns.

### 11.3. stop(Runnable callback) Must Invoke the Callback When Done

With `SmartLifecycle`, the callback lets the component signal the container that stopping has finished, especially when stopping asynchronously.

Example:

~~~java
@Override
public void stop(Runnable callback) {
    subscription.stopAsync()
            .whenComplete((ignored, error) -> {
                running = false;
                callback.run();
            });
}
~~~

This illustrates an API returning a `CompletionStage`; actual types depend on the library. If stopping fails, log the error appropriately and still ensure the callback completes per contract so `LifecycleProcessor` does not hang indefinitely.

### 11.4. Phases Control Start/Stop Ordering

`SmartLifecycle` has a phase:

- Lower phases typically start first.
- Higher phases typically start later.
- During stop, the order reverses: higher phases stop first, lower phases stop last.

This helps when one component depends on another:

~~~text
Startup:
Message transport (low phase)
          │
          ▼
Message consumer (high phase)

Shutdown:
Message consumer stops first
          │
          ▼
Message transport stops later
~~~

For example, a consumer should stop receiving messages before the underlying transport/client is closed.

Do not pick arbitrary phase numbers. Base them on real dependencies and write integration tests for ordering when it matters.

### 11.5. isAutoStartup()

`SmartLifecycle` declares whether the component starts automatically on context refresh. If `isAutoStartup()` returns `true`, Spring starts it automatically per lifecycle. If `false`, the application controls starting separately.

Do not start the same component in both `@PostConstruct` and `SmartLifecycle.start()`, which can open subscriptions or threads twice.

### 11.6. LifecycleProcessor Coordinates Components

Spring uses `LifecycleProcessor` to coordinate starting and stopping lifecycle-aware beans during context refresh and close.

You do not need to call `start()`/`stop()` manually on individual beans from ApplicationContext when relying on Spring's standard lifecycle management.

## 12. Graceful Shutdown: Stop Accepting Work Before Releasing Resources

When an application stops, not every request or task finishes instantaneously. A server may be serving active requests, a consumer may be processing a message, or an executor may still have queued tasks.

**Graceful shutdown** gives the application a bounded window to stop accepting new work and finish in-flight work before releasing resources.

~~~text
Receive shutdown signal
          │
          ▼
Stop accepting new work
          │
          ▼
Wait for in-flight requests / tasks / messages
          │
          ▼
Flush or commit required state
          │
          ▼
Close consumers / executors / clients
          │
          ▼
Close ApplicationContext
          │
          ▼
Process exits
~~~

Exact ordering depends on the server, lifecycle phases, bean dependencies, and timeout settings.

### 12.1. Web Server Graceful Shutdown in Spring Boot

Spring Boot supports configuring shutdown mode:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

With supported server implementations, graceful shutdown stops accepting new requests and grants active requests a window to complete within the configured duration.

If the wait expires, the application must still terminate per shutdown policy; there is no guarantee every request finishes if it runs longer than the timeout.

### 12.2. Timeouts Must Align with Deployment

For instance, if Kubernetes has a termination grace period shorter than the total time Spring needs across shutdown phases, the container runtime can kill the process before cleanup completes.

Align:

- Spring lifecycle timeout.
- Web server graceful shutdown timeout.
- Executor/consumer shutdown timeouts.
- Kubernetes `terminationGracePeriodSeconds` or service manager timeouts.
- Maximum time for the load balancer to stop routing traffic to the instance.

Never set infinite timeouts. A hung shutdown can stall rollouts or scale-downs.

### 12.3. Stopping Intake Differs from Closing Connections Immediately

If you close the `DataSource` or HTTP client while active requests are still running, those requests lose access to their dependencies.

Therefore, shutdown ordering should account for:

1. Stop accepting new traffic.
2. Wait for in-flight requests to finish within bounds.
3. Stop background consumers.
4. Complete or cancel tasks per policy.
5. Close low-level clients, pools, and resources.

Lifecycle phases and shutdown coordination express this order when components have clear dependencies.

## 13. Managing Thread Pools and Executors

Thread pools are long-lived resources. Creating one with `Executors.newFixedThreadPool()` inside a service without shutting it down leaves threads alive after the context closes.

Avoid:

~~~java
@Service
public class ExportService {

    private final ExecutorService executor =
            Executors.newFixedThreadPool(4);
}
~~~

In this example, Spring does not automatically know it should close an executor created inline without a destroy callback.

### 13.1. Use ThreadPoolTaskExecutor as a Spring Bean

~~~java
@Configuration(proxyBeanMethods = false)
public class AsyncConfiguration {

    @Bean
    public ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("report-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);

        return executor;
    }
}
~~~

Spring manages `ThreadPoolTaskExecutor` as a lifecycle-aware bean. It supports initialization and shutdown; the settings above instruct it to wait up to the configured limit for active/queued tasks on context shutdown.

### 13.2. waitForTasksToCompleteOnShutdown

When set to `true`, the executor attempts to let submitted tasks finish during shutdown rather than canceling queued tasks immediately under its default behavior.

This does not guarantee every task finishes:

- A task may exceed the wait window.
- A task may be interrupted/canceled upon timeout.
- A task may fail because a dependency has already begun shutting down.
- Tasks should not depend on a resource that closes before they complete.

### 13.3. awaitTerminationSeconds

Sets the bound for waiting on executor termination:

~~~java
executor.setAwaitTerminationSeconds(20);
~~~

This value must fit within the overall shutdown budget. If the executor waits 60 seconds while the process manager grants only 30 seconds, the process will still be terminated early.

### 13.4. Services Using an Executor Must Not Shut It Down

~~~java
@Service
public class ReportService {

    private final ThreadPoolTaskExecutor executor;

    public ReportService(ThreadPoolTaskExecutor executor) {
        this.executor = executor;
    }

    public void submit(Report report) {
        executor.execute(() -> generate(report));
    }
}
~~~

`ReportService` merely uses the executor. `AsyncConfiguration` owns the bean, and Spring shuts it down when the context ends.

Never call `executor.shutdown()` after every submit or request.

### 13.5. If Managing an ExecutorService Directly

If using a standard Java `ExecutorService` directly, assign an owner and destroy callback:

~~~java
public final class ManagedExecutor implements AutoCloseable {

    private final ExecutorService delegate =
            Executors.newFixedThreadPool(4);

    public void execute(Runnable task) {
        delegate.execute(task);
    }

    @Override
    public void close() {
        delegate.shutdown();
        try {
            if (!delegate.awaitTermination(
                    20, TimeUnit.SECONDS)) {
                delegate.shutdownNow();
            }
        } catch (InterruptedException ex) {
            delegate.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Registration:

~~~java
@Bean(destroyMethod = "close")
ManagedExecutor managedExecutor() {
    return new ManagedExecutor();
}
~~~

This shows an owner managing its executor. In real code, decide how rejected/canceled tasks, task exceptions, and logging are handled; do not share an executor without proper queue and rejection policies.

### 13.6. Do Not Spawn Manual Threads in @PostConstruct and Forget to Stop Them

~~~java
@PostConstruct
void startWorker() {
    worker = new Thread(this::pollForever);
    worker.start();
}
~~~

If you take this approach, the bean must implement stop signals, interruption, bounded `join`, and state handling. Usually a `TaskExecutor`, `ScheduledExecutorService`, or `SmartLifecycle` component expresses ownership and lifecycle much more cleanly.

Avoid infinite loops without stop signals or uninterruptible sleeps.

## 14. Managing ScheduledExecutorService and Scheduled Tasks

A scheduler can keep invoking periodic tasks after a service is no longer usable. Shut down schedulers promptly.

Example using Spring `TaskScheduler`:

~~~java
@Configuration(proxyBeanMethods = false)
public class SchedulerConfiguration {

    @Bean
    public ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler =
                new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("scheduled-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(15);
        return scheduler;
    }
}
~~~

Spring manages the lifecycle of the scheduler bean. When using `@Scheduled`, Spring's scheduling infrastructure manages scheduled tasks against the configured scheduler.

### 14.1. @Scheduled Is Not a Private Thread Pool per Method

~~~java
@Component
public class CleanupJob {

    @Scheduled(fixedDelay = 60_000)
    public void cleanExpiredRecords() {
        // Periodic work.
    }
}
~~~

The method is invoked by scheduling infrastructure. Never instantiate a fresh `ScheduledExecutorService` inside each job run.

### 14.2. Stop Scheduling Before Closing Dependencies

If a job uses a `DataSource` or HTTP client, shutdown must prevent new runs and let running tasks finish or cancel per policy before closing the dependencies those tasks need.

Never let a scheduler continue submitting tasks to a shut-down executor or calling a closed client.

### 14.3. Long-Running Tasks

If a scheduled task can run longer than its period:

- Choose `fixedDelay` vs. `fixedRate` according to desired semantics.
- Decide whether overlapping executions are allowed.
- Use locks/guards if concurrent runs are forbidden.
- Define timeouts and cancellation policies.
- Ensure shutdown can cancel or wait for the task.

Resource lifecycles and task concurrency are directly linked: a running task may still hold a connection or file when the context begins shutting down.

## 15. DataSource and JDBC Resources

Spring Boot auto-configures a `DataSource` based on dependencies and settings. The connection pool is typically managed as a bean in the ApplicationContext.

A service using the `DataSource`:

~~~java
@Repository
public class CustomerRepository {

    private final JdbcTemplate jdbcTemplate;

    public CustomerRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }
}
~~~

The repository does not own the connection pool and does not close the `DataSource` when a query finishes.

### 15.1. Let the Transaction Manager Manage Connections

With Spring JDBC/JPA, the transaction manager handles acquiring, binding to the transaction, and releasing connections according to the transaction lifecycle.

Example:

~~~java
@Transactional
public void transfer(AccountId from, AccountId to, Money amount) {
    // Perform repository operations inside the transaction.
}
~~~

Never manually close a connection bound to a transaction by the framework when transaction management owns it.

### 15.2. When Acquiring JDBC Connections Directly

If code calls `DataSource.getConnection()` directly, that code must close the `Connection`:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
             connection.prepareStatement(
                     "select id from customer where active = ?")) {

    statement.setBoolean(1, true);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            // Read results.
        }
    }
}
~~~

Closing the connection returns it to the pool when the `DataSource` uses pooling; it does not necessarily close the physical socket immediately.

### 15.3. Never Close the Pool from a Repository

A `Connection` is a per-operation/per-transaction resource. A `DataSource` pool is an application-level resource. Their lifecycles are different.

The container closes the pool when the `DataSource` bean is destroyed. A repository only closes connections that its own operation acquired under the JDBC contract.

## 16. HTTP Clients and Connection Pools

An HTTP client may retain connection pools, event loops, selector threads, or native resources. When a client is reused, it needs an application-level owner.

Example configuration:

~~~java
@Configuration(proxyBeanMethods = false)
public class PartnerHttpConfiguration {

    @Bean(destroyMethod = "close")
    PartnerHttpClient partnerHttpClient() {
        return PartnerHttpClient.create();
    }
}
~~~

The class name here illustrates a client exposing `close()`. With real clients such as Apache HttpClient, Reactor Netty, or vendor SDKs, use the exact shutdown/dispose API for your library version.

### 16.1. Injecting the Client into a Service

~~~java
@Service
public class PartnerGateway {

    private final PartnerHttpClient client;

    public PartnerGateway(PartnerHttpClient client) {
        this.client = client;
    }
}
~~~

The gateway uses the client; the bean factory owns it, and the container handles cleanup. Never close the client after every HTTP call if the library designed it for reuse.

### 16.2. Async HTTP Clients Must Stop Event Loops

Some clients manage dedicated event loops or connection providers. Closing only a wrapper without disposing of the event loop or pool can leave threads running.

Check the library's lifecycle API:

- Does `close()` shut down the connection pool?
- Does a separate provider require `dispose()`?
- Is there an async callback when shutdown finishes?
- Is there a timeout for active requests?

A proper destroy method must release all resources created and owned by the bean factory.

### 16.3. Do Not Create a Client per Request Unnecessarily

Repeatedly creating clients can cause:

- Repeated TLS/DNS/connection-pool initialization overhead.
- Rising socket counts.
- Hard-to-track cleanup.
- Lost connection reuse.

If a client is thread-safe and designed for sharing, a singleton bean is usually right. If the library requires a per-scope client, follow the library's contract.

## 17. Files, Streams, and Temporary Resources

File streams are normally short-lived and should be closed right where they are opened.

~~~java
public void copy(Path source, Path target) throws IOException {
    try (InputStream in = Files.newInputStream(source);
         OutputStream out = Files.newOutputStream(target)) {
        in.transferTo(out);
    }
}
~~~

Never keep a stream open in a singleton field just to share it across requests unless the design genuinely needs a long-lived handle with explicit synchronization and lifecycle.

### 17.1. Creating Temporary Files and Deleting Upon Completion

~~~java
Path temp = Files.createTempFile("import-", ".csv");
try {
    process(temp);
} finally {
    Files.deleteIfExists(temp);
}
~~~

If you need to preserve failed files for debugging, implement an explicit retention policy instead of skipping cleanup indefinitely.

### 17.2. Large Files or Async Tasks

If a method submits an async task to process a file:

- Do not close the stream before the worker finishes reading.
- Do not retain a request-scoped `MultipartFile` after the request ends if backing temp files may be deleted.
- Move data to storage with an appropriate lifecycle before submitting.
- Ensure cleanup runs after the task succeeds or fails.

### 17.3. Memory Buffers Are Also Scoped Resources

A `ByteArrayOutputStream` does not require `close()` to free OS handles, yet large buffers still occupy heap memory. Resource lifecycles are not only about closing sockets and files; they also cover releasing references, bounding sizes, and not retaining data longer than necessary.

Never store large request bodies or uploaded files in singleton fields after processing finishes.

## 18. Shutdown Hooks and Closing ApplicationContext

The Spring container can only invoke destroy callbacks when the context actually closes.

With a manually managed context:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(OrderApiApplication.class, args);

// When stopping the application programmatically:
context.close();
~~~

In a normal Spring Boot application, `SpringApplication` registers a shutdown hook to close the ApplicationContext during normal JVM shutdown.

### 18.1. What Is a Shutdown Hook?

The JVM allows registering hooks that run when normal JVM shutdown begins:

~~~java
Runtime.getRuntime().addShutdownHook(
        new Thread(() -> {
            // JVM-level cleanup if truly needed.
        }));
~~~

Spring Boot normally manages context closure through its own shutdown hook. Therefore, you do not need to register a separate hook just to trigger `@PreDestroy` or `context.close()`.

### 18.2. Do Not Call System.exit() in Business Code

Calling `System.exit()` from a service or controller terminates the entire JVM and disrupts every active request.

If an operation needs to stop the application, route the request to a process/deployment manager or an authorized orchestration component. Never let business logic arbitrarily kill the process.

### 18.3. SIGTERM and SIGKILL Differ

In Unix/container environments:

- `SIGTERM` gives the process a chance to shut down cleanly; the JVM runs shutdown hooks.
- `SIGINT` also normally initiates JVM shutdown.
- `SIGKILL` terminates the process immediately; shutdown hooks do not run.

Consequently, containers need a sufficient termination grace period, and applications must shut down promptly within bounded limits.

Never rely on `@PreDestroy` to guarantee critical work finishes when a process can be forcefully killed.

### 18.4. Do Not Register Multiple Shutdown Hooks for the Same Resource

If Spring already manages a client bean and a custom hook also closes that client, duplicate or misordered cleanup can happen.

Pick a single owner and let the lifecycle container invoke the proper callback.

## 19. Cleanup Order Between Beans

A bean can depend on another bean both during operation and during shutdown.

Example:

~~~text
OrderEventConsumer
       │ uses
       ▼
MessageTransport
       │ uses
       ▼
NetworkConnectionPool
~~~

At shutdown, the consumer should stop receiving messages first, the transport should stop next, and the connection pool should close once no component uses it.

### 19.1. The Dependency Graph Helps Spring Determine Order

When bean A has a constructor dependency on bean B, Spring knows A depends on B. During singleton cleanup, dependent beans are normally destroyed before their dependencies so A can release resources while B is still available.

This is yet another reason to declare dependencies via constructors rather than looking up beans manually via ApplicationContext.

### 19.2. @DependsOn for Lifecycle Dependencies Not Expressed via Injection

When an initialization/destruction order exists that is not expressed via constructor dependencies, use `@DependsOn`:

~~~java
@Bean
ResourceRegistry resourceRegistry() {
    return new ResourceRegistry();
}

@Bean
@DependsOn("resourceRegistry")
WorkerService workerService() {
    return new WorkerService();
}
~~~

`WorkerService` is created after `ResourceRegistry`; when singletons are destroyed, dependent beans are generally destroyed before the beans they depend on.

Do not use `@DependsOn` instead of constructor injection if `WorkerService` actually needs `ResourceRegistry`. Inject dependencies directly; `@DependsOn` is only for special ordering relationships not captured by dependency references.

### 19.3. SmartLifecycle Stop Runs Before Destroy Callbacks

In the ApplicationContext shutdown flow, lifecycle components are stopped before singleton beans are destroyed. This lets consumers halt activity before low-level resources close.

A typical design:

1. `SmartLifecycle` consumer stops accepting messages and drains in-flight work.
2. Workers/executors stop per policy.
3. `@PreDestroy` or `destroyMethod` closes clients and pools.

Exact order depends on phases and the dependency graph. Design phases intentionally rather than relying on bean names or file order.

### 19.4. Avoid Cleanup Depending on an Already-Destroyed Bean

If A's `@PreDestroy` must call B, ensure the lifecycle/dependency graph keeps B alive while A cleans up. If this cannot be expressed cleanly, consolidate resource ownership into one bean or create a coordinator with a well-defined lifecycle.

Never let two destroy methods call each other without a stable ordering.

## 20. Handling Errors During Cleanup

Cleanup can fail too:

- Client `close` throws `IOException`.
- Executor fails to finish within timeout.
- Message consumer fails to ack/commit messages.
- File flush fails due to a full disk.
- Remote resource stops responding.

### 20.1. Do Not Hide Cleanup Errors

Avoid:

~~~java
@PreDestroy
void close() {
    try {
        client.close();
    } catch (Exception ignored) {
        // Ignore completely.
    }
}
~~~

If a cleanup failure is operationally meaningful, log it at an appropriate level:

~~~java
@PreDestroy
void close() {
    try {
        client.close();
    } catch (Exception ex) {
        log.warn("Could not close partner client cleanly", ex);
    }
}
~~~

Messages must never expose secrets or sensitive data. Also remember the logging backend might itself be shutting down; avoid relying on a remote appender that may have already stopped.

### 20.2. Cleanup Should Have Bounded Timeouts

A callback waiting indefinitely can prevent the process from exiting. For executors/clients/consumers, set explicit timeouts and define timeout behavior:

- Continue waiting for one more bounded interval?
- Cancel/interrupt tasks?
- Close connections immediately?
- Record the count of incomplete tasks?

The policy depends on business needs. No single choice fits every system.

### 20.3. Do Not Throw Cleanup Exceptions to Pretend Startup Succeeded

If an init callback fails, a destroy callback cannot mask the failure to keep the context running. Cleanup only frees already-created resources; it does not fix initial startup conditions.

### 20.4. Cleanup May Need to Be Idempotent

A `close`/`stop` method can be invoked via multiple lifecycle paths in certain designs or explicit retries. If the contract requires safe repeated calls, ensure:

- Closing an already-closed resource does not error.
- Tasks cannot be submitted after stopping.
- Data is not flushed/committed twice causing side effects.
- Running/closed state is updated safely across threads.

Never assume a third-party library's `close` is idempotent; check its API.

## 21. Separating Initialization from Readiness and Health

A resource can open cleanly in `@PostConstruct` yet lose connectivity to an external service later. Conversely, an external system may be temporarily unavailable at startup.

Decide your policy:

- **Fail-fast:** the application cannot serve safely unless the resource is ready.
- **Bounded retry:** startup waits for a defined period.
- **Degraded mode:** the application serves core features while secondary features stay disabled.
- **Lazy connect:** open connections only when actually needed.

### 21.1. Do Not Use @PostConstruct to Ping Dependencies Forever

Example:

~~~java
@PostConstruct
void waitUntilPartnerIsReady() {
    while (!partnerClient.isHealthy()) {
        // Wait forever.
    }
}
~~~

This can prevent the context from ever refreshing and prevent deployments from assessing startup state.

If waiting on a dependency is needed, enforce timeouts, backoff, logging, and a clear decision between startup failure and degraded mode.

### 21.2. Health Indicators Report Runtime Status

Spring Boot Actuator provides health endpoints to observe dependencies once the application is running.

Health indicators do not release resources and do not replace lifecycle callbacks. They inform operators of status; lifecycles handle start/stop/cleanup.

### 21.3. Readiness Differs from Liveness

- Readiness indicates whether an instance should receive traffic.
- Liveness indicates whether a process/container must be restarted due to an unrecoverable state.

Do not mark an application unhealthy simply because an optional secondary feature is temporarily unavailable if the system is designed for degraded operation.

## 22. Managing Listeners and Message Consumers

Message consumers typically hold sockets, subscriptions, threads, or broker connections. They require ordered start/stop.

A proper lifecycle:

~~~text
Context refresh
      │
      ▼
Open connection / register subscription
      │
      ▼
Receive messages
      │
      ▼
Shutdown begins
      │
      ▼
Stop accepting new messages
      │
      ▼
Wait for in-flight messages / ack / commit
      │
      ▼
Close subscription
      │
      ▼
Close broker client/pool
~~~

### 22.1. Distinguish Stopping a Consumer from Closing a Client

A consumer may manage only its subscription while a client/connection pool is shared across multiple consumers.

In that case:

- Consumer stops: stops its own subscription.
- Client owner closes: closes connections after all consumers have stopped.

Never let one consumer close a shared broker client while other consumers are still running.

### 22.2. Handling In-Flight Messages

During shutdown:

- Are in-flight messages allowed to finish?
- Must ack/commit happen before timeout?
- On timeout, is the message redelivered or dropped?
- Is the handler idempotent to handle redelivery?

These are messaging system and business contracts that `@PreDestroy` alone cannot solve.

### 22.3. Do Not Ack Messages Merely Because of Shutdown

Never mark a message as successfully processed if the business operation did not finish. When stopping, use broker semantics to release/requeue or allow redelivery per policy.

Proper shutdown preserves message processing correctness rather than merely making threads vanish.

## 23. Caches and Lifecycle-Managed Resources

A local cache may need to:

- Close a cleanup scheduler.
- Stop refresh threads.
- Flush persistence if the cache supports write-behind.
- Free native or off-heap memory.

If a cache is a Spring-managed bean, check the library's close/stop API and declare an appropriate destroy method.

### 23.1. Caches Are Not Durable Storage

Do not rely on cache destroy callbacks to persist critical business data. Processes can be killed before cleanup, and write-behind queues might remain unflushed.

Data requiring durability must be committed via appropriate storage/transactions during business processing.

### 23.2. Scheduled Refresh Must Stop Before Closing the Cache

If a scheduler periodically refreshes a cache, shutdown should stop the scheduler first before closing the cache or clients used by the refresh task.

Use `SmartLifecycle` phases or give one owner bean responsibility for both scheduler and cache if they share a lifecycle.

## 24. Managing Resources Across Multiple ApplicationContexts

Some applications use parent/child ApplicationContexts. Resources created in the parent can be used by beans in child contexts.

Example:

~~~text
Parent ApplicationContext
  └── SharedDataSource
  └── SharedHttpClient

Child ApplicationContext
  └── WebController
  └── RequestService
~~~

When a child closes, the parent may stay alive. Therefore:

- A child must not close the parent's `SharedDataSource`.
- The parent closes shared resources only when the parent itself terminates.
- A bean must not assume its own context is the last context in the process.

### 24.1. Scope Ownership by Context

Create resources in the context whose lifecycle matches their consumers. If a resource is shared across multiple child contexts, creating it in the parent makes sense.

If each child needs its own client, register it in the child so the child's lifecycle owns that client.

### 24.2. Avoid Closing a Parent Context from a Child Bean

A bean inside a child context must not call `parent.close()` merely because it finished a task. Doing so can bring down sibling child contexts and shared resources.

Let context management components or deployment tooling orchestrate the overall application lifecycle.

## 25. Initialization and Destruction Callback Order

For a bean under standard lifecycle management, the typical callback order is:

| Initialization Phase | Callback |
|---|---|
| After dependency injection | @PostConstruct |
| Next | InitializingBean.afterPropertiesSet() |
| Last among custom init callbacks | Declared initMethod |

During destruction:

| Destruction Phase | Callback |
|---|---|
| First | @PreDestroy |
| Next | DisposableBean.destroy() |
| Last among custom destroy callbacks | Declared destroyMethod |

This is the ordering among callback mechanisms for a single bean under supported lifecycles. `BeanPostProcessor`s can also wrap initialization and create proxies; lifecycle-aware components may run separate stop steps before destroy callbacks.

### 25.1. Avoid Depending on Callback Order Unless Necessary

If both `@PreDestroy` and `destroyMethod` close the same client, cleanup can run twice. Choose a single primary path for closing.

When multiple steps exist:

~~~java
@PreDestroy
void shutdown() {
    stopAcceptingWork();
    flushPendingState();
    closeClient();
}
~~~

One explicitly ordered method is often easier to follow than multiple scattered callbacks, provided all steps belong to the same owner and follow a clear error policy.

### 25.2. Beans Failing Mid-Initialization Must Clean Up Opened Resources Themselves

An easy-to-miss case:

~~~java
@PostConstruct
void initialize() {
    resource = resourceFactory.open();
    resource.configure(); // May throw an exception.
}
~~~

If `configure()` fails, the bean never finished initialization. You cannot rely on the bean's destroy callback to close the newly opened resource.

Handle cleanup directly during initialization:

~~~java
@PostConstruct
void initialize() {
    ResourceHandle candidate = resourceFactory.open();

    try {
        candidate.configure();
        this.resource = candidate;
    } catch (RuntimeException ex) {
        try {
            candidate.close();
        } catch (Exception closeError) {
            ex.addSuppressed(closeError);
        }
        throw ex;
    }
}
~~~

This example assumes `close()` may throw a checked exception and `configure()` throws a `RuntimeException`. Crucially, the resource is assigned to the field only after initialization succeeds; on failure, `candidate` is closed before rethrowing.

### 25.3. Factory Methods Must Also Clean Up If Bean Creation Fails

If an `@Bean` method opens a resource and throws before returning the object to Spring, the container never received the bean instance to manage its destroy callback.

Ensure the factory method closes the resource if creation/configuration fails:

~~~java
@Bean(destroyMethod = "close")
PartnerClient partnerClient() {
    PartnerClient client = new PartnerClient();
    try {
        client.initialize();
        return client;
    } catch (RuntimeException ex) {
        try {
            client.close();
        } catch (Exception closeError) {
            ex.addSuppressed(closeError);
        }
        throw ex;
    }
}
~~~

Once the factory method returns successfully, Spring assumes ownership per bean configuration and invokes the destroy method when the context closes.

## 26. Testing @PostConstruct and @PreDestroy

A lifecycle test should prove callbacks execute properly when the context refreshes and closes.

JUnit 5 example:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.atomic.AtomicInteger;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class ResourceLifecycleTests {

    @Test
    void callsInitializationAndDestroyCallbacks() {
        AtomicInteger initialized = new AtomicInteger();
        AtomicInteger destroyed = new AtomicInteger();

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.registerBean(
                    LifecycleProbe.class,
                    () -> new LifecycleProbe(initialized, destroyed));

            context.refresh();

            assertThat(initialized.get()).isEqualTo(1);
            assertThat(destroyed.get()).isZero();
        }

        assertThat(destroyed.get()).isEqualTo(1);
    }

    static class LifecycleProbe {

        private final AtomicInteger initialized;
        private final AtomicInteger destroyed;

        LifecycleProbe(
                AtomicInteger initialized,
                AtomicInteger destroyed) {
            this.initialized = initialized;
            this.destroyed = destroyed;
        }

        @PostConstruct
        void initialize() {
            initialized.incrementAndGet();
        }

        @PreDestroy
        void close() {
            destroyed.incrementAndGet();
        }
    }
}
~~~

This test creates a real context, refreshes it to trigger initialization, and closes it via try-with-resources. Once the block exits, the destroy callback must have run.

### 26.1. Testing @Bean destroyMethod

~~~java
@Test
void invokesConfiguredDestroyMethod() {
    AtomicBoolean closed = new AtomicBoolean();

    try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext()) {

        context.registerBean(
                ClientConfigurationForTest.class,
                () -> new ClientConfigurationForTest(closed));
        context.refresh();

        assertThat(closed).isFalse();
    }

    assertThat(closed).isTrue();
}

static class ClientConfigurationForTest {

    private final AtomicBoolean closed;

    ClientConfigurationForTest(AtomicBoolean closed) {
        this.closed = closed;
    }

    @Bean(destroyMethod = "close")
    TestClient testClient() {
        return new TestClient(closed);
    }
}

static class TestClient {

    private final AtomicBoolean closed;

    TestClient(AtomicBoolean closed) {
        this.closed = closed;
    }

    public void close() {
        closed.set(true);
    }
}
~~~

This illustrates the concept of callback testing; in real tests, register the configuration class as a Spring-processed configuration—for instance via `@Configuration` or registering/importing bean definitions properly.

### 26.2. Using ApplicationContextRunner

`ApplicationContextRunner` closes the context automatically after its callback. You can assert:

~~~java
AtomicBoolean destroyed = new AtomicBoolean();

new ApplicationContextRunner()
        .withBean(
                LifecycleProbe.class,
                () -> new LifecycleProbe(destroyed))
        .run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(destroyed).isFalse();
        });

assertThat(destroyed).isTrue();
~~~

The test checks state after `run()` finishes, once the runner has closed the context.

### 26.3. Testing Asynchronous Shutdown

For `SmartLifecycle`, verify:

- `start` is called on context refresh when `autoStartup=true`.
- `isRunning` reflects current state.
- `stop` is called when the context closes.
- The callback in `stop(Runnable)` is invoked after work stops.
- Shutdown does not hang past timeout.

If tests use asynchronous completion, use latches/futures with finite timeouts; never wait indefinitely and hang the test suite.

## 27. Monitoring Resource Leaks at Runtime

An application can run for hours before a resource leak becomes obvious. Warning signs include:

- Thread count steadily climbing.
- Connection pools frequently exhausted.
- File descriptor/socket counts rising.
- Heap retaining unused buffers/sessions.
- Scheduled tasks continuing to run after a feature is disabled.
- The JVM failing to exit after context closure.

### 27.1. Thread Dumps

Thread dumps show:

- Which threads are running.
- Which executor/client owns each thread.
- Whether threads are waiting indefinitely or deadlocked.
- Whether an executor still has live workers after shutdown.

If a process refuses to exit, do not simply increase termination delays. Identify which thread or resource is keeping the JVM alive.

### 27.2. Metrics

Track relevant indicators:

- Pool active/idle/pending connections.
- Active threads, queue sizes, rejected tasks.
- HTTP connection pool utilization.
- Scheduled task durations/failures.
- Filesystem usage.
- Message consumer lag and in-flight messages.

Metrics expose leak trends before a process crashes.

### 27.3. Actuator and Micrometer

Spring Boot Actuator/Micrometer can expose metrics for datasources, the JVM, executors, or web servers depending on dependencies and instrumentation.

Not every custom resource gets metrics automatically. Custom pools/clients may require explicit instrumentation or metric adapters.

### 27.4. Observing Startup/Shutdown Logs

Lifecycle components can log start/stop milestones:

~~~java
log.info("Starting order event consumer");
log.info("Stopping order event consumer");
log.info("Order event consumer stopped");
~~~

Keep messages brief with clear component identity. Never log payloads or credentials. Across multiple replicas, include safe instance/service identity to distinguish logs.

## 28. Common Resource Management Pitfalls

### 28.1. Opening a File Without Closing It

**Symptom:** file handle count grows, files stay locked, or the process runs out of descriptors.

**Cause:** opening `InputStream`/`OutputStream` without closing along every branch.

**Remedy:** use try-with-resources for local resources.

### 28.2. Closing an Injected Singleton After Every Request

**Symptom:** the first request succeeds, subsequent requests fail with "client closed."

**Cause:** a consumer closed a resource it merely borrowed.

**Remedy:** identify the owner bean; only the owner/container closes shared resources.

### 28.3. Prototype Beans Never Cleaned Up

**Symptom:** many prototype instances open resources without corresponding destroy callbacks.

**Cause:** Spring does not fully manage destruction of prototype instances once handed to callers.

**Remedy:** the caller closes each instance, typically via `AutoCloseable`/try-with-resources.

### 28.4. Injecting a Prototype Directly into a Singleton

**Symptom:** expecting a fresh instance per method call, yet reusing the same instance.

**Cause:** the prototype was resolved once when the singleton was created.

**Remedy:** use `ObjectProvider` or `Provider` to resolve instances per use.

### 28.5. Executors Preventing JVM Exit

**Symptom:** shutdown logs appear, yet the process never exits.

**Cause:** executors or manual threads were not shut down or interrupted.

**Remedy:** manage executors as beans with shutdown policies; never spawn threads without stop signals.

### 28.6. @PreDestroy Not Running on kill -9

**Symptom:** cleanup does not execute when the process is forcefully terminated.

**Cause:** the JVM never gets a chance to run shutdown hooks.

**Remedy:** use graceful termination, appropriate timeouts, and durable data designs that do not depend on cleanup hooks.

### 28.7. Cleanup Running Twice

**Symptom:** client `close` called multiple times, throwing errors or duplicating logs.

**Cause:** both consumer and owner bean close the resource, or both an annotation and `destroyMethod` trigger the same action.

**Remedy:** designate a single owner and a single primary cleanup path; ensure idempotency if required by contract.

### 28.8. @PostConstruct Opens a Resource Then Fails Midway

**Symptom:** context startup fails, yet a newly opened socket or file handle leaks.

**Cause:** the bean never completed initialization, so destroy callbacks are not a reliable cleanup path for local resources opened mid-method.

**Remedy:** clean up inside `catch` before rethrowing; assign the resource to a field only after initialization succeeds.

### 28.9. Startup Runners Running Forever

**Symptom:** the app never reaches ready state.

**Cause:** `ApplicationRunner` waits on an external system or executes an unbounded job.

**Remedy:** apply timeout/retry policies and move long-running jobs to background workers or dedicated job runners.

### 28.10. @PostConstruct Calling Other Beans Too Early

**Symptom:** circular dependency errors, unpredictable initialization order, or premature side effects before the context is ready.

**Cause:** one bean's callback triggers initialization across many other beans.

**Remedy:** keep callbacks simple; use `ApplicationRunner`/events when coordination after context refresh is needed.

### 28.11. Scheduler Calling Already-Closed Clients

**Symptom:** exceptions during shutdown or after context closure.

**Cause:** scheduled tasks did not stop before their dependencies were destroyed.

**Remedy:** stop scheduling/consumers first; define explicit lifecycle phases and shutdown policies.

### 28.12. DataSource Closed by a Repository

**Symptom:** other repositories fail with "connection pool has been shut down."

**Cause:** a consumer bean closed the shared `DataSource`.

**Remedy:** close JDBC `Connection`s per transaction/operation; let the `DataSource` owner/container close the pool.

### 28.13. Graceful Shutdown Timeout Too Short

**Symptom:** in-flight requests/tasks are terminated during deployments.

**Cause:** Spring or deployment timeouts are shorter than actual processing time.

**Remedy:** measure shutdown duration, configure realistic timeouts, and ensure the process manager grants enough termination grace period.

### 28.14. Graceful Shutdown Timeout Too Long

**Symptom:** slow rollouts/scale-downs with instances holding resources too long.

**Cause:** waiting indefinitely or setting timeouts higher than operationally acceptable.

**Remedy:** cap timeouts, define cancellation/fallback behavior, and monitor remaining active tasks.

### 28.15. Context Closed Yet Client Threads Stay Alive

**Symptom:** JVM does not exit, or thread dumps show event loop/client workers still alive.

**Cause:** the destroy method does not call the library's right close/dispose API.

**Remedy:** verify the client's lifecycle contract and confirm threads/pools terminate after context closure.

### 28.16. Using ContextClosedEvent Instead of All Destroy Callbacks

**Symptom:** multiple listeners close the same resource or cleanup order becomes unclear.

**Cause:** ownership is centralized into global event handlers.

**Remedy:** keep destroy callbacks on owner beans; use events only for coordination when genuinely needed.

### 28.17. Closing a Parent Resource from a Child Context

**Symptom:** closing one web context breaks datasources/clients for another context.

**Cause:** a child closed a resource owned by the parent.

**Remedy:** separate ownership by context and only let the owning context close its resources.

### 28.18. Relying on @PreDestroy to Commit Critical Data

**Symptom:** data is lost if the process is killed or shutdown times out.

**Cause:** cleanup hooks are not durability mechanisms.

**Remedy:** commit data inside business transactions or durable outboxes/storage; destroy callbacks should only flush safely flushable buffers/resources.

## 29. Complete Example: Managing a Message Consumer and Client

Suppose an application consumes order events from a message broker:

- The broker client holds a connection pool and must close on shutdown.
- The consumer opens its subscription once the application is ready.
- During shutdown, the consumer must stop taking new messages and wait for in-flight processing.
- The client must close only after the consumer has stopped.

Separate ownership into two beans:

~~~java
@Configuration(proxyBeanMethods = false)
public class MessagingResourceConfiguration {

    @Bean(destroyMethod = "close")
    MessageTransport messageTransport() {
        return MessageTransport.create();
    }
}
~~~

`MessageTransport` is an illustrative class exposing a public `close` method.

Consumer:

~~~java
@Component
public class OrderEventConsumer implements SmartLifecycle {

    private final MessageTransport transport;
    private volatile boolean running;

    public OrderEventConsumer(MessageTransport transport) {
        this.transport = transport;
    }

    @Override
    public void start() {
        transport.subscribe("order-events");
        running = true;
    }

    @Override
    public void stop() {
        if (running) {
            transport.stopSubscription("order-events");
            running = false;
        }
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
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

This code illustrates ownership and ordering. In real implementations, ensure `stopSubscription` stops receiving new messages and waits for in-flight messages up to a timeout. If stopping is async, invoke the callback only after stopping finishes.

### 29.1. Desired Sequence

~~~text
Startup:
MessageTransport is created
          │
          ▼
OrderEventConsumer.start()
          │
          ▼
Subscription receives messages

Shutdown:
OrderEventConsumer.stop()
          │
          ▼
Subscription stops / in-flight finishes
          │
          ▼
MessageTransport.close()
~~~

The consumer holds a reference to the transport, so the dependency graph and lifecycle phase keep the transport alive while the consumer stops.

### 29.2. Who Closes the Transport?

In the example, the bean factory creates `MessageTransport` and declares `destroyMethod = "close"`. The consumer merely uses the transport to subscribe and stop its subscription; it does not close the shared client.

When multiple consumers share one transport, having a single client owner becomes even more critical.

### 29.3. What If the Consumer Fails to Stop on Time?

Set shutdown timeouts matching message processing times and broker policies. When the timeout expires:

- Record the count of incomplete messages.
- Allow the broker to redeliver if supported by the contract.
- Never ack messages that did not finish successfully.
- Proceed with closing the client within shutdown limits.

Never wait indefinitely, and never silently ack incomplete messages just to make the process exit.

## 30. Designing Lifecycles by Resource Type

A quick decision table:

| Resource | Where Created | Where Stopped / Closed |
|---|---|---|
| File stream inside a method | Inside method | try-with-resources |
| Manual JDBC Connection | Within operation/transaction | try-with-resources or transaction manager |
| DataSource pool | Bean config/auto-configuration | Container destroy callback |
| Shared HTTP client | `@Bean` factory | destroyMethod/close/dispose |
| ThreadPoolTaskExecutor | `@Bean` config | Spring executor lifecycle |
| Self-managed ExecutorService | Owner bean/factory | close/destroy callback with timeout |
| Scheduled task | Scheduling infrastructure | Scheduler lifecycle/shutdown |
| Message subscription | `SmartLifecycle.start()` | `SmartLifecycle.stop()` |
| Prototype resource session | `ObjectProvider.getObject()` | Caller closes instance |
| Request-scoped state | Request scope | Scope cleanup when request ends |
| Temporary file | Inside task | `finally`/delete upon completion |
| Durable business event | Transaction/outbox | Never rely on shutdown hooks |

Do not pick lifecycle mechanisms out of habit. Choose based on the **resource's real lifetime** and **ownership**.

## 31. Common Misconceptions

**"Spring automatically closes every object it creates."**  
No. Fully managed singletons get destroy callbacks; prototype beans do not have container-managed destruction after being handed to callers.

**"@PostConstruct is the right place to run all startup tasks."**  
No. It belongs to a single bean's lifecycle. Tasks requiring multiple beans to be ready fit `ApplicationRunner` or `ApplicationReadyEvent` better.

**"@PreDestroy always runs when the process exits."**  
No. Forcefully killed processes or JVM crashes may bypass shutdown hooks.

**"A bean injecting a client has the right to close it."**  
No. Using a resource does not mean owning it.

**"try-with-resources works for every injected dependency."**  
No. Use it only when the method/caller truly owns the resource for that block's scope.

**"@Bean destroyMethod must always be declared manually."**  
No. Spring can infer certain public `close`/`shutdown` methods; declare it explicitly when you want the contract crystal clear.

**"@PostConstruct and InitializingBean must be used together."**  
No. Pick one primary callback per responsibility.

**"Closing a bean in both @PreDestroy and destroyMethod cannot collide."**  
No. If both trigger `close`, cleanup can run twice. Establish one cleanup path.

**"Prototype scope means Spring closes each instance automatically."**  
No. Callers are usually responsible for cleaning up prototype instances they receive.

**"Injecting a prototype into a singleton creates a new prototype on every method call."**  
No. Dependencies are normally resolved at singleton creation time; use `ObjectProvider`/`Provider` when fresh instances per call are needed.

**"Thread pools stop automatically when ApplicationContext closes."**  
Not if created outside lifecycle management or without a shutdown policy. Manage executors as beans and configure timeouts.

**"SmartLifecycle is just another way to write @PostConstruct."**  
No. `SmartLifecycle` manages component start/stop, phases, and asynchronous stops.

**"Higher phases start first."**  
No. Lower phases normally start first; on stop, the order reverses.

**"Graceful shutdown guarantees every request/task finishes."**  
No. It grants a bounded time window; timeouts can still terminate long-running tasks.

**"ContextClosedEvent replaces destroy callbacks."**  
No. Events are for observation/coordination; destroy callbacks express resource ownership more directly.

**"A cleanup callback can wait forever."**  
No. Shutdown needs timeouts so the process does not hang.

**"You can use @PreDestroy to commit critical transactions."**  
No. Durable data must be committed within business transactions or durable mechanisms.

**"If @PostConstruct fails, @PreDestroy will definitely close any opened resources."**  
Do not rely on that. Mid-initialization failures must clean up local resources before throwing.

**"A shared resource can be closed by multiple beans."**  
No. A single clear owner prevents premature closing and duplicate cleanup.

**"Actuator health manages resources."**  
No. Health only observes status; lifecycle callbacks and owners handle start/stop/close.

## 32. Resource Lifecycle Design and Verification Workflow

When a bean must open or hold resources, follow this sequence:

### Step 1 — Identify the Resource Type

Is it a local file/stream, database connection, connection pool, executor, scheduler, HTTP client, message subscription, or cache?

Read its API to see whether it uses `close()`, `shutdown()`, `dispose()`, or a dedicated lifecycle contract.

### Step 2 — Identify Ownership

Who creates it? Who uses it? Who closes it? Is it shared across beans?

Designate a single owner responsible for cleanup.

### Step 3 — Choose the Lifecycle Scope

- Method/task → try-with-resources or `finally`.
- Bean/application → Spring bean lifecycle.
- Prototype instance → caller cleanup.
- Request/session → scope lifecycle.
- Start/stop component → `Lifecycle`/`SmartLifecycle`.

### Step 4 — Choose the Appropriate Callback

- Simple initialization → `@PostConstruct` or `initMethod`.
- Singleton cleanup → `@PreDestroy`, `destroyMethod`, or `DisposableBean`.
- Background-active component → `SmartLifecycle`.
- Startup action needing context refresh → `ApplicationRunner`.

### Step 5 — Design Ordering

Consumers stop before transports; workers stop before clients; schedulers stop before the resources their tasks use.

Use the dependency graph, phases, or `@DependsOn` only when necessary and with an explicit contract.

### Step 6 — Set Timeouts

Choose timeouts for:

- Waiting for tasks to finish.
- Stopping consumers.
- Closing clients.
- Web server graceful shutdown.
- Overall process termination grace period.

Never let a resource keep the process alive indefinitely.

### Step 7 — Handle Mid-Initialization Errors

If a resource is opened yet the callback/factory method can still fail, close the resource yourself before throwing. Transfer ownership to the bean only once initialization succeeds.

### Step 8 — Test

Test init callbacks, destroy callbacks, close methods, lifecycle start/stop, and startup failure cases. Use finite timeouts for asynchronous cleanup.

### Step 9 — Observe at Runtime

Monitor thread counts, pool utilization, queue sizes, open connections, and shutdown logs. Inspect thread dumps if the JVM fails to exit.

### Step 10 — Verify Deployment

Ensure systemd/containers/Kubernetes grant sufficient graceful shutdown time and do not kill the process before lifecycle completion.

### Decision Diagram

~~~text
Application needs a resource
          │
          ▼
Used only within one operation?
          │
      ┌───┴────┐
      │        │
     Yes       No
      │        │
      ▼        ▼
try-with-   Lives for a bean /
resources   component scope?
                │
            ┌───┴────┐
            │        │
           Yes       No
            │        │
            ▼        ▼
      Spring bean   Caller / scope /
      lifecycle     external owner
            │
            ▼
      Needs async
      start/stop?
            │
        ┌───┴────┐
        │        │
       Yes       No
        │        │
        ▼        ▼
 SmartLifecycle  init/destroy callback
~~~

## 33. Self-Practice Exercises

### Exercise 1 — Choose the Owner for an HTTP Client

A singleton `PartnerGateway` injects a shared HTTP client. Each `send()` call runs across many requests.

**Question:** Should `PartnerGateway` close the client after every `send()`?

**Suggested Answer:** No. The gateway only uses the client. The bean factory or owning bean is responsible for closing the client when the context shuts down.

### Exercise 2 — Prototype Resource

A prototype `CsvImportSession` opens a file handle. `ImportCoordinator` is a singleton and needs a new session for every file.

**Question:** Does injecting `CsvImportSession` directly create a fresh instance per file? Who closes the session?

**Answer:** No. Direct injection resolves the prototype once at singleton creation time. Use `ObjectProvider` to obtain a fresh instance per file; the caller closes the instance after importing—for example via try-with-resources if it implements `AutoCloseable`.

### Exercise 3 — Choose a Callback

A bean needs to build an internal index after its repository is injected.

**Question:** Which callback should be used?

**Suggested Answer:** `@PostConstruct` or `InitializingBean`/custom init method. Keep initialization brief and avoid assuming every bean in the context is already initialized.

### Exercise 4 — Running Work After Startup

A verification step needs multiple beans and must run only after context refresh.

**Question:** Is `@PostConstruct` on an arbitrary bean the best option?

**Answer:** Not necessarily. `ApplicationRunner` fits better when running after context refresh; `ApplicationReadyEvent` fits when waiting for the startup flow to finish and the app to be ready.

### Exercise 5 — Executor Fails to Stop

The application logged `ContextClosedEvent`, yet the JVM stays alive due to worker threads.

**Question:** What should you check?

**Suggested Answer:** Check whether the executor is registered as a bean, whether its destroy callback triggers shutdown, whether tasks are blocked indefinitely, whether threads respond to interrupts, and whether `awaitTermination` has a timeout.

### Exercise 6 — @PreDestroy Does Not Run After Pod Kill

A pod was forcefully killed and cleanup logs never appeared.

**Question:** Is this a Spring lifecycle bug?

**Answer:** Not necessarily. `SIGKILL`/JVM crashes bypass shutdown hooks. Configure an adequate termination grace period and design durability without relying on cleanup hooks.

### Exercise 7 — Message Consumer and Transport

A consumer and transport share a broker connection.

**Question:** Which component should stop first?

**Suggested Answer:** The consumer stops accepting messages and drains in-flight work first; afterward, the owner closes the transport/connection pool.

### Exercise 8 — Resource Opened Before Init Fails

`@PostConstruct` opens a socket, then `configure()` throws an exception.

**Question:** Should you wait for `@PreDestroy` to close the socket?

**Answer:** Do not rely on it because the bean did not finish initialization. Close the socket inside `catch` and rethrow the original exception, adding any close failure as a suppressed exception if needed.

### Exercise 9 — Parent and Child Contexts

A parent context owns a shared `DataSource`. A child context closes.

**Question:** Should a child bean close the `DataSource`?

**Answer:** No. The parent is the owner; the child only uses it. The `DataSource` is closed only when the parent context terminates.

### Exercise 10 — Choosing a Shutdown Mechanism

A component continuously receives messages and needs asynchronous shutdown ordered by phase relative to its transport.

**Question:** Is `@PreDestroy` enough?

**Suggested Answer:** Likely not. `SmartLifecycle` is better suited for managing start/stop, phases, and asynchronous stop completion callbacks; low-level resources still close via their owner's destroy callbacks.

## Core Takeaways

**Resource management starts with ownership.** The component that creates and owns a resource is responsible for closing it; beans injected merely to use a resource must never close a shared resource arbitrarily. Short-lived resources belong in `try-with-resources`; application-lived resources need a clear owner bean and destroy callback.

Spring provides **@PostConstruct/@PreDestroy**, **InitializingBean/DisposableBean**, and **@Bean initMethod/destroyMethod** to handle initialization and cleanup. **Singletons** get container-managed destruction when the context closes; **prototypes** are created by Spring, yet callers must handle cleanup after receiving an instance. **Lifecycle/SmartLifecycle** fits components needing start/stop, phase ordering, or asynchronous shutdown.

A safe shutdown stops accepting new work, waits within bounded time for active requests/tasks/messages, and then closes executors, consumers, clients, and connection pools in proper dependency order. Graceful shutdown and `@PreDestroy` are not guaranteed when a process is forcefully killed; critical data must be protected via transactions or durable storage during business processing.

When designing beans, determine whether each resource belongs to a method, bean, scope, or entire application; pick the right callback; clean up immediately if initialization fails midway; set bounded timeouts; and test both context creation and closure. Doing so lets Spring Boot applications release resources cleanly, prevent leaks, and shut down reliably across deployments and upgrades.
