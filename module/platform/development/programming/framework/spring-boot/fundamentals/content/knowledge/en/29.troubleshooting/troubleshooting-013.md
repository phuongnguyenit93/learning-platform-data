# Callback, Runner, or Listener Not Invoked at the Expected Time

In Spring Boot, a piece of code can be invoked automatically when a bean is created, when the ApplicationContext finishes refreshing, after the application starts, when an application event is published, or when the application begins shutting down. These extension points are convenient, yet they do not share the same timing or activation conditions.

Common scenarios:

- A `@PostConstruct` method runs before you think the entire application is ready.
- A `CommandLineRunner` does not run because the bean is not registered or startup failed before the runner phase.
- `ApplicationReadyEvent` never arrives because a runner threw an exception.
- `@EventListener` misses an event published before the listener was registered.
- `@TransactionalEventListener` does not run because the event was published outside a transaction.
- A listener runs asynchronously, so logs appear later or completion order differs from expectations.
- A second test does not see the runner execute because Spring reuses a cached ApplicationContext.
- Shutdown callbacks do not run when the process is forcefully killed.

This lesson belongs to the **Troubleshooting** chapter of **Spring Boot Fundamentals**. Its goal is to understand the lifecycle accurately, choose the right callback/event for the job, identify why a callback fails to run or runs at the wrong time, and follow an evidence-based verification workflow.

## 1. Distinguishing callbacks, runners, and listeners

These three terms are often used interchangeably, yet in Spring they refer to different mechanisms.

| Mechanism | When is it triggered? | Examples |
|---|---|---|
| Bean lifecycle callback | During creation or destruction of a bean | `@PostConstruct`, `@PreDestroy` |
| Application runner | After ApplicationContext refreshes successfully, during startup | `ApplicationRunner`, `CommandLineRunner` |
| Application event listener | When a matching event is published in the event system | `@EventListener`, `ApplicationListener` |
| Context lifecycle callback | When context refreshes or closes | `ContextRefreshedEvent`, `ContextClosedEvent` |
| Lifecycle component | When the container starts/stops lifecycle components | `SmartLifecycle` |
| Scheduled task | On a schedule after scheduling is enabled | `@Scheduled` |

A callback not running does not necessarily mean Spring is broken. The callback may be attached to a lifecycle phase different from the one you are observing, the bean may not have been created, the event may not have been published, or the activation condition may not match.

### 1.1. Start by asking "what am I waiting for?"

Before editing code, state clearly:

- Do I want a method to run **once when the bean is created**?
- Do I want it to run **after all singleton beans are initialized**?
- Do I want it to run **after Spring context refresh**?
- Do I want it to run **after all startup runners complete**?
- Do I want to handle **each specific event**?
- Do I want it to run **after transaction commit**?
- Do I want it to run **periodically or on a schedule**?
- Do I want to clean up resources **when the context closes**?

Without pinpointing the expected timing, it is easy to pick the wrong extension point.

## 2. Spring Boot startup timeline

A Spring Boot application passes through multiple phases. Different callbacks trigger at different points.

High-level diagram:

```text
SpringApplication.run(...)
          │
          ▼
ApplicationStartingEvent
          │
          ▼
Prepare Environment and configuration
          │
          ▼
ApplicationEnvironmentPreparedEvent
          │
          ▼
Create ApplicationContext
          │
          ▼
ApplicationContextInitializedEvent
          │
          ▼
ApplicationPreparedEvent
          │
          ▼
Load bean definitions / refresh context
          │
          ├── Bean construction
          ├── Dependency injection
          ├── @PostConstruct
          ├── afterPropertiesSet()
          ├── custom init method
          ├── SmartInitializingSingleton
          ├── SmartLifecycle start
          └── ContextRefreshedEvent
          │
          ▼
ApplicationStartedEvent
          │
          ▼
LivenessState.CORRECT
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
Application ready
```

This is the primary timeline for diagnosing startup. Fine-grained events may interleave depending on application context type, web server, and Spring Boot version. What matters is distinguishing **bean initialization**, **context refresh**, **runner execution**, and **application ready**.

### 2.1. Key milestones to remember

| Milestone | Meaning |
|---|---|
| `ApplicationStartingEvent` | SpringApplication begins running; Environment and context are not yet fully prepared |
| `ApplicationEnvironmentPreparedEvent` | Environment is ready for subsequent steps |
| `ApplicationContextInitializedEvent` | ApplicationContext has been created and initializers have been applied |
| `ApplicationPreparedEvent` | Context is prepared, bean definitions are about to be loaded/refreshed per bootstrap |
| `ContextRefreshedEvent` | An ApplicationContext has finished refreshing |
| `ApplicationStartedEvent` | Boot has refreshed the context; startup runners have not yet been called |
| `ApplicationReadyEvent` | Startup runners have completed; the application transitions to the ready phase |
| `ApplicationFailedEvent` | Startup failed at a stage handled by SpringApplication |

`ApplicationReadyEvent` is the right milestone when a task genuinely needs to wait for startup runners to complete. `ContextRefreshedEvent` fires earlier and can be published for multiple contexts in a hierarchy.

### 2.2. An open web server port does not mean the application is ready

In a web application, the embedded server may be started during context refresh. However, Spring Boot manages readiness separately; startup runners still have to finish before the application transitions to `ReadinessState.ACCEPTING_TRAFFIC`.

Therefore, do not infer merely from seeing a listening port that all startup work has completed.

## 3. Where do bean lifecycle callbacks run?

Callbacks tied to bean lifecycle typically execute when Spring creates and initializes a bean.

Example:

```java
@Component
public class CacheWarmup {

    @PostConstruct
    void initialize() {
        System.out.println("Bean initialized");
    }
}
```

`@PostConstruct` is invoked after dependency injection for that bean finishes, during the bean's initialization phase.

It **does not mean the entire ApplicationContext is ready**. Other beans may not be initialized yet, and application startup runners have not executed.

### 3.1. Common initialization callback order

In a typical singleton bean lifecycle, the general order is:

1. Constructor.
2. Dependency injection and property population steps.
3. Pre-initialization BeanPostProcessors, including handling `@PostConstruct`.
4. `InitializingBean.afterPropertiesSet()` if the bean implements that interface.
5. Custom init method declared in the bean definition/`@Bean`.
6. Post-initialization BeanPostProcessors, which may wrap the bean in a proxy.
7. The bean enters service according to the container lifecycle.

Exact ordering also depends on post-processors and bean creation mechanisms. Never use a single bean's callback to infer that all other beans have completed initialization.

### 3.2. @PostConstruct is not ApplicationReadyEvent

Example:

```java
@Component
public class StartupProbe {

    private static final Logger log =
            LoggerFactory.getLogger(StartupProbe.class);

    @PostConstruct
    void afterInjection() {
        log.info("StartupProbe bean initialized");
    }

    @EventListener(ApplicationReadyEvent.class)
    void afterApplicationReady() {
        log.info("Application is ready");
    }
}
```

The two logs may appear separated by the creation of other beans, context refresh, and startup runner execution.

If a method needs to call other beans assuming the whole context is ready, `@PostConstruct` is usually not the right place.

### 3.3. @PostConstruct does not run if the bean has not been created

Example:

```java
@Component
@Lazy
public class ExpensiveInitializer {

    @PostConstruct
    void initialize() {
        System.out.println("ExpensiveInitializer initialized");
    }
}
```

With lazy initialization, the bean may not be created during context refresh. The callback only runs when the bean is actually instantiated.

Some mechanisms such as runner lookups or listener infrastructure can cause a bean to be instantiated later. Thus, do not conclude an annotation is broken merely because its log does not appear immediately at context refresh.

### 3.4. @PostConstruct is not suited for every startup task

Avoid placing tasks inside `@PostConstruct` that:

- Require all application beans to be ready.
- Require the web server to have finished its lifecycle.
- Require other startup runners to run first.
- Take a long time or block the context creation thread.
- Need complex retry/backoff logic.
- Need explicit transaction or async workflow management.

Choose a runner, event listener, or dedicated lifecycle component as required.

## 4. InitializingBean and custom init methods

Besides `@PostConstruct`, Spring supports the `InitializingBean` interface:

```java
@Component
public class ConnectionRegistry implements InitializingBean {

    @Override
    public void afterPropertiesSet() {
        // Validate configuration and prepare bean state.
    }
}
```

Or using a custom init method:

```java
@Configuration
class ClientConfiguration {

    @Bean(initMethod = "initialize")
    ClientRegistry clientRegistry() {
        return new ClientRegistry();
    }
}
```

Three common approaches:

| Approach | Advantage | Note |
|---|---|---|
| `@PostConstruct` | Clear, widely used annotation | Callback during bean initialization |
| `InitializingBean` | Interface-based lifecycle contract | Class depends on Spring API |
| `@Bean(initMethod = "...")` | Lifecycle configured from bean definition | Must declare a valid method |

These are not startup runners. They serve to finish initializing **one specific bean**.

### 4.1. What if you need to run after all singleton beans?

Spring provides `SmartInitializingSingleton`:

```java
@Component
public class SingletonInitializationReporter
        implements SmartInitializingSingleton {

    @Override
    public void afterSingletonsInstantiated() {
        // Regular singleton beans have been pre-instantiated.
    }
}
```

This callback runs after pre-instantiation of regular singleton beans completes, during context refresh.

It still happens **before ApplicationStartedEvent and before startup runners** in the standard Spring Boot flow. If you need to wait for runners, use a post-runner milestone such as `ApplicationReadyEvent`.

### 4.2. Avoid lifecycle dependency cycles

If bean A calls bean B inside `@PostConstruct`, and bean B depends on A or calls back into A during initialization, you can introduce a dependency cycle or observe partially initialized state.

Keep bean initialization simple: validate local state, prepare the bean's own data, and fail fast if configuration is invalid.

## 5. ApplicationRunner and CommandLineRunner

These two interfaces are meant for work that runs during startup **after the ApplicationContext refreshes successfully**.

### 5.1. CommandLineRunner

```java
@Component
public class InitialDataRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("Runner started");
    }
}
```

It receives command-line arguments as strings.

### 5.2. ApplicationRunner

```java
@Component
public class ConfigurationReporter implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "Option names: " + args.getOptionNames()
        );
    }
}
```

`ApplicationArguments` helps distinguish option arguments like `--key=value` from non-option arguments.

### 5.3. Declaring a runner with @Bean

A runner does not have to be a `@Component` class:

```java
@Configuration
class StartupConfiguration {

    @Bean
    ApplicationRunner initialCheck() {
        return args -> {
            System.out.println("Initial check completed");
        };
    }
}
```

When using `@Bean`, verify that the method is actually configured inside a class scanned or imported by Spring.

### 5.4. Runners do not execute on every request

A runner typically executes once each time SpringApplication starts an ApplicationContext. It is not:

- An HTTP request callback.
- A scheduled task.
- A message consumer callback.
- A callback invoked each time a bean is injected.
- An event listener for arbitrary refresh calls.

If you want to handle every request, put logic in a controller/filter/interceptor or an appropriate service boundary. If you want periodic execution, use scheduling. If you want to process messages, use a message broker listener.

## 6. Runner not invoked: common causes

When `run(...)` does not execute, check in order.

### 6.1. Runner bean is not registered

Wrong:

```java
public class ImportRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("Import started");
    }
}
```

The class above lacks `@Component` and is not declared via `@Bean`. Without another registration mechanism, Spring does not know to create this bean.

Right:

```java
@Component
public class ImportRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("Import started");
    }
}
```

Or:

```java
@Configuration
class ImportConfiguration {

    @Bean
    CommandLineRunner importRunner() {
        return args -> System.out.println("Import started");
    }
}
```

### 6.2. Package is outside component scan

Suppose the main class is:

```java
package com.example.shop;

@SpringBootApplication
public class ShopApplication {
}
```

By default, component scanning usually starts from this configuration class's package and its subpackages.

If the runner is located in:

```text
com.other.startup.ImportRunner
```

it may fall outside the scan boundary.

Solutions:

- Place the runner under the application's root package.
- Or declare component scanning intentionally.
- Or import the configuration containing the runner bean.

Example:

```java
@SpringBootApplication(
        scanBasePackages = {
                "com.example.shop",
                "com.other.startup"
        }
)
public class ShopApplication {
}
```

Do not broaden component scanning over wider packages than necessary if it could cause unintended beans to register.

### 6.3. Bean excluded by profile or condition

Example:

```java
@Component
@Profile("maintenance")
public class MaintenanceRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        // ...
    }
}
```

If the `maintenance` profile is not active, the bean is not registered.

Similarly with `@ConditionalOnProperty`:

```java
@Component
@ConditionalOnProperty(
        prefix = "app.import",
        name = "enabled",
        havingValue = "true"
)
public class ImportRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        // ...
    }
}
```

If the property is absent or not `true` under the configured condition, the runner does not appear in the context.

Check active profiles and effective property values in the actual running environment.

### 6.4. Context did not follow the SpringApplication startup path

`ApplicationRunner` and `CommandLineRunner` are invoked by `SpringApplication`'s startup orchestration.

If you manually instantiate a context and call `refresh()`, do not assume Spring automatically runs full Boot runner orchestration like `SpringApplication.run(...)`.

In a normal Spring Boot application, the entry point should call:

```java
SpringApplication.run(ShopApplication.class, args);
```

### 6.5. Startup failed before the runner phase

If a bean constructor, configuration properties binding, or context refresh fails, Spring Boot never reaches the runner invocation phase.

Look for the first error in the cause chain, for example:

```text
ApplicationContextException
BeanCreationException
UnsatisfiedDependencyException
ConfigurationPropertiesBindException
```

Do not modify the runner before fixing the error preventing context refresh from succeeding.

### 6.6. Another runner threw an exception

If an earlier runner throws an exception, startup can abort and subsequent runners are not invoked.

Example:

```java
@Bean
@Order(1)
CommandLineRunner firstRunner() {
    return args -> {
        throw new IllegalStateException("Initialization failed");
    };
}

@Bean
@Order(2)
CommandLineRunner secondRunner() {
    return args -> System.out.println("This may never run");
}
```

If the second runner is missing from the logs, check preceding runners and startup failures. Do not catch and ignore every exception just to make startup look successful; identify which tasks are truly mandatory.

### 6.7. Runner ran yet its logs are not visible

Possible reasons:

- Logger level is disabled.
- Output is routed to another file/container collector.
- Logs are filtered.
- The runner ran in another process/replica.
- You are looking at the wrong profile or instance.
- The method ran, yet no log existed on that code branch.

Place a breakpoint or log at the start of the method, use an appropriate logger, and verify process identity. Do not conclude a method did not run solely because a log line is missing.

## 7. Runner ordering and runners executing too early

When multiple runners exist, Spring Boot sorts them by order.

Example:

```java
@Component
@Order(10)
public class DatabaseCheckRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Database check");
    }
}
```

```java
@Component
@Order(20)
public class CacheWarmupRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("Cache warmup");
    }
}
```

Lower order runs first. Both `ApplicationRunner` and `CommandLineRunner` participate together in startup runner ordering.

### 7.1. Why does a runner see unready data?

A runner may be running ahead of another runner responsible for preparing data.

Example:

```text
Runner A: loads configuration data from the database
Runner B: warms cache using that data
```

If B runs before A, the cache may be empty or missing entries.

How to handle:

- Assign intentional ordering when two tasks are genuinely independent runner lifecycle steps.
- Better yet, model the dependency explicitly in a service/workflow and call the prerequisite step directly.
- Do not rely on accidental bean discovery order.

### 7.2. Tied order is not a stable contract

If multiple runners share the same order or declare no order, do not rely on whatever specific sequence the framework happens to pick. Configure explicit order if sequencing is required, or group dependent steps into one orchestration service.

### 7.3. Runners are not a dependency graph

`@Order` controls callback sequencing; it does not fully express task dependencies, retries, rollbacks, or distributed workflows.

If one task needs the output of another, make the dependency explicit in code rather than scattering numeric order annotations.

## 8. ApplicationStartedEvent and ApplicationReadyEvent

These two events are frequently confused.

### 8.1. ApplicationStartedEvent

This event is published after the ApplicationContext has refreshed successfully and before startup runners are called.

Example:

```java
@Component
public class StartedListener {

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("Context refreshed; runners are next");
    }
}
```

This is a useful point to observe that the application passed context refresh. If you need to wait for runners, this event is too early.

### 8.2. ApplicationReadyEvent

This event is published after startup runners complete.

```java
@Component
public class ReadyListener {

    private static final Logger log =
            LoggerFactory.getLogger(ReadyListener.class);

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        log.info("Application startup work completed");
    }
}
```

If a task needs all startup runners to finish, this is usually the more appropriate milestone.

### 8.3. Ready event is not a per-traffic callback

`ApplicationReadyEvent` is typically published once per corresponding SpringApplication startup. It is not published per request or each time a controller is called.

If you need periodic work, use a scheduler; if you need to react to business events, publish a dedicated business event.

### 8.4. Why is ApplicationReadyEvent missing?

Common causes:

- Context refresh has not succeeded.
- A startup runner threw an exception.
- Listener bean is not registered.
- Listener was registered too late relative to the event.
- You are listening to events from the wrong context/process.
- The application has not reached ready because a startup task is blocked.
- Listener logs are filtered or running on another instance.

Check runner failures and startup logs before concluding the event listener is broken.

## 9. Spring Application events and Context events

Spring has many kinds of events. Not every event shares the same lifecycle or fires at the same moment.

### 9.1. Spring Boot application events

Events such as:

- `ApplicationStartingEvent`.
- `ApplicationEnvironmentPreparedEvent`.
- `ApplicationContextInitializedEvent`.
- `ApplicationPreparedEvent`.
- `ApplicationStartedEvent`.
- `ApplicationReadyEvent`.
- `ApplicationFailedEvent`.

are published by `SpringApplication` during bootstrap.

### 9.2. Spring context events

Events such as:

- `ContextRefreshedEvent`.
- `ContextStartedEvent`.
- `ContextStoppedEvent`.
- `ContextClosedEvent`.

are tied to the lifecycle of `ApplicationContext`.

### 9.3. Do not pick an event merely because its name sounds similar

For example:

- `ContextRefreshedEvent` means a context finished refreshing.
- `ApplicationStartedEvent` means the Spring Boot startup sequence reached that milestone.
- `ApplicationReadyEvent` means startup runners have completed.

Using `ContextRefreshedEvent` as a substitute for "all runners have finished" can execute work too early.

## 10. @EventListener not called: what to check?

Example:

```java
@Component
public class OrderEventListener {

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Received " + event.orderId());
    }
}
```

If the method does not run, check each condition.

### 10.1. Is the listener a Spring bean?

The class must be component scanned, imported, or registered through an appropriate mechanism.

Wrong if the class is only instantiated manually:

```java
OrderEventListener listener = new OrderEventListener();
```

This object is not automatically registered with Spring's event infrastructure.

Right:

```java
@Component
public class OrderEventListener {
    // ...
}
```

or register the listener/configuration through the corresponding Spring mechanism.

### 10.2. Was the event actually published?

A listener only reacts when an event is published.

```java
@Component
public class OrderService {

    private final ApplicationEventPublisher publisher;

    public OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void create(String orderId) {
        // Save order or perform business logic.
        publisher.publishEvent(
                new OrderCreatedEvent(orderId)
        );
    }
}
```

Event type:

```java
public record OrderCreatedEvent(String orderId) {
}
```

If the code branch containing `publishEvent` does not execute, the listener has nothing to receive.

Place breakpoints right before the publish call and inside the listener to verify both sides.

### 10.3. Listener listening for the wrong event type

Suppose the publisher emits:

```java
publisher.publishEvent(new OrderCreatedEvent(orderId));
```

yet the listener accepts:

```java
@EventListener
public void onEvent(PaymentCompletedEvent event) {
    // ...
}
```

The two event types differ; this method will not be called for `OrderCreatedEvent`.

Check package, class, generic event type, and the actual object type published.

### 10.4. Listener registered after the event was already published

Spring's event multicaster is not a message queue that stores history and replays past events to new listeners.

If an event was published before the listener was registered, a listener registered later does not automatically receive old events.

This is a common issue with very early startup events. Bean listeners in the ApplicationContext cannot inherently receive every `SpringApplication` event emitted before the context/listener infrastructure is ready.

### 10.5. Event published in a different context

In applications with parent/child contexts, understand which context publishes the event and where the listener is registered.

Normally events from a child context propagate upward to the parent per hierarchy rules; events from the parent are not automatically broadcast downward to every child context.

If an application has a management context or multiple contexts, log the event's identity/context source and check listener placement.

### 10.6. @EventListener condition filters out the event

Example:

```java
@EventListener(condition = "#event.priority > 5")
public void onHighPriority(OrderCreatedEvent event) {
    // Only processed when condition is true.
}
```

If the SpEL condition returns false, the method does not run even though the event was published and the listener is registered.

Inspect the condition and event data. While debugging, temporarily remove the condition or log predicate values appropriately.

### 10.7. Incompatible method signature

`@EventListener` typically uses a method with one event parameter or an annotation configured with specific event classes.

Simple example:

```java
@EventListener
public void onOrderCreated(OrderCreatedEvent event) {
}
```

If the method uses the wrong type or a signature that the event infrastructure cannot interpret, listener registration may fail or fail to match events as expected.

## 11. Listeners for very early events must register early

A bean-based listener:

```java
@Component
public class EarlyStartupListener {

    @EventListener
    public void onStarting(ApplicationStartingEvent event) {
        // ...
    }
}
```

is not a reliable choice for events published before the ApplicationContext and listener bean infrastructure exist.

For very early SpringApplication events, register the listener directly on `SpringApplication` before calling `run`.

Example:

```java
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ShopConfiguration.class);

        application.addListeners(
                (ApplicationListener<ApplicationStartingEvent>) event ->
                        System.out.println("SpringApplication is starting")
        );

        application.run(args);
    }
}
```

The listener is registered before bootstrap begins, so it can receive events earlier than a listener existing solely as a bean in the context.

### 11.1. Using an explicit ApplicationListener class

```java
public class StartupListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(
            ApplicationStartingEvent event
    ) {
        System.out.println("Starting event received");
    }
}
```

Registration:

```java
application.addListeners(new StartupListener());
```

This approach fits when receiving events at a very early stage is needed.

### 11.2. Do not put dependency injection into early listeners

An early listener can run before the ApplicationContext is created or before dependency injection is ready. Therefore, it must not assume normal service/repository injection is available.

Keep early listeners simple, using only data available from the event and components genuinely ready at that bootstrap phase.

## 12. @TransactionalEventListener does not run

This is a very common reason why an event listener appears to work in one environment yet stays silent in another.

Example:

```java
@Component
public class PurchaseListener {

    @TransactionalEventListener
    public void afterPurchaseCreated(PurchaseCreatedEvent event) {
        // ...
    }
}
```

By default, `@TransactionalEventListener` is bound to transaction phase `AFTER_COMMIT`.

It is only triggered via transaction synchronization when the event is published inside an appropriate active transaction.

### 12.1. Publishing an event outside a transaction

Example:

```java
@Service
public class PurchaseService {

    private final ApplicationEventPublisher publisher;

    public PurchaseService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void createPurchase(String id) {
        publisher.publishEvent(new PurchaseCreatedEvent(id));
    }
}
```

If this method does not run inside a transaction, the default `@TransactionalEventListener` may not be invoked.

This differs from a regular `@EventListener`, which handles events upon publication without requiring a transaction.

### 12.2. Setting an explicit transaction boundary

```java
@Service
public class PurchaseService {

    private final PurchaseRepository repository;
    private final ApplicationEventPublisher publisher;

    public PurchaseService(
            PurchaseRepository repository,
            ApplicationEventPublisher publisher
    ) {
        this.repository = repository;
        this.publisher = publisher;
    }

    @Transactional
    public void createPurchase(String id) {
        repository.save(new Purchase(id));

        publisher.publishEvent(
                new PurchaseCreatedEvent(id)
        );
    }
}
```

When the event is published inside an active transaction, the `AFTER_COMMIT` listener can run after the transaction commits successfully.

### 12.3. What if the transaction rolls back?

If the transaction rolls back, an `AFTER_COMMIT` listener is not invoked as it would be on a successful commit.

You can pick another phase:

- `BEFORE_COMMIT`.
- `AFTER_COMMIT` (default).
- `AFTER_ROLLBACK`.
- `AFTER_COMPLETION`.

Example:

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_ROLLBACK
)
public void onPurchaseRollback(PurchaseCreatedEvent event) {
    // Handle when transaction rolls back.
}
```

Pick the phase based on business semantics. Do not switch every listener to `fallbackExecution=true` just to "make it run."

### 12.4. fallbackExecution

If a listener needs to process events even without a transaction, you can configure:

```java
@TransactionalEventListener(fallbackExecution = true)
public void onPurchase(PurchaseCreatedEvent event) {
    // ...
}
```

When no transaction exists, the listener can execute immediately under fallback behavior.

However, this changes semantics: the same event could be processed either inside or outside a transaction. Enable it only when that behavior genuinely matches requirements.

### 12.5. Transaction manager and proxy boundaries

If you add `@Transactional` yet the method is called via self-invocation or the bean bypasses the transactional proxy, no transaction may start as expected.

Then `@TransactionalEventListener` also has no transaction synchronization to wait on.

Check:

- Is the bean managed by Spring?
- Is transaction management enabled/configured?
- Is there an appropriate transaction manager?
- Does the call go through the proxy?
- Did an exception cause the transaction to roll back?
- Was the event published before or after the transaction actually started?

## 13. Synchronous and asynchronous @EventListener

By default, Spring event listeners are typically invoked synchronously on the publishing thread under the current event multicaster.

Example:

```java
publisher.publishEvent(new OrderCreatedEvent(orderId));

log.info("Event published");
```

With a synchronous listener:

```java
@EventListener
public void onOrderCreated(OrderCreatedEvent event) {
    log.info("Listener handling orderId={}", event.orderId());
}
```

The listener normally finishes before `publishEvent` returns.

### 13.1. Why do listener logs appear late?

If a listener uses `@Async`:

```java
@EnableAsync
@Configuration
class AsyncConfiguration {
}
```

```java
@Component
public class AsyncOrderListener {

    @Async
    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        // Background processing.
    }
}
```

The listener call is handed off to an executor according to async configuration. The publisher does not necessarily wait for the listener to finish.

Logs:

```text
Event published
Async listener started
Async listener completed
```

may appear in a different order or timing than expected, especially with multiple tasks or executor threads.

### 13.2. @Async must be enabled and go through a proper proxy

In standard Spring setups, `@EnableAsync` or corresponding async infrastructure is required.

`@Async` relies on proxies in common mode. Calling an async method from the same object (`this`) can bypass the proxy and run the method synchronously.

Do not assume simply adding `@Async` makes every method in the class run in the background automatically.

### 13.3. Exceptions in async listeners do not propagate back to the publisher

For asynchronously running listeners, exceptions thrown on a worker thread are generally not rethrown onto the publishing thread.

You need to:

- Log exceptions at the async boundary.
- Configure `AsyncUncaughtExceptionHandler` for void methods when appropriate.
- Use `Future`/`CompletableFuture` if the caller needs to observe the outcome.
- Have a retry/dead-letter strategy if the event is critical and requires durability.

### 13.4. Completion order is not guaranteed by @Order

`@Order` can sequence listener invocations in a synchronous event multicaster. Once listeners dispatch to an executor, **start or completion** order can differ due to concurrency.

If listener B must run after listener A completes, orchestrate explicitly via a service/workflow or chain async results instead of relying solely on two `@Order` values.

## 14. Event published yet listener processes wrong data

An event should contain the data the listener needs, or an identifier sufficient for the listener to reload valid data.

Example:

```java
public record OrderCreatedEvent(
        String orderId,
        Instant occurredAt
) {
}
```

Publisher:

```java
publisher.publishEvent(
        new OrderCreatedEvent(
                orderId,
                Instant.now()
        )
);
```

Listener:

```java
@EventListener
public void onOrderCreated(OrderCreatedEvent event) {
    log.info(
            "Order event: orderId={} occurredAt={}",
            event.orderId(),
            event.occurredAt()
    );
}
```

### 14.1. Do not publish a mutable object and mutate it immediately afterward

If an event carries a mutable object and the publisher modifies it after publishing, an async listener may read state different from what existed when the event was emitted.

Prefer immutable event payloads such as records or immutable objects, or pass only an identifier and load data under a consistent rule.

### 14.2. Internal events are not a message broker

Spring application events by default are an in-process communication mechanism. They do not automatically guarantee:

- Persisting events across restarts.
- Replaying events when new listeners appear.
- Exactly-once delivery.
- Durable retries.
- Communication across multiple application instances.

If an event represents a business fact requiring guaranteed delivery across services/processes, look into a message broker and transactional outbox instead of treating `ApplicationEventPublisher` as a durable message queue.

## 15. Context hierarchy and listeners receiving events multiple times

Some applications have parent/child ApplicationContexts, such as a web context and a root context or a separate management context.

Events published from a child context can propagate up to the parent; thus listeners placed in parent and child can sometimes both receive the same event depending on registration.

This can create the impression that a listener ran twice.

### 15.1. Inspect the event source

```java
@EventListener
public void onContextRefresh(ContextRefreshedEvent event) {
    log.info(
            "Refreshed context id={}",
            event.getApplicationContext().getId()
    );
}
```

Log the context ID to distinguish which context emitted the event.

### 15.2. ContextRefreshedEvent can occur multiple times

`ContextRefreshedEvent` signifies that a context refreshed. An application can have multiple contexts or complex refresh lifecycles.

Do not assume it is "a single JVM-wide event."

If you only need a single Boot application startup event, consider `ApplicationReadyEvent` or a narrower lifecycle hook, and filter by the right context when needed.

### 15.3. Avoid duplicate side effects

If a listener initializes data or sends notifications, repeated events can create duplicate side effects.

Design idempotency or check context identity/event identity when repetition is not allowed. For critical startup tasks, define the scope of "once" clearly: per bean, per context, per process, or cluster-wide.

## 16. SmartLifecycle: managing start/stop by lifecycle

`SmartLifecycle` suits components whose start and stop must be managed by the container, such as consumers or background components with a clear lifecycle.

Example:

```java
@Component
public class MessageConsumerLifecycle implements SmartLifecycle {

    private volatile boolean running;

    @Override
    public void start() {
        // Start consumer.
        running = true;
    }

    @Override
    public void stop() {
        // Stop consumer.
        running = false;
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }
}
```

In real applications, start/stop must coordinate with consumer clients, in-flight messages, and timeouts.

### 16.1. Phase controls ordering

`SmartLifecycle` supports `getPhase()`. Lifecycle components are started/stopped according to container phase ordering; during shutdown, stop order is typically the reverse of start order to honor dependencies.

Example:

```java
@Override
public int getPhase() {
    return 100;
}
```

Do not pick phase values arbitrarily. If component A requires component B to be running, assign phases so B starts earlier and stops later according to the dependency relationship.

### 16.2. isAutoStartup

If `isAutoStartup()` returns false, the container does not start the component automatically under default startup lifecycle. This is a direct reason why `start()` is never called.

Check this value before suspecting the Spring lifecycle processor.

### 16.3. Stop callback with timeout

`SmartLifecycle` supports an asynchronous stop callback:

```java
@Override
public void stop(Runnable callback) {
    try {
        // Request consumer stop and await required tasks.
    } finally {
        running = false;
        callback.run();
    }
}
```

The callback must be invoked once stopping finishes per the lifecycle contract. Forgetting to call it can cause shutdown to wait until timeout.

## 17. @PreDestroy and shutdown callbacks not running

`@PreDestroy` is invoked when Spring destroys beans during a normal context close.

Example:

```java
@Component
public class ResourceHolder {

    @PreDestroy
    void close() {
        System.out.println("ResourceHolder is closing");
    }
}
```

### 17.1. Cases where it may not run

- Process killed forcefully, e.g., `SIGKILL`.
- JVM crash or machine power loss.
- Context not closed through normal lifecycle.
- Bean was never created.
- Bean is not managed by Spring.
- Container terminated before the shutdown phase finished.
- Callback threw an exception or logs were lost during shutdown.
- Test context stopped via a different lifecycle path than a production process.

No Java callback is guaranteed to run when a process is terminated abruptly.

### 17.2. SpringApplication shutdown hook

SpringApplication normally registers a shutdown hook to close the context on normal JVM shutdown.

It can be disabled via configuration, though doing so is unwise if the application relies on Spring lifecycle to close resources.

Example:

```java
SpringApplication application =
        new SpringApplication(ShopApplication.class);

application.setRegisterShutdownHook(false);
```

If the hook is disabled, the application or runtime host must assume responsibility for closing the context another way.

### 17.3. Do not place critical non-losable work in @PreDestroy

If you must guarantee a business event is processed, do not rely solely on `@PreDestroy` to send a final message. Shutdown can time out or be forced.

Persist state/commands beforehand, use a broker/outbox, and design graceful shutdown to reduce the risk of losing work.

## 18. @Scheduled is not a startup runner

A method:

```java
@Scheduled(fixedDelay = 5000)
public void refreshCache() {
    // ...
}
```

is a scheduled task, not a runner.

For scheduling to work, appropriate infrastructure must be enabled, typically via:

```java
@EnableScheduling
@Configuration
class SchedulingConfiguration {
}
```

### 18.1. Why does a scheduled method not run immediately at startup?

`fixedDelay` normally measures the delay after the previous execution finishes. If you need to run once right after startup and periodically thereafter, use an appropriate `initialDelay` or call a service from a startup hook.

Example:

```java
@Scheduled(
        initialDelay = 0,
        fixedDelay = 5000
)
public void refreshCache() {
    // ...
}
```

Define concurrency and scheduler lifecycle requirements carefully. Do not use a scheduled task as an arbitrary substitute for `ApplicationRunner`.

### 18.2. Multiple replicas running the same scheduled method

If the application runs multiple replicas, each process has its own scheduler and can run the same job simultaneously.

If a task must run only once cluster-wide, use distributed coordination/locking or a dedicated scheduler; `@Scheduled` by itself does not guarantee singleton execution across replicas.

## 19. How listeners run before/after transactions

Choosing the right event listener depends on whether you need to react before or after commit.

| Mechanism | Timing |
|---|---|
| `@EventListener` | When the event is published, typically immediately and synchronously per multicaster |
| `@TransactionalEventListener(BEFORE_COMMIT)` | Before transaction commit |
| `@TransactionalEventListener(AFTER_COMMIT)` | After successful commit |
| `@TransactionalEventListener(AFTER_ROLLBACK)` | After rollback |
| `@TransactionalEventListener(AFTER_COMPLETION)` | After transaction completion whether commit or rollback |

### 19.1. Why sending email inside @EventListener can be wrong

Suppose:

```java
@Transactional
public void createOrder(...) {
    repository.save(order);
    publisher.publishEvent(new OrderCreatedEvent(order.getId()));
}
```

Regular listener:

```java
@EventListener
public void sendEmail(OrderCreatedEvent event) {
    mailService.sendConfirmation(event.orderId());
}
```

With a synchronous listener, the email may be sent **before the transaction commits**. If the transaction subsequently rolls back, the customer still receives a confirmation email for a nonexistent order.

Using `@TransactionalEventListener(AFTER_COMMIT)` can be more appropriate when the requirement is to send only after data commits successfully.

### 19.2. After commit does not mean durable delivery

Even when a listener runs after commit, the process can crash between commit and sending the email. Internal events are not persisted automatically.

If losing emails/notifications is unacceptable, use a transactional outbox or a suitable durable messaging mechanism.

### 19.3. Database operations after commit

In `AFTER_COMMIT`, the original transaction has already completed. If the listener needs to write additional data using a new transaction, design an explicit transaction boundary (for example, a service method with suitable propagation) rather than assuming the original transaction is still open.

## 20. Event listeners returning a new event

`@EventListener` can return a new event/payload object for Spring to publish onward in certain synchronous listener scenarios.

Example:

```java
@EventListener
public OrderAuditEvent onOrderCreated(OrderCreatedEvent event) {
    return new OrderAuditEvent(event.orderId());
}
```

Another listener can receive `OrderAuditEvent`.

However, this pattern does not suit asynchronous listeners marked `@Async`, because returned values are not published via the synchronous mechanism described above. When you need an async chain, use `ApplicationEventPublisher` explicitly or an appropriate workflow.

### 20.1. Avoid hard-to-trace event chains

If event A produces B, B produces C, and C triggers side effects, keep event names, correlation IDs, and ownership clear. An event chain without observability easily makes debugging "which listener ran first?" difficult.

For long business workflows, consider an orchestrator/service or a message broker with proper tracing and retries.

## 21. Tests making callbacks/runners appear not to run

A very common cause in test suites is the **Spring TestContext cache**.

Spring can reuse the same ApplicationContext across multiple test classes if their context configuration is equivalent.

Example:

```java
@SpringBootTest
class FirstIntegrationTest {

    @Test
    void testOne() {
    }
}
```

```java
@SpringBootTest
class SecondIntegrationTest {

    @Test
    void testTwo() {
    }
}
```

If both tests share the same cache key, the context may be created once and reused.

Because runners execute during SpringApplication/context startup, they will not necessarily re-run for every test method or every test class.

### 21.1. Do not expect runners to run before every @Test

Runners are not JUnit lifecycle callbacks.

If you need setup before each test:

```java
@BeforeEach
void setUp() {
    // Prepare data for this test.
}
```

If you need setup once for the class:

```java
@BeforeAll
static void beforeAll() {
    // Class-level setup.
}
```

If you need a Spring bean fixture, use test configuration or an appropriate test lifecycle. Do not use `ApplicationRunner` as a per-test hook.

### 21.2. @DirtiesContext

`@DirtiesContext` instructs Spring Test to mark the context dirty and evict it from the cache so a fresh context can be created next time.

Example:

```java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ContextRecreationTest {
}
```

When the context is recreated, startup lifecycle and runners can execute again.

However, do not add `@DirtiesContext` just to force runners to appear in logs. It slows down the test suite and can mask shared-state problems.

### 21.3. Test context does not necessarily run SpringApplication.run identically to production

Spring TestContext has its own bootstrapper to create contexts suitable for testing. While much of the lifecycle and Boot infrastructure still operates, do not assume every startup event/runner repeats per test the same way as launching a fresh process.

If you need to verify a specific event/lifecycle, write targeted tests and control context creation deliberately.

## 22. Testing runners properly

You can test runner logic by calling `run` directly without booting the entire application.

Example:

```java
@Component
public class ImportRunner implements ApplicationRunner {

    private final ImportService importService;

    public ImportRunner(ImportService importService) {
        this.importService = importService;
    }

    @Override
    public void run(ApplicationArguments args) {
        importService.importPending();
    }
}
```

Unit test:

```java
@ExtendWith(MockitoExtension.class)
class ImportRunnerTest {

    @Mock
    ImportService importService;

    @InjectMocks
    ImportRunner runner;

    @Test
    void invokesImportService() throws Exception {
        runner.run(
                new DefaultApplicationArguments(
                        "--mode=initial"
                )
        );

        verify(importService).importPending();
    }
}
```

This test verifies the runner's behavior when called. It does **not** prove Spring Boot automatically registers or invokes the runner during startup.

### 22.1. Integration test verifying runner registration

If you need to verify Spring detects the runner bean, you can load a context with test configuration and use an appropriate spy/recording bean to verify invocation.

Conceptual example:

```java
@SpringBootTest
class RunnerStartupIntegrationTest {

    @MockitoSpyBean
    ImportRunner runner;

    @Test
    void runnerBeanIsCreatedAndStartupInvoked() {
        verify(runner).run(any(ApplicationArguments.class));
    }
}
```

The `@MockitoSpyBean` API belongs to newer Spring Framework versions with bean override support; older projects can use the spy/mock bean mechanism corresponding to their Boot version. Be mindful of context caching and the fact that runners are called before the test method starts.

### 22.2. Recording event listener

To test published events:

```java
@Component
public class RecordingOrderListener {

    private final List<OrderCreatedEvent> received =
            new CopyOnWriteArrayList<>();

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        received.add(event);
    }

    public List<OrderCreatedEvent> received() {
        return List.copyOf(received);
    }
}
```

A test can publish an event via `ApplicationEventPublisher` and assert the listener received the expected payload.

If the listener is async, wait using proper synchronization (Awaitility, latch, or future); do not use `Thread.sleep` arbitrarily to guess timing.

## 23. Testing @TransactionalEventListener

To test an after-commit listener, the test must create a real transaction and observe the phase.

Points to distinguish:

- Whether the test method itself is wrapped in `@Transactional`.
- Whether the service method has its own transaction.
- Which transaction the event is published in.
- Whether the test transaction commits or rolls back by default.
- Whether the listener phase is AFTER_COMMIT or AFTER_ROLLBACK.

A `@Transactional` test method that rolls back by default after the test can prevent an `AFTER_COMMIT` listener from running because no successful commit occurred.

### 23.1. Why does the test pass green yet the listener does not run?

Example:

```java
@SpringBootTest
@Transactional
class PurchaseEventTest {

    @Test
    void publishesPurchaseEvent() {
        purchaseService.createPurchase("P-1");
    }
}
```

If the test transaction still rolls back at the end of the method, the `AFTER_COMMIT` listener may not be triggered.

Decide clearly whether the test needs to verify commit behavior or only publication. In integration tests, you can explicitly commit the transaction or use suitable transaction test utilities while avoiding tests that depend on leftover database state.

### 23.2. Testing both positive and negative paths

- Successful commit: AFTER_COMMIT listener is called.
- Rollback: AFTER_COMMIT listener is not called.
- Rollback: AFTER_ROLLBACK listener is called if registered.
- Publish outside transaction: default transactional listener does not run when fallback is disabled.

These cases help catch wrong transaction phase selections.

## 24. ApplicationFailedEvent and startup exceptions

If startup fails, Spring Boot can publish `ApplicationFailedEvent` during failure handling.

Early-registered listener example:

```java
public class FailureListener
        implements ApplicationListener<ApplicationFailedEvent> {

    @Override
    public void onApplicationEvent(ApplicationFailedEvent event) {
        Throwable failure = event.getException();

        System.err.println(
                "Application startup failed: "
                        + failure.getClass().getName()
        );
    }
}
```

Register before startup:

```java
SpringApplication application =
        new SpringApplication(ShopApplication.class);

application.addListeners(new FailureListener());

application.run(args);
```

### 24.1. Context bean listeners may not exist when startup fails early

If an error happens before the ApplicationContext finishes, a listener registered only as a bean inside the context may not be ready to receive failure events.

If you need to observe very early startup failures, register the listener directly with SpringApplication.

### 24.2. Do not replace logging/exit codes with a failure listener

A failure listener is useful for collecting extra diagnostics. It must not swallow exceptions or cause the process to return a successful exit code when startup failed.

Preserve failure semantics so orchestrators/CI recognize that the application failed to start.

## 25. How ApplicationContextInitializer, BeanFactoryPostProcessor, and BeanPostProcessor differ from callbacks

These extension points are often confused with startup runners.

### 25.1. ApplicationContextInitializer

`ApplicationContextInitializer` is invoked while preparing the context before refresh.

Example:

```java
public class CustomContextInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(
            ConfigurableApplicationContext context
    ) {
        // Adjust Environment or context before refresh.
    }
}
```

Use it when you need to customize the context before beans are created. It is not a callback after the application is ready.

### 25.2. BeanFactoryPostProcessor

`BeanFactoryPostProcessor` operates on bean definitions before normal application beans are instantiated.

Example:

```java
@Component
public class DefinitionInspector
        implements BeanFactoryPostProcessor {

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory
    ) {
        // Inspect/modify bean definitions.
    }
}
```

Do not use it as a place to invoke business services because most application beans have not been created yet.

### 25.3. BeanPostProcessor

`BeanPostProcessor` intercepts individual beans before/after initialization. Spring uses many post-processors to handle annotations, dependencies, and proxies.

This is bean-level lifecycle infrastructure, not an event published for business workflows.

### 25.4. Choosing an extension point by timing

| Need | Suitable extension point |
|---|---|
| Modify Environment/context before refresh | ApplicationContextInitializer or EnvironmentPostProcessor depending on phase |
| Modify bean definitions | BeanFactoryPostProcessor |
| Intercept a bean during lifecycle | BeanPostProcessor |
| Initialize a single bean's state | `@PostConstruct`/init method |
| After regular singletons are initialized | SmartInitializingSingleton |
| After context refresh | ContextRefreshedEvent |
| After context refresh yet before runners | ApplicationStartedEvent |
| After runners | ApplicationReadyEvent |
| Startup work with arguments | ApplicationRunner/CommandLineRunner |
| Start/stop component | SmartLifecycle |
| Periodic execution | `@Scheduled` |

## 26. Complete example: startup runner and ready listener

The example below illustrates the expected log sequence.

### 26.1. Application class

```java
@SpringBootApplication
public class LifecycleApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                LifecycleApplication.class,
                args
        );
    }
}
```

### 26.2. Bean initialization

```java
@Component
public class InitializationLogger {

    private static final Logger log =
            LoggerFactory.getLogger(InitializationLogger.class);

    @PostConstruct
    void initialize() {
        log.info("1. Bean initialization callback");
    }
}
```

### 26.3. Application started listener

```java
@Component
public class StartedEventLogger {

    private static final Logger log =
            LoggerFactory.getLogger(StartedEventLogger.class);

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        log.info("2. ApplicationStartedEvent");
    }
}
```

### 26.4. Startup runner

```java
@Component
public class InitialCheckRunner implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(InitialCheckRunner.class);

    @Override
    public void run(ApplicationArguments args) {
        log.info("3. ApplicationRunner executing");
    }
}
```

### 26.5. Ready listener

```java
@Component
public class ReadyEventLogger {

    private static final Logger log =
            LoggerFactory.getLogger(ReadyEventLogger.class);

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        log.info("4. ApplicationReadyEvent");
    }
}
```

Illustrative log:

```text
1. Bean initialization callback
2. ApplicationStartedEvent
3. ApplicationRunner executing
4. ApplicationReadyEvent
```

Ordering among multiple bean initialization callbacks should not be treated as a dependency contract without explicit ordering/lifecycle design. The example above merely illustrates the main stages.

### 26.6. Adding a failing runner

If a runner throws an exception:

```java
@Override
public void run(ApplicationArguments args) {
    throw new IllegalStateException("Startup validation failed");
}
```

then `ApplicationReadyEvent` may not be published because startup did not complete successfully.

This is a useful experiment for understanding why the ready listener fails to appear even though the started event appeared.

## 27. Diagnosing "listener runs twice"

If a listener runs twice, do not rush to add a static variable to block the second run. Find the duplicate emission source.

Common causes:

1. The same listener bean is registered in two contexts.
2. Both parent and child contexts have matching listeners.
3. The publisher calls `publishEvent` twice.
4. Two components both emit an event for one action.
5. Retry logic re-publishes the event.
6. A consumer/message handler receives duplicate delivery from an external system.
7. Test context is recreated or tests run multiple times.
8. A listener returns/emits a new event of the same type, creating an unintended feedback loop.

### 27.1. Log event identity and source

```java
@EventListener
public void onOrderCreated(OrderCreatedEvent event) {
    log.info(
            "Received event: orderId={} source={}",
            event.orderId(),
            event.getClass().getName()
    );
}
```

For SpringApplication/context events, also log the context ID or appropriate source object. For business events, consider a unique event ID and correlation ID.

### 27.2. Idempotency is better than a static boolean

A static `alreadyHandled` variable may stop an event from running twice inside one process, yet fails to handle:

- Multiple replicas.
- Process restarts.
- Concurrent deliveries.
- Legitimate event retries.
- Context recreation in tests.

If an event represents a business operation that must happen once semantically, use an idempotency key with appropriate persistence/locking.

## 28. Diagnosing callbacks running too early or too late

### 28.1. Running too early

Symptoms:

- Another bean is not initialized yet.
- Database migration has not completed.
- Cache warmup has not run.
- A runner depends on data produced by another runner.
- A ready listener needs to wait for runners yet was placed on ApplicationStartedEvent.

How to resolve:

1. Identify which dependency is not ready yet.
2. Pick the right lifecycle phase.
3. Use service orchestration instead of relying on accidental order.
4. If needed after runners, move to ApplicationReadyEvent.
5. If needed after transaction commit, use the appropriate transactional event listener phase.

### 28.2. Running too late

Symptoms:

- A task needed to finish before traffic arrives yet only begins in a scheduled task after startup.
- A listener is registered after the event already published.
- An async listener runs on an executor after the publisher continued.
- A task is blocked by another task on the same executor.

How to resolve:

1. Verify publish timing and listener registration timing.
2. Check whether the listener uses `@Async` or an async multicaster executor.
3. Check executor queue, thread count, and saturation.
4. Choose a runner or lifecycle callback if work must finish before readiness.
5. Do not use async if the caller needs to wait synchronously for the outcome.

### 28.3. No timing guarantee from @Order alone

`@Order` sorts certain callbacks/listeners within their corresponding mechanism. It does not guarantee one async listener finishes before another, does not build a dependency graph, and does not guarantee execution timing.

If the requirement is "B runs only after A completes," call B after A in the same workflow or chain outcomes explicitly.

## 29. A systematic debugging workflow

When a callback, runner, or listener does not run as expected, follow this sequence:

### Step 1 — Write down the expected milestone

For example: "I need a callback after all runners finish" differs from "after context refresh."

### Step 2 — Identify the mechanism in use

`@PostConstruct`, `ApplicationRunner`, `@EventListener`, `@TransactionalEventListener`, `@Async`, `@Scheduled`, or `SmartLifecycle`?

### Step 3 — Confirm the bean/listener is registered

Check component scan, `@Bean`, imports, profiles, and conditional annotations.

### Step 4 — Confirm the trigger source

Runner: did SpringApplication reach the runner invocation phase?

Listener: did the publisher emit the exact event type?

Transactional listener: is there an active transaction matching the phase?

Scheduled task: is scheduling enabled and has the trigger fired?

### Step 5 — Confirm lifecycle ordering

Cross-check against the timeline: bean init, context refresh, started, runners, ready, shutdown.

### Step 6 — Confirm sync/async behavior

Was the listener dispatched to an executor? Is it queued or throwing on a worker thread?

### Step 7 — Check context and process identity

Are you inspecting the right ApplicationContext, JVM, container, pod, and replica?

### Step 8 — Read startup failure causes

If ready/runners are never reached, inspect context refresh errors and preceding runners.

### Step 9 — Check test caching

A runner may have run when the context was created for an earlier test and not re-run due to caching.

### Step 10 — Add temporary observability

Use logs at the start of callbacks, breakpoints, event types, context IDs, thread names, and correlation IDs. Remove overly verbose diagnostic logs once the root cause is found.

## 30. Common errors table

| Symptom | Possible cause | How to check/fix |
|---|---|---|
| `@PostConstruct` does not run | Bean not created, not a Spring bean, or lazy bean | Check bean registration and instantiation timing |
| `@PostConstruct` runs before other services are ready | Using bean init for whole-context work | Switch to runner/ready event or orchestration |
| `CommandLineRunner` does not run | Bean not registered or context failed to refresh | Check scan, profile, conditions, and startup exceptions |
| Second runner does not run | Previous runner threw an exception | Check ordering and the first exception |
| `ApplicationReadyEvent` does not appear | Runner failed or startup not finished | Check ApplicationFailedEvent and runner logs |
| `ApplicationStartedEvent` appears yet runner has not run | Normal order | Runners execute after started event |
| `@EventListener` misses event | Wrong event type, listener unregistered, event unpublished | Breakpoint publisher and listener |
| Listener misses early startup event | Bean listener registered too late | Register directly on SpringApplication |
| `@TransactionalEventListener` does not run | No active transaction or transaction rolled back | Check transaction boundary/phase |
| Listener runs immediately outside transaction | `fallbackExecution=true` | Verify fallback semantics |
| Listener runs late | `@Async` or executor queue | Inspect thread/executor |
| Listener runs twice | Parent/child context or duplicate publish | Log source/context/event ID |
| `@PreDestroy` does not run | Process killed forcefully or context never closed | Use graceful shutdown; do not rely on callback under SIGKILL |
| `SmartLifecycle.start` does not run | `isAutoStartup=false` or lifecycle not started | Check lifecycle processor and phase |
| `@Scheduled` does not run | Scheduling not enabled or trigger not due yet | Check `@EnableScheduling` and schedule config |
| Runner does not re-run in later test | Spring TestContext cache | Understand context reuse; use proper test lifecycle |
| Callback runs on another thread | Async executor or async multicaster | Log thread name and check propagation |
| Event handled yet data is unexpected | Mutable payload modified or event missing snapshot | Use immutable event payloads |
| Events lost on process restart | Application events are not durable | Use broker/outbox if durable delivery is needed |

## 31. Anti-patterns to avoid

### 31.1. Using @PostConstruct to run a complex workflow

Avoid:

```java
@PostConstruct
void initialize() {
    importAllFiles();
    callRemoteApi();
    warmEveryCache();
    sendStartupEmails();
}
```

Bean initialization should be fast and narrowly scoped. A large workflow inside it can prolong context refresh or fail in hard-to-diagnose ways.

Better: extract startup orchestration into a runner/service with clear logging, timeouts, retries, and readiness policy.

### 31.2. Swallowing exceptions in runners

Avoid:

```java
@Override
public void run(String... args) {
    try {
        validateStartupData();
    } catch (Exception ignored) {
        // Startup continues even though state may be invalid.
    }
}
```

If validation is mandatory, fail startup with clear information. If continuing in degraded mode is acceptable, expose degraded state and readiness deliberately.

### 31.3. Using internal events as a durable queue

Do not publish an application event and assume it will be processed after a process restart. Spring application events do not persist/replay by default.

Use a message broker or outbox for durable delivery requirements.

### 31.4. Using Thread.sleep to wait for listeners

Avoid:

```java
publisher.publishEvent(event);
Thread.sleep(2000);
assertThat(listener.completed()).isTrue();
```

This makes tests flaky, dependent on machine speed and executors.

Use a latch, future, Awaitility, or synchronization with an explicit timeout.

### 31.5. Running unbounded work inside a startup runner

A runner waiting indefinitely on a remote API can prevent the application from ever becoming ready.

Set clear timeouts, retry budgets, and failure policies. If work is not strictly required before serving traffic, move it to a background workflow after readiness.

### 31.6. Using static state to prevent duplicate callbacks

A static boolean can persist across multiple contexts in the same JVM and break test isolation. Across multiple processes, it does not synchronize between replicas.

Choose idempotency at the exact scope you need to guarantee.

## 32. Designing startup tasks intentionally

A startup task should answer:

- Must it finish before serving traffic?
- Is it safe to re-run on restart?
- Does it have a timeout?
- Does it retry? What is the max retry count?
- On failure, should startup fail or run degraded?
- Can it run on every replica or only one replica?
- Does it need a lock or leader election?
- Are progress and errors observable?
- Does it need persistence to resume?

### 32.1. Task classification

| Task category | Typically suitable implementation |
|---|---|
| Validate bean configuration | `@PostConstruct` or validation binding |
| Verify whole context readiness | Context/application lifecycle event |
| Mandatory task after context refresh | `ApplicationRunner`/`CommandLineRunner` |
| Task after all runners | `ApplicationReadyEvent` |
| Start/stop consumer | `SmartLifecycle` or integration lifecycle |
| React to internal business event | `@EventListener` |
| Execute only after commit | `@TransactionalEventListener(AFTER_COMMIT)` |
| Periodic task | `@Scheduled` or dedicated scheduler |
| Durable cross-process dispatch | Message broker/outbox |
| Cleanup when context closes | `@PreDestroy`/`DisposableBean`/`SmartLifecycle.stop` |

### 32.2. Should startup runners run on every replica?

If each instance needs to warm a local cache, running the runner on every replica may make sense.

If the runner seeds shared data, sends emails, runs migrations, or performs work meant to execute once cluster-wide, concurrent execution across replicas can cause duplicate side effects.

Distinguish "once per ApplicationContext" from "once system-wide."

### 32.3. Database migrations and startup order

Migration tools such as Flyway/Liquibase have their own lifecycles and auto-configurations. If a runner requires a migrated schema, rely on properly configured startup migration mechanisms and integration tests; do not add an arbitrary runner and assume it always runs after migrations solely by bean order.

When ordering is required, express proper dependencies or use supported service/initializer integrations.

## 33. Observability for callbacks and events

When debugging lifecycle issues, logs should carry details distinguishing process, context, and thread.

Example:

```java
log.info(
        "Lifecycle callback: phase={} contextId={} thread={}",
        "application-ready",
        context.getId(),
        Thread.currentThread().getName()
);
```

For business events:

```java
log.info(
        "Handling event: eventType={} eventId={} orderId={}",
        event.getClass().getSimpleName(),
        event.eventId(),
        event.orderId()
);
```

Fields such as event ID and order ID are useful in logs. Do not use UUIDs/order IDs as metric tags if they create high cardinality.

### 33.1. Measuring startup task duration

A runner can measure duration:

```java
long started = System.nanoTime();

try {
    warmupService.execute();
} finally {
    long elapsed = System.nanoTime() - started;
    log.info("Warmup completed in {} ms", elapsed / 1_000_000);
}
```

In applications with Micrometer, you can also use a Timer with low-cardinality tags like `task=cache-warmup`.

### 33.2. Do not log merely "listener called"

A log entry:

```text
Listener called
```

does not identify which listener, which event, or which context.

Better:

```java
log.info(
        "Received OrderCreatedEvent: orderId={} eventId={}",
        event.orderId(),
        event.eventId()
);
```

For startup callbacks, log the phase name and start/end timestamps if the task can take significant time.

## 34. Example: event listener not running due to missing transaction

### 34.1. Event type

```java
public record InvoiceCreatedEvent(String invoiceId) {
}
```

### 34.2. Publisher without a transaction

```java
@Service
public class InvoiceService {

    private final ApplicationEventPublisher publisher;

    public InvoiceService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void create(String invoiceId) {
        publisher.publishEvent(
                new InvoiceCreatedEvent(invoiceId)
        );
    }
}
```

### 34.3. Listener waiting for commit by default

```java
@Component
public class InvoiceListener {

    private static final Logger log =
            LoggerFactory.getLogger(InvoiceListener.class);

    @TransactionalEventListener
    public void afterCommit(InvoiceCreatedEvent event) {
        log.info(
                "Invoice committed: invoiceId={}",
                event.invoiceId()
        );
    }
}
```

If `create` does not execute inside a transaction, the default listener does not run.

### 34.4. Fixing with a transaction boundary

```java
@Transactional
public void create(String invoiceId) {
    repository.save(new Invoice(invoiceId));

    publisher.publishEvent(
            new InvoiceCreatedEvent(invoiceId)
    );
}
```

Only after a successful commit does the listener execute.

### 34.5. Verifying with an integration test

The test should confirm:

- The invoice is saved.
- The event is published inside the transaction.
- The listener runs only after commit.
- On rollback, the after-commit listener does not run.

Do not use Mockito to verify `publishEvent` and conclude the transaction listener works. Mockito only proves the publisher method was called, not that transaction synchronization executed properly.

## 35. Example: early listener and ApplicationContext listener

Suppose we want to record two milestones:

- `ApplicationStartingEvent`: very early.
- `ApplicationReadyEvent`: after startup runners.

### 35.1. Early listener

```java
public class EarlyListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(
            ApplicationStartingEvent event
    ) {
        System.out.println("EARLY: application starting");
    }
}
```

Registration:

```java
public static void main(String[] args) {
    SpringApplication application =
            new SpringApplication(ShopApplication.class);

    application.addListeners(new EarlyListener());

    application.run(args);
}
```

### 35.2. Ready listener in the context

```java
@Component
public class ReadyListener {

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("READY: all runners completed");
    }
}
```

The two listeners have different registration mechanisms and lifecycles. You cannot use a regular `@EventListener` bean and expect it to consistently receive events emitted before the context listener infrastructure is created.

## 36. Distinguishing "callback did not run" from "callback ran but has not finished yet"

Especially with async:

```java
@Async
@EventListener
public void onEvent(MyEvent event) {
    longRunningOperation();
}
```

The publisher can return before `longRunningOperation` finishes.

There are three distinct milestones:

1. Event is published.
2. Listener invocation is dispatched/submitted.
3. Listener finishes processing.

A log at the publisher only confirms milestone 1. An executor queue metric or log at the start of the method confirms milestone 2. A log at the end of the method, a future, or a latch confirms milestone 3.

When investigating, state explicitly which milestone you are waiting on.

## 37. Practice: choosing the right lifecycle hook

Sample requirements:

| Requirement | Appropriate choice | Why |
|---|---|---|
| Validate field values after injection | `@PostConstruct` or configuration validation | Part of bean initialization |
| Read all command-line options and run import | `ApplicationRunner` | Provides `ApplicationArguments` |
| Run a task after all startup runners | `ApplicationReadyEvent` | Emitted after the runner phase |
| Initialize a consumer and stop it with context | `SmartLifecycle` | Has start/stop lifecycle |
| Send email only after transaction commit | `@TransactionalEventListener(AFTER_COMMIT)` | Prevents sending before data commits |
| Update metrics/logs when an order is created | `@EventListener` or direct service call | Reacts to business event |
| Run a daily report | `@Scheduled` or scheduler | Scheduled work |
| Close resources on normal context shutdown | `@PreDestroy`/`SmartLifecycle.stop` | Lifecycle cleanup |
| Receive `ApplicationStartingEvent` | `SpringApplication.addListeners` | Listener must be registered before context |
| Setup before each JUnit test | `@BeforeEach` | JUnit lifecycle, not a Boot runner |

## 38. Practice exercises

### Exercise 1 — Observing @PostConstruct

Create a bean with a constructor, dependency injection, and `@PostConstruct`. Log at each step, then add another bean to observe why you must not assume all beans are ready inside a single bean's callback.

### Exercise 2 — Comparing InitializingBean and custom init method

Create a bean using `InitializingBean.afterPropertiesSet()` and a bean using `@Bean(initMethod=...)`. Observe the ordering alongside `@PostConstruct` and note that these callbacks belong to the bean lifecycle.

### Exercise 3 — Observing SmartInitializingSingleton

Create two singleton beans and one `SmartInitializingSingleton`. Log when each bean initializes and when the callback runs. Compare with `ContextRefreshedEvent`.

### Exercise 4 — Creating a CommandLineRunner

Create a `CommandLineRunner` component, pass a few command-line arguments, and print them. Verify the runner executes once per application startup.

### Exercise 5 — Creating an ApplicationRunner

Use `ApplicationArguments` to read option `--mode=initial` and non-option arguments. Compare with `CommandLineRunner`.

### Exercise 6 — Reproducing an unscanned runner

Place a runner in a package outside component scan. Confirm it is not registered, then fix the package or component scan and observe the runner execute.

### Exercise 7 — Reproducing a runner excluded by condition

Attach `@Profile` or `@ConditionalOnProperty`. Run with different values/profiles and determine why the runner appears or disappears.

### Exercise 8 — Reproducing an earlier runner failing startup

Create two runners with different orders; have the first runner throw an exception. Observe the subsequent runner and `ApplicationReadyEvent`. Read the startup failure cause chain.

### Exercise 9 — Comparing ApplicationStartedEvent and ApplicationReadyEvent

Register both listeners and a runner. Log timestamps to show the started event occurs before runners, while the ready event occurs after runners.

### Exercise 10 — Early event listener

Register an `ApplicationStartingEvent` listener using `SpringApplication.addListeners`. Compare with an `@EventListener` bean in the ApplicationContext and explain the registration timing difference.

### Exercise 11 — Publishing business events

Create `OrderCreatedEvent` and publish it via `ApplicationEventPublisher`. Register an `@EventListener`, verifying the exact event type and payload.

### Exercise 12 — @EventListener condition

Add a SpEL condition based on priority. Publish events with low/high priority and observe the listener only processes events matching the condition.

### Exercise 13 — Transactional events

Create a `@TransactionalEventListener(AFTER_COMMIT)`. Publish events inside and outside a transaction. Verify default behavior and test `fallbackExecution=true` in a separate test.

### Exercise 14 — Transaction rollback

Create a transaction that saves data and then throws an exception. Register AFTER_COMMIT and AFTER_ROLLBACK listeners, confirming the listener matching the transaction outcome runs.

### Exercise 15 — Async event listener

Enable `@EnableAsync` and mark a listener `@Async`. Log thread names and publish/completion timestamps. Use CountDownLatch or Awaitility in tests instead of `Thread.sleep`.

### Exercise 16 — Context hierarchy

Create parent/child contexts or configure multiple contexts in a test. Log context IDs when receiving `ContextRefreshedEvent` and discover why a listener can receive events multiple times.

### Exercise 17 — SmartLifecycle

Create a component implementing `SmartLifecycle`, logging start/stop and phase. Try `isAutoStartup=false`, then re-enable it to observe the difference.

### Exercise 18 — Shutdown callbacks

Create a bean with `@PreDestroy`. Close the context normally and observe the callback. Compare conceptually with forcefully killing the process and explain why cleanup is not guaranteed in that scenario.

### Exercise 19 — Runners and Spring TestContext cache

Create two `@SpringBootTest` classes sharing the same configuration. Log the runner and observe context reuse. Try `@DirtiesContext` to see context recreation, then evaluate its cost.

### Exercise 20 — Testing a runner in isolation

Use Mockito to unit test `ApplicationRunner.run`. Assert the service dependency is called. Then explain why this test does not prove component scan or Boot startup automatically calls the runner.

### Exercise 21 — Scheduled tasks

Enable `@EnableScheduling` and create a `@Scheduled` method with an initial delay. Observe how it differs from a runner. Run two application instances and analyze the risk of executing the job twice.

### Exercise 22 — Debugging a mistimed callback

Create a workflow with a dependency between cache warmup and initialization data. Initially use two unordered runners, then refactor into explicit orchestration. Explain why a dependency graph beats relying on accidental ordering.

### Exercise 23 — Measuring startup task duration

Use `System.nanoTime` or a Micrometer Timer to measure warmup duration. Add phase, context ID, and thread name logs to support operations.

### Exercise 24 — Designing durable events

Create a business event that must not be lost across restarts. Compare Spring application events with a message broker/transactional outbox and propose an appropriate architecture.

## 39. Official references

- [Spring Boot Reference — SpringApplication Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html): lifecycle events, runners, and application availability.
- [Spring Boot Reference — Application Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-events-and-listeners): events during SpringApplication bootstrap.
- [Spring Boot Reference — Application Runners](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.command-line-runner): `ApplicationRunner` and `CommandLineRunner`.
- [Spring Framework Reference — Bean Lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): initialization, destruction callbacks, and lifecycle.
- [Spring Framework Reference — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events): publishing and subscribing to application events.
- [Spring Framework Reference — Annotation-based Event Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events-annotation): `@EventListener` and listener methods.
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener` and transaction phases.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Async`, executors, and `@Scheduled`.
- [Spring Framework Reference — Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html#beans-factory-lifecycle): `SmartLifecycle` and lifecycle callbacks.
- [Spring Boot Reference — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): test contexts, startup behavior, and Spring Boot testing.

**The most important rule when diagnosing callbacks, runners, or listeners:** identify the exact lifecycle phase before inspecting code. `@PostConstruct` belongs to a single bean's initialization; runners execute after context refresh; `ApplicationReadyEvent` arrives after startup runners; `@EventListener` requires the listener to be registered before the event is published; `@TransactionalEventListener` also depends on transaction phases; async listeners have their own completion timing. Once you understand these boundaries, you can trace the cause through bean registration, component scan, profiles/conditions, startup exceptions, event types, transactions, executors, or context caching instead of arbitrarily adding delays or invoking callbacks manually.
