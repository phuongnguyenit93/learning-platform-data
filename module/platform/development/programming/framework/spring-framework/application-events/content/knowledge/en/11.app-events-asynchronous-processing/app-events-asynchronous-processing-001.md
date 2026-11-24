# @Async on Event Listeners in Spring Framework

## 1. Purpose and Role of @Async

In Spring Framework, a method annotated with `@EventListener` can receive events published by `ApplicationEventPublisher.publishEvent(...)`. By default, the listener is invoked synchronously on the event-publishing thread: if the listener performs time-consuming work, the `publishEvent` call may have to wait.

Adding `@Async` to the listener method allows Spring to **offload the method body to an executor**, so the event-publishing thread does not have to wait for all of that listener's work to complete:

~~~java
@EventListener
@Async("eventExecutor")
public void onOrderCreated(OrderCreated event) {
    // Runs on a thread provided by eventExecutor.
}
~~~

Common use cases: sending non-blocking notifications, handling auxiliary auditing, performing post-processing calculations, or executing independent work without increasing the response time of the event-publishing thread. Distinguish **asynchronous execution** from **durable processing**: `@Async` only changes where code runs within the same JVM; it does not persist events, retry after process termination, or guarantee exactly-once processing.

Related concepts:

| Component | Responsibility |
|---|---|
| `ApplicationEventPublisher` / `ApplicationContext` | Receives the application's event publication calls |
| `ApplicationEventMulticaster` | Resolves and triggers listeners that receive the event |
| `@EventListener` | Marks a method to handle a matching event type |
| `@Async` and Spring's proxy mechanism | Intercepts the method call and dispatches the body to an executor |
| `@EnableAsync` | Enables `@Async` annotation processing in the context |
| `Executor` / `TaskExecutor` | Manages task scheduling and execution threads |

**Important point:** simply adding `@Async` without an active async mechanism or calling the method through the wrong path can cause the code to still execute synchronously.

## 2. Execution Flow: From publishEvent to the Executor

With a standard `@EventListener`:

~~~text
Event-publishing thread             Listener
       |                               |
       | publishEvent(event)           |
       +------------------------------>|
       |            run handle(event)  |
       |<------------------------------+
       | continue after publishEvent   |
~~~

With `@EventListener` combined with `@Async` and an active async proxy:

~~~text
Event-publishing thread   Spring event adapter/proxy        eventExecutor
       |                            |                           |
       | publishEvent(event)        |                           |
       +--------------------------->|                           |
       |                filter event type, call listener proxy  |
       |                            +---- submit task --------->|
       |                            |                    run handle(event)
       |<---------------------------+                           |
       | continue work              |                           | finishes later
~~~

Detailed sequence:

1. Spring receives the event via `publishEvent` and uses the `ApplicationContext`'s event multicaster to select matching listeners.
2. The `@EventListener` processing infrastructure creates an adapter that invokes the listener method on the Spring-managed bean.
3. When the bean has the `@Async` mechanism applied, the call goes through a proxy; the interceptor offloads execution to the configured executor.
4. The listener body runs on a worker thread; the work result may arrive before or after the publisher's next step, depending on scheduling.
5. An executor rejecting a task or an error occurring during task submission is a different case from an exception thrown **inside** the listener method after it has started running asynchronously.

Do not infer log line ordering between publisher and listener solely from the call site of `publishEvent`. Spring does not guarantee that the task has started before `publishEvent` returns, nor does it guarantee that the task will wait until the publisher returns before starting.

## 3. Conditions for @Async to Actually Work

### Enable Annotations with @EnableAsync

In plain Spring Framework, the clearest approach is to add `@EnableAsync` to a configuration class registered in the context:

~~~java
@Configuration
@EnableAsync
public class AsyncConfig {
    // Beans for listeners and executors.
}
~~~

`@EnableAsync` activates the `@Async` processing infrastructure. In a Spring Boot application, the same annotation can be used; Boot auto-creating an executor does not mean every `@Async` method automatically runs asynchronously if the corresponding infrastructure has not been enabled.

### The Listener Must Be a Spring Bean

The `@EventListener` method must reside in a Spring-managed bean, such as a bean returned from `@Bean` or a `@Component` class within the component scan scope. A class instantiated manually with `new` outside the context does not become a registered listener and does not receive a Spring async proxy.

### The Call Must Go Through the Proxy

In the common proxy mode of `@EnableAsync`, Spring can only intercept calls that pass through the proxy:

~~~java
@Service
public class NotificationService {

    public void dispatch() {
        sendLater(); // Self-invocation within the same object: bypasses the async proxy.
    }

    @Async("eventExecutor")
    public void sendLater() {
        // Does not automatically run asynchronously when called via this.sendLater().
    }
}
~~~

The snippet above illustrates a **self-invocation bug**, not a standalone runnable application. The standard solution is to extract the async work into another bean and call that bean, or let Spring invoke the `@EventListener` method through the adapter and properly registered bean proxy. Do not expect `@Async` to take effect on `private` methods, methods that cannot be properly proxied, or objects created manually outside Spring.

### Choose an Explicit Executor

Declare `@Async("eventExecutor")` to select the exact executor bean, rather than relying on how Spring selects a default executor:

~~~java
@Bean(name = "eventExecutor")
public ThreadPoolTaskExecutor eventExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("events-");
    return executor;
}
~~~

When registered via `@Bean`, Spring manages initializing and shutting down the executor. If you create a `ThreadPoolTaskExecutor` manually outside the bean lifecycle, you must actively manage `initialize()` and shutdown.

## 4. Runnable Java 17 Example: Listener Running on a Worker Thread

This example uses **Spring Framework 6.2.8**, Maven, and Java 17, with no Spring Boot dependency. A record serves as the event payload; `@EventListener` receives that record; `@Async("eventExecutor")` processes it on a pool whose thread names start with `events-`.

Project structure:

~~~text
async-listener-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── AsyncEventsDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>async-listener-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/demo/AsyncEventsDemo.java`:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class AsyncEventsDemo {

    public static void main(String[] args) throws InterruptedException {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderListener listener = context.getBean(OrderListener.class);

            // Spring supports publishing payloads that do not extend ApplicationEvent.
            context.publishEvent(new OrderCreated("ORD-42"));

            // Wait with a timeout to demonstrate/test async deterministically.
            if (!listener.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Listener did not complete");
            }

            System.out.println("worker thread: "
                    + listener.workerThread().startsWith("events-"));
            System.out.println("order id: " + listener.lastOrderId());
        }
    }

    public record OrderCreated(String orderId) {
    }

    @Configuration
    @EnableAsync
    public static class AppConfig {

        @Bean(name = "eventExecutor")
        public ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(20);
            executor.setThreadNamePrefix("events-");
            return executor;
        }

        @Bean
        public OrderListener orderListener() {
            return new OrderListener();
        }
    }

    public static class OrderListener {

        private final CountDownLatch finished = new CountDownLatch(1);
        private volatile String lastOrderId;
        private volatile String workerThread;

        @EventListener
        @Async("eventExecutor")
        public void onOrderCreated(OrderCreated event) {
            try {
                lastOrderId = event.orderId();
                workerThread = Thread.currentThread().getName();
            } finally {
                finished.countDown();
            }
        }

        public boolean await(long timeout, TimeUnit unit)
                throws InterruptedException {
            return finished.await(timeout, unit);
        }

        public String lastOrderId() {
            return lastOrderId;
        }

        public String workerThread() {
            return workerThread;
        }
    }
}
~~~

Run from the `async-listener-demo` directory with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.AsyncEventsDemo
~~~

Two lines printed by the program, when the executor is initialized and the listener completes normally:

~~~text
worker thread: true
order id: ORD-42
~~~

**Why is the result deterministic?** The listener method stores the thread name starting with `events-` and the order ID, then calls `CountDownLatch.countDown()`. The main thread uses `await` before reading the two values. Thus, the verification order is controlled by a completion signal instead of relying on `Thread.sleep(...)` or machine speed. `@EventListener` can receive the `OrderCreated` record via the payload event mechanism, even though the record does not extend `ApplicationEvent`.

**What the example does not guarantee:** there is no guarantee that the listener finishes before `publishEvent` returns; that is precisely why main must wait. This is a deterministic demonstration pattern for a single event, not a durable event storage design or a load capacity test.

## 5. Choosing an Executor and Managing Resources

There are two common paths:

1. Use `@Async("eventExecutor")`: that listener is dispatched to the specified executor; other listeners can continue executing synchronously.
2. Use `@Async` without a name: Spring selects an executor according to the `AsyncConfigurer` configuration / suitable bean or fallback mechanism; the selection can change depending on application configuration.

For applications with multiple task groups, dedicated executor names help isolate load: `paymentNotificationExecutor`, `auditExecutor`, `reportExecutor`, etc. It is not necessary to create one pool per listener; grouping by resource type and priority level is usually easier to manage.

Essential parameters:

| Parameter | Impact |
|---|---|
| `corePoolSize` | Number of core threads |
| `maxPoolSize` | Thread limit when the pool needs to expand |
| `queueCapacity` | Number of tasks that can wait in the queue |
| `threadNamePrefix` | Helps identify workers in logs and thread dumps |
| Rejection policy | Behavior when the pool/queue runs out of capacity to accept work |
| Shutdown policy | How remaining queued/active tasks are handled when the application shuts down |

In `ThreadPoolExecutor`, when the queue is not yet full, the pool may keep placing tasks into the queue instead of immediately creating threads up to `maxPoolSize`; therefore, simply raising `maxPoolSize` while keeping the queue too large may not improve processing throughput. You should measure latency, queue length, number of rejected tasks, and processing time under real load.

If the executor rejects `submit`, an error can occur directly on the thread publishing the event. Therefore, the statement "exceptions from an async listener never reach the publisher" **is only true for errors inside the listener body once it is already running asynchronously**, not for every scheduling error.

## 6. Exceptions and AsyncUncaughtExceptionHandler

An `@EventListener @Async` method with a `void` return type is the common form. When the listener body throws an exception, the publisher has normally already left the direct call path; a `try/catch` wrapping `publishEvent` will not catch an error occurring later on the worker.

~~~java
try {
    publisher.publishEvent(new OrderCreated("ORD-42"));
} catch (RuntimeException ex) {
    // Does not catch errors thrown later inside the @Async listener body.
    // However, it can still encounter synchronous errors when submitting the task or from other listeners.
}
~~~

Spring provides `AsyncUncaughtExceptionHandler` to handle exceptions that cannot be returned from `void` async methods. It can be configured via `AsyncConfigurer`:

~~~java
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncErrorsConfig implements AsyncConfigurer {

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (error, method, params) -> {
            System.err.println("Async method failed: "
                    + method.getName() + " - " + error.getMessage());
        };
    }
}
~~~

This is a **separate configuration snippet** that needs to be registered in the context; do not paste the class directly into the demo file without reorganizing packages/imports. In production, use a logger and error observability system, and optionally add an appropriate retry/queue mechanism. The default handler may log the error, but does not guarantee that the task has been retried successfully.

Do not confuse `AsyncUncaughtExceptionHandler` for `@Async` calls with `ErrorHandler` on `SimpleApplicationEventMulticaster`. They catch errors at different layers:

- `AsyncUncaughtExceptionHandler` handles exceptions with no return channel from the body of a `void` async method.
- `SimpleApplicationEventMulticaster.setErrorHandler(...)` handles exceptions when the multicaster invokes a listener through the multicast path. When the listener call has already gone through the proxy and returned after enqueueing, errors occurring later in the worker may fall outside that scope.

For work that must succeed, a handler that only logs is not enough: you need state tracking, bounded retries, idempotency, and monitoring of failure cases.

## 7. Return Value Limitations and Publishing Follow-up Events

With a **synchronous** `@EventListener`, Spring allows a handler to return an object or collection to automatically publish follow-up events. This mechanism **is not supported for `@Async` asynchronous listeners**.

Do not write code expecting the following:

~~~java
// DO NOT use to automatically publish a follow-up event in an async listener.
@EventListener
@Async("eventExecutor")
public OrderProcessed onOrderCreated(OrderCreated event) {
    return new OrderProcessed(event.orderId());
}
~~~

If you want to publish another event after async work completes, explicitly inject `ApplicationEventPublisher` and call `publishEvent` at the appropriate time:

~~~java
public class AsyncOrderHandler {

    private final ApplicationEventPublisher publisher;

    public AsyncOrderHandler(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @EventListener
    @Async("eventExecutor")
    public void onOrderCreated(OrderCreated event) {
        // Complete a processing step.
        publisher.publishEvent(new OrderProcessed(event.orderId()));
    }
}
~~~

The snippet above is **illustrative code that needs integration**: `OrderCreated` and `OrderProcessed` are application event types; `AsyncOrderHandler` must be registered as a Spring bean. The new `publishEvent` is emitted from the worker thread, so listeners of `OrderProcessed` may run on that same worker if they are synchronous; be careful with event loops, errors, and dependencies between steps.

## 8. Does @Async Replace the ApplicationEventMulticaster Executor?

No. The two configuration approaches operate at different layers.

| Criterion | `@Async` on `@EventListener` | Executor on `SimpleApplicationEventMulticaster` |
|---|---|---|
| Scope | Selected per listener method | Affects listeners that allow async via the multicaster |
| Mechanism | Spring async method proxy/interceptor | Multicaster schedules `ApplicationListener` invocations |
| Enabled via | `@EnableAsync` and annotation | `applicationEventMulticaster` bean with `setTaskExecutor` |
| Error handling | Primarily via async method mechanism | Multicaster's `ErrorHandler`, executor |
| Remaining synchronous listeners | Not switched by `@Async` on another listener | May be dispatched asynchronously if the listener supports it |
| Relation to transactions | Must consider transaction phase and worker context | Transactional listeners may decline async |

Multicaster configuration example (illustrative configuration code, different from this article's `@Async` approach):

~~~java
@Bean(name = "applicationEventMulticaster")
public ApplicationEventMulticaster applicationEventMulticaster(
        ThreadPoolTaskExecutor eventExecutor) {
    SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();
    multicaster.setTaskExecutor(eventExecutor);
    return multicaster;
}
~~~

When using this example, you must import `ApplicationEventMulticaster` and `SimpleApplicationEventMulticaster`, register the executor bean in the same context, and evaluate the behavior of every related listener. Since Spring 6.1, `ApplicationListener.supportsAsyncExecution()` allows a listener to request running on the publishing thread, such as transaction-bound synchronous listeners; configuring an executor on the multicaster does not force every listener onto a worker.

For scenarios where **only a few listeners need to run asynchronously**, `@Async` on the specific listener and a named executor is usually the clearer choice.

## 9. @TransactionalEventListener, Transactions, and Thread Context

Asynchrony introduces an execution thread boundary. Things bound to the publishing thread usually do not automatically carry over to the worker, for example:

- Spring transaction synchronization and transaction-bound resources.
- Custom application `ThreadLocal`, request context, or security context if no context propagation mechanism is in place.
- Trace IDs and logging MDC, when propagation is not configured.
- A persistence context/session belonging to another thread's transaction.

In particular, `@EventListener @Async` does not mean "process only after the transaction has committed." The publisher may emit the event while the transaction is still active; the worker may start before commit, miss new data, or the publisher's transaction may later roll back.

If the business logic must wait for commit, consider `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`. You can design async work to occur **after the commit phase**, but keep in mind that worker processing runs in its own thread context and does not automatically inherit the publisher's transaction:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
@Async("eventExecutor")
public void afterOrderCommitted(OrderCreated event) {
    // Asynchronous work triggered after the AFTER_COMMIT callback.
    // If DB operations are needed, use an appropriate transaction on the worker thread.
}
~~~

This snippet requires `OrderCreated`, actual transaction management, and a configured executor. By default, `@TransactionalEventListener` does not run if there is no active transaction, unless `fallbackExecution = true` is configured. When handing off to a worker, pass only the necessary data (such as IDs and sufficient snapshots); avoid relying on lazy-loaded entities or transactional objects from the publishing thread. For operations requiring durable events across crashes/rollbacks, consider a transactional outbox and message broker.

## 10. @Order Does Not Guarantee Async Completion Order

Suppose two listeners receive the same event:

~~~java
@Order(1)
@EventListener
@Async("eventExecutor")
public void updateSearchIndex(OrderCreated event) {
    // May finish after the other listener.
}

@Order(2)
@EventListener
@Async("eventExecutor")
public void notifyDashboard(OrderCreated event) {
    // May finish before the @Order(1) listener.
}
~~~

`@Order` primarily relates to the order in which listeners are invoked during dispatch, **not the completion order of the async bodies**. If step B strictly depends on step A's result, do not use two independent async listeners with `@Order` to express that relationship. Instead, place them in the same ordered workflow, use explicit synchronization, or publish the next event once A has genuinely completed.

With multiple events of the same type, listeners may also run concurrently and complete out of order; locking/idempotency/partitioning by business key is needed if ordering is a strict requirement.

## 11. Testing Async Listeners Reliably

A test that only does:

~~~java
publisher.publishEvent(event);
verify(service).sendMessage();
~~~

can fail flakily if `verify` runs before the worker, or create false confidence if the test context accidentally omits `@EnableAsync` and the code runs synchronously.

You should verify meaningful signals:

1. The context has `@EnableAsync` enabled and contains the exact executor the listener uses.
2. The event is published using `ApplicationEventPublisher` or a real context, with the listener registered.
3. Output state is correct once **the listener has completed**; use `CountDownLatch` as in the demo, `CompletableFuture` at the service layer, or a condition-waiting library.
4. Test exceptions, retry policies, timeouts, and rejected tasks when those requirements matter.
5. If the application requires not running on the publisher thread, check thread name/ID or a measurable synchronization mechanism, rather than just adding `Thread.sleep` and guessing.

`CountDownLatch.await(timeout, unit)` gives tests a clear time bound. In real applications, other completion signals can be used; do not block an HTTP handling thread waiting on an async task only to turn the processing back into synchronous execution.

## 12. Real-World Scenarios and Design Decisions

**Scenario A — Sending notification email after order creation.** The service creates the order and publishes `OrderCreated`. An `@Async` listener calls the email service. If email is best-effort, latency is decoupled from the request. However, if sending fails, logging/tracking and a retry strategy are needed depending on requirements; `@Async` does not persist unsent emails automatically.

**Scenario B — Mandatory audit trail logging.** If auditing must succeed with the transaction, pushing the sole write into an `@Async` listener can break consistency. Define transaction boundaries and durable persistence mechanisms before choosing async execution.

**Scenario C — Cache refresh processing.** An async listener can refresh the cache without blocking the publisher. However, if the next request must read the updated state immediately, eventual consistency may not meet the requirement; the data consistency contract must be stated explicitly.

**Scenario D — High burst of incoming events.** The executor has bounded threads and a queue; when full, publishing may encounter submission errors or lose tasks if code swallows errors. Monitor backlog, choose a rejection policy, apply rate control, and design fault tolerance.

## 13. Common Errors and Diagnostics

| Symptom | Possible Cause | How to Check/Fix |
|---|---|---|
| Listener still runs on publisher thread | Missing `@EnableAsync`, bean not managed by Spring, self-invocation call | Check context config, proxy, thread name |
| Listener is not invoked | Bean not registered, `@EventListener` mismatched event type, wrong context | Check bean and payload type |
| `@Async("...")` reports missing executor | Wrong executor bean name or config not loaded | Verify the bean name being used |
| Publisher does not see listener errors | Exception occurred inside worker | Configure `AsyncUncaughtExceptionHandler`, logs/metrics |
| Listener cannot read newly saved DB data | Worker ran before commit or lacks a transaction | Use the right transaction phase and a separate transaction |
| Log lines lose trace/request ID | MDC/ThreadLocal does not cross threads automatically | Use `TaskDecorator` or appropriate propagation mechanism |
| Tasks process slowly, queue grows | Insufficient pool resources, blocking I/O work, oversized queue | Measure duration, throughput, queue, and load |
| Unfinished work on application shutdown | Context closed while tasks are still running | Define shutdown policy, await or provide durable mechanisms if needed |
| Two listeners finish out of order | `@Order` does not mean async completion order | Design an explicit dependency chain |
| Event processed multiple times | Publisher emits multiple times, duplicate listener, non-idempotent retry | Attach event ID and design safe idempotent handling |

When diagnosing, log `eventId`, event type, listener name, thread name, enqueue/start/finish timestamps, and processing outcome. Clearly separate **event published**, **task accepted**, **execution started**, and **completed successfully**; those are four distinct states.

## 14. Key Principles to Remember

- `@EventListener` selects the method receiving the matching event; `@Async` offloads that method's execution to an executor when the infrastructure/proxy is active.
- `@EnableAsync` must be enabled, the listener must be a Spring bean, and a named executor is preferred so configuration is verifiable.
- `publishEvent` returning does not prove the async listener has finished; use a completion signal or separate status tracking.
- Exceptions in a `void @Async` body do not propagate back to the publisher automatically; handle them via `AsyncUncaughtExceptionHandler` and monitoring, and note that enqueue errors are a separate case.
- Async listeners do not automatically publish new events via their `return` value; call `ApplicationEventPublisher.publishEvent` explicitly if needed.
- Transactions, ThreadLocal, MDC, and completion order are not automatically preserved across thread boundaries.
- `@Async` is useful for background processing within a single Spring process; requirements for durability, retries, delivery guarantees, and crash recovery need additional mechanisms.

### References

- [Spring Framework Reference — ApplicationContext events, asynchronous listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework Reference — Task execution and @Async](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Javadoc 6.2.8 — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Javadoc — @EventListener](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/EventListener.html)