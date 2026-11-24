# ApplicationListener, @EventListener, and Early Listener Registration

Spring Boot publishes numerous application events during startup and runtime. Listeners can be used to log milestones, prepare caches, observe application state, initialize integrations, or react once the context is ready.

Spring provides two common ways to write listeners:

- **`ApplicationListener<E>`**: implementing an interface with a specific event type and the `onApplicationEvent` method.
- **`@EventListener`**: annotating a method on a Spring bean so that method receives matching events.

A crucial point when working with startup events is **when the listener is registered**. A listener created as a bean inside the ApplicationContext is usually wired into the event multicaster only during context refresh. Therefore, it cannot receive events published before the context exists or before the listener is registered. If you need to listen for very early events such as `ApplicationStartingEvent` or `ApplicationEnvironmentPreparedEvent`, register the listener directly with `SpringApplication` before calling `run()`, or publish the listener through the appropriate `spring.factories` mechanism.

This lesson progresses from the event model, the two ways of writing listeners, startup event ordering, and early registration points, to ordering, common errors, and testing.

## 1. How Do Spring Application Events Work?

Spring has an in-process event model. One component publishes an object extending `ApplicationEvent` or using a Spring-supported event type; registered listeners receive the corresponding event.

For example, a service can publish a business event:

~~~java
public record OrderPlacedEvent(String orderId) {
}
~~~

A component publishes the event via `ApplicationEventPublisher`:

~~~java
@Service
public class OrderService {
    private final ApplicationEventPublisher events;

    public OrderService(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void placeOrder(String orderId) {
        // Process order business logic...
        events.publishEvent(new OrderPlacedEvent(orderId));
    }
}
~~~

A listener receives the event:

~~~java
@Component
public class OrderAuditListener {

    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        System.out.println("Order placed: " + event.orderId());
    }
}
~~~

When `placeOrder` calls `publishEvent`, Spring dispatches the event to matching listeners registered in the context.

Application events are normally processed synchronously on the publishing thread by default. Therefore, if a listener performs long work, the `publishEvent` call must wait until the listener completes. You can configure an asynchronous event multicaster or use `@Async` when appropriate, though switching to asynchronous handling requires explicitly designing executors, error handling, ordering, and consistency.

### 1.1. Spring Boot Events vs. Business Events

Two event groups must be distinguished:

**Spring Boot lifecycle events** describe the application's startup progress, such as `ApplicationReadyEvent`.

**Application/domain events** describe something that occurred in the business domain, such as `OrderPlacedEvent`.

Both can be handled with `ApplicationListener` or `@EventListener`, yet their timing and purpose differ. Lifecycle events may be published before regular beans are created; business events are normally published after the application context is ready.

## 2. Implementing ApplicationListener<E>

`ApplicationListener` is a Spring interface:

~~~java
import org.springframework.context.ApplicationListener;
~~~

A listener can implement it directly:

~~~java
@Component
public class OrderPlacedListener
        implements ApplicationListener<OrderPlacedEvent> {

    @Override
    public void onApplicationEvent(OrderPlacedEvent event) {
        System.out.println("Received order: " + event.orderId());
    }
}
~~~

The generic parameter `OrderPlacedEvent` indicates which event type the listener is interested in. Spring can use this type to filter matching events.

A listener for a Spring Boot event:

~~~java
@Component
public class ReadyApplicationListener
        implements ApplicationListener<ApplicationReadyEvent> {

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        System.out.println("Application is ready");
    }
}
~~~

`ApplicationReadyEvent` is published when the application has completed startup steps and runners have finished. This kind of bean listener is suitable for performing a post-startup reaction if the work should be managed by the context.

### 2.1. Filtering Events by Generic Type

If declared as:

~~~java
public class ReadyListener
        implements ApplicationListener<ApplicationReadyEvent> {
    // ...
}
~~~

the listener only cares about `ApplicationReadyEvent`.

You can implement a listener accepting a more general type:

~~~java
public class BootEventListener
        implements ApplicationListener<SpringApplicationEvent> {

    @Override
    public void onApplicationEvent(SpringApplicationEvent event) {
        System.out.println(event.getClass().getSimpleName());
    }
}
~~~

In practice, only listen to broad event types when you genuinely need to observe multiple lifecycle milestones. A listener receiving too many events can end up with many conditional branches and become hard to maintain.

### 2.2. Listeners Can Be Beans or Directly Registered Objects

A class implementing `ApplicationListener` can be registered via `@Component` or `@Bean` for the Spring context to manage.

~~~java
@Configuration(proxyBeanMethods = false)
public class EventConfiguration {

    @Bean
    ApplicationListener<ApplicationReadyEvent> readyListener() {
        return event -> System.out.println("Ready event received");
    }
}
~~~

This registration approach works for events published after the listener bean has been added to the context. For very early events, a bean in the context may be registered too late; a later section explains how to handle those.

## 3. Using @EventListener on Methods

Instead of implementing an interface, you can annotate a method with `@EventListener`:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventHandlers {

    @EventListener
    public void handleOrderPlaced(OrderPlacedEvent event) {
        System.out.println("Order: " + event.orderId());
    }
}
~~~

Spring detects annotated methods on beans and registers them as event listeners.

A method can accept the event type directly via its parameter. The method name can be anything; the parameter type tells Spring which event type to match.

You can declare the event type explicitly:

~~~java
@EventListener(OrderPlacedEvent.class)
public void handle(Object event) {
    // ...
}
~~~

Even so, a specific parameter type usually makes the code easier to read:

~~~java
@EventListener
public void handle(OrderPlacedEvent event) {
    // ...
}
~~~

### 3.1. One Class Can Have Multiple Event Handlers

~~~java
@Component
public class ApplicationLifecycleHandlers {

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("Context refreshed; runners have not run yet");
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("Runners completed; application is ready");
    }

    @EventListener
    public void onFailed(ApplicationFailedEvent event) {
        System.err.println("Application startup failed");
    }
}
~~~

These methods are registered as separate listeners for their respective event types. A listener bean can only receive events published after its listener methods are registered.

### 3.2. A Listener Method Can Return Another Event

An `@EventListener` method can return an event object. Spring will publish the returned object as a new event:

~~~java
@EventListener
public OrderNotificationEvent onOrderPlaced(OrderPlacedEvent event) {
    return new OrderNotificationEvent(event.orderId());
}
~~~

This example assumes `OrderNotificationEvent` is an application-defined event type. Other listeners can receive the new event.

Avoid using returned events to build hard-to-trace processing chains. If business flow is complex, an explicit coordinating service is usually easier to read.

### 3.3. Event Listener Methods Are Not HTTP Endpoints

`@EventListener` does not create web routes and does not accept external requests. It only registers a method to handle application events within the Spring context.

If you need to handle HTTP requests, use controller mappings such as `@GetMapping` or `@PostMapping`. If you need to process messages from a broker, use the corresponding listener abstraction such as a Kafka or JMS listener; application events do not replace a message broker.

## 4. Key Events in the Spring Boot Lifecycle

Spring Boot publishes a chain of events during `SpringApplication.run`. Some appear before the ApplicationContext is created; others appear after refresh and after runners complete.

General lifecycle sequence in a modern Spring Boot application:

~~~text
SpringApplication starts
        │
        ▼
ApplicationStartingEvent
        │
        ▼
ApplicationEnvironmentPreparedEvent
        │
        ▼
ApplicationContextInitializedEvent
        │
        ▼
ApplicationPreparedEvent
        │
        ▼
ApplicationContext.refresh()
        │
        ▼
ContextRefreshedEvent
        │
        ▼
ApplicationStartedEvent
        │
        ▼
AvailabilityChangeEvent (LivenessState.CORRECT)
        │
        ▼
ApplicationRunner / CommandLineRunner
        │
        ▼
ApplicationReadyEvent
        │
        ▼
AvailabilityChangeEvent (ReadinessState.ACCEPTING_TRAFFIC)
~~~

If startup fails, Boot can publish `ApplicationFailedEvent` during error handling.

Event names and lifecycle milestones can vary across Spring Boot generations. The milestones below describe the common lifecycle in modern Boot releases; check your project's API version whenever relying on a specific event.

### 4.1. ApplicationStartingEvent

Published very early, right when `SpringApplication` starts running.

At this point:

- The application's Environment is not fully prepared yet.
- The ApplicationContext has not been created yet.
- Application beans have not been registered yet.
- You cannot rely on dependency injection from the application context.

This is the right event for a very early listener to record that startup began or configure initial observation behavior. The listener must be registered before calling `run()`.

### 4.2. ApplicationEnvironmentPreparedEvent

Published after Boot prepares the Environment and before the ApplicationContext is created.

Listeners can read the environment, profiles, and properties already loaded at this stage:

~~~java
public class EnvironmentPreparedListener
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

    @Override
    public void onApplicationEvent(ApplicationEnvironmentPreparedEvent event) {
        Environment environment = event.getEnvironment();

        System.out.println(
                "Active profiles: "
                        + Arrays.toString(environment.getActiveProfiles())
        );
    }
}
~~~

This listener still has to be registered early via `SpringApplication` or the corresponding listener discovery mechanism. A bean inside the ApplicationContext cannot receive an event published before the context is created.

### 4.3. ApplicationContextInitializedEvent

This event is published after the ApplicationContext has been created and `ApplicationContextInitializer` instances have run, but before the application's bean definition sources are fully loaded into the context.

It is useful when you need to observe or work at the milestone where the context is initialized yet has not entered the full preparation/refresh phase.

Do not treat this as the moment all beans exist. Regular singleton beans have not been created simply because this event fired.

### 4.4. ApplicationPreparedEvent

Published after the context has been prepared and bean definitions have been loaded, but before the context is refreshed.

At this milestone, the context has configuration info and bean definitions, yet singletons have not necessarily been instantiated. Listeners can observe the context's prepared state; do not assume all dependencies are ready to use.

### 4.5. ContextRefreshedEvent

This is a Spring Framework event, published when the ApplicationContext finishes refreshing.

For a typical Spring Boot application context, required beans have been instantiated during refresh (excluding lazy beans or special cases).

A listener bean in the context can receive this event if it was registered prior to the event's publication.

~~~java
@Component
public class ContextRefreshListener {

    @EventListener
    public void onRefresh(ContextRefreshedEvent event) {
        System.out.println("Application context refreshed");
    }
}
~~~

If the application has parent-child contexts, each context can publish its own refresh event. Listeners need to account for the event source/context if they must avoid running multiple times.

### 4.6. ApplicationStartedEvent

Published after the ApplicationContext has refreshed and before `ApplicationRunner` and `CommandLineRunner` are invoked.

This event is appropriate when you need to know the context has finished starting, while startup runners may still not have finished.

Do not use `ApplicationStartedEvent` as proof that all initialization tasks performed by runners are done.

### 4.7. AvailabilityChangeEvent with LivenessState.CORRECT

After the started milestone, Boot updates the liveness state to `CORRECT` in the modern lifecycle.

Liveness indicates that the application process has started far enough to be considered alive per Boot's availability model. It does not automatically prove all external dependencies are healthy or that the application is ready to accept traffic.

### 4.8. ApplicationRunner and CommandLineRunner

After `ApplicationStartedEvent`, Boot calls beans implementing `ApplicationRunner` and `CommandLineRunner`.

These are callbacks for one-time tasks running after the context refreshes and before the ready event:

~~~java
@Component
public class StartupDataLoader implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Load startup data");
    }
}
~~~

Runners fit work such as loading initial data, validating business configuration, or preparing resources that must finish before the application announces ready.

A runner is not an event listener. It is a distinct startup callback with its own ordering rules, invoked directly by Boot during `run`.

### 4.9. ApplicationReadyEvent

Published after runners complete. This is the milestone signaling that the application completed startup per Boot's workflow.

~~~java
@Component
public class ReadyListener {

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("Application startup completed");
    }
}
~~~

Bean listeners in the context can receive this event because listeners were already registered during the preceding refresh.

Use this event when you need to react after startup, such as recording the ready milestone or signaling an internal component. If you need to execute a mandatory task before the application is considered ready, consider a runner rather than starting an async task and returning immediately from a listener.

### 4.10. AvailabilityChangeEvent with ReadinessState.ACCEPTING_TRAFFIC

After the ready milestone, Boot transitions readiness to `ACCEPTING_TRAFFIC` in the standard lifecycle.

Readiness expresses whether the application can accept traffic. It differs from liveness:

- Liveness: is the process alive according to application state?
- Readiness: is the application ready to accept requests?

When deployed on an orchestration platform, the readiness state can be used by health indicators and routing mechanisms to decide whether to send traffic to the instance.

### 4.11. ApplicationFailedEvent

Published when startup fails and Boot has details about the exception that caused the error.

~~~java
public class StartupFailureListener
        implements ApplicationListener<ApplicationFailedEvent> {

    @Override
    public void onApplicationEvent(ApplicationFailedEvent event) {
        Throwable failure = event.getException();
        System.err.println("Startup failed: " + failure.getMessage());
    }
}
~~~

Because this event may fire when the context is incomplete or already closed during error handling, a listener should not assume it can inject and call arbitrary application beans. An early-registered listener is generally more suitable if you need to observe failures at all startup stages.

## 5. Early Listener Registration: The Most Important Rule

Not every listener can receive every lifecycle event. What decides this is whether the listener was registered with the event source before the event is published.

### 5.1. Listeners as Beans in ApplicationContext

Example:

~~~java
@Component
public class ReadyListener
        implements ApplicationListener<ApplicationReadyEvent> {

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        System.out.println("Ready");
    }
}
~~~

Or:

~~~java
@Component
public class StartingListener {

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("Ready");
    }
}
~~~

Bean listeners are discovered and registered during context refresh. They work well for events published after the listener is registered, such as `ContextRefreshedEvent`, `ApplicationStartedEvent`, `ApplicationReadyEvent`, and subsequent runtime events.

They cannot receive events published before the ApplicationContext is created and the listener is wired up, such as `ApplicationStartingEvent` and `ApplicationEnvironmentPreparedEvent`.

### 5.2. Registering with SpringApplication.addListeners Before run()

If you need to receive very early events, instantiate the listener and register it directly on `SpringApplication` before calling `run()`.

~~~java
public class EarlyStartupListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("SpringApplication is starting");
    }
}
~~~

Main class:

~~~java
@SpringBootConfiguration
@EnableAutoConfiguration
@ComponentScan
public class Application {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(Application.class);

        application.addListeners(new EarlyStartupListener());

        application.run(args);
    }
}
~~~

In a typical application, the annotations above can be replaced with `@SpringBootApplication`:

~~~java
@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(Application.class);

        application.addListeners(new EarlyStartupListener());

        application.run(args);
    }
}
~~~

Key point: the listener is added before `run()`, so it is present when Boot publishes the starting event.

Multiple listeners can be registered:

~~~java
application.addListeners(
        new EarlyStartupListener(),
        new EnvironmentPreparedListener()
);
~~~

These listeners are not beans created via ApplicationContext constructor injection. If they need dependencies, design them to use data available on the event or environment, or move bean-dependent work to a stage after the context is ready.

### 5.3. Using SpringApplicationBuilder

Another option is configuring via `SpringApplicationBuilder`:

~~~java
new SpringApplicationBuilder(Application.class)
        .listeners(new EarlyStartupListener())
        .run(args);
~~~

The listener is likewise registered before the application runs.

This approach is useful when building an application with multiple contexts or needing a fluent builder chain.

### 5.4. Registering Listeners via spring.factories

If developing a library or starter that wants its listener discovered automatically by applications using the library, you can publish the listener in the file:

~~~text
META-INF/spring.factories
~~~

Contents:

~~~properties
org.springframework.context.ApplicationListener=\
com.example.boot.EarlyStartupListener
~~~

Spring Boot uses SpringFactoriesLoader to discover listeners declared under this key. Listeners are instantiated early so they can receive `SpringApplication` events before the application context exists.

This approach fits when a listener belongs to a library and needs to ship alongside its dependency. It differs from auto-configuration imports metadata:

- `META-INF/spring.factories` with key `org.springframework.context.ApplicationListener` is used to publish application listeners.
- `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` is used to publish auto-configurations in modern Boot releases.

Do not move listeners into `AutoConfiguration.imports`; that file is not a registry for `ApplicationListener`.

### 5.5. Early-Created Listeners Must Manage Dependencies Themselves

An early listener can be instantiated by `SpringApplication` or `SpringFactoriesLoader` before the ApplicationContext is ready. Therefore, do not write:

~~~java
@Component
public class EarlyListener implements ApplicationListener<ApplicationStartingEvent> {

    private final SomeApplicationService service;

    public EarlyListener(SomeApplicationService service) {
        this.service = service;
    }

    // ...
}
~~~

and expect Boot to auto-inject `SomeApplicationService` before the context is created. Listeners registered via early mechanisms are not instantiated like regular beans in the context.

Instead:

- Keep early listeners simple with minimal dependencies.
- Read data from the event or Environment if the event provides it.
- Record necessary data and hand off bean-dependent processing to a post-refresh bean.
- If you need to configure beans in the context, consider `ApplicationContextInitializer` or Spring configuration matching the right lifecycle hook.

## 6. Table for Choosing Registration Approach by Event Timing

| Event to Receive | Bean Listener in Context | addListeners Before run() / spring.factories |
| --- | --- | --- |
| `ApplicationStartingEvent` | Too late | Appropriate |
| `ApplicationEnvironmentPreparedEvent` | Too late | Appropriate |
| `ApplicationContextInitializedEvent` | Usually too late | Appropriate |
| `ApplicationPreparedEvent` | Should not rely on bean listener | Appropriate |
| `ContextRefreshedEvent` | Can receive once registered during refresh | Can receive |
| `ApplicationStartedEvent` | Can receive | Can receive |
| `ApplicationReadyEvent` | Can receive | Can receive |
| Post-startup business events | Can receive | Can receive |

This table describes typical rules for a single Boot context. With parent-child contexts or custom lifecycles, inspect exactly which context emits the event and which context the listener is attached to.

An easy-to-remember rule of thumb:

- Need events before context creation: register listeners before `run()`.
- Need events during or after refresh: bean listeners are the natural choice.
- Need listeners using Spring-managed dependencies: prefer bean listeners at stages where the context is ready.

## 7. Ordering: Which Listener Runs First?

An event can be handled by multiple listeners. If order matters, use `Ordered` or `@Order`.

### 7.1. With ApplicationListener

~~~java
@Component
@Order(10)
public class FirstReadyListener
        implements ApplicationListener<ApplicationReadyEvent> {

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        System.out.println("First");
    }
}
~~~

Another listener:

~~~java
@Component
@Order(20)
public class SecondReadyListener
        implements ApplicationListener<ApplicationReadyEvent> {

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        System.out.println("Second");
    }
}
~~~

Lower order values take precedence first when Spring sorts listeners under its ordering contract.

You can implement `Ordered` directly:

~~~java
public class OrderedReadyListener
        implements ApplicationListener<ApplicationReadyEvent>, Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        // ...
    }
}
~~~

### 7.2. With `@EventListener` Methods

~~~java
@Component
public class ReadyHandlers {

    @EventListener
    @Order(10)
    public void prepareMetrics(ApplicationReadyEvent event) {
        System.out.println("Prepare metrics");
    }

    @EventListener
    @Order(20)
    public void logReady(ApplicationReadyEvent event) {
        System.out.println("Log ready");
    }
}
~~~

`@Order` helps control the order of listeners handling the same event in Spring's event mechanism. Do not use it to replace dependencies between business steps.

### 7.3. Listener Order Does Not Change Lifecycle Event Order

`@Order` only orders listeners handling the same event according to ordering rules. It cannot make `ApplicationReadyEvent` fire before `ApplicationStartedEvent` or alter the lifecycle order managed by Spring Boot.

If task B must finish after task A, the clearest approach is coordinating both tasks inside one service/runner rather than hoping ordering across different events will solve the dependency.

## 8. `@EventListener` and Asynchronous Handling

By default, listeners are called synchronously on the event-publishing thread. If a listener performs long work, startup or the request publishing the event can be blocked.

You can annotate a listener method with `@Async` once async processing is enabled in the application:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

~~~java
@Component
public class AsyncReadyListener {

    @Async
    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        // Background work that may run for a long time.
    }
}
~~~

Considerations:

- Configure a dedicated executor rather than letting all tasks share an uncontrolled executor.
- Handle exceptions because errors in async listeners are not propagated back like normal synchronous calls.
- Do not assume the listener finishes before the event publisher continues.
- Do not use async for work that must finish before the application reports ready unless Boot is explicitly configured to wait for it.
- Set timeouts, retries, and idempotency for tasks with side effects.

If an initialization step must finish before the application is marked ready, `ApplicationRunner` or `CommandLineRunner` is usually more appropriate. Runners execute in the startup sequence before `ApplicationReadyEvent`.

## 9. Comparing Listeners with ApplicationRunner and CommandLineRunner

Both listeners and runners can perform work at startup, yet their lifecycle hooks differ.

### 9.1. ApplicationRunner

~~~java
@Component
public class ReferenceDataLoader implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        // Load reference data after context refresh.
    }
}
~~~

`ApplicationRunner` receives `ApplicationArguments`, allowing access to parsed command-line arguments.

### 9.2. CommandLineRunner

~~~java
@Component
public class StartupReporter implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("Arguments count: " + args.length);
    }
}
~~~

`CommandLineRunner` receives the raw array of argument strings.

### 9.3. Comparison Table

| Criterion | ApplicationListener / @EventListener | ApplicationRunner | CommandLineRunner |
| --- | --- | --- | --- |
| Goal | React when an event is published | Run a task after refresh | Run a task after refresh |
| Trigger | Matching event | Invoked by Boot during startup | Invoked by Boot during startup |
| Lifecycle event awareness | Yes | Not directly | Not directly |
| Command-line args access | Via matching event or Environment | `ApplicationArguments` | `String... args` |
| Can run before ApplicationReadyEvent | Depends on event; runners run before ready | Yes | Yes |
| Best suited for | Observing lifecycle, reacting to events | Structured startup tasks | Simple startup tasks |

If you need to react when `ApplicationReadyEvent` fires, use a listener. If you need to execute work that must complete before ready, use a runner. If you need to receive very early events, the listener must be registered before the context exists.

## 10. Event Listeners Are Not a Durable Message Storage Mechanism

Spring application events typically live only within the current process and context:

- No default replay after application restart.
- No durable queue or delivery guarantee across processes.
- Listeners registered after an event fires do not automatically receive past events.
- Exceptions and retries depend on how the event multicaster/executor is configured.
- Synchronous events can directly impact the publisher's latency.

If you need to send events across services, persist events for reprocessing, or ensure messages survive restarts, consider a message broker or an appropriate event persistence mechanism.

Application events are great for decoupling components within the same application, but should not be treated as Kafka, RabbitMQ, or an event store.

## 11. Complete Example: Recording Startup Milestones

You can register an early listener to listen for pre-context events:

~~~java
public class EarlyLifecycleListener
        implements ApplicationListener<SpringApplicationEvent> {

    @Override
    public void onApplicationEvent(SpringApplicationEvent event) {
        System.out.println(
                "Early lifecycle event: "
                        + event.getClass().getSimpleName()
        );
    }
}
~~~

Main class:

~~~java
@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(DemoApplication.class);

        app.addListeners(new EarlyLifecycleListener());
        app.run(args);
    }
}
~~~

This listener is registered before `run()` and can observe matching `SpringApplicationEvent` instances during startup.

To handle events after the context is ready, use a bean:

~~~java
@Component
public class ApplicationLifecycleLogger {

    private static final Logger log =
            LoggerFactory.getLogger(ApplicationLifecycleLogger.class);

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        log.info("Context refreshed; startup runners are next");
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        log.info("Startup runners completed; application is ready");
    }

    @EventListener
    public void onFailure(ApplicationFailedEvent event) {
        log.error("Application startup failed", event.getException());
    }
}
~~~

The example demonstrates the two timing groups:

- An early listener registered with `SpringApplication` to receive pre-context lifecycle events.
- A listener bean using `@EventListener` to handle events after methods are registered in the context.

Do not rely on a single bean listener expecting to receive every event from the moment the JVM begins starting.

## 12. Testing Listeners

### 12.1. Testing `@EventListener` in Context

You can create a small context and publish an event manually:

~~~java
class OrderEventListenerTest {

    @Test
    void handlesPublishedOrderEvent() {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        OrderEventListenerConfiguration.class
                );

        try {
            OrderEventRecorder recorder =
                    context.getBean(OrderEventRecorder.class);

            context.publishEvent(new OrderPlacedEvent("order-123"));

            assertEquals("order-123", recorder.lastOrderId());
        } finally {
            context.close();
        }
    }
}
~~~

Recorder listener:

~~~java
@Component
public class OrderEventRecorder {
    private String lastOrderId;

    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        this.lastOrderId = event.orderId();
    }

    public String lastOrderId() {
        return lastOrderId;
    }
}
~~~

Test configuration:

~~~java
@Configuration
@ComponentScan(basePackageClasses = OrderEventRecorder.class)
class OrderEventListenerConfiguration {
}
~~~

The example requires appropriate JUnit and Spring Context imports. The test verifies an event published after the context and listener are ready.

### 12.2. Testing Early Listeners

Early listeners can be tested by creating a `SpringApplication` and registering the listener before running:

~~~java
@SpringBootTest
class EarlyListenerTest {
    // Can use ApplicationContextRunner or a dedicated test SpringApplication
    // to verify the listener receives the expected lifecycle event.
}
~~~

When testing very early events, do not just register the listener as a bean in the test context. Test the actual pre-`run()` registration path that the production application uses.

You can extract event recording into a simple class and pass a recorder into the manually constructed listener in tests. This verifies logic without depending on the Spring context already existing.

### 12.3. Testing Runners Differs from Testing Listeners

If the goal is to verify data was loaded before `ApplicationReadyEvent`, verify that the runner completed and the ready event was published afterward. Do not simply call `run` manually and treat that as testing Boot's full lifecycle.

## 13. Common Errors

### 13.1. `@EventListener` Does Not Receive ApplicationStartingEvent

**Cause:** The bean containing the listener method is registered only inside the ApplicationContext, whereas `ApplicationStartingEvent` fires before the context is created.

**Solution:** Register an `ApplicationListener` via `SpringApplication.addListeners` before `run()`, or publish the listener via `spring.factories`.

### 13.2. Listener Does Not Receive ApplicationEnvironmentPreparedEvent

**Cause:** The event fires before the ApplicationContext creation and refresh stage. Bean listeners cannot receive events already published.

**Solution:** Use an early listener. Read the Environment from the event if prepared configuration is needed.

### 13.3. Early Listener Does Not Receive Dependency Injection

**Cause:** The listener is instantiated by SpringApplication or SpringFactoriesLoader before the ApplicationContext is ready.

**Solution:** Keep the listener standalone, use data from the event, or move bean-dependent work to a bean listener/runner after refresh.

### 13.4. Listener Runs Twice

**Possible causes:**

- The listener is registered via both `addListeners` and `spring.factories`.
- The application has multiple contexts in a hierarchy.
- The same logic is registered across multiple beans or methods.
- An event is published in multiple contexts.

**Solution:** Check all registration paths, identify the context emitting the event, and make handlers idempotent if duplicate events are possible.

### 13.5. Listener Slows Down Startup

**Cause:** The listener runs synchronously and executes a long task.

**Solution:** Move tasks required before ready to a runner; if background execution after ready is acceptable, use an explicitly configured async executor. Measure actual duration and handle async errors.

### 13.6. Using ApplicationReadyEvent to Run Work Mandatory Before Ready

**Cause:** The ready event only fires after runners complete. An async listener on this event may start work after the application is already marked ready.

**Solution:** Use `ApplicationRunner` or `CommandLineRunner` for tasks that must finish before ready.

### 13.7. Using `@Order` to Alter Lifecycle Order

**Cause:** Confusing listener order for a single event with lifecycle event order.

**Solution:** `@Order` orders listeners for an event; it does not alter the order in which Boot publishes events.

### 13.8. Using Application Events for Inter-Service Communication

**Cause:** Confusing in-process events with a message broker.

**Solution:** Use a broker or appropriate messaging mechanism when network communication, durable storage, retries, and replay are required.

## 14. Workflow for Choosing a Listener and Registration Timing

When designing a listener, answer these questions in order:

1. **Which event needs handling?** A Boot lifecycle event or an application-published business event?
2. **When does the event fire?** Before context creation, during refresh, or after ready?
3. **Does the listener need Spring dependencies?** If so, a bean listener inside the context is usually more appropriate.
4. **Do you need to listen to very early events?** Use `SpringApplication.addListeners` or `spring.factories`.
5. **Is ordering relative to other listeners needed?** Use `@Order` or `Ordered`.
6. **Must the task finish before ready?** Use a runner instead of an async listener after ready.
7. **Could the task run for a long time?** Consider an executor, async execution, and error handling.
8. **Must the event be durable or sent across services?** If so, use appropriate messaging infrastructure.

Choosing the lifecycle hook based on real requirements prevents listeners from running too late, depending on nonexistent beans, or accidentally lengthening startup time.

## 15. Practice Exercises

### Exercise A: Listen to ApplicationReadyEvent with `@EventListener`

Create a bean with an `@EventListener` method accepting `ApplicationReadyEvent`. Run the application and confirm the log appears after runners.

### Exercise B: Compare ApplicationStartedEvent and ApplicationReadyEvent

Create two separate listeners. Add an `ApplicationRunner` that logs a message.

Observe the sequence:

- Context refresh completes.
- `ApplicationStartedEvent` is published.
- Runner executes.
- `ApplicationReadyEvent` is published.

Explain why these two events are not interchangeable.

### Exercise C: Register ApplicationStartingEvent Early Enough

Create a class implementing `ApplicationListener<ApplicationStartingEvent>`. Register it using `SpringApplication.addListeners` before `run()`.

Then try turning the listener into a `@Component` in the context and observe why it does not receive the starting event.

### Exercise D: Register a Listener via spring.factories

Create `META-INF/spring.factories` with the key `org.springframework.context.ApplicationListener`. Package the listener into a test module or sample library and confirm Boot discovers the listener.

Compare with `AutoConfiguration.imports` and explain the distinct roles of the two metadata files.

### Exercise E: Ordering

Create two `@EventListener` methods both accepting `ApplicationReadyEvent`. Annotate them with `@Order(1)` and `@Order(2)` and observe log order.

Then emit another event and confirm `@Order` does not alter the lifecycle order between the two events.

### Exercise F: Move Startup Work to a Runner

Write an `ApplicationReadyEvent` listener performing a mandatory task. Move that task into an `ApplicationRunner` and verify the work finishes before the ready event is published.

### Exercise G: Test Business Events

Create `OrderPlacedEvent`, publish it with `ApplicationEventPublisher`, and test the listener with a small context. Verify the listener does not need an HTTP request to be invoked.

## 16. Self-Check Questions

**1. How do `ApplicationListener` and `@EventListener` differ?**

`ApplicationListener<E>` is an interface implemented via the `onApplicationEvent` method. `@EventListener` annotates a method on a bean so Spring registers it to handle the corresponding event.

**2. Why doesn't a bean listener receive `ApplicationStartingEvent`?**

Because the event fires before the ApplicationContext is created and listener beans are registered.

**3. How do you register a listener early enough?**

Use `SpringApplication.addListeners` or `SpringApplicationBuilder.listeners` before `run()`; for library listeners, publish them via `META-INF/spring.factories` under the key `org.springframework.context.ApplicationListener`.

**4. How do `ApplicationStartedEvent` and `ApplicationReadyEvent` differ?**

Started fires after context refresh but before runners. Ready fires after runners complete.

**5. When should you use ApplicationRunner instead of `@EventListener`?**

When you need a structured startup task that must finish before the application announces ready.

**6. Does `@Order` change lifecycle event order?**

No. It orders listeners handling the same event according to ordering rules.

**7. Do listeners run synchronously or asynchronously?**

By default, event listeners process synchronously. Async can be used when properly configured, though executors and errors must be managed.

**8. Is `@EventListener` a message broker?**

No. It is an internal in-process event mechanism that does not provide durable delivery or replay by default.

**9. Why should early listeners have minimal dependencies?**

Because the listener may be instantiated before the ApplicationContext, so it cannot receive bean dependencies via standard constructor injection.

## 17. Conclusion

`ApplicationListener` and `@EventListener` are two ways to handle application events in Spring. The interface fits when you want an explicit listener class and specific event type; the annotation fits when registering handlers directly on bean methods.

When handling Spring Boot lifecycle events, **registration timing determines which events a listener can receive**. Bean listeners inside the context fit events published during or after refresh. To receive very early events such as `ApplicationStartingEvent` or `ApplicationEnvironmentPreparedEvent`, register before `SpringApplication.run()` with `addListeners` or publish the listener in `spring.factories`.

Use `@Order` to order listeners subscribing to the same event, use runners for work that must finish before `ApplicationReadyEvent`, and consider async for background tasks that can be decoupled from startup. Picking the right lifecycle hook ensures listeners receive events on time, use dependencies at the right phase, and keep startup easy to control.
