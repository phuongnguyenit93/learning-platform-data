# Configuring ApplicationEventMulticaster via Bean in Spring Framework

## 1. Objective and Context

In Spring Framework, an application publishes events through `ApplicationEventPublisher.publishEvent(...)`; the receiving side uses `ApplicationListener` or `@EventListener` methods. The component responsible for dispatching events to matching listeners is **`ApplicationEventMulticaster`**.

Normally you do not need to create a multicaster yourself: `ApplicationContext` provides a `SimpleApplicationEventMulticaster` automatically. However, when you need to control how listeners execute and how errors are handled at the event-dispatching level, you can **declare a bean with the exact name `applicationEventMulticaster`**.

After this lesson, you will be able to:

- Explain how `ApplicationContext` selects the default multicaster or an application-provided bean.
- Declare the `applicationEventMulticaster` bean using Java Configuration and know how to use it with Spring Boot.
- Configure `SimpleApplicationEventMulticaster#setTaskExecutor(...)` for synchronous execution or dispatching via a thread pool.
- Configure `setErrorHandler(...)` and understand its impact on event publishing when a listener throws an exception.
- Run a Java 17+ example with a custom-declared multicaster bean, measure its output, and identify risks with async, transactions, and thread resources.

## 2. Where Does the Multicaster Sit in the Event Flow?

~~~text
Service / component
      |
      | publishEvent(event)
      v
ApplicationEventPublisher
(usually the ApplicationContext itself)
      |
      v
ApplicationEventMulticaster
      | finds listeners matching the event type
      | orders listener calls if Ordered/@Order is present
      | selects executor and handles errors per configuration
      |
      +----> Listener A
      +----> Listener B
      +----> Listener C
~~~

`ApplicationEventPublisher` is the API to **publish** events. `ApplicationEventMulticaster` is the internal strategy inside the context to **dispatch** an event to registered listeners. Typically, business code still depends only on `ApplicationEventPublisher`, while multicaster bean configuration lives in the application configuration layer.

`AbstractApplicationContext` defines the constant:

~~~java
AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME
~~~

The value of this constant is **`"applicationEventMulticaster"`**. During context initialization, Spring searches for a bean with **that exact name** and requires its type to be compatible with `ApplicationEventMulticaster`. If absent, the context creates a default `SimpleApplicationEventMulticaster`.

This is a **by-bean-name** convention, not merely by type:

- Bean named `applicationEventMulticaster`, type `SimpleApplicationEventMulticaster` → used to dispatch events for the context.
- Bean of type `SimpleApplicationEventMulticaster` named `myEventMulticaster` → does not automatically replace the context's internal multicaster just because the type matches.
- `@Primary` on a bean with a different name also does not override the rule of looking up the name `applicationEventMulticaster`.
- Using the right name with a type that is not `ApplicationEventMulticaster` → the context will not initialize normally.

With `@Bean` Java Config, the least error-prone approach is using the constant provided by Spring directly:

~~~java
@Bean(name = AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME)
SimpleApplicationEventMulticaster applicationEventMulticaster() {
    return new SimpleApplicationEventMulticaster();
}
~~~

The snippet above is a **configuration fragment**; it must be placed in a `@Configuration` class with complete imports; a standalone runnable example is in section 5. Simply declaring the bean like this leaves behavior almost identical to the default; the real value usually lies in configuring the **executor** and **error handler**.

## 3. Two Main Configuration Options

### 3.1. `setTaskExecutor(...)`: Which Thread Are Listeners Invoked On?

By default, `SimpleApplicationEventMulticaster` invokes listeners on **the thread publishing the event**, equivalent to using `SyncTaskExecutor`. For standard synchronous listeners:

~~~text
publisher thread:
  publishEvent -> listener A (done)
               -> listener B (done)
               -> listener C (done)
               -> returns to publisher
~~~

The advantage is easy tracing, easily verifiable ordering, and typically preserving the calling thread's context. In return, a long-running listener holds up the entire `publishEvent(...)` call.

If you pass a truly asynchronous executor, such as `ThreadPoolTaskExecutor`, the multicaster **schedules invocations** for listeners that allow async execution:

~~~text
publisher thread:
  publishEvent -> submit A -> submit B -> submit C -> returns

event worker threads:
  A processes ...
  B processes ...
  C processes ...
~~~

This does not guarantee listeners start or finish in the same order. Listeners can run concurrently; completion timing depends on the thread pool, queue, execution duration, and errors.

Since Spring Framework 6.1, the `ApplicationListener#supportsAsyncExecution()` API allows a listener to declare that it **does not support** being invoked by the multicaster on another thread. Transaction-synchronized listeners, such as `TransactionalApplicationListener` types, are an important example: they need to run their transaction-synchronization registration on the event-publishing thread. Therefore, **you must not infer that every listener moves to the thread pool simply because an executor was set**.

Additionally, `@Async` placed on an `@EventListener` method is a method-level async mechanism, distinct from configuring an executor on the multicaster. Understand the task flow and error handling of each mechanism before combining them.

### 3.2. `setErrorHandler(...)`: What Happens When a Listener Throws an Exception?

With synchronous listeners and **no `ErrorHandler` configured**, an unhandled exception normally propagates back up to the `publishEvent(...)` call, stopping the current dispatch pass. If the multicaster is configured with an async executor, the exception can occur on the executor's thread and not return to the publisher as in the synchronous case.

`SimpleApplicationEventMulticaster#setErrorHandler(...)` accepts an `org.springframework.util.ErrorHandler`:

~~~java
multicaster.setErrorHandler(error -> {
    // Record / classify the error and decide how to handle it.
});
~~~

This is a **configuration fragment**, not a complete bean definition. Spring also provides two built-in policies in `org.springframework.scheduling.support.TaskUtils`:

| Policy | Meaning |
| --- | --- |
| No `ErrorHandler` | If a listener throws an exception, it is not swallowed by the multicaster; when synchronous, it can propagate to the publisher and halt the current multicast |
| `TaskUtils.LOG_AND_SUPPRESS_ERROR_HANDLER` | Logs and then **swallows** the exception; remaining listeners still have a chance to be invoked |
| `TaskUtils.LOG_AND_PROPAGATE_ERROR_HANDLER` | Logs and then **rethrows** the exception; whether the error reaches the publisher still depends on sync/async |
| Custom `ErrorHandler` | Defines how errors are recorded and whether to rethrow or swallow; must have an explicit policy |

**Caution:** "Swallowing exceptions" can make the publisher believe the process succeeded even though a listener failed. Use this only when listeners are truly independent and proper logging/monitoring/retry mechanisms exist. The multicaster's error handler also does not automatically catch errors occurring **later** in a task that a listener scheduled itself via `@Async`.

## 4. Which Configuration Should You Choose?

| Need | Suggested configuration | What must be verified |
| --- | --- | --- |
| Default, no special requirements | No bean needed; use default multicaster | Does any listener run long and block the publisher? |
| Keep synchronous but control errors | Declare `applicationEventMulticaster` and `setErrorHandler(...)` | Are errors propagated or swallowed? Do subsequent listeners run after an error? |
| Dispatch independent processing via thread pool | `applicationEventMulticaster` bean with Spring-managed `ThreadPoolTaskExecutor` | Thread pool, queue, shutdown, thread context, and completion order |
| Listener needs a transaction phase | Use `@TransactionalEventListener` with the right phase | Do not force async when registration needs the publisher's transaction |
| Need durable delivery and retries across app stops | Design a dedicated outbox/message broker | Internal multicaster does not replace a durable queue |

For business logic with a strict dependency like "B must succeed after A", an explicit processing sequence invoked from a service is easier to control than configuring a concurrent multicaster and hoping event order suffices.

## 5. Complete Java 17+ Example: Multicaster Bean and ErrorHandler

This example uses **plain Spring Framework**, without Spring Boot, databases, or external APIs. We deliberately configure `SyncTaskExecutor` so **execution output has a clear order**, while setting an `ErrorHandler` to simulate one listener failing while the publisher continues dispatching to the next listener.

### 5.1. Directory Structure and Gradle

~~~text
multicaster-bean-demo/
├── build.gradle
└── src/
    └── main/
        └── java/
            └── demo/
                └── EventMulticasterBeanDemo.java
~~~

Contents of `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.15'
}

application {
    mainClass = 'demo.EventMulticasterBeanDemo'
}
~~~

`spring-context` pulls in the required Spring libraries via Gradle. Spring Framework 6.2.x requires Java 17 or higher; the example uses Java 17 or higher. In real Spring Boot projects, let Boot's dependency management choose the compatible Spring version rather than pinning a different version manually.

### 5.2. Source Code `EventMulticasterBeanDemo.java`

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.context.support.AbstractApplicationContext;
import org.springframework.core.annotation.Order;
import org.springframework.core.task.SyncTaskExecutor;

public class EventMulticasterBeanDemo {

    // Spring can publish a POJO/record as an event payload.
    public record Registered(String username) {}

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean(name =
                AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME)
        public SimpleApplicationEventMulticaster applicationEventMulticaster() {
            SimpleApplicationEventMulticaster multicaster =
                    new SimpleApplicationEventMulticaster();

            // Runs on the event-publishing thread; equivalent to default
            // executor behavior, set explicitly here to learn configuration.
            multicaster.setTaskExecutor(new SyncTaskExecutor());

            // Learning example: print error and do not rethrow.
            multicaster.setErrorHandler(error ->
                    System.out.println("handled: "
                            + error.getClass().getSimpleName()
                            + ": " + error.getMessage()));

            return multicaster;
        }

        @Bean
        public Handlers handlers() {
            return new Handlers();
        }
    }

    public static class Handlers {

        @EventListener
        @Order(-10)
        public void first(Registered event) {
            System.out.println("listener -10: " + event.username());
        }

        @EventListener
        @Order(0)
        public void fail(Registered event) {
            throw new IllegalStateException("demo failure");
        }

        @EventListener
        @Order(10)
        public void last(Registered event) {
            System.out.println("listener 10: " + event.username());
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            Object registeredMulticaster = context.getBean(
                    AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME);

            System.out.println("multicaster bean = "
                    + registeredMulticaster.getClass().getSimpleName());

            System.out.println("publisher: before");
            context.publishEvent(new Registered("Mai"));
            System.out.println("publisher: after");
        }
    }
}
~~~

Key points to observe in the code:

1. `AppConfig` is the configuration loaded by `AnnotationConfigApplicationContext` during initialization.
2. The `@Bean` method is assigned the **exact name** using the `APPLICATION_EVENT_MULTICASTER_BEAN_NAME` constant, so the context uses it as the internal multicaster.
3. `Registered` is a Java record. Spring can publish any object as an event payload; extending `ApplicationEvent` is not required.
4. `Handlers` is a bean containing three `@EventListener` methods with different orders.
5. The middle handler throws `IllegalStateException`. Our configured `ErrorHandler` handles the error and **does not rethrow**, so the last listener is still invoked.

### 5.3. Running and Output

From the `multicaster-bean-demo` directory, with JDK 17+ and Gradle installed:

~~~bash
gradle run
~~~

If a Gradle Wrapper is present, use `./gradlew run` on Linux/macOS or `gradlew.bat run` on Windows instead of `gradle run`.

Lines explicitly printed by the application **in order**:

~~~text
multicaster bean = SimpleApplicationEventMulticaster
publisher: before
listener -10: Mai
handled: IllegalStateException: demo failure
listener 10: Mai
publisher: after
~~~

Gradle may emit additional build logs; the block above shows only the `System.out.println` lines from the example.

Because listeners run synchronously, `publishEvent` returns only after the last listener. If you remove `multicaster.setErrorHandler(...)` while keeping the `fail` listener, the error propagates out of the `publishEvent` call; the lines `listener 10: Mai` and `publisher: after` are no longer executed along the normal path. This is a clear way to verify the effect of configuring the multicaster bean for errors.

**Boundary of the example:** printing and swallowing errors is solely to illustrate control flow. In real deployments, log with context and define which cases are allowed to continue and which must report errors back to the caller.

## 6. Async Configuration with Bean and ThreadPoolTaskExecutor

When a listener handles independent work, such as sending notifications or auxiliary calculations that do not need to block the publisher, you can choose a dedicated thread pool for events. To avoid creating unbounded threads, configure core size, max size, and queue capacity suited to actual load.

**This is a replacement configuration for the synchronous `AppConfig` in section 5**; you cannot declare two beans named `applicationEventMulticaster` in the same context. Place the following in a configuration class of a Spring application that already has listeners:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.context.support.AbstractApplicationContext;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.support.TaskUtils;

@Configuration(proxyBeanMethods = false)
public class AsyncEventConfiguration {

    @Bean("eventTaskExecutor")
    public ThreadPoolTaskExecutor eventTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("app-event-");
        return executor;
    }

    @Bean(name =
            AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME)
    public SimpleApplicationEventMulticaster applicationEventMulticaster(
            @Qualifier("eventTaskExecutor")
            ThreadPoolTaskExecutor executor) {

        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();

        multicaster.setTaskExecutor(executor);

        // Policy example: log error then rethrow on the execution thread.
        multicaster.setErrorHandler(
                TaskUtils.LOG_AND_PROPAGATE_ERROR_HANDLER);

        return multicaster;
    }
}
~~~

This snippet is a **configuration to integrate into an existing application** (not a standalone Java program). When adding it to a project, the class must be within component-scan scope or imported via `@Import(AsyncEventConfiguration.class)`. Does it use APIs from `spring-context` and `spring-context-support`? **`spring-context-support` is not needed** here; both `ThreadPoolTaskExecutor` and `TaskUtils` belong to `spring-context`. Declaring the executor as a Spring-managed bean lets the framework initialize and manage the thread pool's lifecycle; do not create a new pool with `new ThreadPoolTaskExecutor()` on every event publication.

The numbers `2 / 4 / 100` are examples, **not default parameters suitable for every system**. Tune them based on task duration, load level, queue tolerance, and overload policies.

**Important impacts of async configuration:**

- `publishEvent(...)` may finish before async listeners finish their work. Therefore, do not write code assuming "`publishEvent` finished means the email was sent".
- `@Order` can still determine **dispatch/submission** order, but does not guarantee tasks complete in order.
- Exceptions occurring on worker threads normally **do not return to the publisher thread**. `LOG_AND_PROPAGATE_ERROR_HANDLER` logs and rethrows within the listener-invocation context; it does not turn async errors into synchronous exceptions for the publisher.
- Under overload, the executor can reject tasks or apply a custom rejection policy. Monitor rejected tasks, queue depth, active threads, and shutdown policies; do not assume every event is processed successfully.
- `ThreadLocal`, logging MDC, security context, and transaction context on the publisher do not naturally travel with a task to another thread. For required data, pass it via an immutable event payload or use an explicitly configured context-propagation mechanism; **do not rely on the current transaction existing on the worker thread**.
- Some listeners that do not support async at the multicaster level still run on the event-publishing thread; this behavior preserves the semantics of those listeners.

If you genuinely need to wait to verify async tasks in tests, use `CountDownLatch` or a waiting mechanism with an explicit timeout. Do not evaluate success based on `Thread.sleep(100)`, as schedulers and CI machines vary.

## 7. Configuration in a Spring Boot Application

In Spring Boot, declaring the bean remains the same as in Spring Framework: place the `@Configuration` class in Boot's component-scan scope (or import it) and use the exact name `applicationEventMulticaster`. You do not need to call `context.addApplicationListener(...)` manually for normally discovered `@EventListener` methods.

Short example for Boot:

~~~java
@Configuration(proxyBeanMethods = false)
public class EventsConfig {

    @Bean(name = "applicationEventMulticaster")
    public SimpleApplicationEventMulticaster applicationEventMulticaster() {
        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();
        multicaster.setErrorHandler(
                TaskUtils.LOG_AND_SUPPRESS_ERROR_HANDLER);
        return multicaster;
    }
}
~~~

This snippet is for **integrating into a Boot application** and needs the corresponding Spring imports. With Boot, let the starter/BOM manage the Spring version and avoid manually pinning mismatched `spring-context` versions. You can stay synchronous and only customize `ErrorHandler`; configuring a thread pool is a separate, optional choice.

Common sources of confusion:

- Declaring `@Bean("myMulticaster")` and thinking Boot changed the internal dispatcher: that is not the name the context looks up.
- Creating `SimpleApplicationEventMulticaster` with `new` in a service and calling it manually: that instance does not automatically know about container-managed listeners.
- Adding `@EnableAsync` merely to make the multicaster use an executor: `@EnableAsync` enables `@Async` processing, and does not automatically replace `applicationEventMulticaster` with an asynchronous multicaster.
- Configuring both an async multicaster and `@Async` on listeners without analyzing two-layer scheduling.
- Defining two beans named `applicationEventMulticaster` in different configurations: depending on context settings, the application may fail with a duplicate bean definition error or override one configuration unintentionally.

## 8. If the Project Uses XML Bean Configuration

The **bean-name** rule also applies when configuring with XML. The snippet below is **a configuration fragment** of a Spring XML file with the `beans` namespace declared, where `eventTaskExecutor` is defined elsewhere:

~~~xml
<bean id="applicationEventMulticaster"
      class="org.springframework.context.event.SimpleApplicationEventMulticaster">
    <property name="taskExecutor" ref="eventTaskExecutor"/>
</bean>
~~~

If you want to keep synchronous execution, omit the `taskExecutor` property or declare an appropriate `SyncTaskExecutor`. For new projects using Java Configuration/Spring Boot, `@Bean` is usually easier to track and verify in Java. Do not have XML and Java both define different multicasters in the same context without an agreed unified configuration strategy.

## 9. Interaction with @Order, @Async, and Transactions

### 9.1. Listener Ordering

If a listener has `@Order` or implements `Ordered`, Spring uses the order value when preparing the matching listener list. **Lower numbers have higher priority**: `-10` before `0` before `10`. However, if an asynchronous executor is used, list ordering only affects the order of calling `executor.execute(...)`; **completion order** is not guaranteed. Listeners with the same order level should not be designed with implicit dependencies.

### 9.2. Method-Level `@Async`

`@Async` on `@EventListener` requires Spring's async support (`@EnableAsync` or equivalent configuration). When a listener runs via `@Async` on its own, errors occurring inside the delegated task have their own notification/monitoring mechanism; the multicaster's `ErrorHandler` does not replace the error handler for `@Async` tasks after control has already been returned.

Not every application needs async at both levels. Usually choose one intentional strategy: async only on individual listeners, or an executor for many eligible listeners.

### 9.3. `@TransactionalEventListener`

`@TransactionalEventListener` binds event handling to a transaction phase, defaulting to `AFTER_COMMIT`. It is not merely an `@EventListener` with a special `@Order`.

- Transactional listeners need to register synchronization with the original transaction on the appropriate thread; therefore, this type of listener is marked as not supporting the multicaster automatically offloading it to an async executor at the registration step.
- If published when **no transaction** is active, `@TransactionalEventListener` is not triggered by default unless `fallbackExecution = true` is enabled.
- Post-commit handling is subject to resource/transaction access rules of that phase; do not assume a task running in a thread pool still holds the publisher's transaction.
- To send an outbound message **only after a successful commit**, use the right phase, and if reliable delivery across application crashes is required, design an outbox.

Illustrative annotation example:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(Registered event) {
    // Execute only after commit within a valid transaction.
}
~~~

This is an illustrative snippet requiring `spring-tx`, imports for `TransactionPhase` and `TransactionalEventListener`, a configured transaction manager, and the corresponding `Registered` class; it is not part of the standalone runnable example in section 5.

## 10. Common Configuration Mistakes and How to Diagnose Them

| Symptom | Common cause | How to check or fix |
| --- | --- | --- |
| Multicaster declared, yet listeners still run synchronously | Bean name is wrong; async executor not configured; or listener does not support async | Verify a bean named `applicationEventMulticaster` exists; check executor and listener type |
| `@EventListener` is not called | Listener is not a bean, payload type mismatches, configuration not scanned/imported | Check bean registration, method signature, and event payload |
| No exception seen at `publishEvent` | `ErrorHandler` is suppressing; or listener runs asynchronously | Check policy, executor logs, and error-reporting mechanism |
| One failing listener prevents subsequent listeners from running | Synchronous execution with exception propagated | Catch errors inside the listener where appropriate or configure `ErrorHandler` intentionally |
| `@Order` is present, yet completion logs are out of order | Executor runs tasks concurrently | Do not use order as a completion guarantee; make tasks and dependencies explicit |
| Async listener cannot access transaction or MDC as before | Thread context does not propagate automatically | Pass needed data via payload and configure appropriate context propagation |
| Application struggles to shut down because event tasks are still running | Executor lifecycle/shutdown not managed properly | Use a Spring-managed executor bean, configure and test shutdown |
| Thread pool saturated, event processing slow | Pool/queue too small or listeners hold threads too long | Measure task duration, queue depth, active threads, and tune load/rejection policy |
| Spring fails on startup | Duplicate bean name, wrong bean type, or dependency cycle | Check name `applicationEventMulticaster`, type `ApplicationEventMulticaster`, and dependencies |

**Do not manually add listeners directly to a self-created multicaster just to "connect" with `@EventListener`**. When a bean is selected by Spring as the internal multicaster, the framework manages discovering and registering appropriate listeners. If you want to change filtering or scheduling rules at a very deep level, you must understand the `ApplicationEventMulticaster` contract and how the context initializes it before writing a brand-new implementation.

## 11. Verifying the Configuration Properly

After adding the bean, a small verification suite is worth much more than merely inspecting configuration:

1. **Right bean**: look up `context.getBean(AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME)`; confirm the expected type/configuration.
2. **Synchronous**: print thread names and timestamps before/after `publishEvent`; synchronous listeners must finish within the call.
3. **ErrorHandler**: create a listener that intentionally throws an error in a test, and check whether subsequent listeners are called and whether the error propagates to the publisher.
4. **Async executor**: use `CountDownLatch` or `CompletableFuture` waiting with a timeout to be sure the task finished, rather than reading results right after `publishEvent` and drawing conclusions.
5. **Ordering**: verify dispatch order if needed; with async, verify correctness even when completion timing changes.
6. **Transactions**: include real transaction tests for `BEFORE_COMMIT`/`AFTER_COMMIT` phases when the feature uses transactions.
7. **Operations**: measure load levels, queue depth, active thread counts, listener errors, and shutdown behavior.

In production environments, balance returning fast responses to requests against the reliability of downstream work. Application events are an **in-context communication mechanism**; configuring a thread pool does not turn events into messages durable across restarts or replace a queuing system.

## 12. Self-Check Questions

**1.** Does declaring `@Bean("customMulticaster")` of type `SimpleApplicationEventMulticaster` automatically replace the internal multicaster?

**Answer:** No. `AbstractApplicationContext` looks up the bean by the name `applicationEventMulticaster`.

**2.** The multicaster bean has a `ThreadPoolTaskExecutor`. Can we conclude every listener runs on a worker thread?

**Answer:** No. Listeners declaring they do not support async, especially transaction-synchronized listeners, need to run on the publisher thread for the relevant processing step.

**3.** Listener A fails, but `ErrorHandler` only logs and does not rethrow. Is listener B invoked?

**Answer:** In the synchronous example with `SimpleApplicationEventMulticaster`, yes. However, A failed; a clear policy for handling the aftermath is needed rather than treating this as total success.

**4.** `@Order(-10)` is set on A and `@Order(10)` on B, while running the multicaster on a thread pool. Is B guaranteed to finish after A?

**Answer:** No. Order does not guarantee completion timing of asynchronous tasks.

**5.** What should be noted when wanting a listener to run after commit while preserving proper transaction semantics?

**Answer:** Use `@TransactionalEventListener(phase = AFTER_COMMIT)` and do not assume the multicaster's thread pool automatically carries the transaction context to another thread. If durable delivery is required, design a separate outbox/message broker.

## 13. References

- Spring Framework Reference — Standard and Custom Events: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Javadoc `AbstractApplicationContext` (bean name constant and initialization mechanism): https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
- Javadoc `SimpleApplicationEventMulticaster` (executor and error handler): https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Javadoc `ApplicationListener` (async execution support): https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/ApplicationListener.html
- Javadoc `ThreadPoolTaskExecutor`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework Reference — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework Reference — Observability and event context propagation: https://docs.spring.io/spring-framework/reference/integration/observability.html
