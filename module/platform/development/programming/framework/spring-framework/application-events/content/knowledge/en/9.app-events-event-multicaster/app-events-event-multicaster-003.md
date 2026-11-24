# `SimpleApplicationEventMulticaster` in Spring Framework

## 1. Role and Position in the Application Events Mechanism

`SimpleApplicationEventMulticaster` is the default implementation of the `ApplicationEventMulticaster` interface in a Spring `ApplicationContext`. Its job is **to find listeners matching an event and deliver the event to those listeners**. It extends `AbstractApplicationEventMulticaster`, which provides listener registration, management, and filtering.

Components to distinguish:

- **Publisher**: application code calling `ApplicationEventPublisher.publishEvent(event)` or `ApplicationContext.publishEvent(event)`.
- **ApplicationContext**: receives the event-publishing request and delegates to the context's multicaster.
- **`SimpleApplicationEventMulticaster`**: selects listeners compatible with the event type and decides how each listener is invoked.
- **Listener**: a bean implementing `ApplicationListener<E>` or a method annotated with `@EventListener`; performs business logic when receiving the event.

Typical processing flow after the context has initialized:

```text
Service -> publishEvent(event)
        -> ApplicationContext
        -> ApplicationEventMulticaster.multicastEvent(...)
        -> filter matching ApplicationListeners
        -> invoke each listener (synchronously or via Executor)
```

Each `ApplicationContext` has its own multicaster. If no bean with the exact name `applicationEventMulticaster` is declared, Spring creates a default `SimpleApplicationEventMulticaster`. A custom bean with a different name will not automatically replace the context's multicaster.

**Scope:** This is an event-passing mechanism **within the same application/context**, not a message broker. It does not durably persist events on its own, does not guarantee delivery if the process crashes, and does not provide retries, dead-letter queues, or cross-service event delivery. When those characteristics are needed, consider Spring Integration or a dedicated messaging system.

## 2. Default Behavior: Synchronous on the Event-Publishing Thread

When `taskExecutor` is not configured, the multicaster behaves equivalently to `SyncTaskExecutor`: each listener is invoked directly on **the thread calling `publishEvent()`**.

For example, if thread `http-nio-8080-exec-1` publishes `OrderCreated`, the listener runs on that same thread by default. `publishEvent()` returns only after the relevant synchronous listeners complete or a listener throws an error that interrupts the process. Consequently, a slow listener can increase request response time or hold a transaction thread for too long.

The advantage of the synchronous default is that ordering and errors are easy to verify, and because the listener runs on the same thread, it can see thread-bound context at the time of publishing (such as transaction context or MDC, if present). You should not assume by default that the listener only runs after the transaction commits: that is the specific semantics of `@TransactionalEventListener`.

### Standalone Runnable Java 17+ Example: Synchronous Event Publishing and Receiving

Create a Gradle project with the structure:

```text
spring-event-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/EventDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-event-demo'
```

`build.gradle` (example pinned to Spring Framework 6.2.12 and JDK 17 or higher):

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
}

application {
    mainClass = 'demo.EventDemo'
}
```

`src/main/java/demo/EventDemo.java`:

```java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class EventDemo {

    record OrderCreated(String orderId) {}

    static class OrderObserver {
        @EventListener
        public void onOrderCreated(OrderCreated event) {
            System.out.println("listener: " + event.orderId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {
        @Bean
        OrderObserver orderObserver() {
            return new OrderObserver();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            System.out.println("before publish");
            context.publishEvent(new OrderCreated("A-42"));
            System.out.println("after publish");
        }
    }
}
```

Run with JDK 17+ and Gradle installed:

```bash
gradle -q run
```

`stdout` output of the three `println` calls:

```text
before publish
listener: A-42
after publish
```

`OrderCreated` is a plain Java record; it does not need to extend `ApplicationEvent`. Spring allows publishing any object; internally, the framework can wrap the object in a `PayloadApplicationEvent` and still route it properly to the `@EventListener` method accepting `OrderCreated`. The order of the three lines above shows that the synchronous listener finishes before `publishEvent()` returns.

If you use `ApplicationListener<E>` directly, `E` is typically a type extending `ApplicationEvent`; for a payload not extending that class, you can use `ApplicationListener<PayloadApplicationEvent<OrderCreated>>` or `@EventListener` as in the example.

## 3. Main APIs and How Spring Selects Listeners

| API | Purpose |
| --- | --- |
| `multicastEvent(ApplicationEvent event)` | Dispatches an event to compatible listeners. |
| `multicastEvent(ApplicationEvent event, ResolvableType eventType)` | Dispatches with specific type information, useful when generics need to be resolved. |
| `setTaskExecutor(Executor executor)` | Sets the listener execution strategy. Without it, execution is synchronous. |
| `setErrorHandler(ErrorHandler handler)` | Chooses how to handle a `Throwable` thrown by a listener. |
| `addApplicationListener(...)`, `addApplicationListenerBean(...)` | Registers a listener (inherited from the base class). |
| `removeApplicationListener(...)` and other remove APIs | Unregisters a registered listener (inherited). |

When receiving an event, the multicaster uses the actual event type and `ResolvableType` information if available to retrieve matching listeners. A listener of type `ApplicationListener<OrderCreatedEvent>` is only called for events matching that type; `@EventListener` methods are also converted by Spring into appropriate listeners via annotation infrastructure. `SimpleApplicationEventMulticaster` itself is not what scans `@Component` or reads all annotations in the application.

Some useful details:

- `@Order` on an `@EventListener` method or the `Ordered` interface helps order **invoking / submitting tasks to the executor**. When running asynchronously, **completion** order is still not guaranteed.
- One event can have multiple listeners; there is no aggregated return value from `publishEvent()`.
- A listener can publish additional events. With a synchronous model, nested event-publishing chains must avoid infinite recursion and time-consuming operations.
- When using complex generic types, declare explicit event types or use `ResolvableTypeProvider` if needed so Spring can distinguish type parameters.

## 4. Configuring `taskExecutor`: Moving Eligible Listeners to Another Thread

You can replace the default multicaster with a bean named **exactly** `applicationEventMulticaster` and attach a `ThreadPoolTaskExecutor`. The following example is a complete configuration class, placed in `src/main/java/demo/AsyncEventsConfig.java` of a Spring project with the `spring-context` dependency:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ApplicationEventMulticaster;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.context.support.AbstractApplicationContext;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class AsyncEventsConfig {

    @Bean
    ThreadPoolTaskExecutor eventTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("app-event-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }

    @Bean(name = AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME)
    ApplicationEventMulticaster applicationEventMulticaster(
            ThreadPoolTaskExecutor eventTaskExecutor) {

        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();
        multicaster.setTaskExecutor(eventTaskExecutor);
        multicaster.setErrorHandler(error ->
                System.err.println("Event listener failed: " + error));
        return multicaster;
    }
}
```

When using this example, include `AsyncEventsConfig.class` in the application's context configuration (for example, registering it alongside other configuration classes). Spring manages initialization and shutdown of the `ThreadPoolTaskExecutor` bean; you do not need to call `initialize()` manually for a Spring-managed bean.

**Important point:** Having an `Executor` does not mean *every* listener runs asynchronously. Since Spring Framework 6.1, `ApplicationListener.supportsAsyncExecution()` tells the multicaster whether the listener allows invocation via an executor. The default value is `true`; a listener returning `false` must still be invoked on the event-publishing thread. `TransactionalApplicationListener` is a key example of a case that does not support offloading transaction-synchronization registration to another thread.

Overview of the execution path:

```text
multicastEvent(event)
  └─ for each matching listener:
       ├─ has Executor and supportsAsyncExecution() == true
       │    └─ executor.execute(() -> invokeListener(listener, event))
       └─ does not meet the conditions above
            └─ invokeListener(listener, event) on the current thread
```

For listeners running in the pool, `publishEvent()` typically only waits until **submitting the task** to the executor, not until processing completes. Completion timing and log output order across multiple listeners can vary between runs. Some listeners still run synchronously as noted above. You also need to account for task rejection policies when the pool is overloaded or shutting down; calling `publishEvent()` successfully cannot be treated as a guarantee that asynchronous business work has completed.

### Resource and Thread-Context Considerations

- Bound the thread count and queue length; monitor backlog, latency, and failed tasks. A pool with a bounded queue can still become overloaded.
- Transaction context, `ThreadLocal`, security context, request context, and MDC are **not automatically** carried over to the new thread. If context propagation is needed, use an appropriate mechanism such as `TaskDecorator` / context propagation, and pass only necessary data.
- Do not rely on the publisher's JPA/Hibernate session, entity lazy loading, or transaction inside a listener on another thread. Pass required IDs/data snapshots and open a separate transaction scope if business logic requires it.
- Regular `@EventListener` offers no durability guarantees. Design idempotency, event storage/outbox, or a dedicated queue if losing tasks is unacceptable.
- Ensure the shutdown strategy handles in-flight tasks within an appropriate timeout; the example above waits at most 10 seconds and does not provide a delivery guarantee.

## 5. `setErrorHandler`: Synchronous vs. Asynchronous Errors Differ

If there is **no** `ErrorHandler`, a synchronous listener throwing a `RuntimeException` can cause the `publishEvent()` call to rethrow it and stop dispatching the event to subsequent listeners in that multicast pass. This behavior must be considered when listeners are not allowed to break the main flow.

If an `ErrorHandler` is attached, `SimpleApplicationEventMulticaster` delegates listener errors to `handleError(Throwable)`. A handler that only logs and returns will **swallow the error at the multicaster boundary**; therefore, other listeners can continue to be invoked. If the handler rethrows the error, the synchronous call can still fail. `TaskUtils.LOG_AND_SUPPRESS_ERROR_HANDLER` and `TaskUtils.LOG_AND_PROPAGATE_ERROR_HANDLER` are two built-in strategies available for reference.

When listeners run via an executor, exceptions occurring in a task on another thread normally **do not** return directly to the thread calling `publishEvent()`. Log sufficient event information, emit metrics/alerts, and design appropriate retry or compensation policies; merely printing errors to `stderr` as in the configuration snippet above is a minimal illustration.

| Configuration | Thread running eligible listener | Impact of listener error |
| --- | --- | --- |
| Default, no handler | Publisher thread | Error can propagate to publisher and interrupt multicast |
| Synchronous, log/suppress handler | Publisher thread | Handler receives error; invoking other listeners can continue |
| Asynchronous executor, no handler | Pool thread | Error stays in task/executor, not guaranteed to reach publisher |
| Asynchronous executor, log/suppress handler | Pool thread | Handler records error; publisher typically does not wait for handling |

## 6. Distinguishing from `@Async` and `@TransactionalEventListener`

### `@Async` on Individual Listeners

If you only want a single method to execute on another thread instead of configuring the entire multicaster, you can use:

```java
@EnableAsync
@Configuration
class AsyncConfig {
}

@Component
class NotificationListener {
    @Async
    @EventListener
    public void onOrderCreated(OrderCreated event) {
        // Send notification on @Async's executor.
    }
}
```

This snippet **only illustrates the configuration and listener**, using the `OrderCreated` type from the application; it requires the corresponding imports (`EnableAsync`, `Configuration`, `Component`, `Async`, `EventListener`) and a Spring context managing the beans. `@EnableAsync` activates `@Async` processing infrastructure. Exceptions in asynchronous methods have their own handling mechanism such as `AsyncUncaughtExceptionHandler`; an asynchronous listener method cannot use its return value to publish a follow-up event the way a synchronous `@EventListener` can. When the global multicaster is already configured to run on a pool, consider avoiding unnecessary stacking of `@Async`.

### Transaction-Bound Listeners

`@TransactionalEventListener` handles events in the `AFTER_COMMIT` phase by default. It needs to register a callback with the active transaction at the time of publishing, so transaction-synchronized listeners are not arbitrarily moved entirely to another thread by the multicaster. Without a suitable transaction, the listener does not run by default unless `fallbackExecution = true` is set. You should not use a plain `@EventListener` and expect it to run only after commit.

If you need to send an email after an order commits, one option is `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`; if asynchronous processing is also needed after commit, explicitly design `@Async`/an executor in the post-transaction processing step and manage errors for that step. For critical data requiring guaranteed delivery, combine with a transactional outbox or persistent broker.

## 7. Testing and Common Configuration Mistakes

**Testing synchronous behavior:** Publish the event with `context.publishEvent(...)`, then assert listener state/spies right after the call. In real applications, also test scenarios where a listener throws an error and rollback rules if transactions are involved.

**Testing asynchronous behavior:** Do not assert log order or use `Thread.sleep(100)` to wait. Use `CountDownLatch`, `CompletableFuture`, Awaitility, or a synchronization mechanism with a timeout to wait for the listener to finish; then verify data and errors. When reproducing pool errors, also test queue bounds and shutdown behavior.

Common misconceptions:

1. **Wrong bean name:** `@Bean("customMulticaster")` does not replace the `applicationEventMulticaster` used by `ApplicationContext`.
2. **Assuming `publishEvent()` is always asynchronous:** it is synchronous by default; only listeners supporting async are offloaded to the configured executor.
3. **Assuming `@Order` guarantees completion order across threads:** it only orders task selection/submission, while completion time depends on scheduling.
4. **Swallowing exceptions and treating business work as successful:** an `ErrorHandler` can log and continue, but listener failures still need handling and monitoring.
5. **Reading transaction/MDC on a pool thread as on the publisher thread:** thread-bound contexts do not carry over automatically to another thread.
6. **Using internal events instead of a message queue:** the multicaster does not natively provide durable storage, retries, consumer groups, or multi-instance guarantees.
7. **Forgetting executor lifecycle:** the application can exit or shut down while tasks are still running; configure resource shutdown and timeouts.
8. **Mixing `@Async`, a global executor, and transactional listeners without clear boundaries:** clearly determine which callback runs on which thread and where errors go.

## 8. When to Use Which Approach?

- **Default synchronous:** short, in-memory reactions that need straightforward control and do not block the thread.
- **`SimpleApplicationEventMulticaster` + `ThreadPoolTaskExecutor`:** many independent listeners eligible to run concurrently, where asynchrony is acceptable and load/error control plans are in place.
- **`@Async @EventListener`:** only a few listeners need background processing, while keeping most other listeners synchronous.
- **`@TransactionalEventListener`:** the action must be tied to transaction commit/rollback outcomes; pick the right phase before considering async.
- **Broker/outbox:** business-critical events requiring durable delivery or crossing multiple services.

Official references:

- [Spring Framework: `SimpleApplicationEventMulticaster` API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework: ApplicationContext Events, `@EventListener`, and Multicaster](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework: Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework: `TransactionalApplicationListener` API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionalApplicationListener.html)
