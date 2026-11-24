# Observing Singleton, Prototype, and On-Demand Bean Lookup

In Spring, scope determines **how the container manages the number of bean instances and when a new instance is created**. The two foundational scopes to understand clearly are `singleton` and `prototype`.

- `singleton`: one instance per bean definition within an `ApplicationContext`.
- `prototype`: each time a bean is requested from the container, Spring creates a new instance.

The difference sounds simple, yet it directly affects state, dependency injection, thread safety, lifecycle, and how tests are written. A common mistake is injecting a prototype bean into a singleton and expecting Spring to automatically create a new prototype on every method call. In reality, dependencies are resolved when the singleton is created, so the singleton holds onto the same prototype instance unless an on-demand lookup mechanism is used.

The lesson **Spring Boot Fundamentals → Integrated Practice → Observing Singleton, Prototype, and On-Demand Bean Lookup** walks through observing bean identity, checking scope in the context, fetching prototypes on demand, choosing the right bean when multiple implementations exist, and managing prototype resources.

## 1. What Is Bean Scope?

Scope describes the lifecycle and instance-sharing boundary that the Spring container applies to a bean definition.

When the container creates a bean, scope governs questions such as:

- Does one bean registration produce one shared instance or many instances?
- When code requests the bean again, does Spring return the existing object or create a new one?
- Are instances shared across consumers?
- Who is responsible for releasing resources when an instance is no longer used?

Common scopes:

| Scope | Behavior | Boundary |
|---|---|---|
| `singleton` | One instance is reused | Per bean definition in one container |
| `prototype` | Creates a new instance each time the container resolves the bean | Per request for the bean |
| `request` | One instance per HTTP request | Web application context |
| `session` | One instance per HTTP session | Web application context |
| `application` | One instance per ServletContext | Web application context |
| `websocket` | One instance per WebSocket lifecycle | Web application context |

In a typical Spring Boot application, most services, repositories, controllers, and components are registered with the default `singleton` scope.

This lesson focuses on `singleton`, `prototype`, and ways to look up beans on demand. Web scopes are mentioned for contrast rather than as the main implementation target.

## 2. Singleton: One Instance per Bean Definition in a Container

When a bean does not declare a specific scope, Spring defaults to `singleton`.

For example:

~~~java
@Service
public class CartService {
    public int itemCount() {
        return 0;
    }
}
~~~

Spring creates and manages one `CartService` instance for that bean definition inside the `ApplicationContext`. When multiple consumers inject that bean, they typically receive the same object:

~~~text
ApplicationContext
       |
       +-- bean definition: cartService
                 |
                 v
          CartService instance
             /        \
            /          \
           v            v
    CheckoutFacade   CartController
~~~

An explicit configuration can also be written as:

~~~java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_SINGLETON)
CartService cartService() {
    return new CartService();
}
~~~

However, since singleton is the default, `@Scope` is usually unnecessary unless you want to emphasize it.

### 2.1. Singleton Does Not Mean One Object for the Entire JVM

This is a very easy point to misunderstand.

Spring's singleton is scoped by **container and bean definition**, not a global singleton pattern across the entire JVM.

If you create two independent contexts:

~~~java
try (var first = new AnnotationConfigApplicationContext(AppConfig.class);
     var second = new AnnotationConfigApplicationContext(AppConfig.class)) {

    Object a = first.getBean(CartService.class);
    Object b = second.getBean(CartService.class);

    System.out.println(a == b); // false
}
~~~

The two contexts hold two separate instances. Within each context, subsequent resolutions of that bean return the same instance.

A normal application usually has one root context, but tests, multi-context applications, parent/child contexts, or embedded applications can create multiple containers.

Therefore, the accurate statement is:

> A singleton bean has one shared instance within the scope of its bean definition inside the ApplicationContext that manages it.

### 2.2. Observing Singletons by Identity

You can check directly with the `==` operator or JUnit's `assertSame`.

~~~java
@Test
void singletonReturnsTheSameInstance() {
    try (var context =
            new AnnotationConfigApplicationContext(AppConfig.class)) {

        CartService first = context.getBean(CartService.class);
        CartService second = context.getBean(CartService.class);

        assertSame(first, second);
    }
}
~~~

`assertSame` checks that two variables reference the exact same object. This is more appropriate than comparing values as defined by `equals()`.

If a class overrides `equals()` to compare data, two distinct objects can still return `true` from `equals()`. That does not prove they are the same instance.

### 2.3. Observing Shared State

A singleton bean can hold state:

~~~java
public class RequestCounter {

    private int count;

    public void increment() {
        count++;
    }

    public int current() {
        return count;
    }
}
~~~

If two consumers receive this bean, mutations through the first consumer are observed by the second consumer:

~~~java
RequestCounter first = context.getBean(RequestCounter.class);
RequestCounter second = context.getBean(RequestCounter.class);

first.increment();

assertEquals(1, second.current());
assertSame(first, second);
~~~

This example shows that a singleton shares both object identity and state. It also highlights an important design requirement: **mutable singleton state must be managed carefully when accessed concurrently by multiple requests or threads**.

## 3. Thread Safety of Singletons

A Spring singleton is not automatically thread-safe. The container only manages instance creation and sharing; it does not synchronize methods or protect mutable bean fields.

A risky example:

~~~java
@Service
public class ShoppingCartService {

    private final List<String> currentItems = new ArrayList<>();

    public void add(String item) {
        currentItems.add(item);
    }

    public List<String> items() {
        return currentItems;
    }
}
~~~

If `ShoppingCartService` is a singleton, the list above is shared across all callers. One user's data can mix with another's, and `ArrayList` is not safe under unsynchronized concurrent access.

For request-handling services, a better design is usually to keep beans stateless:

~~~java
@Service
public class ShoppingCartService {

    public Cart calculate(CartInput input) {
        // Per-invocation data lives in local variables.
        return new Cart(input.items());
    }
}
~~~

If genuinely shared state is needed, pick an appropriate mechanism:

- Synchronized collections or concurrent collections.
- Atomic types or locks when atomic operations are required.
- Dedicated database/cache for shared state.
- Per-request/per-user state stored in an appropriate scope or passed via parameters.
- A state-managing component with a clear contract and concurrency policy.

**Do not switch every service to prototype just to avoid thinking about thread safety.** Prototype does not make an object thread-safe either; callers can still share a prototype instance across multiple threads.

## 4. Prototype: Creating a New Instance per Request for the Bean

Declare a prototype using `@Scope`:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class WorkUnit {

    private final UUID id = UUID.randomUUID();

    public UUID id() {
        return id;
    }
}
~~~

Or use the scope name:

~~~java
@Component
@Scope("prototype")
public class WorkUnit {
    // ...
}
~~~

Whenever the container is asked to resolve the `workUnit` bean, Spring creates a new instance from the bean definition.

~~~text
1st getBean("workUnit") call
             |
             v
        WorkUnit A

2nd getBean("workUnit") call
             |
             v
        WorkUnit B

3rd getBean("workUnit") call
             |
             v
        WorkUnit C
~~~

Typically:

~~~java
WorkUnit first = context.getBean(WorkUnit.class);
WorkUnit second = context.getBean(WorkUnit.class);

assertNotSame(first, second);
assertNotEquals(first.id(), second.id());
~~~

Each resolution of a prototype from the container produces a new instance. If code fetches it once and stores the reference in a field, subsequent uses of that field still use the same fetched instance; prototype scope does not swap references inside consumer objects.

### 4.1. Prototype Does Not Mean "New Object per Method Call"

Scope applies only when the container resolves a bean. It does not intercept every method call on a reference held by a caller.

For example:

~~~java
WorkUnit unit = context.getBean(WorkUnit.class);

unit.execute();
unit.execute();
unit.execute();
~~~

All three `execute()` calls run on the **same `WorkUnit` instance**. To get a new instance, you must request the bean from the container again or use an on-demand lookup mechanism.

This is the core distinction between object lifecycle and method call count.

## 5. Practice Setup to Observe Both Scopes

Create two simple classes.

`SingletonProbe.java`:

~~~java
package com.example.scope;

import java.util.UUID;

public class SingletonProbe {

    private final UUID id = UUID.randomUUID();

    public UUID id() {
        return id;
    }
}
~~~

`PrototypeProbe.java`:

~~~java
package com.example.scope;

import java.util.UUID;

public class PrototypeProbe {

    private final UUID id = UUID.randomUUID();

    public UUID id() {
        return id;
    }
}
~~~

Configuration:

~~~java
package com.example.scope;

import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;

@Configuration(proxyBeanMethods = false)
public class ScopeConfiguration {

    @Bean
    SingletonProbe singletonProbe() {
        return new SingletonProbe();
    }

    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    PrototypeProbe prototypeProbe() {
        return new PrototypeProbe();
    }
}
~~~

`singletonProbe` uses the default scope. `prototypeProbe` is configured to create a new instance on every resolution.

Test:

~~~java
package com.example.scope;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class BeanScopeTest {

    @Test
    void observesSingletonAndPrototype() {
        try (var context =
                new AnnotationConfigApplicationContext(
                        ScopeConfiguration.class)) {

            SingletonProbe singletonA =
                    context.getBean(SingletonProbe.class);
            SingletonProbe singletonB =
                    context.getBean(SingletonProbe.class);

            PrototypeProbe prototypeA =
                    context.getBean(PrototypeProbe.class);
            PrototypeProbe prototypeB =
                    context.getBean(PrototypeProbe.class);

            assertSame(singletonA, singletonB);
            assertNotSame(prototypeA, prototypeB);
            assertNotEquals(prototypeA.id(), prototypeB.id());
        }
    }
}
~~~

The test uses a real context to verify scope behavior managed by Spring. It does not merely call constructors with `new`.

## 6. Inspecting Scope from `ApplicationContext`

Besides comparing identity, you can ask the container what scope a bean has:

~~~java
boolean singleton =
        context.isSingleton("singletonProbe");

boolean prototype =
        context.isPrototype("prototypeProbe");
~~~

Expected assertions in the configuration above:

~~~java
assertTrue(context.isSingleton("singletonProbe"));
assertTrue(context.isPrototype("prototypeProbe"));
~~~

These APIs let you observe scope metadata/behavior by bean name.

If there are multiple beans of the same type, specify the bean name or qualifier. Do not use a single Java type to infer a unique bean name.

You can list bean names by type:

~~~java
String[] names =
        context.getBeanNamesForType(PrototypeProbe.class);
~~~

If you want to inspect bean definition metadata in more detail, with a context whose bean factory supports a registry you can access `BeanDefinitionRegistry`:

~~~java
BeanDefinitionRegistry registry =
        (BeanDefinitionRegistry) context.getBeanFactory();

String scope =
        registry.getBeanDefinition("prototypeProbe").getScope();
~~~

A bean definition that does not explicitly record a scope may return an empty string because singleton is the default. Therefore, an empty `getScope()` does not mean the bean has no scope. `context.isSingleton(...)` reflects effective behavior more clearly for this example.

## 7. Lifecycle Differences Between Singleton and Prototype

Spring manages the lifecycle of a singleton fairly completely:

~~~text
Create singleton
     |
     v
Dependency injection
     |
     v
Initialization callbacks
     |
     v
Bean is in use
     |
     v
ApplicationContext closes
     |
     v
Destroy callbacks
~~~

For a prototype:

~~~text
Container is asked for bean
        |
        v
Create new instance
        |
        v
Dependency injection
        |
        v
Initialization callbacks
        |
        v
Return instance to caller
        |
        v
Caller owns usage and cleanup
~~~

Spring still performs the creation and initialization steps for a prototype bean, including dependency injection and init callbacks. However, once the instance is handed to the caller, the container **does not continue managing the full destruction lifecycle of the prototype as it does for singletons**.

In particular, Spring does not automatically invoke `@PreDestroy` or destroy methods for every prototype instance when the `ApplicationContext` closes.

This is critical if a prototype holds:

- File handles or streams.
- Sockets or client connections.
- Executors or threads.
- Temporary files.
- Native resources.
- Objects with their own cleanup callbacks.

The caller or a component owning the prototype needs a resource-closing policy.

## 8. Common Trap: Injecting a Prototype Directly into a Singleton

Suppose there is a prototype bean:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class JobContext {

    private final UUID id = UUID.randomUUID();

    public UUID id() {
        return id;
    }
}
~~~

And a singleton consumer:

~~~java
@Service
public class JobCoordinator {

    private final JobContext jobContext;

    public JobCoordinator(JobContext jobContext) {
        this.jobContext = jobContext;
    }

    public UUID currentJobId() {
        return jobContext.id();
    }
}
~~~

Many expect each call to `currentJobId()` to receive a new `JobContext` because `JobContext` is a prototype.

In reality:

1. Spring creates the singleton `JobCoordinator`.
2. While creating the coordinator, Spring resolves the `JobContext` dependency.
3. One prototype instance is created and injected into the constructor.
4. The coordinator stores that reference in a field.
5. Subsequent calls to `currentJobId()` reuse the same reference.

~~~text
ApplicationContext creates JobCoordinator
                 |
                 v
       resolve JobContext prototype
                 |
                 v
             JobContext A
                 |
                 v
       inject into JobCoordinator
                 |
                 v
     JobCoordinator holds reference A
           /           \
          v             v
      call #1        call #2
          |             |
          +------ A ----+
~~~

Prototype scope only tells Spring to create a new instance when Spring is asked for a new bean. It does not make already-injected dependencies change on their own.

A test can observe this:

~~~java
@Test
void prototypeInjectedDirectlyIntoSingletonIsResolvedOnce() {
    try (var context =
            new AnnotationConfigApplicationContext(
                    DirectInjectionConfiguration.class)) {

        JobCoordinator coordinator =
                context.getBean(JobCoordinator.class);

        UUID first = coordinator.currentJobId();
        UUID second = coordinator.currentJobId();

        assertEquals(first, second);
    }
}
~~~

`DirectInjectionConfiguration` represents the configuration registering the prototype `JobContext` and singleton `JobCoordinator` from the example.

**This is one of the most important rules when mixing scopes.**

## 9. Using `ObjectProvider` to Look Up Prototypes on Demand

Spring provides `ObjectProvider<T>` so consumers can request beans from the container at the exact moment needed.

Instead of injecting a prototype instance:

~~~java
public JobCoordinator(JobContext jobContext) {
    this.jobContext = jobContext;
}
~~~

inject a provider:

~~~java
@Service
public class JobCoordinator {

    private final ObjectProvider<JobContext> jobContexts;

    public JobCoordinator(ObjectProvider<JobContext> jobContexts) {
        this.jobContexts = jobContexts;
    }

    public UUID startNewJob() {
        JobContext context = jobContexts.getObject();
        return context.id();
    }
}
~~~

Each call to `getObject()` resolves the bean according to its registered scope. If `JobContext` is a prototype, each call creates a new instance.

~~~text
Singleton JobCoordinator
          |
          v
ObjectProvider<JobContext>
          |
          +-- getObject() --> JobContext A
          |
          +-- getObject() --> JobContext B
          |
          +-- getObject() --> JobContext C
~~~

Important point: `ObjectProvider` does not turn a bean into a prototype by itself. It applies the scope rules of the target bean. If the bean is a singleton, repeated `getObject()` calls still return the same singleton.

### 9.1. Complete Example

Prototype:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class JobContext {

    private final UUID id = UUID.randomUUID();

    public UUID id() {
        return id;
    }
}
~~~

Singleton:

~~~java
@Service
public class JobCoordinator {

    private final ObjectProvider<JobContext> contexts;

    public JobCoordinator(ObjectProvider<JobContext> contexts) {
        this.contexts = contexts;
    }

    public JobContext createContext() {
        return contexts.getObject();
    }
}
~~~

Test:

~~~java
@Test
void providerCreatesANewPrototypeForEachLookup() {
    try (var context =
            new AnnotationConfigApplicationContext(JobConfiguration.class)) {

        JobCoordinator coordinator =
                context.getBean(JobCoordinator.class);

        JobContext first = coordinator.createContext();
        JobContext second = coordinator.createContext();

        assertNotSame(first, second);
        assertNotEquals(first.id(), second.id());
    }
}
~~~

The test confirms that a singleton can obtain multiple prototype instances over its lifetime.

### 9.2. When Is `ObjectProvider` a Good Fit?

- A bean must be created per processing invocation.
- A dependency may not exist in certain configurations.
- Multiple candidates exist and the consumer needs to resolve by qualifier.
- Dependency resolution needs to be deferred.
- On-demand access to a bean is needed instead of holding a pre-injected instance.

`ObjectProvider` is a Spring API integrated with the bean factory and dependency resolution mechanisms.

## 10. Useful Methods of `ObjectProvider`

`ObjectProvider<T>` offers several ways to fetch beans:

| Method | Meaning |
|---|---|
| `getObject()` | Resolves the bean; throws an error if it cannot be supplied |
| `getIfAvailable()` | Returns the bean if present, or `null` if absent |
| `getIfUnique()` | Returns the bean if a single unique candidate can be determined |
| `ifAvailable(consumer)` | Executes the consumer when a bean is available |
| `ifUnique(consumer)` | Executes the consumer when a unique bean exists |
| `stream()` | Streams matching candidates |
| `orderedStream()` | Streams candidates in Spring's applied order |

Optional dependency example:

~~~java
@Service
public class ReportCoordinator {

    private final ObjectProvider<ReportExporter> exporters;

    public ReportCoordinator(ObjectProvider<ReportExporter> exporters) {
        this.exporters = exporters;
    }

    public void exportIfConfigured(Report report) {
        ReportExporter exporter = exporters.getIfAvailable();

        if (exporter != null) {
            exporter.export(report);
        }
    }
}
~~~

If the exporter is required, use `getObject()` so dependency errors surface clearly. If the exporter is optional, `getIfAvailable()` makes the intent explicit.

### 10.1. `getIfAvailable` and `getIfUnique` Are Not the Same

Suppose two beans implement `ReportExporter`.

- `getIfAvailable()` can throw an error if multiple candidates exist that cannot be resolved uniquely.
- `getIfUnique()` returns a candidate if one can be uniquely determined according to resolution rules, otherwise it can return `null`.

Do not use `getIfUnique()` to hide a configuration with multiple implementations when the business logic requires an explicit selection. If a choice is required, use a qualifier or a registry with explicit selection rules.

## 11. On-Demand Bean Lookup via `ApplicationContext`

You can inject `ApplicationContext` and call `getBean()`:

~~~java
@Service
public class JobCoordinator {

    private final ApplicationContext context;

    public JobCoordinator(ApplicationContext context) {
        this.context = context;
    }

    public JobContext createContext() {
        return context.getBean(JobContext.class);
    }
}
~~~

With a prototype, each call resolves a new instance.

This works, but it couples the class directly to the Spring container API. It follows the **Service Locator** style: the class fetches dependencies itself rather than declaring required dependencies via constructor.

Compare:

~~~java
public JobCoordinator(ObjectProvider<JobContext> contexts) {
    this.contexts = contexts;
}
~~~

with:

~~~java
public JobCoordinator(ApplicationContext context) {
    this.context = context;
}
~~~

`ObjectProvider<JobContext>` clearly states that the consumer needs to obtain a `JobContext` on demand. `ApplicationContext` grants access to virtually the entire container, hiding dependencies and forcing unit tests to mock framework APIs.

**Prefer injecting `ObjectProvider<T>` when you only need to resolve a specific bean type on demand.** Use `ApplicationContext.getBean()` when the class genuinely has container-coordination or plugin-registry responsibilities by design.

Do not inject `ApplicationContext` into every service just to replace constructor injection with manual lookups.

## 12. Using `jakarta.inject.Provider` When Appropriate

If the project includes the `jakarta.inject-api` dependency, you can use `jakarta.inject.Provider<T>`:

~~~java
import jakarta.inject.Provider;

@Service
public class JobCoordinator {

    private final Provider<JobContext> contexts;

    public JobCoordinator(Provider<JobContext> contexts) {
        this.contexts = contexts;
    }

    public JobContext createContext() {
        return contexts.get();
    }
}
~~~

`Provider` represents a source capable of resolving objects on demand. Spring integrates `Provider` injection support when the corresponding API is present.

Practical differences:

- `ObjectProvider<T>` is a Spring API with methods like `getIfAvailable`, `getIfUnique`, and `stream`.
- `Provider<T>` is a Jakarta Inject abstraction with a simpler `get()` API.

If the application already uses Spring and needs Spring-specific resolution capabilities, `ObjectProvider` is usually more convenient. If code wants to depend on a more framework-agnostic injection standard, `Provider` can fit.

Do not add a second abstraction if `ObjectProvider` already solves the need cleanly.

## 13. Method Injection with `@Lookup`

Another way to retrieve prototypes from a singleton is method injection with `@Lookup`.

Example:

~~~java
@Component
public abstract class JobCoordinator {

    public JobContext createContext() {
        return createJobContext();
    }

    @Lookup
    protected abstract JobContext createJobContext();
}
~~~

Spring generates a subclass for the `JobCoordinator` bean and overrides the lookup method to resolve `JobContext` from the container whenever the method is called.

Each call to `createJobContext()` performs a lookup according to the bean definition and scope of `JobContext`. If prototype, each call returns a new instance.

~~~text
Caller
  |
  v
JobCoordinator proxy/subclass
  |
  v
@Lookup method
  |
  v
BeanFactory.getBean(JobContext)
  |
  v
New prototype instance
~~~

### 13.1. Requirements and Limitations of `@Lookup`

- The bean containing the lookup method must be Spring-managed.
- Spring must be able to subclass the class to override the method.
- The lookup method cannot be `private`, `final`, or `static`.
- The class should not be `final`.
- Do not instantiate the coordinator with `new` if you expect method injection to work.
- Verify behavior when using factory methods or special bean setups.

This example illustrates method injection, but in many projects `ObjectProvider<T>` is easier to read and test because the dependency is declared explicitly in the constructor.

### 13.2. When Is `@Lookup` Useful?

- You want a method to directly express "create a new instance."
- The class has one clear lookup point and few dynamic dependencies.
- The project is already familiar with method injection.
- You want to avoid a general-purpose service locator.

If the class needs multiple lookup types or optional resolution, `ObjectProvider` is usually more flexible.

## 14. Comparing Ways to Obtain Prototypes on Demand

| Approach | Pros | Limitations |
|---|---|---|
| Inject prototype directly into singleton | Simple configuration | Resolved only once when singleton is created |
| `ObjectProvider<T>` | Explicit dependency, supports optional and multiple candidates | Consumer depends on Spring API |
| `Provider<T>` | Concise injection API, less framework-specific | Fewer resolution features |
| `ApplicationContext.getBean()` | Flexible, easy lookup by name/type | Service Locator, container dependency hidden |
| `@Lookup` | Method expresses per-call instance lookup | Requires subclassing, method/class visibility limits |

For a singleton needing a fresh prototype per operation, a maintainable default is usually:

~~~java
private final ObjectProvider<JobContext> contexts;
~~~

and calling:

~~~java
JobContext context = contexts.getObject();
~~~

## 15. Looking Up Beans by Type, Name, and Qualifier

In one context, multiple beans may implement the same interface.

Example:

~~~java
public interface DocumentExporter {
    void export(Document document);
}
~~~

~~~java
@Component
@Qualifier("pdf")
public class PdfExporter implements DocumentExporter {
    @Override
    public void export(Document document) {
        // Export PDF.
    }
}
~~~

~~~java
@Component
@Qualifier("csv")
public class CsvExporter implements DocumentExporter {
    @Override
    public void export(Document document) {
        // Export CSV.
    }
}
~~~

If you inject:

~~~java
public ExportCoordinator(DocumentExporter exporter) {
    this.exporter = exporter;
}
~~~

Spring can throw `NoUniqueBeanDefinitionException` because multiple candidates share the type.

You can select with a qualifier:

~~~java
public ExportCoordinator(
        @Qualifier("pdf") DocumentExporter exporter
) {
    this.exporter = exporter;
}
~~~

If on-demand lookup is needed:

~~~java
public ExportCoordinator(
        @Qualifier("pdf")
        ObjectProvider<DocumentExporter> exporters
) {
    this.exporters = exporters;
}
~~~

~~~java
public void export(Document document) {
    exporters.getObject().export(document);
}
~~~

Qualifiers narrow the candidate set; the provider controls resolution timing. If the chosen candidate is a prototype, each provider call creates a new instance; if singleton, the provider returns the managed singleton instance.

### 15.1. Bean Name and Type Lookup

You can look up by name and type:

~~~java
DocumentExporter exporter =
        context.getBean("pdfExporter", DocumentExporter.class);
~~~

This is useful when the bean name is an explicit part of configuration, though hard-coding bean names across many services can increase coupling.

If selection is a business decision, design a factory/registry with a domain-meaningful API:

~~~java
public interface ExporterRegistry {
    DocumentExporter exporterFor(ExportFormat format);
}
~~~

The registry can use a map/qualifier/provider internally while consumers only know the business contract.

## 16. Singleton Depending on Prototype: Three Common Designs

Suppose an application creates multiple `JobContext` instances during the lifetime of `JobCoordinator`.

### Option A — Inject Prototype Directly

~~~java
@Service
public class JobCoordinator {

    private final JobContext context;

    public JobCoordinator(JobContext context) {
        this.context = context;
    }
}
~~~

Result: one prototype is resolved when the singleton is created and retained.

Fits when the singleton only needs a single prototype instance tied to the singleton's own lifetime. Does not fit when you want a fresh instance per job.

### Option B — Inject `ObjectProvider`

~~~java
@Service
public class JobCoordinator {

    private final ObjectProvider<JobContext> contexts;

    public JobCoordinator(ObjectProvider<JobContext> contexts) {
        this.contexts = contexts;
    }

    public void startJob() {
        JobContext context = contexts.getObject();
        // Process the job with the new context.
    }
}
~~~

Result: each `getObject()` resolves a fresh prototype.

Fits when the singleton needs multiple instances across operations.

### Option C — Inject an Application-Defined Factory

~~~java
public interface JobContextFactory {
    JobContext create();
}
~~~

~~~java
@Component
public class SpringJobContextFactory implements JobContextFactory {

    private final ObjectProvider<JobContext> contexts;

    public SpringJobContextFactory(ObjectProvider<JobContext> contexts) {
        this.contexts = contexts;
    }

    @Override
    public JobContext create() {
        return contexts.getObject();
    }
}
~~~

Singleton depends on the factory:

~~~java
@Service
public class JobCoordinator {

    private final JobContextFactory factory;

    public JobCoordinator(JobContextFactory factory) {
        this.factory = factory;
    }

    public void startJob() {
        JobContext context = factory.create();
        // ...
    }
}
~~~

A factory is useful when you want to decouple Spring-specific lookup from domain/service logic. Unit tests can pass a fake factory to produce objects per scenario.

Do not create a factory just to wrap a single `getObject()` line unless it provides real benefits for boundaries, testability, or construction logic. Choose the abstraction based on actual need.

## 17. Creating Prototype Beans and Cleaning Up Resources

Spring calls initialization callbacks for prototypes, but does not automatically call destroy callbacks when the context closes.

Example:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class TemporaryWorkspace implements AutoCloseable {

    private final Path directory;

    public TemporaryWorkspace() throws IOException {
        this.directory = Files.createTempDirectory("job-");
    }

    public Path directory() {
        return directory;
    }

    @Override
    public void close() throws IOException {
        // Delete temp files and directory per application policy.
    }
}
~~~

When obtaining a prototype via a provider:

~~~java
TemporaryWorkspace workspace = workspaces.getObject();

try {
    process(workspace);
} finally {
    workspace.close();
}
~~~

The caller knows a new instance was created and bears responsibility for closing the resource.

You can use try-with-resources if the type implements `AutoCloseable`:

~~~java
try (TemporaryWorkspace workspace = workspaces.getObject()) {
    process(workspace);
}
~~~

This guarantees `close()` is called even if `process()` throws an exception.

### 17.1. `@PreDestroy` on Prototypes Does Not Auto-Run on Context Close

Example:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class PrototypeResource {

    @PreDestroy
    public void destroy() {
        // Close resources.
    }
}
~~~

Do not expect Spring to automatically call `destroy()` on every prototype instance when `ApplicationContext` closes. The container does not retain a list to manage the full destruction lifecycle of prototypes the way it does for singletons.

If you need Spring to execute destruction-aware callbacks for a specific prototype instance, the owning code can invoke `AutowireCapableBeanFactory.destroyBean(instance)` when done. However, for resources with a clear Java contract like `AutoCloseable`, having the caller invoke `close()` directly is usually easier to understand.

Avoid both calling `close()` manually and triggering destroy callbacks unless cleanup is designed to be idempotent, as doing both can release the same resource twice.

## 18. Lazy Initialization Differs from Prototype

`@Lazy` controls when a bean is initialized or a dependency is resolved. It is not synonymous with prototype.

Lazy singleton example:

~~~java
@Component
@Lazy
public class ExpensiveCatalog {
    // Initialized when first requested.
}
~~~

A lazy singleton bean is created on first demand, and subsequent resolutions still reuse that same instance in the context.

Prototype:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class JobContext {
}
~~~

Every resolution of a prototype creates a new instance.

| Attribute | Lazy singleton | Prototype |
|---|---|---|
| Creation time | Deferred until needed | On every resolution |
| Instances in context | One instance per bean definition | Multiple instances |
| Subsequent resolutions | Reuses already-created singleton | Creates a new instance |
| Primary purpose | Defer initialization | Create isolated objects per request |

`@Lazy` at an injection point can create a proxy that defers dependency resolution. Do not use it to express "need a new prototype on every method call." When the requirement is a fresh instance per operation, use `ObjectProvider<T>` or an explicit factory.

## 19. A Singleton Bean Can Hold a Prototype Provider Long-Term

A provider injected into a singleton is a stable dependency:

~~~java
@Service
public class BatchCoordinator {

    private final ObjectProvider<BatchItemContext> contexts;

    public BatchCoordinator(
            ObjectProvider<BatchItemContext> contexts
    ) {
        this.contexts = contexts;
    }
}
~~~

The provider is not itself a prototype instance. It is an object accessing the bean factory to resolve beans according to their current scope.

Therefore:

~~~java
BatchItemContext first = contexts.getObject();
BatchItemContext second = contexts.getObject();
~~~

If `BatchItemContext` is a prototype, two lookups create two distinct objects. If the bean is switched to singleton, two lookups return the same singleton.

This keeps the consumer agnostic of how the container implements caching/creation; it simply uses the provider to request the dependency when needed.

## 20. Observing Creation Count with a Constructor or Counter

In a practice setting, you can record how many times the constructor is called:

~~~java
public class CreationProbe {

    private static final AtomicInteger CREATED =
            new AtomicInteger();

    private final int sequence;

    public CreationProbe() {
        this.sequence = CREATED.incrementAndGet();
    }

    public int sequence() {
        return sequence;
    }

    public static int createdCount() {
        return CREATED.get();
    }

    public static void reset() {
        CREATED.set(0);
    }
}
~~~

Register as prototype:

~~~java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
CreationProbe creationProbe() {
    return new CreationProbe();
}
~~~

Test:

~~~java
@Test
void createsAPrototypeForEachLookup() {
    CreationProbe.reset();

    try (var context =
            new AnnotationConfigApplicationContext(ProbeConfig.class)) {

        CreationProbe first = context.getBean(CreationProbe.class);
        CreationProbe second = context.getBean(CreationProbe.class);

        assertNotSame(first, second);
        assertEquals(2, CreationProbe.createdCount());
    }
}
~~~

A static counter is only suitable for a simple test demonstration. In parallel test suites or multi-context runs, static mutable state can introduce coupling between tests. For precise observation, inject a recorder instance into the bean or isolate/reset contexts appropriately.

### 20.1. Identity Hash Code Is Not a Business ID

You can print:

~~~java
System.out.println(System.identityHashCode(bean));
~~~

This value helps observe identity within a single run, but should not be stored as a stable ID or treated as sole proof of long-term uniqueness. Hash codes can collide between two objects.

For clearer demos, use a UUID or sequence assigned by a test recorder; to check whether two references point to the same object, use `assertSame`/`assertNotSame`.

## 21. Observing Singletons and Prototypes Across Multiple Consumers

Create two consumers injecting the same singleton:

~~~java
@Component
public class CartReaderA {

    private final SharedCart cart;

    public CartReaderA(SharedCart cart) {
        this.cart = cart;
    }

    public SharedCart cart() {
        return cart;
    }
}
~~~

~~~java
@Component
public class CartReaderB {

    private final SharedCart cart;

    public CartReaderB(SharedCart cart) {
        this.cart = cart;
    }

    public SharedCart cart() {
        return cart;
    }
}
~~~

Test:

~~~java
assertSame(
        context.getBean(CartReaderA.class).cart(),
        context.getBean(CartReaderB.class).cart()
);
~~~

When a prototype is injected directly into two different singleton consumers, each consumer can receive a distinct prototype instance when that consumer itself is created. Yet each consumer still keeps its injected instance.

~~~text
Container
  |
  +-- Create Consumer A
  |       |
  |       +-- resolve Prototype X
  |
  +-- Create Consumer B
          |
          +-- resolve Prototype Y
~~~

The two different consumers receive two different prototypes, but repeated method calls on each consumer still use that consumer's own instance.

If consumer A needs a new prototype per operation, A needs a provider or factory rather than a directly injected prototype field.

## 22. Scopes of Nested Dependencies

A bean's scope and its dependency's scope do not automatically match.

For example:

- Singleton `OrderCoordinator` injects prototype `OrderContext`: one prototype is resolved when the coordinator is created.
- Prototype `OrderWorker` injects singleton `PricingService`: each new worker still uses the same singleton pricing service.
- Prototype `OrderWorker` injects prototype `OrderContext`: when each worker is created, a new `OrderContext` is resolved for that worker.
- Singleton injects `ObjectProvider<OrderContext>`: each provider lookup creates a new prototype if the target bean is a prototype.

Table:

| Consumer | Dependency | Result when consumer is created |
|---|---|---|
| Singleton | Singleton | Uses singleton instance |
| Singleton | Prototype directly | One prototype is injected and retained |
| Prototype | Singleton | Uses shared singleton |
| Prototype | Prototype directly | One new prototype per consumer creation |
| Singleton | `ObjectProvider<Prototype>` | Consumer can request multiple prototypes over time |

Rule of thumb: **a dependency's scope is applied at the moment the container resolves that dependency**. If the dependency is resolved in a constructor, that resolution happens when the consumer is created.

## 23. When Should You Choose Singleton?

Singleton fits objects such as:

- Stateless services.
- Repositories or gateways with stable configuration.
- Validators, mappers, and formatters that hold no per-request state.
- Coordinators using thread-safe shared dependencies.
- Caches or registries designed for concurrent access.
- Objects that are expensive to initialize and safe to share.

Think carefully when a bean:

- Holds mutable per-user or per-request data.
- Has fields mutated during each execution.
- Holds short-lived resources.
- Lacks concurrency control while called by multiple threads.
- Has state tied to an individual transaction or job.

A singleton can contain state if that state is intentionally shared, properly protected, and has a clear lifecycle. The issue is not "singletons cannot have fields," but whether **the field's sharing boundary and concurrency semantics are right**.

## 24. When Should You Choose Prototype?

Prototype fits when each object creation needs isolated state:

- Context objects processing a single job.
- Builders carrying per-operation state.
- Command objects created per execution.
- Temporary objects holding workflow state.
- Components owning dedicated resources that callers clean up.
- Algorithms requiring an isolated mutable workspace.

Prototype is not appropriate just because you want "a separate service per request" without a state or lifecycle reason. A stateless singleton service is simpler and more efficient.

Additionally, prototype incurs object-creation cost on each lookup and requires callers to manage cleanup. If an object is just a small data holder, creating it with a plain Java constructor may be better than registering it as a Spring bean.

## 25. Not Every Object Needs to Be a Spring Bean

A class can be instantiated directly with `new` if:

- It is a value object or DTO.
- It does not need dependency injection.
- It does not need Spring lifecycle callbacks.
- It does not need proxies or framework-managed behavior.
- The caller can manage its simple lifetime.

For example:

~~~java
public record Money(BigDecimal amount, Currency currency) {
}
~~~

~~~java
public class InvoiceCalculator {

    public Invoice calculate(InvoiceInput input) {
        Money total = new Money(
                input.amount(),
                input.currency()
        );

        return new Invoice(total);
    }
}
~~~

There is no need to register every `Money` as a prototype bean. The object can be created via its constructor because it is pure data.

Spring beans make sense when the container adds value such as DI, lifecycle, AOP, configuration, or scoping. **Do not turn the container into a factory for every Java object without a clear benefit.**

## 26. Choosing Scope on `@Component` and `@Bean`

You can declare scope on a component:

~~~java
@Component
@Scope("prototype")
public class CommandContext {
}
~~~

Or on a factory method:

~~~java
@Configuration(proxyBeanMethods = false)
class CommandConfiguration {

    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    CommandContext commandContext() {
        return new CommandContext();
    }
}
~~~

The scope applies to the bean definition registered from that class or factory method.

If the same class is registered as two bean definitions with different scopes, each definition can behave differently:

~~~java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_SINGLETON)
CommandContext sharedCommandContext() {
    return new CommandContext();
}

@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
CommandContext newCommandContext() {
    return new CommandContext();
}
~~~

In that case, looking up by type `CommandContext.class` becomes ambiguous. Select by name or qualifier:

~~~java
context.getBean("newCommandContext", CommandContext.class);
~~~

Do not register multiple beans of the same type without a disambiguation rule if consumers expect a single candidate.

## 27. Distinguishing Scope from Proxy

Some scopes or dependency resolutions can use a proxy to represent the target. This is common with request/session scopes or when injecting a shorter-lived dependency into a singleton.

Proxy and scope are two distinct concepts:

- Scope governs the target's instance lifetime/creation.
- A proxy is an intermediary object that routes calls to the appropriate target.
- `ObjectProvider` is an API for asking the container to resolve objects on demand.
- `@Lookup` is a method injection mechanism to look up a bean when a method is called.

For example, a scoped proxy can hold a stable proxy reference in a singleton while resolving the target per active request. That is not a simple prototype.

Do not see a proxy and conclude a bean is singleton or prototype based solely on its runtime class. To determine scope, inspect the bean definition and its resolution behavior in the context.

## 28. Testing `ObjectProvider` Without Mocking the Entire `ApplicationContext`

A straightforward approach is testing against a real Spring context:

~~~java
@Test
void coordinatorRequestsFreshContexts() {
    try (var context =
            new AnnotationConfigApplicationContext(JobConfiguration.class)) {

        JobCoordinator coordinator =
                context.getBean(JobCoordinator.class);

        JobContext first = coordinator.createContext();
        JobContext second = coordinator.createContext();

        assertNotSame(first, second);
    }
}
~~~

This test verifies both provider wiring and prototype scope.

If you want to unit-test coordinator logic independently, you can mock or fake the provider:

~~~java
ObjectProvider<JobContext> provider =
        mock(ObjectProvider.class);

JobContext first = new JobContext();
JobContext second = new JobContext();

when(provider.getObject())
        .thenReturn(first, second);

JobCoordinator coordinator = new JobCoordinator(provider);

assertSame(first, coordinator.createContext());
assertSame(second, coordinator.createContext());
verify(provider, times(2)).getObject();
~~~

The example uses Mockito, commonly available via `spring-boot-starter-test`. It verifies that the coordinator calls the provider each time it needs a context, while the context integration test proves Spring actually creates prototypes.

The two test levels answer two different questions.

## 29. Testing Multiple Implementations with a Provider

Suppose there are multiple `DocumentExporter` beans. A consumer needs a specific exporter per configuration.

You can inject a provider with a qualifier:

~~~java
@Service
public class PdfJob {

    private final ObjectProvider<DocumentExporter> exporterProvider;

    public PdfJob(
            @Qualifier("pdfExporter")
            ObjectProvider<DocumentExporter> exporterProvider
    ) {
        this.exporterProvider = exporterProvider;
    }

    public void execute(Document document) {
        exporterProvider.getObject().export(document);
    }
}
~~~

If the exporter is registered as prototype, each `execute()` call resolves a fresh exporter. If singleton, the same instance is reused.

If format selection comes from runtime data, a fixed provider with qualifier `pdf` is insufficient. In that case, you need a registry/factory accepting `ExportFormat` and choosing the implementation by key.

Example:

~~~java
public interface ExporterFactory {
    DocumentExporter forFormat(ExportFormat format);
}
~~~

The factory can hold a map of providers or a map of stateless singleton implementations. Pick the option matching the exporter's lifecycle.

## 30. Common Pitfalls When Working with Scopes

| Symptom | Common cause | Resolution |
|---|---|---|
| Prototype injected into singleton never changes | Prototype resolved only when singleton was created | Inject `ObjectProvider<T>` or a factory |
| Two `getBean()` calls still return the same object | Bean is actually singleton | Check scope definition and bean name |
| Multiple beans of same type cause failure | Missing qualifier or primary | Select via qualifier or registry |
| Prototype `@PreDestroy` never runs | Spring does not manage full destruction for prototypes | Caller cleanup or invoke appropriate destruction callback |
| User state gets mixed | Mutable state stored in singleton | Stateless service or proper scope/state boundary |
| Prototype object still shared across threads | Caller retained and shared the same reference | Manage ownership and concurrency |
| `@Lazy` does not create a new object each time | Lazy defers resolution, not a prototype factory | Use a provider |
| `@Lookup` does not work | Bean not Spring-managed or method/class cannot be overridden | Check subclassing and method visibility |
| `getBean(Type.class)` is ambiguous | Multiple candidates of the same type | Use qualifier or bean name |
| Context test sees unexpected instance count | Test reuses context or static counter | Verify scope and isolate test state |

## 31. Practice Lab: Observing Scopes in a Small Application

Create the classes:

- `SessionMarker`: singleton, holds a UUID to identify the instance.
- `TaskMarker`: prototype, each instance gets its own UUID.
- `TaskCoordinator`: singleton, injects `ObjectProvider<TaskMarker>`.

`SessionMarker.java`:

~~~java
public class SessionMarker {

    private final UUID id = UUID.randomUUID();

    public UUID id() {
        return id;
    }
}
~~~

`TaskMarker.java`:

~~~java
public class TaskMarker {

    private final UUID id = UUID.randomUUID();

    public UUID id() {
        return id;
    }
}
~~~

`TaskCoordinator.java`:

~~~java
public class TaskCoordinator {

    private final ObjectProvider<TaskMarker> taskMarkers;

    public TaskCoordinator(ObjectProvider<TaskMarker> taskMarkers) {
        this.taskMarkers = taskMarkers;
    }

    public TaskMarker newTask() {
        return taskMarkers.getObject();
    }
}
~~~

Configuration:

~~~java
@Configuration(proxyBeanMethods = false)
public class ScopeLabConfiguration {

    @Bean
    SessionMarker sessionMarker() {
        return new SessionMarker();
    }

    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    TaskMarker taskMarker() {
        return new TaskMarker();
    }

    @Bean
    TaskCoordinator taskCoordinator(
            ObjectProvider<TaskMarker> taskMarkers
    ) {
        return new TaskCoordinator(taskMarkers);
    }
}
~~~

Test:

~~~java
@Test
void observesScopeAndOnDemandLookup() {
    try (var context =
            new AnnotationConfigApplicationContext(
                    ScopeLabConfiguration.class)) {

        SessionMarker firstSession =
                context.getBean(SessionMarker.class);
        SessionMarker secondSession =
                context.getBean(SessionMarker.class);

        TaskCoordinator coordinator =
                context.getBean(TaskCoordinator.class);

        TaskMarker firstTask = coordinator.newTask();
        TaskMarker secondTask = coordinator.newTask();

        assertSame(firstSession, secondSession);
        assertNotSame(firstTask, secondTask);

        assertTrue(context.isSingleton("sessionMarker"));
        assertTrue(context.isPrototype("taskMarker"));
    }
}
~~~

After running the test, explain:

1. Why are the two session markers the same object?
2. Why are the two task markers different objects?
3. Why does `TaskCoordinator` still have only one instance?
4. Is `ObjectProvider` itself a prototype bean?
5. If you remove the provider and inject `TaskMarker` directly, what changes?
6. Who must clean up a `TaskMarker` if it holds a file or socket?

This exercise demonstrates that the coordinator's scope is independent of the scope of the dependencies it resolves on demand.

## 32. A Note on Parent and Child `ApplicationContext`

In some applications, Spring has a parent context and child contexts. Each container manages singletons for bean definitions belonging to its scope.

A bean in the parent can be visible to a child context via hierarchy lookup. The child seeing a parent bean does not mean the child creates a separate singleton copy of that bean.

If the same configuration is registered independently in both parent and child, the two bean definitions in the two containers can have two separate instances.

This is uncommon in a simple Spring Boot application, but important when working with multi-context web apps or tests that build custom contexts.

## 33. Scope and Lookup Checklist

Before picking singleton, prototype, or a provider, ask:

- Does the bean hold mutable state?
- Does that state belong to the whole application, a single job, or a single request?
- Will multiple threads call the same bean?
- Does the bean need one shared instance or a fresh instance per operation?
- Could the caller instantiate the object with a constructor instead of registering a Spring bean?
- If prototype, who is responsible for cleanup?
- Is a singleton injecting a prototype directly?
- Do you need `ObjectProvider`, `Provider`, a factory, or `@Lookup`?
- Are there multiple candidates of the same type?
- Do qualifiers/bean names make selection explicit?
- Is `@Lazy` being used to defer creation or mistaken for per-call instantiation?
- Do tests verify identity using `assertSame`/`assertNotSame`?
- Are tests accidentally depending on static state or context caching?

A sound scope decision starts with **lifetime and state ownership**, and only then selects the annotation or lookup API.

## Conclusion

Spring scopes define how the container creates and shares instances. **Singleton** provides one instance per bean definition within an `ApplicationContext`; **prototype** creates a new instance every time the container resolves the bean.

The easiest mistake to make is injecting a prototype directly into a singleton: Spring resolves the prototype once when the singleton is constructed, so the consumer retains the same reference. When you need a fresh prototype per operation, use `ObjectProvider<T>`, `Provider<T>`, a factory, or `@Lookup` as appropriate.

In practice:

- Use `assertSame` to observe singletons and `assertNotSame` to observe prototypes.
- Use `context.isSingleton()` and `context.isPrototype()` to query the container about scope.
- Remember singletons are scoped per `ApplicationContext`, not globally across the JVM.
- Design singletons to be stateless or protect mutable state under concurrent access.
- Remember Spring does not auto-invoke destroy callbacks for all prototype instances; callers handle cleanup.
- Choose a provider or factory when on-demand bean resolution is required.
- Do not register every Java object as a Spring bean when a normal constructor is enough.

Understanding scopes helps applications manage state, dependencies, and resources with the proper lifetime, while keeping container behavior observable and testable.
