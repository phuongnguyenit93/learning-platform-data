# Limitations of Bean Callbacks for Tasks Requiring the Application to Have Started

In Spring Boot, a bean can run work right after creation via **@PostConstruct**, **InitializingBean.afterPropertiesSet()**, or the **initMethod** attribute of **@Bean**. These callbacks are useful for validating the bean's own configuration, preparing internal state, and finalizing initialization of resources owned by the bean.

However, **a bean finishing initialization does not mean the entire application has finished starting up**. When one bean's callback runs, Spring may still be creating other singletons, completing the ApplicationContext, publishing startup events, or preparing to invoke startup runners. If a task depends on all components being ready, you must choose the right milestone in the application lifecycle.

For instance, the following tasks are usually unsuitable to place arbitrarily inside @PostConstruct:

- Calling another service assuming every bean in the application is already ready.
- Scanning large datasets or warming up a cache that takes a long time.
- Running an initialization workflow depending on the entire context.
- Calling an external service that may be slow or temporarily unavailable.
- Spawning background tasks and expecting the application to accept traffic only after those tasks complete.

To pick the right mechanism, distinguish **the lifecycle of a single bean** from **the startup lifecycle of the Spring ApplicationContext and Spring Boot application**.

## 1. Bean Callbacks Speak Only About One Bean's Lifecycle

A Spring-managed bean can pass through stages such as:

1. Spring reads the bean definition and determines how to create the object.
2. The container creates the instance via constructor or factory method.
3. Dependencies are injected and appropriate Aware callbacks are invoked.
4. BeanPostProcessors process the object before the initialization phase.
5. Initialization callbacks are called.
6. BeanPostProcessors continue processing after initialization; some mechanisms may create proxies.
7. The bean is supplied to other components per its scope and usage timing.

At this stage, the callback speaks about **one specific bean**. Spring ensures the dependencies needed to create that bean are resolved via the container mechanism, yet that does not mean every other bean in the application has been initialized.

Example:

~~~java
import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;

@Component
public class CacheMetadata {

    @PostConstruct
    void initialize() {
        System.out.println("CacheMetadata initialized");
    }
}
~~~

This message only confirms that CacheMetadata's callback has run. It does not confirm that:

- All other singleton beans have been created.
- Startup runners have finished.
- Startup tasks of other beans have completed.
- The application has transitioned to a state ready to accept traffic.

This is the most important limitation to remember when choosing callbacks.

## 2. Common Initialization Callbacks

Spring supports several ways to declare bean initialization actions. They can serve the same purpose while differing in how they attach to the class and container.

### 2.1. @PostConstruct

With Spring Boot 3.x, import the annotation from Jakarta:

~~~java
import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;

@Component
public class SearchIndexMetadata {

    @PostConstruct
    void initialize() {
        // Prepare internal state of the bean.
    }
}
~~~

@PostConstruct is called after dependency injection for the bean finishes and before the bean goes through post-initialization post-processing steps. It is an appropriate place for local, fast initialization work that does not require the entire application to be ready.

In older Spring Boot lines based on Spring Framework 5, code may use the **javax.annotation.PostConstruct** package. Starting with Spring Framework 6 and Spring Boot 3, the corresponding annotation belongs to **jakarta.annotation**.

### 2.2. InitializingBean.afterPropertiesSet()

A bean can implement the interface:

~~~java
import org.springframework.beans.factory.InitializingBean;
import org.springframework.stereotype.Component;

@Component
public class ReportSettings implements InitializingBean {

    @Override
    public void afterPropertiesSet() {
        // Validate state after dependencies have been set.
    }
}
~~~

Spring calls **afterPropertiesSet()** during the initialization phase after properties/dependencies are set. This mechanism couples the class directly to the Spring API, so it is usually less preferred than annotation callbacks or init methods when you want to keep business classes framework-independent.

### 2.3. initMethod in @Bean

For a third-party class or a class where you do not want Spring annotations:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean(initMethod = "initialize")
    ExternalClient externalClient() {
        return new ExternalClient();
    }
}
~~~

Spring invokes the specified method after creating and configuring the bean per the initialization lifecycle. This approach is helpful when you cannot edit the source of ExternalClient.

### 2.4. Initialization callback order

In a typical bean creation flow, steps generally follow this conceptual order:

~~~text
Create instance
     │
     ▼
Dependency injection
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
Custom initMethod
     │
     ▼
BeanPostProcessor after initialization
     │
     ▼
Bean provided to consumers
~~~

Exact details are influenced by container mechanics and registered processors; the diagram above illustrates the typical path of a Spring-managed bean. Do not use multiple different callbacks to assemble a complex application-wide startup workflow.

## 3. Bean Destruction Callbacks Also Have Their Own Scope

Spring supports mechanisms such as:

- **@PreDestroy**.
- **DisposableBean.destroy()**.
- **destroyMethod** on @Bean.

Example:

~~~java
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class ConnectionManager {

    @PreDestroy
    void shutdown() {
        // Close resources owned by the bean.
    }
}
~~~

This is a cleanup callback when the bean is destroyed by the container per the appropriate lifecycle, normally when the ApplicationContext closes gracefully for singleton beans.

A bean destruction callback is not the place to launch work after the application has stopped. When @PreDestroy runs, dependent components may already be entering shutdown; calling other services may no longer be safe.

Additionally:

- Sudden JVM termination, power loss, or process crashes do not guarantee destruction callbacks will run.
- With prototype scope, the container creates and initializes instances but does not automatically manage full destruction callbacks for every prototype instance after handing them to callers.
- If a bean owns thread pools, sockets, or clients, clearly define who owns and who closes the resources.

## 4. Why Is @PostConstruct Not Yet the Application-Ready Milestone?

Spring creates beans following the dependency graph. When creating a bean, the container must create or resolve the dependencies that bean needs. However, beans not on that dependency branch may not have been created yet.

Example:

~~~text
ApplicationContext refreshing
          │
          ├── create OrderService
          │      └── create OrderRepository
          │             └── repository's @PostConstruct
          │
          ├── SearchService not created yet
          │
          ├── NotificationService not created yet
          │
          └── all singletons not yet complete
~~~

If OrderRepository's callback calls SearchService via a context lookup, it can inadvertently force the container to create extra beans during refresh. If that bean in turn depends back on the initializing branch, the application can hit ordering issues, circular dependencies, or unready state.

A bean callback should only rely on dependencies injected into that bean and defined lifecycle contracts. Do not infer that the entire system is finished just because one callback has run.

### 4.1. Injected dependencies do not mean every service is business-ready

Suppose:

~~~java
@Component
public class ProductCache {
    private final ProductRepository repository;

    public ProductCache(ProductRepository repository) {
        this.repository = repository;
    }

    @PostConstruct
    void load() {
        // Read data and populate cache.
    }
}
~~~

ProductRepository has already been injected when ProductCache runs @PostConstruct. Yet that does not guarantee:

- The database already contains all seed data.
- Other migrations or data imports have finished.
- A data synchronization service has finished running.
- Other beans are ready for the caching workflow.
- Reading the data will not prolong or fail startup.

If the cache requires a startup workflow after context refresh, move coordination to a suitable startup milestone and keep the bean callback focused on internal initialization.

### 4.2. Bean callbacks can run before proxies are finalized

AOP proxies for transactions, caching, or custom aspects are normally created during post-processing after initialization. Thus, calling a method expected to have @Transactional directly inside @PostConstruct of the same bean may not pass through a transaction proxy as desired.

Misleading example:

~~~java
@Service
public class ImportService {

    @PostConstruct
    void initialize() {
        importInitialData();
    }

    @Transactional
    public void importInitialData() {
        // Write data.
    }
}
~~~

The importInitialData() call above is an internal call on the initializing instance, bypassing the bean's proxy. Moreover, the callback runs prior to the final post-processing phase that can create proxies. Therefore, do not rely on @Transactional taking effect for that call.

If the task requires a transaction, call a separate transactional service from a startup runner or listener once the context has refreshed and bean proxies are ready:

~~~java
@Service
public class InitialImportService {
    @Transactional
    public void importInitialData() {
        // Execute import inside a transaction.
    }
}
~~~

~~~java
@Component
public class StartupImportRunner implements ApplicationRunner {
    private final InitialImportService importService;

    public StartupImportRunner(InitialImportService importService) {
        this.importService = importService;
    }

    @Override
    public void run(ApplicationArguments args) {
        importService.importInitialData();
    }
}
~~~

This is an illustrative example of a task that needs to run after context refresh. Transaction infrastructure, datasource, and rollback policies must still be configured properly.

## 5. Key Milestones During Spring Boot Startup

To select the right callback, look beyond a single bean's lifecycle. Spring Boot has distinct event milestones during application startup.

A conceptual sequence:

~~~text
SpringApplication.run(...)
          │
          ▼
Prepare Environment and ApplicationContext
          │
          ▼
Register bean definitions / process configuration
          │
          ▼
ApplicationContext.refresh()
          │
          ├── Create eager singletons
          │      └── Bean callbacks: @PostConstruct,
          │          afterPropertiesSet, initMethod
          │
          ├── SmartInitializingSingleton
          │
          └── ContextRefreshedEvent
          │
          ▼
ApplicationStartedEvent
          │
          ▼
ApplicationRunner / CommandLineRunner
          │
          ▼
ApplicationReadyEvent
          │
          ▼
ReadinessState.ACCEPTING_TRAFFIC
          │
          ▼
SpringApplication.run(...) completes
~~~

The diagram illustrates typical startup milestones of a Spring Boot application. Other preparation events may appear before refresh; internal details depend on version and application type. What matters is that **bean callbacks happen during bean creation, whereas runners and ApplicationReadyEvent belong to the broader application startup phase**.

### 5.1. ContextRefreshedEvent

Spring publishes **ContextRefreshedEvent** when the ApplicationContext is initialized or refreshed. This milestone indicates that context refresh has completed per Spring's mechanism.

Example:

~~~java
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ContextRefreshListener {

    @EventListener
    public void onContextRefreshed(ContextRefreshedEvent event) {
        // Context has refreshed.
    }
}
~~~

This milestone is broader than a single bean's @PostConstruct, yet still not the milestone where the Spring Boot application has finished running startup runners.

Limitations to remember:

- A context may be refreshed multiple times in certain structures or special cases.
- An application can have parent and child contexts; events are published in a specific context and may propagate per event hierarchy rules.
- Spring Boot still has the runner and application-ready phases after context refresh.

Therefore, if a task must run after **all startup runners finish**, ContextRefreshedEvent is not the right choice.

### 5.2. SmartInitializingSingleton

**SmartInitializingSingleton.afterSingletonsInstantiated()** is called after the BeanFactory completes initializing regular eager singletons during pre-instantiation.

Example:

~~~java
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.stereotype.Component;

@Component
public class SingletonRegistryCheck
        implements SmartInitializingSingleton {

    @Override
    public void afterSingletonsInstantiated() {
        // Regular eager singletons have been pre-instantiated.
    }
}
~~~

This callback is useful for infrastructure that needs to observe initialized singletons. However, it still runs during context refresh, before ContextRefreshedEvent and before Spring Boot runners.

It also does not mean every lazy bean, prototype, or startup task has finished. Do not use it in place of ApplicationReadyEvent if the requirement is genuinely that the application has cleared its runners.

### 5.3. ApplicationStartedEvent

Spring Boot publishes **ApplicationStartedEvent** after the ApplicationContext has refreshed and before ApplicationRunner/CommandLineRunner are invoked.

Consequently, if a listener runs on ApplicationStartedEvent, the context has refreshed yet runners have not finished executing. This is not the right milestone for work depending on results prepared by runners.

### 5.4. ApplicationReadyEvent

Spring Boot publishes **ApplicationReadyEvent** after ApplicationRunners and CommandLineRunners finish. This is the right milestone when a task needs to know normal startup has completed and the application is about to be considered ready to accept traffic.

Example:

~~~java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ReadyListener {

    @EventListener
    public void onApplicationReady(ApplicationReadyEvent event) {
        System.out.println("Application reached ready milestone");
    }
}
~~~

In Spring Boot's default sequence, availability state **ACCEPTING_TRAFFIC** is published after ApplicationReadyEvent. Because standard event listeners are invoked synchronously, work running in the listener can complete before publishing the ready event finishes and traffic acceptance is announced.

If the event multicaster or listener is configured asynchronously, work completion order can differ. Do not assume every listener blocks readiness when the system has altered event dispatch mechanics.

## 6. Using ApplicationRunner or CommandLineRunner for Startup Tasks

If work must run **after the context has refreshed yet before the application reports ready**, two interfaces are usually suitable:

- **ApplicationRunner**: receives an ApplicationArguments object with parsed command-line arguments.
- **CommandLineRunner**: receives the raw String array of command-line arguments.

Spring Boot invokes runners after context refresh and before ApplicationReadyEvent.

### 6.1. ApplicationRunner example

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public class ReferenceDataLoader implements ApplicationRunner {
    private final ReferenceDataService dataService;

    public ReferenceDataLoader(ReferenceDataService dataService) {
        this.dataService = dataService;
    }

    @Override
    public void run(ApplicationArguments args) {
        dataService.loadRequiredReferenceData();
    }
}
~~~

In this example, ReferenceDataService is injected like a normal bean. When run() is called, the ApplicationContext has refreshed; beans and proxies created during refresh are ready per container mechanics.

If loading reference data is mandatory for the application to serve requests properly, running synchronously in the runner ensures startup only proceeds to ApplicationReadyEvent after the task completes.

### 6.2. CommandLineRunner example

~~~java
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class StartupArgumentLogger implements CommandLineRunner {

    @Override
    public void run(String... args) {
        for (String arg : args) {
            System.out.println("Argument: " + arg);
        }
    }
}
~~~

CommandLineRunner fits when only raw argument strings are needed. ApplicationRunner is handier when querying options parsed by Spring Boot.

### 6.3. Order among multiple runners

If there are multiple ApplicationRunners or CommandLineRunners, they can be ordered with:

- **@Order**.
- **Ordered** interface.

Example:

~~~java
@Component
@Order(1)
public class DatabasePreparationRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        // First preparation step.
    }
}
~~~

~~~java
@Component
@Order(2)
public class CacheWarmupRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        // Next preparation step.
    }
}
~~~

Lower order values take precedence in standard sorting. If one task depends on another task's result, you can use a single runner coordinating explicitly or order runners by a clear contract.

Do not rely on accidental component scan order to determine runner sequence.

### 6.4. What if a runner throws an exception?

Runners execute during startup. If a runner throws an unhandled exception, startup typically fails and ApplicationReadyEvent is not published along the normal success path.

This fits **mandatory** tasks: if seed data is missing or an essential condition cannot be fulfilled, the application should not pretend to be ready.

For optional tasks, decide explicitly:

- Can it be skipped while recording a degraded state?
- Can it be retried within a bounded window?
- Is the application allowed to accept traffic while the task is incomplete?
- If an error occurs, who is responsible for alerting and recovery?

Do not catch broad exceptions and merely log so the runner always finishes successfully if doing so leaves the application serving requests with invalid data.

## 7. When to Use ApplicationReadyEvent?

**ApplicationReadyEvent** fits tasks that must wait for runners to finish. For example:

- Emitting an internal signal that the application has passed the startup phase.
- Starting work that only makes sense once configuration and runners are done.
- Triggering a final warm-up step before availability transitions to accepting traffic.
- Recording when the application reaches the ready milestone.

Example:

~~~java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class FinalWarmupListener {
    private final SearchWarmupService warmupService;

    public FinalWarmupListener(SearchWarmupService warmupService) {
        this.warmupService = warmupService;
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        warmupService.warmUp();
    }
}
~~~

With synchronous event listeners under default configuration, the warmUp() call finishes before the listener returns. Spring Boot then proceeds to publish ACCEPTING_TRAFFIC readiness per the normal startup sequence.

If warmUp() takes several minutes, a synchronous listener also prolongs the period before the application is marked accepting traffic. That may be intentional if warm-up is a hard prerequisite, yet inappropriate if the work can run in the background once the app serves requests.

### 7.1. ApplicationReadyEvent does not mean all external systems are healthy

This event only reflects that the application has passed the startup steps orchestrated by Spring Boot. It does not guarantee that:

- Databases or external services will remain operational afterward.
- Every message consumer has already received messages.
- All long-running background tasks have finished.
- External endpoints are reachable from every network.
- Real business logic is error-free.

If readiness requirements depend on an external service, implement appropriate health/readiness checks and policies for when that service loses connectivity after startup.

## 8. Choosing a Callback by Required Timing

The table below distinguishes the mechanisms:

| Mechanism | Execution milestone | Suited for |
|---|---|---|
| Constructor | During instance creation | Establishing required state from arguments; no external service calls. |
| **@PostConstruct** | After bean injection, during initialization | Local bean validation/preparation, short work. |
| **afterPropertiesSet()** | Bean initialization phase | Initialization callback coupled to Spring InitializingBean. |
| **@Bean(initMethod=...)** | Bean initialization phase | Initializing third-party objects or objects configured via factory methods. |
| **SmartInitializingSingleton** | After pre-instantiation of eager singletons, during refresh | Infrastructure tasks needing regular singletons already created. |
| **ContextRefreshedEvent** | After context refresh | Logic depending on refreshed context, accepting context-event caveats. |
| **ApplicationStartedEvent** | After refresh, before runners | Reacting to app-started milestone while runners haven't finished yet. |
| **ApplicationRunner / CommandLineRunner** | After refresh, before ApplicationReadyEvent | Startup tasks that must complete before the ready milestone. |
| **ApplicationReadyEvent** | After runners complete | Tasks needing to wait for normal startup phase to finish. |
| **@PreDestroy / destroyMethod** | When bean is destroyed per lifecycle | Releasing resources owned by the bean. |

There is no single "best" callback for every task. Identify the prerequisites of the work and choose the earliest milestone that guarantees those prerequisites are met.

## 9. Example: Task Needing to Run After All Beans Are Ready

Suppose an application needs to read a configuration catalog from the database and warm up a cache before receiving requests.

Do not default to putting the entire workflow inside the cache's @PostConstruct:

~~~java
@Component
public class ProductCache {
    private final ProductRepository repository;

    public ProductCache(ProductRepository repository) {
        this.repository = repository;
    }

    @PostConstruct
    void initialize() {
        // May run too early relative to overall startup workflow.
        repository.findAll();
    }
}
~~~

Instead, keep the cache as a bean with a clear API:

~~~java
import org.springframework.stereotype.Component;

@Component
public class ProductCache {
    private volatile java.util.Map<Long, Product> products =
            java.util.Map.of();

    public void replaceAll(java.util.Map<Long, Product> values) {
        this.products = java.util.Map.copyOf(values);
    }

    public Product find(long id) {
        return products.get(id);
    }
}
~~~

A service responsible for loading data and preparing the cache:

~~~java
import java.util.Map;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheWarmupService {
    private final ProductRepository repository;
    private final ProductCache cache;

    public ProductCacheWarmupService(
            ProductRepository repository,
            ProductCache cache) {
        this.repository = repository;
        this.cache = cache;
    }

    public void warmUp() {
        Map<Long, Product> values = repository.findAll().stream()
                .collect(Collectors.toMap(Product::getId, product -> product));
        cache.replaceAll(values);
    }
}
~~~

A runner coordinating execution:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class ProductCacheWarmupRunner implements ApplicationRunner {
    private final ProductCacheWarmupService warmupService;

    public ProductCacheWarmupRunner(
            ProductCacheWarmupService warmupService) {
        this.warmupService = warmupService;
    }

    @Override
    public void run(ApplicationArguments args) {
        warmupService.warmUp();
    }
}
~~~

With this approach:

1. Spring creates beans and completes dependency injection.
2. ApplicationContext refreshes.
3. The runner loads data and updates the cache.
4. If warm-up succeeds, Spring Boot proceeds to ApplicationReadyEvent.
5. Only then does the application transition to the readiness accepting-traffic milestone in the default flow.

If warm-up fails and the exception propagates out of the runner, startup does not report success. This fits when the cache is a mandatory prerequisite for serving requests.

## 10. Synchronous and Asynchronous Work Have Different Meanings

A startup task can fall into one of two categories:

**Must complete before accepting traffic**

- Seed data required to handle requests correctly.
- Configuration that needs validation and fail-fast behavior.
- Essential initialization without which the application cannot function.

For this category, execute synchronously in ApplicationRunner/CommandLineRunner or a synchronous listener at the appropriate milestone. Execution duration becomes part of startup time.

**Can continue running after the application already accepts traffic**

- Warming up an optional cache where requests still have a fallback.
- Loading optional statistics data.
- Sending a startup report.
- Starting a periodic sync task with observability and retries.

For this category, you can offload processing to an executor/background worker. Still, clearly define the feature's state while the task is not yet finished.

### 10.1. @Async does not automatically make the application wait for completion

Spring supports @Async when asynchronous method execution is enabled via appropriate configuration, typically **@EnableAsync**.

Example:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class BackgroundWarmupService {

    @Async
    public CompletableFuture<Void> warmUp() {
        // Work can run on an executor.
        performWarmup();
        return CompletableFuture.completedFuture(null);
    }

    private void performWarmup() {
        // Load data or warm up cache.
    }
}
~~~

Configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

If the @Async method is called through the bean proxy, the call is dispatched to the configured executor. However, the caller can continue before the work finishes.

### 10.2. Calling @Async from the same bean bypasses the proxy

Example:

~~~java
@Component
public class WarmupComponent {

    public void start() {
        warmAsync();
    }

    @Async
    public void warmAsync() {
        // ...
    }
}
~~~

In standard proxy mode, an internal call from start() to warmAsync() does not go through the proxy, so @Async may not be applied. This is self-invocation, similar to the limitation in many other Spring AOP mechanisms.

A cleaner design is moving the async task to a separate bean and invoking that bean from the runner or listener.

### 10.3. ApplicationReadyEvent combined with background tasks

Listener example:

~~~java
@Component
public class BackgroundWarmupListener {
    private final BackgroundWarmupService warmupService;

    public BackgroundWarmupListener(
            BackgroundWarmupService warmupService) {
        this.warmupService = warmupService;
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        warmupService.warmUp();
    }
}
~~~

The listener invokes the async service through another bean. The listener can return immediately after submitting the work; the application finishes publishing ApplicationReadyEvent and announcing readiness.

That means **ApplicationReadyEvent does not wait for async tasks to finish**. If requests require data that warm-up is generating, provide a fallback or a dedicated readiness gate. Do not assume that just because work starts from ApplicationReadyEvent, requests will wait for it.

### 10.4. Managing errors in background tasks

When tasks run asynchronously:

- Decide where results or exceptions are handled.
- Log with context; do not swallow errors.
- Define a bounded retry policy with backoff if business logic permits.
- Expose progress/completion status for observability.
- Set timeouts and bound executor resources.
- Have a shutdown strategy so critical resources are not left dangling.

If the method returns CompletableFuture, the caller can attach callbacks or store the Future to track outcomes. If using a void method, exceptions cannot be received directly by the caller via return value; an appropriate async error handling mechanism is needed.

## 11. Readiness Differs from Liveness

Spring Boot Actuator has the concept of **availability** to express whether an application can receive traffic and whether the process is still healthy.

- **Liveness:** is the process/application in a state where it can keep running or should it be restarted?
- **Readiness:** is the application ready to receive requests/traffic right now?

An application can be alive yet not ready:

~~~text
Process running
      │
      ▼
Liveness = UP
      │
      ▼
Loading required data
      │
      ▼
Readiness = REFUSING_TRAFFIC
      │
      ▼
Required initialization completes
      │
      ▼
Readiness = ACCEPTING_TRAFFIC
~~~

In Spring Boot, readiness state can be observed via Actuator health groups when properly configured. Deployment platforms such as Kubernetes can use readiness probes to decide whether to route traffic to an instance.

### 11.1. Synchronous runners make readiness wait for startup tasks

In the default startup flow, Boot calls runners before ApplicationReadyEvent and afterward publishes ACCEPTING_TRAFFIC readiness. Thus, if a runner runs synchronously and only returns after mandatory work finishes, the application does not reach the ready milestone while that work is running.

This is a simple approach for startup tasks that must finish before traffic. In return, startup time increases, and if the task hangs, the application may never report ready.

### 11.2. Background tasks after ready need a dedicated readiness gate if traffic must still be blocked

If a task runs asynchronously after ApplicationReadyEvent while requests must not yet use that feature, @Async alone is not enough to block traffic. A readiness/health mechanism designed to reflect the true task state is needed.

One approach is creating a **HealthIndicator** or health contributor belonging to the readiness group that only reports UP once mandatory warm-up completes. The deployment platform continues treating the instance as unready while that contributor is not UP.

Illustrative example of a separate state holder:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

@Component
public class WarmupState {
    private final AtomicBoolean complete = new AtomicBoolean(false);

    public boolean isComplete() {
        return complete.get();
    }

    public void markComplete() {
        complete.set(true);
    }
}
~~~

A health contributor can read this state:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("warmup")
public class WarmupHealthIndicator implements HealthIndicator {
    private final WarmupState state;

    public WarmupHealthIndicator(WarmupState state) {
        this.state = state;
    }

    @Override
    public Health health() {
        if (state.isComplete()) {
            return Health.up().build();
        }
        return Health.outOfService()
                .withDetail("warmup", "in progress")
                .build();
    }
}
~~~

Then configure the readiness group to include this contributor per Actuator conventions of your Boot version. For example:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,warmup
~~~

This illustrates health-gate design; verify actual health endpoints, groups, and probe setups in your environment. A contributor only takes effect if the readiness probe actually queries the corresponding readiness group.

### 11.3. Do not put every external dependency into liveness

If a database temporarily loses connectivity, that usually does not mean the process must be restarted immediately. Thoughtlessly putting external dependencies into liveness can cause the platform to restart entire fleets of instances while a downstream service is experiencing an outage.

Readiness is usually better suited for temporarily pausing traffic when a mandatory dependency is unavailable. Liveness should reflect the process's ability to keep operating, avoiding useless restart loops.

## 12. Why Shouldn't You Put Heavy Tasks in @PostConstruct?

### 12.1. Slows down context creation

If a bean takes 90 seconds to load data inside @PostConstruct, bean creation and context refresh must wait for that callback. Subsequent beans are not yet initialized, and the application has not reached later startup milestones.

When multiple beans perform heavy work in callbacks, startup time grows sequentially and dependencies can create hard-to-predict waiting chains.

### 12.2. Calling external services can make startup unstable

An HTTP API, database, or message broker might:

- Not have opened its port yet when the application starts.
- Be slow over the network.
- Return transient errors.
- Require retries.
- Enforce connection limits.

If called directly inside a callback without proper timeouts and retry policies, the application can fail startup or hang for a long time. Tasks needing retries/timeouts usually fit an explicit startup-coordinating service better.

### 12.3. Creates circular dependencies or accesses beans before context completes

A callback might call ApplicationContext.getBean() to fetch another bean. This creates hidden dependencies, makes bean creation order hard to read, and can trigger premature initialization. If a cycle exists, the context can fail with circular dependency or unready bean errors.

Prefer declaring dependencies via constructors. If work needs the entire context, pick a post-refresh lifecycle hook instead of looking up beans arbitrarily from @PostConstruct.

### 12.4. Invokes transactions or AOP at the wrong time

Inside an initialization callback, the current bean's proxy may not be finished yet and internal calls bypass proxies. That prevents annotations such as @Transactional or @Async from behaving as intended.

Extracting work to another bean and calling it from an appropriate runner/event is usually much clearer.

### 12.5. Hard to distinguish configuration errors from business task errors

If @PostConstruct simultaneously validates properties, calls external APIs, imports data, and warms up caches, startup logs may merely show bean creation failed. Diagnosing the root cause and deciding whether to fail startup becomes harder.

Separate responsibilities:

- Bean callbacks: validate configuration and internal state.
- Startup services: coordinate an application-wide task.
- Runners/event listeners: choose the right execution milestone.
- Health/readiness: represent how ready the application is.

## 13. Designing Startup Tasks by Level of Criticality

Before selecting a hook, classify the work:

| Task category | Example | Typically suitable organization |
|---|---|---|
| Fast internal initialization | Building an immutable lookup table from bound properties | Constructor or @PostConstruct. |
| Bean invariant validation | Checking required parameters, local configuration | @PostConstruct or initMethod; fail fast if bean is invalid. |
| Validation after eager singletons are created | Confirming internal registry collected beans | SmartInitializingSingleton. |
| Task needing context refresh complete | An integration step needing the complete bean graph | ContextRefreshedEvent, if waiting for runners is unnecessary. |
| Mandatory task before reporting ready | Loading reference data, mandatory cache warm-up | Synchronous ApplicationRunner/CommandLineRunner. |
| Task needing to wait for other runners | Emitting signal or final step after startup runners | ApplicationReadyEvent. |
| Long task that can run in background | Data synchronization not impacting current requests | Executor/@Async, with status and error handling. |
| Task required before traffic yet run asynchronously | Large warm-up that can continue past process startup | Explicitly designed readiness gate/health contributor. |
| Releasing bean resources | Closing clients, executors, connection wrappers | @PreDestroy, destroyMethod, or appropriate lifecycle. |

A single task can span categories depending on business requirements. For example, a cache might be mandatory for one endpoint yet optional for another; in that case, design readiness and fallbacks per feature rather than by the generic label "cache warm-up."

## 14. Avoiding Unwanted Repeated Task Execution

Startup callbacks do not always correspond to running strictly once across the entire JVM lifetime.

Scenarios to keep in mind:

- A test suite can create multiple ApplicationContexts within the same JVM.
- A context can be refreshed again in specialized structures.
- Multiple instances of the application run in parallel in a deployment.
- A runner can run again if the application is restarted.
- A message or external trigger can repeat the same initialization request.

If a task has side effects such as writing data, creating default accounts, or sending notifications, design **idempotency** and proper transactions. Do not rely solely on a JVM static boolean to guarantee a system-wide task runs only once.

Example:

~~~java
@Component
public class InitialCatalogRunner implements ApplicationRunner {
    private final CatalogInitializationService service;

    public InitialCatalogRunner(CatalogInitializationService service) {
        this.service = service;
    }

    @Override
    public void run(ApplicationArguments args) {
        service.initializeIfRequired();
    }
}
~~~

The name initializeIfRequired suggests an idempotent contract: the service should check durable state or use appropriate unique constraints/locks before writing data. Implementation details depend on the database and business domain.

### 14.1. Multiple replicas all running the runner

If 5 replicas of a service are deployed, each replica can run ApplicationRunner. Thus, a runner is not automatically a leader election or distributed lock mechanism.

If a task must run strictly once across the whole system, use an appropriate distributed mechanism such as:

- A separate job/migration in the deployment pipeline.
- Distributed locks with leases and error handling.
- Leader election.
- A task queue with idempotency mechanisms.
- A separately deployed scheduler/worker with clear ownership.

Do not use bean callbacks or ApplicationRunner to substitute for a distributed task coordinator.

## 15. Difference Between Startup Runners and Schedulers

**ApplicationRunner** and **CommandLineRunner** normally run once per SpringApplication startup that successfully reaches the runner stage.

**@Scheduled** is used to run recurring scheduled tasks once scheduling is enabled and a scheduler is configured:

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class CatalogRefreshJob {

    @Scheduled(fixedDelayString = "PT5M")
    public void refresh() {
        // Refresh catalog on a schedule.
    }
}
~~~

~~~java
@Configuration
@org.springframework.scheduling.annotation.EnableScheduling
class SchedulingConfiguration {
}
~~~

Runners fit **initial steps at startup**. Schedulers fit **recurring scheduled work**. A runner may perform the initial run and the scheduler continue updating afterward, provided both tasks avoid racing on the same data.

## 16. Practice: Choosing the Right Milestone for Each Requirement

### Scenario A: Validating a client's required properties

A client needs a base URL and API key. If either is missing, the bean is invalid.

**Choice:** constructor validation or @PostConstruct. This is an invariant of the bean itself, so failing fast inside the bean's lifecycle is reasonable.

~~~java
@Component
public class PartnerClient {
    private final PartnerProperties properties;

    public PartnerClient(PartnerProperties properties) {
        this.properties = properties;
    }

    @PostConstruct
    void validateConfiguration() {
        if (properties.getBaseUrl() == null
                || properties.getBaseUrl().isBlank()) {
            throw new IllegalStateException("Missing partner.base-url");
        }
    }
}
~~~

There is no need to wait until the entire application is ready to catch invalid local configuration.

### Scenario B: Loading seed data before accepting requests

Data required to handle every request must be present before the app receives traffic.

**Choice:** synchronous ApplicationRunner. If the task fails, startup does not advance to the ready milestone.

### Scenario C: Sending a notification after runners finish

An internal notification only makes sense once normal startup has succeeded.

**Choice:** ApplicationReadyEvent. If sending the notification must not fail startup, handle errors per a clear policy and record the outcome.

### Scenario D: Cache warm-up takes minutes, yet the API has a fallback

The application can serve requests by querying the data source directly while the cache warms up.

**Choice:** executor or @Async after an appropriate milestone, with progress status and fallback. If any endpoint lacks a fallback, use a readiness gate for that endpoint/feature or the whole instance depending on architecture.

### Scenario E: Opening a shared connection or thread pool

A bean owns a resource that must be initialized and closed according to its own lifecycle.

**Choice:** factory method/init callback or appropriate lifecycle mechanism; close the resource via a destroy callback. If opening the connection depends on an external service with long retries, consider a startup coordinator rather than stuffing retry logic into @PostConstruct.

### Scenario F: Checking that all eager singletons have been created

A registry needs to collect metadata from ordinary singletons after pre-instantiation.

**Choice:** SmartInitializingSingleton. However, if you need to wait for runners or readiness, use a later hook.

## 17. Common Mistakes and How to Recognize Them

### 17.1. @PostConstruct runs before another bean's task

**Symptom:** bean A's log appears before bean B finishes its initialization task.

**Explanation:** the container creates beans by dependency/lifecycle; A's @PostConstruct is not an application-wide barrier.

**Resolution:** if the task needs the whole context, move coordination to a post-refresh hook or runner. If only a specific dependency is needed, declare the dependency explicitly.

### 17.2. @Transactional does not work inside @PostConstruct

**Symptom:** writes inside the callback are not inside a transaction as expected.

**Explanation:** the current bean may not yet be wrapped in a proxy; internal calls bypass proxies.

**Resolution:** call a separate transactional service from a runner or listener after context refresh.

### 17.3. ContextRefreshedEvent arrives, yet startup runners have not run

**Symptom:** a listener sees the context refreshed, yet data prepared by a runner is missing.

**Explanation:** ContextRefreshedEvent fires before ApplicationStartedEvent and before runners.

**Resolution:** use ApplicationRunner if the work must happen before ready; use ApplicationReadyEvent if you need to wait for runners to finish.

### 17.4. ApplicationReadyEvent fired, yet async warm-up is still unfinished

**Symptom:** the application accepts traffic while cache data is still missing.

**Explanation:** the listener submitted async work and returned; Boot does not automatically wait for the Future to finish.

**Resolution:** if the work is mandatory, run synchronously before ready or integrate a readiness gate; if optional, provide fallbacks and explicit status.

### 17.5. Startup drags on or hangs

**Symptom:** logs never reach ApplicationReadyEvent; a runner or callback runs for a very long time.

**Explanation:** a synchronous task is holding up startup, possibly due to I/O, unbounded retries, or deadlock.

**Resolution:** add timeouts, bound retries, measure durations, log per stage, and move optional work to the background.

### 17.6. Runner executes on every replica

**Symptom:** seed data or notifications are duplicated when scaling a deployment.

**Explanation:** each process runs its own runners.

**Resolution:** idempotency, distributed locks, or moving the task to a dedicated job/worker.

### 17.7. @PreDestroy is not called when the process is killed

**Symptom:** external resources remain lingering after an abrupt process stop.

**Explanation:** bean destruction callbacks only run when lifecycle shutdown executes properly; they are not guaranteed across every failure.

**Resolution:** design timeouts/leases on the external service side, recoverable cleanup mechanisms, and an adequate shutdown grace period.

## 18. How to Observe Startup Milestones

To see which stages the application actually passes through, you can log inside each hook:

~~~java
@Component
public class LifecycleTrace implements ApplicationRunner {

    @PostConstruct
    void postConstruct() {
        System.out.println("1. Bean PostConstruct");
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("4. ApplicationRunner");
    }

    @EventListener
    public void onContextRefresh(ContextRefreshedEvent event) {
        System.out.println("3. ContextRefreshedEvent");
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("5. ApplicationReadyEvent");
    }
}
~~~

In real applications, logs across multiple beans can interleave because there are many dependency branches and listeners. This example only helps observe milestones, not test detailed ordering of every bean.

To make logs more informative, include timestamps, thread names, bean names, or startup phases. When async tasks are used, thread names help verify whether work is running on an executor or still blocking the startup thread.

## 19. Principles for Designing Callbacks and Startup Tasks

1. **Keep bean callbacks short and local.** Constructors, @PostConstruct, and initMethod should prepare the bean's own state, validate configuration, and complete what is needed for the bean to be valid.
2. **Do not use @PostConstruct as an application-wide barrier.** It does not mean every singleton, runner, or external service is ready.
3. **Declare dependencies explicitly.** Avoid calling ApplicationContext.getBean() arbitrarily inside callbacks to create hidden ordering.
4. **Use runners for tasks that must finish before ready.** Synchronous runners enable fail-fast behavior and keep the app from reporting ready until done.
5. **Use ApplicationReadyEvent when you need to wait for runners.** This is a broader milestone than ContextRefreshedEvent.
6. **Separate background tasks from the startup thread.** Provide an executor, timeouts, retries, and proper exception handling.
7. **Represent readiness accurately against ability to serve requests.** If an async task remains a hard prerequisite, provide a real health/readiness gate.
8. **Design idempotent tasks.** Startup can repeat across restarts, test contexts, or multiple replicas.
9. **Manage resources by lifecycle.** Destruction callbacks are helpful, yet do not replace timeouts, leases, and recoverable cleanup.
10. **Measure startup duration.** Knowing which callbacks or runners consume time helps decide what should be synchronous and what can run in the background.

## 20. Common Misconceptions

**"@PostConstruct means the application has finished starting up."**  
No. It is only a post-injection callback for one specific bean.

**"Once one bean runs @PostConstruct, every other bean is ready."**  
No. Other beans may not have been created yet or may not have finished their own tasks.

**"ContextRefreshedEvent and ApplicationReadyEvent are the same milestone."**  
No. ContextRefreshedEvent reports that the context has refreshed; ApplicationReadyEvent is published after Spring Boot finishes invoking ApplicationRunner and CommandLineRunner.

**"SmartInitializingSingleton is a callback after the entire application is ready."**  
No. It runs after pre-instantiation of eager singletons, still inside context refresh.

**"ApplicationRunner runs after ApplicationReadyEvent."**  
No. Runners execute before ApplicationReadyEvent.

**"@Async called from anywhere runs in the background."**  
No. In standard proxy mode, self-invocation bypasses the proxy; async processing also requires enabling and an appropriate executor.

**"An ApplicationReadyEvent listener always waits for every background task."**  
No. A synchronous listener only waits for synchronous code inside the listener. If the listener submits a Future/async task and returns, background work may still continue.

**"A runner executes only once for the entire deployment."**  
No. It runs per application process startup; multiple replicas can all run it.

**"@PreDestroy is guaranteed to run when the JVM stops."**  
No. Only normal shutdown gives callbacks a chance to execute; crashes or sudden kills offer no guarantee.

**"Every startup task should run synchronously for simplicity."**  
No. Only tasks that must finish before readiness should block the ready milestone. Optional or long-running work can run in the background when proper fallbacks and observability exist.

## Core Takeaway

**Bean callbacks** such as @PostConstruct, afterPropertiesSet, and initMethod serve initializing a single bean. They do not guarantee the entire ApplicationContext or application has finished starting up. **SmartInitializingSingleton** runs after ordinary eager singletons are created, while **ContextRefreshedEvent** reports context refresh; both still occur before startup runners.

If a task must complete before the application reports ready, use a synchronous **ApplicationRunner** or **CommandLineRunner**. If you need to wait for runners to finish, use **ApplicationReadyEvent**. If work can run in the background, manage executors, errors, and readiness state explicitly; do not assume @Async will keep the application from accepting traffic. Choosing the right milestone based on the task's prerequisites makes startup predictable, prevents callbacks from running prematurely, and keeps application readiness aligned with actual request-serving capability.
