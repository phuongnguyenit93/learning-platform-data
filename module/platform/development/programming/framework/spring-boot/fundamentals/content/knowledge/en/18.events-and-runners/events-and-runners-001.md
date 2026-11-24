# `SpringApplicationEvent` and Standard `ApplicationContext` Events

Both Spring Boot and Spring Framework use **events** to notify that something has happened during the application lifecycle. For example, Spring Boot can publish events when startup begins, when the `Environment` is prepared, when the application context is refreshed, when runners finish, or when the application is ready to receive traffic. Spring Framework also publishes standard events such as `ContextRefreshedEvent` and `ContextClosedEvent`.

These events allow a component to react to the application lifecycle without being called directly by the component that publishes the event. However, each event type has its own timing and scope. **`ApplicationStartedEvent` is not synonymous with `ContextRefreshedEvent`; nor does `ApplicationReadyEvent` mean that every background task in the application has completed.**

This lesson distinguishes:

- **`SpringApplicationEvent`**: events published by Spring Boot while running `SpringApplication`.
- **Context lifecycle events**: events published by Spring Framework when an `ApplicationContext` is refreshed, started, stopped, or closed.
- **Application event listener**: a component that receives and handles events using `ApplicationListener` or `@EventListener`.
- **Event propagation**: how events are forwarded between contexts in a parent-child hierarchy.

## 1. What Is an Event in Spring?

An event is an object representing something that has occurred. In Spring Framework, traditional events extend `ApplicationEvent`; a listener receives the event and performs an appropriate reaction.

For example, after an order is created, the application can publish `OrderCreatedEvent` so other components can send an email, write an audit record, or update a projection.

```text
OrderService
    |
    | publish OrderCreatedEvent
    v
ApplicationEventPublisher
    |
    v
ApplicationEventMulticaster
    |
    +------> EmailListener
    |
    +------> AuditListener
    |
    +------> MetricsListener
```

The publisher does not need to know specifically how many listeners exist or what work each listener performs. Listeners subscribe to the event types they care about.

### 1.1. Events vs. Direct Method Calls

Direct method calls:

```java
emailService.sendOrderConfirmation(order);
auditService.recordOrderCreated(order);
```

`OrderService` must know which services to call and depend on them directly.

Publishing an event:

```java
publisher.publishEvent(new OrderCreatedEvent(this, order));
```

`OrderService` only announces that an order was created. Matching listeners receive the notification via Spring's event mechanism.

Events are useful when reactions can be decoupled from the main business flow. If an operation is a required dependency to complete the business logic—such as checking inventory before confirming an order—calling a service via dependency injection usually expresses that relationship more clearly.

## 2. What Is `SpringApplicationEvent`?

`SpringApplicationEvent` is the base event class for events published by Spring Boot while orchestrating `SpringApplication`. These events typically carry information about the `SpringApplication` and, at appropriate stages, the `Environment` or `ApplicationContext`.

Representative events:

| Event | General Timing |
| --- | --- |
| `ApplicationStartingEvent` | Startup begins, before the Environment and context are fully prepared |
| `ApplicationEnvironmentPreparedEvent` | Environment has been prepared |
| `ApplicationContextInitializedEvent` | Context has been created and initializers have run, before loading bean definitions from application sources |
| `ApplicationPreparedEvent` | Context has been prepared and configuration loaded, before refresh |
| `ApplicationStartedEvent` | Context has been refreshed, before calling application/command-line runners |
| `ApplicationReadyEvent` | Runners have finished; the application has reached the ready state in the startup sequence |
| `ApplicationFailedEvent` | Startup failed |

In addition to the events above, Spring Boot also publishes events related to availability and web servers, such as `AvailabilityChangeEvent`, `ServletWebServerInitializedEvent`, or `ReactiveWebServerInitializedEvent`.

The class names reside in package `org.springframework.boot.context.event` for many of the lifecycle events listed above. Refer to the API of the exact Spring Boot version you are using because event details and timing can evolve across versions.

## 3. Event Sequence During Spring Boot Startup

A typical sequence can be pictured as follows:

```text
SpringApplication.run(...)
        |
        v
ApplicationStartingEvent
        |
        v
Prepare Environment
        |
        v
ApplicationEnvironmentPreparedEvent
        |
        v
Create ApplicationContext
        |
        v
Run ApplicationContextInitializer
        |
        v
ApplicationContextInitializedEvent
        |
        v
Load primary sources / configuration
        |
        v
ApplicationPreparedEvent
        |
        v
Refresh ApplicationContext
        |
        +----> ContextRefreshedEvent
        |
        +----> Web server initialized event (if web app)
        |
        v
ApplicationStartedEvent
        |
        v
AvailabilityChangeEvent: LivenessState.CORRECT
        |
        v
ApplicationRunner / CommandLineRunner
        |
        v
ApplicationReadyEvent
        |
        v
AvailabilityChangeEvent: ReadinessState.ACCEPTING_TRAFFIC
```

This is a high-level diagram to locate the key milestones. Some events may be published during refresh or across different startup branches; when startup fails, `ApplicationFailedEvent` is published instead of reaching the ready state.

### 3.1. `ApplicationStartingEvent`

This is one of Spring Boot's earliest events. It is published very early, before the application's `Environment` and `ApplicationContext` are fully prepared.

You can use this event to record when the process starts or to perform a very early infrastructure task that does not need application context beans.

Because the context is not ready yet, a listener receiving this event should not assume it can inject or retrieve business services from the application context.

### 3.2. `ApplicationEnvironmentPreparedEvent`

This event is published after the `Environment` has been prepared. Property sources such as command-line arguments, environment variables, system properties, and configuration files have participated in building the environment according to Spring Boot rules.

This is an appropriate milestone to observe the startup environment or integrate operations that need to know profiles/properties have been prepared. The context is still not in a refreshed state.

Listener example:

```java
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;

public class EnvironmentPreparedListener
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

    @Override
    public void onApplicationEvent(
            ApplicationEnvironmentPreparedEvent event) {
        String[] profiles =
                event.getEnvironment().getActiveProfiles();

        System.out.println(
                "Active profiles: " + String.join(", ", profiles)
        );
    }
}
```

This listener reads the `Environment` directly from the event without needing to retrieve beans from the context.

### 3.3. `ApplicationContextInitializedEvent`

This event is published after the context has been created and `ApplicationContextInitializer` instances have been applied, but before application sources are fully loaded into the context.

You can use it to record the milestone that the context has been initially prepared. You should not treat this as the moment when all bean definitions are registered or bean instances are created.

### 3.4. `ApplicationPreparedEvent`

This event marks that the context has been prepared with application sources but has **not yet been refreshed**.

This is still the stage before the container completes creating regular singleton beans. A listener at this stage should not call business services as if the application context were ready.

### 3.5. `ContextRefreshedEvent`

This is a Spring Framework event, not a subclass of `SpringApplicationEvent`. It is published when an `ApplicationContext` is successfully refreshed.

In a Spring Boot application, this event typically appears during context refresh before `ApplicationStartedEvent`.

`ContextRefreshedEvent` can be published whenever a context refreshes; in systems with multiple contexts or multiple refreshes, you should not assume it occurs only once across the entire JVM.

### 3.6. `ApplicationStartedEvent`

Spring Boot publishes this event after the application context has been refreshed and before calling `ApplicationRunner` or `CommandLineRunner`.

This is an important distinction:

- The context has been refreshed.
- Regular eager singletons have been initialized.
- Startup runners have not run yet.
- The application has not yet reached the `ApplicationReadyEvent` milestone.

If you need work performed during the runner phase, do not use `ApplicationStartedEvent` as proof that runners have finished.

### 3.7. `ApplicationReadyEvent`

This event is published after runners have completed. It indicates that the application has reached the ready state according to Spring Boot's startup lifecycle.

Example:

```java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ReadyReporter {

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("Application is ready");
    }
}
```

This is an appropriate place to record that startup has finished or to trigger a lightweight, controlled post-startup task.

You should not put a long-running, unbounded, or startup-blocking task into this listener unintentionally. Synchronous listeners can slow down event publishing and keep `run()` from returning.

### 3.8. `ApplicationFailedEvent`

This event is published when startup fails. It is useful for logging, sending monitoring signals, or recording startup errors.

However, failures can happen very early, before the application context is fully created. Therefore, a listener cannot always rely on a complete context to retrieve beans.

A listener should read exception details from the event, record the error, and avoid adding dependencies on beans that might not exist yet.

## 4. Availability Events in Spring Boot

Spring Boot has events representing an application's liveness and ability to accept traffic:

- `LivenessState.CORRECT`: the application has passed the corresponding startup milestone and the process is considered alive.
- `ReadinessState.ACCEPTING_TRAFFIC`: the application is ready to accept traffic.
- `ReadinessState.REFUSING_TRAFFIC`: the application is temporarily not accepting traffic.

These changes are published via `AvailabilityChangeEvent`.

Listener example:

```java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ReadinessListener {

    @EventListener
    public void onReadinessChange(
            AvailabilityChangeEvent<ReadinessState> event) {
        System.out.println(
                "Readiness: " + event.getState()
        );
    }
}
```

An application can also proactively publish a state:

```java
AvailabilityChangeEvent.publish(
        applicationContext,
        ReadinessState.REFUSING_TRAFFIC
);
```

The example above requires an appropriate `ApplicationContext` and imports for the corresponding availability types. In real systems, combine these states with your health checks, load balancers, and orchestration mechanisms.

**Liveness and readiness are not the same:** an application can still be alive while temporarily not ready to handle requests. Do not use one state as a substitute for the other.

## 5. Standard `ApplicationContext` Events

Spring Framework publishes events tied to the lifecycle of an application context. Common standard events:

| Event | When Is It Published? | Meaning |
| --- | --- | --- |
| `ContextRefreshedEvent` | Context refreshes successfully | Context has been loaded and is ready per the refresh cycle |
| `ContextStartedEvent` | `ConfigurableApplicationContext.start()` is called | Context is requested to start operating |
| `ContextStoppedEvent` | `ConfigurableApplicationContext.stop()` is called | Context is requested to stop |
| `ContextClosedEvent` | Context is closed | Container is ending its lifecycle |

These classes belong to package `org.springframework.context.event`.

### 5.1. `ContextRefreshedEvent`

Listener example:

```java
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ContextRefreshReporter {

    @EventListener
    public void onRefresh(ContextRefreshedEvent event) {
        System.out.println(
                "Context refreshed: " +
                event.getApplicationContext().getId()
        );
    }
}
```

The event carries the refreshed application context. In applications with parent-child contexts, each context can publish its own event. A listener may receive events forwarded from a child context depending on where it is registered.

You should not use `ContextRefreshedEvent` as the "application is completely ready" event in all Spring Boot applications. Runners may still not have been called; use `ApplicationReadyEvent` when you need the post-runner milestone.

### 5.2. `ContextStartedEvent`

This event is published when the context is requested to start via the lifecycle API:

```java
ConfigurableApplicationContext context = ...;
context.start();
```

It is not synonymous with calling `SpringApplication.run()` initially. In many typical Spring Boot applications, you rarely need to call `context.start()` directly.

### 5.3. `ContextStoppedEvent`

This event is published when calling:

```java
context.stop();
```

`stop()` signals a request to stop the lifecycle of the context and eligible lifecycle beans. It differs from `close()`: the context can still be restarted if the context type and state allow it.

### 5.4. `ContextClosedEvent`

This event is published when the application context closes:

```java
context.close();
```

This is a suitable milestone for a listener to log shutdown or perform necessary cleanup. However, bean callbacks such as `@PreDestroy`, `DisposableBean`, or destroy methods should be preferred for cleanup tied to a bean's own lifecycle.

You should not rely on `ContextClosedEvent` to call services that may already be destroyed or are in the middle of shutting down. Listeners should do brief work and avoid creating new beans while the context is closing.

## 6. How Do Spring Boot Events Differ from ApplicationContext Events?

| Criterion | `SpringApplicationEvent` | Context lifecycle event |
| --- | --- | --- |
| Source | Spring Boot's `SpringApplication` execution lifecycle | A `ApplicationContext`'s lifecycle in Spring Framework |
| Scope | Overall startup lifecycle at the Spring Boot level | A specific context |
| Examples | `ApplicationStartingEvent`, `ApplicationReadyEvent` | `ContextRefreshedEvent`, `ContextClosedEvent` |
| Can occur before context exists? | Yes, for early events | No, because events are tied to a context |
| Used to answer | Which startup milestone is the Boot app at? | Which lifecycle state is this context in? |

A Boot event can be dispatched to listeners through the application's event mechanism; meanwhile, startup also causes the context to publish its own events. They are related in time but are not the same category.

### 6.1. Comparing Easily Confused Milestones

```text
ContextRefreshedEvent
        |
        v
ApplicationStartedEvent
        |
        v
ApplicationRunner / CommandLineRunner
        |
        v
ApplicationReadyEvent
```

Therefore:

- Use `ContextRefreshedEvent` when you care that a context just refreshed.
- Use `ApplicationStartedEvent` when you care that startup has passed refresh but runners have not executed yet.
- Use `ApplicationReadyEvent` when you care that runners have finished.

If you only need to run code after a bean is initialized, you can use a bean lifecycle callback. If you need an application-wide milestone, choose the event matching the exact timing you want.

## 7. Registering Listeners with `ApplicationListener`

`ApplicationListener<E>` is Spring's standard interface:

```java
public interface ApplicationListener<E extends ApplicationEvent> {
    void onApplicationEvent(E event);
}
```

Example:

```java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;

@Component
public class ApplicationReadyListener
        implements ApplicationListener<ApplicationReadyEvent> {

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        System.out.println("Ready: " + event.getApplicationContext().getId());
    }
}
```

When the class is component-scanned and the context is initialized, Spring registers the listener to receive the corresponding event type.

### 7.1. Listeners for Early Events Must Be Registered Before the Context Exists

A listener created with `@Component` can only be registered when Spring processes bean definitions and initializes the listener bean. Therefore, it cannot receive events that occur before that point, such as `ApplicationStartingEvent`.

To receive early events, register the listener directly on `SpringApplication`:

```java
SpringApplication application =
        new SpringApplication(DemoApplication.class);

application.addListeners(new StartingListener());
application.run(args);
```

Listener example:

```java
public class StartingListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("Spring Boot is starting");
    }
}
```

Listeners can be registered through Spring Boot's appropriate factory metadata mechanism when developing libraries. For simple applications, `SpringApplication.addListeners(...)` is easy to see and control.

### 7.2. `setListeners()` and `addListeners()`

`SpringApplication` provides operations to both set the listener list and append listeners:

```java
application.addListeners(
        new StartingListener(),
        new EnvironmentPreparedListener()
);
```

`addListeners(...)` expresses the intent to add listeners to the existing configuration. If you use `setListeners(...)`, you are replacing the listener list via that setter; be careful not to accidentally overwrite listeners configured elsewhere.

## 8. Registering Listeners with `@EventListener`

For Spring-managed beans, `@EventListener` is usually more concise than implementing an interface:

```java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class StartupReporter {

    @EventListener
    public void onApplicationReady(ApplicationReadyEvent event) {
        System.out.println("Application ready");
    }
}
```

Spring detects methods annotated with `@EventListener` and registers them as listeners for their parameter's event type.

### 8.1. One Class Can Listen to Multiple Events

```java
@Component
public class LifecycleReporter {

    @EventListener
    public void onRefresh(ContextRefreshedEvent event) {
        System.out.println("Context refreshed");
    }

    @EventListener
    public void onClose(ContextClosedEvent event) {
        System.out.println("Context closing");
    }
}
```

Each method listens to a separate event type. This approach helps group related lifecycle reactions into a single component.

### 8.2. Listening by Supertype

A listener can accept a more general event type. For example, a method accepting `ApplicationEvent` can be invoked for many events in Spring's system, as long as the event is published within the scope where the listener is registered.

```java
@EventListener
public void onAnyApplicationEvent(ApplicationEvent event) {
    System.out.println(event.getClass().getSimpleName());
}
```

In real applications, broad listeners need to filter events carefully to avoid excessive logging or accidentally handling unrelated events.

### 8.3. `@EventListener` Can Publish Subsequent Events

A listener method can return an event/payload object; Spring will publish that result as a subsequent event according to `@EventListener`'s supported rules.

Conceptual example:

```java
@EventListener
public OrderAuditedEvent onOrderCreated(OrderCreatedEvent event) {
    return new OrderAuditedEvent(event.orderId());
}
```

In large applications, consider publishing events explicitly via `ApplicationEventPublisher` if the event flow needs to be easy to trace or if the method needs to return a different business result.

## 9. Publishing Custom Events with `ApplicationEventPublisher`

Spring provides `ApplicationEventPublisher` for beans to publish events:

```java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ApplicationEventPublisher publisher;

    public OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void createOrder(String orderId) {
        // Execute order creation logic
        publisher.publishEvent(new OrderCreatedEvent(orderId));
    }
}
```

The event class can be a simple object:

```java
public record OrderCreatedEvent(String orderId) {
}
```

Modern Spring allows publishing any object; custom events do not have to extend `ApplicationEvent`. When publishing an object that is not an `ApplicationEvent`, Spring can wrap it in a `PayloadApplicationEvent`.

Listener:

```java
@Component
public class OrderCreatedListener {

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Order created: " + event.orderId());
    }
}
```

`ApplicationEventPublisher` is the abstraction for publishing events; the service does not need to know specifically which listeners will receive them.

### 9.1. When Should You Use Custom Events?

Custom events are a good fit when a domain occurrence can trigger multiple independent reactions:

- An order is created.
- A user registers an account.
- A payment is confirmed.
- A profile is updated.
- A batch job finishes.

Name events after what happened, typically in the past tense such as `OrderCreatedEvent` or `PaymentConfirmedEvent`. This helps listeners understand that an event describes a fact, not a command requesting an action.

## 10. Are Events Processed Synchronously or Asynchronously?

Under common default configuration, Spring event listeners are invoked **synchronously** on the thread that publishes the event. This means:

```java
publisher.publishEvent(event);
```

typically does not return to the publisher until synchronous listeners finish.

Consequences:

- Slow listeners can slow down the business flow publishing the event.
- Exceptions from synchronous listeners can affect the event-publishing flow.
- In-process events do not automatically become a message queue or background task.

### 10.1. Running Listeners Asynchronously

One approach is combining `@Async` and `@EnableAsync`:

```java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
```

```java
@Component
public class EmailListener {

    @Async
    @EventListener
    public void sendEmail(OrderCreatedEvent event) {
        // Send email on an appropriate executor
    }
}
```

For production use, configure an executor with bounded threads/queues, handle exceptions, and monitor task status. `@Async` does not guarantee that work is durably persisted if the process stops abruptly.

If requirements demand guaranteed delivery, retries, or cross-process handling, consider a message broker or transactional outbox instead of relying solely on in-process events.

### 10.2. Synchronous Events Are Not Automatic Transactions

Publishing an event does not create a transaction and does not guarantee that a listener runs after transaction commit. If a listener reads data just written in a transaction, you need to understand transaction boundaries and when the listener is invoked.

Spring provides `@TransactionalEventListener` for cases where a listener needs to bind to a transaction phase:

```java
@Component
public class OrderNotificationListener {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void afterOrderCommitted(OrderCreatedEvent event) {
        // React after the transaction commits
    }
}
```

Listeners of this kind usually run only when an active matching transaction exists. You can configure `fallbackExecution` if you want handling when there is no transaction, but carefully weigh the business semantics before enabling it.

`AFTER_COMMIT` means the listener is called after transaction commit; it does not automatically turn an email or HTTP call into a durable operation. If the application needs to guarantee that an event is not lost between commit and message dispatch, consider a transactional outbox.

## 11. Listener Execution Order

If multiple listeners receive the same event, you can use `@Order` or `Ordered` to specify order within an event multicaster that supports ordering.

Example:

```java
@Component
@Order(10)
public class AuditListener {

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Audit order " + event.orderId());
    }
}
```

```java
@Component
@Order(20)
public class MetricsListener {

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Metric order " + event.orderId());
    }
}
```

For synchronous listeners on the same multicaster, listeners with a lower order value take precedence first. If listeners run asynchronously, the start or completion order of tasks should not be assumed sequential just because `@Order` is present.

Do not use ordering to express complex business dependencies between listeners. If listener B needs a result produced by listener A, consider an explicit workflow/coordinator or publishing a follow-up event after step A finishes.

## 12. Event Propagation in Parent-Child Contexts

Spring supports application context hierarchies. A child context can have a parent context. In this model, events published from a child can be forwarded up to the parent so listeners in the parent receive them.

```text
             Parent ApplicationContext
             (Shared listeners)
                      ^
                      | event from child forwarded up
                      |
             Child ApplicationContext
             (Web/API listeners)
```

Rules to remember:

- Events published in a child can propagate up to the parent.
- Events published in a parent do not automatically propagate down to children.
- Both contexts have their own event multicaster and listener beans.
- If the same listener is registered in multiple contexts, watch out for receiving the same event multiple times via registration/propagation paths.

Example:

```java
@Component
public class SharedAuditListener {

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Shared audit: " + event.orderId());
    }
}
```

If the listener resides in the parent context, it can receive events published from the child context via propagation. However, do not assume the parent can see listener beans registered only in the child.

## 13. Web Events and Other Events in Spring Boot

Beyond application lifecycle events, web applications also have specialized events:

| Event | Meaning |
| --- | --- |
| `ServletWebServerInitializedEvent` | Servlet web server has been initialized |
| `ReactiveWebServerInitializedEvent` | Reactive web server has been initialized |
| `RequestHandledEvent` | A request was handled in Spring web environments that support this event |

Example listening for a servlet server:

```java
import org.springframework.boot.web.context.WebServerInitializedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class WebServerReporter {

    @EventListener
    public void onWebServerInitialized(
            WebServerInitializedEvent event) {
        System.out.println(
                "Server port: " + event.getWebServer().getPort()
        );
    }
}
```

`WebServerInitializedEvent` is the parent type of specific server initialization events. When you want to receive only servlet or reactive server events, use the corresponding specific event type.

Server-initialized events are useful when ports are chosen dynamically, such as `server.port=0`. Reading the actual port from the web server event tells you which port the operating system assigned.

## 14. Choosing the Right Event for Your Goal

| Goal | Event or Mechanism to Consider |
| --- | --- |
| Record that the application started running very early | `ApplicationStartingEvent` |
| Read profiles/properties after Environment is prepared | `ApplicationEnvironmentPreparedEvent` |
| Observe a context that just refreshed | `ContextRefreshedEvent` |
| Perform work after context refresh but before runners | `ApplicationStartedEvent` |
| Perform work after runners complete | `ApplicationReadyEvent` |
| Record startup failure | `ApplicationFailedEvent` |
| Know the web server's actual assigned port | `WebServerInitializedEvent` or an appropriate subtype |
| Record context closing | `ContextClosedEvent` |
| React to an application domain event | Custom event via `ApplicationEventPublisher` |
| Handle domain events only after commit | `@TransactionalEventListener(AFTER_COMMIT)` |
| Enforce required business dependencies | Constructor injection and direct service calls |

Do not choose an event merely because its name sounds right. Determine whether your listener needs to run **before or after context refresh, before or after runners, before or after transaction commit**, and then pick the mechanism.

## 15. Combined Example: Recording the Startup Lifecycle

You can combine an early listener registered on `SpringApplication` with a listener inside the context.

### 15.1. Listener for Early Events

```java
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;

public class EarlyStartupListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("[1] Application starting");
    }
}
```

### 15.2. Listener for In-Context Events

```java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ContextLifecycleListener {

    @EventListener
    public void onContextRefreshed(ContextRefreshedEvent event) {
        System.out.println("[2] Context refreshed");
    }

    @EventListener
    public void onApplicationReady(ApplicationReadyEvent event) {
        System.out.println("[3] Application ready");
    }
}
```

### 15.3. Registering the Early Listener Before `run()`

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DemoApplication.class);

        application.addListeners(new EarlyStartupListener());
        application.run(args);
    }
}
```

`EarlyStartupListener` is registered before `run()` starts, so it can receive `ApplicationStartingEvent`. `ContextLifecycleListener` is a bean, so it only begins receiving events after being discovered and registered in the context.

Illustrative log order:

```text
[1] Application starting
[2] Context refreshed
[3] Application ready
```

Other startup logs may appear in between. In particular, if there are multiple contexts, `ContextRefreshedEvent` may appear multiple times.

## 16. Common Pitfalls and Misconceptions

### 16.1. `@Component` Listener Does Not Receive `ApplicationStartingEvent`

The cause is usually that listener beans are only registered after the context processes configuration. `ApplicationStartingEvent` happens earlier.

**Solution:** register the listener directly on `SpringApplication` before calling `run()`.

### 16.2. Using `ContextRefreshedEvent` to Assert the Application Is Ready

The context has refreshed, but `ApplicationRunner` and `CommandLineRunner` may not have run yet.

**Solution:** use `ApplicationReadyEvent` if you need the post-runner milestone.

### 16.3. Synchronous Listeners Slow Down Startup

An `ApplicationReadyEvent` listener may perform long-running work and block the event-publishing thread.

**Solution:** limit work inside the listener, or use an executor/async when clear error-handling and shutdown policies are in place.

### 16.4. Events Processed Twice in a Context Hierarchy

A listener may be registered in both parent and child, while events from the child propagate up to the parent.

**Solution:** identify which context the listener is registered in, check the context ID, and design a single responsible handler.

### 16.5. Using Events Instead of Transactions or Message Queues

In-process application events do not inherently guarantee durability, retries, or cross-instance delivery.

**Solution:** use `@TransactionalEventListener` when a transaction phase is needed; use a message broker/outbox when durable, cross-process delivery is required.

### 16.6. Assuming `ContextStoppedEvent` and `ContextClosedEvent` Are the Same

`stop()` and `close()` have different lifecycle meanings. Stop requests eligible lifecycle components to stop; close ends the context and triggers bean destruction.

**Solution:** choose the API based on whether you intend a temporary stop or context termination.

## 17. Testing Events

Event listeners should be tested to verify the right event types and behaviors.

### 17.1. Testing Custom Events with `ApplicationEventPublisher`

Listener example:

```java
@Component
public class OrderEventListener {
    private final List<String> received = new ArrayList<>();

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        received.add(event.orderId());
    }

    public List<String> receivedOrders() {
        return List.copyOf(received);
    }
}
```

A test can obtain the publisher and listener from the context:

```java
@SpringBootTest
class OrderEventTest {

    @Autowired
    ApplicationEventPublisher publisher;

    @Autowired
    OrderEventListener listener;

    @Test
    void listenerReceivesPublishedEvent() {
        publisher.publishEvent(new OrderCreatedEvent("ORD-100"));

        assertThat(listener.receivedOrders())
                .contains("ORD-100");
    }
}
```

This example assumes the listener runs synchronously under default configuration. If the listener uses `@Async`, the test needs to await the result with appropriate synchronization instead of asserting immediately.

### 17.2. Recording Startup Events

You can register a test listener via `SpringApplication.addListeners(...)` to collect startup milestones. When testing early events, do not rely solely on a `@Component` listener since it does not exist before the context is created.

### 17.3. Testing Context Lifecycle

You can create a context in a test, refresh it, and close it explicitly:

```java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();

context.register(TestConfiguration.class);
context.refresh();
context.close();
```

Listeners registered in the context can observe `ContextRefreshedEvent` and `ContextClosedEvent`. This is a way to test lifecycle behavior at the Spring Framework level without starting a full Spring Boot application.

## 18. Practice Exercises

### Exercise 1 — Record Spring Boot Startup Milestones

Create listeners for:

- `ApplicationStartingEvent`
- `ApplicationEnvironmentPreparedEvent`
- `ApplicationContextInitializedEvent`
- `ApplicationPreparedEvent`
- `ApplicationStartedEvent`
- `ApplicationReadyEvent`

Register the listeners needed for early events via `SpringApplication.addListeners(...)`. Print event names and compare their order of appearance.

### Exercise 2 — Compare `ContextRefreshedEvent` and `ApplicationReadyEvent`

Create two listeners, each logging a line. Add a `CommandLineRunner` that takes a short amount of time to finish.

Observe:

1. When does context refresh occur?
2. Between which events does the runner execute?
3. Does `ApplicationReadyEvent` appear before or after the runner?

### Exercise 3 — Create a Custom Event

Create `UserRegisteredEvent`, publish it from `UserService`, and write two listeners:

- `WelcomeEmailListener`
- `AuditListener`

Verify that both receive the same event without `UserService` calling the two listeners directly.

### Exercise 4 — Verify Early Listeners

Try registering an `ApplicationStartingEvent` listener with `@Component`. Observe whether the listener receives the event. Then switch to `SpringApplication.addListeners(...)` before `run()` and compare.

### Exercise 5 — Experiment with Synchronous and Asynchronous Events

Create a listener that logs start/end timestamps and a listener with `@Async`. Compare the threads and the return timing of `publishEvent()`.

Explain why an in-process async listener does not guarantee that work is durably persisted if the JVM stops.

### Exercise 6 — Experiment with Parent-Child Propagation

Create parent and child `ApplicationContext` instances. Register a listener in the parent, publish a custom event from the child, and observe whether the event is received. Then publish an event from the parent and inspect the child listener.

Explain the propagation direction and the risk of duplicate event handling when listeners are registered at multiple levels.

### Exercise 7 — Tie Events to Transactions

Create an `OrderCreatedEvent` published inside a `@Transactional` method. Write a regular `@EventListener` and a `@TransactionalEventListener(phase = AFTER_COMMIT)`.

Observe the difference when the transaction commits successfully versus when it rolls back. Explain why regular events do not automatically wait for transaction commit.

## 19. Key Takeaways

`SpringApplicationEvent` describes milestones in Spring Boot's startup lifecycle, from `ApplicationStartingEvent` to `ApplicationReadyEvent` or `ApplicationFailedEvent`. Standard `ApplicationContext` events such as `ContextRefreshedEvent`, `ContextStartedEvent`, `ContextStoppedEvent`, and `ContextClosedEvent` describe the lifecycle of each individual context.

Choose the event matching the exact milestone you need to react to: Environment ready, context refreshed, runners completed, or context closing. Early listeners must be registered before the context exists; in-context listeners can use `ApplicationListener` or `@EventListener`. By default, events are typically processed synchronously, whereas async and transaction-bound listeners require explicit configuration and clear semantics.

Events help reduce direct coupling between publishers and listeners, but they do not replace dependency injection, transaction managers, or message brokers. When you understand event types, publication timing, and context scope, you can extend a Spring Boot application along its lifecycle cleanly and predictably.
